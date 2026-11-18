"""Removing a vehicle or driver while a request holds the route that references it.

The request locks the route, then the vehicle/driver. The removal must take the
route first too, or the two wait on each other and Postgres aborts one.
"""

import threading
import time

import pytest
from sqlalchemy import select, text

from app.models.base import db
from app.models.onibus import Onibus
from app.models.rota import Rota
from app.services import onibus_service, rotas_service, user_service

pytestmark = [pytest.mark.integration, pytest.mark.concurrency]


def _esperar_alguem_bloqueado() -> None:
    """Wait until the removal is blocked on a row lock (the route, with or without the fix)."""
    with db.engine.connect() as conexao:
        for _ in range(100):
            bloqueados = conexao.execute(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname = current_database() AND wait_event_type = 'Lock'"
                )
            ).scalar()
            if bloqueados:
                return
            time.sleep(0.05)
    raise AssertionError("a remoção nunca esperou pelo lock da rota")


def _corrida(app, rota_id, travar_referenciado, remover) -> list:
    """Thread 0 locks the route, then (after the removal started) the referenced row."""
    rota_travada = threading.Event()
    remocao_comecou = threading.Event()
    resultados: list = [None, None]

    def requisicao() -> None:
        with app.app_context():
            try:
                rotas_service.travar_rota(rota_id)
                rota_travada.set()
                remocao_comecou.wait(timeout=10)
                _esperar_alguem_bloqueado()
                travar_referenciado()
                db.session.commit()
                resultados[0] = "ok"
            except Exception as e:  # noqa: BLE001 — the test inspects the error
                db.session.rollback()
                resultados[0] = e

    def remocao() -> None:
        with app.app_context():
            try:
                rota_travada.wait(timeout=10)
                remocao_comecou.set()
                remover()
                resultados[1] = "ok"
            except Exception as e:  # noqa: BLE001 — the test inspects the error
                resultados[1] = e

    threads = [threading.Thread(target=requisicao), threading.Thread(target=remocao)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
        assert not thread.is_alive(), "deadlock: uma thread não terminou"
    return resultados


def test_remover_veiculo_enquanto_a_rota_esta_travada(app, _db, gestor, rota, onibus):
    onibus_id = onibus.id

    def travar_onibus() -> None:
        db.session.execute(
            select(Onibus.id).where(Onibus.id == onibus_id).with_for_update(key_share=True)
        )

    resultados = _corrida(
        app,
        rota.id,
        travar_onibus,
        lambda: onibus_service.delete_onibus(str(gestor.user.id), str(onibus_id)),
    )

    assert resultados == ["ok", "ok"]
    _db.session.expire_all()
    assert _db.session.get(Rota, rota.id).veiculo_padrao_id is None


def test_remover_motorista_enquanto_a_rota_esta_travada(app, _db, gestor, rota, motorista):
    motorista_id = motorista.user.id

    def travar_motorista() -> None:
        # What the FK check of a new trip for this driver takes (gerar_viagem).
        db.session.execute(
            text("SELECT 1 FROM motorista WHERE usuario_id = :id FOR KEY SHARE"),
            {"id": motorista_id},
        )

    resultados = _corrida(
        app,
        rota.id,
        travar_motorista,
        lambda: user_service.delete_motorista(str(gestor.user.id), str(motorista_id)),
    )

    assert resultados == ["ok", "ok"]
    _db.session.expire_all()
    assert _db.session.get(Rota, rota.id).motorista_padrao_id is None
