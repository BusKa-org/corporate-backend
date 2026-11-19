"""Gestor switches a route on and off (closest requirement: RF-04, with RF-05's refusal)."""

from datetime import date

import pytest
from sqlalchemy import delete, update
from sqlalchemy.orm.attributes import set_committed_value

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.enum import StatusViagem
from app.models.rota import Rota
from app.models.viagem import Viagem
from app.services import rotas_service, solicitacoes_service
from tests.factories.viagem_factory import ViagemFactory

# relogio pins "today" to Monday 2026-11-02 (local time).
SEGUNDA_FUTURA = date(2026, 11, 9)


def _ligar(ator, rota, ligada):
    return ator.client.put(f"/v1/rotas/{rota.id}", json={"ligada": ligada})


def test_gestor_desliga_e_religa_a_rota(_db, gestor, rota):
    r = _ligar(gestor, rota, False)
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["ligada"] is False

    # Still listed for the gestor, so it can be switched back on.
    ids = []
    for item in gestor.client.get("/v1/rotas/").get_json()["items"]:
        ids.append(item["id"])
    assert str(rota.id) in ids

    r = _ligar(gestor, rota, True)
    assert r.status_code == 200
    _db.session.expire_all()
    assert _db.session.get(Rota, rota.id).ligada is True


def test_apenas_gestor_da_organizacao_liga_e_desliga(_db, motorista, other_gestor, rota):
    assert _ligar(motorista, rota, False).status_code == 403
    assert _ligar(other_gestor, rota, False).status_code == 403
    _db.session.expire_all()
    assert _db.session.get(Rota, rota.id).ligada is True


def test_rota_com_viagem_pendente_nao_desliga(_db, gestor, horario_rota, relogio):
    viagem = ViagemFactory(
        horario_rota_id=horario_rota.id,
        rota_id=horario_rota.rota_id,
        status=StatusViagem.AGENDADA,
        data=SEGUNDA_FUTURA,
    )
    _db.session.add(viagem)
    _db.session.commit()
    rota = _db.session.get(Rota, horario_rota.rota_id)

    assert _ligar(gestor, rota, False).status_code == 409
    _db.session.expire_all()
    assert _db.session.get(Rota, rota.id).ligada is True


def test_rota_desligada_nao_gera_viagem(_db, gestor, horario_rota):
    rota = _db.session.get(Rota, horario_rota.rota_id)
    assert _ligar(gestor, rota, False).status_code == 200

    r = gestor.client.post(
        "/v1/viagens/", json={"rota_id": str(rota.id), "data": str(SEGUNDA_FUTURA)}
    )
    assert r.status_code == 400
    assert "Rota desligada" in r.get_data(as_text=True)


def test_rota_desligada_nao_aceita_solicitacao(gestor, aluno, rota_sob_demanda, janela, relogio):
    assert _ligar(gestor, rota_sob_demanda, False).status_code == 200

    r = aluno.client.post(f"/v1/rotas/{rota_sob_demanda.id}/solicitacoes")
    assert r.status_code == 400
    assert "Rota desligada" in r.get_data(as_text=True)


def test_solicitacao_rele_a_rota_sob_o_lock(_db, aluno, rota_sob_demanda, janela, relogio):
    # Another transaction switched the route off after this one loaded it: the stale
    # ligada=True in the session must not let the request open a round.
    _db.session.execute(
        update(Rota).where(Rota.id == rota_sob_demanda.id).values(ligada=False),
        execution_options={"synchronize_session": False},
    )
    assert rota_sob_demanda.ligada is True

    with pytest.raises(ValidationError, match="Rota desligada"):
        solicitacoes_service.solicitar_viagem(str(aluno.user.id), str(rota_sob_demanda.id))


def test_desligar_rele_a_rota_sob_o_lock(_db, gestor, horario_rota, relogio):
    # This gestor loaded the route while it was off; another one switched it on and a
    # trip opened. The stale ligada=False must not skip the pending-trip check.
    viagem = ViagemFactory(
        horario_rota_id=horario_rota.id,
        rota_id=horario_rota.rota_id,
        status=StatusViagem.AGENDADA,
        data=SEGUNDA_FUTURA,
    )
    _db.session.add(viagem)
    _db.session.commit()
    rota = _db.session.get(Rota, horario_rota.rota_id)
    set_committed_value(rota, "ligada", False)

    with pytest.raises(ConflictError):
        rotas_service.update_rota(str(gestor.user.id), str(rota.id), {"ligada": False})
    _db.session.rollback()
    assert _db.session.get(Rota, rota.id).ligada is True


def test_desligar_com_sessao_desatualizada_grava_no_banco(_db, gestor, rota):
    # Stale ligada=False with no pending trip: the switch-off must still reach the row.
    set_committed_value(rota, "ligada", False)

    rotas_service.update_rota(str(gestor.user.id), str(rota.id), {"ligada": False})
    _db.session.expire_all()
    assert _db.session.get(Rota, rota.id).ligada is False


def test_solicitacao_em_rota_removida_sob_o_lock(_db, aluno, rota_sob_demanda, janela, relogio):
    _db.session.execute(
        update(Rota).where(Rota.id == rota_sob_demanda.id).values(ativa=False),
        execution_options={"synchronize_session": False},
    )

    with pytest.raises(NotFoundError):
        solicitacoes_service.solicitar_viagem(str(aluno.user.id), str(rota_sob_demanda.id))


def test_ligar_com_sessao_desatualizada_grava_no_banco(_db, gestor, rota):
    # Another gestor switched it off after this session loaded ligada=True.
    _db.session.execute(
        update(Rota).where(Rota.id == rota.id).values(ligada=False),
        execution_options={"synchronize_session": False},
    )

    rotas_service.update_rota(str(gestor.user.id), str(rota.id), {"ligada": True})
    _db.session.expire_all()
    assert _db.session.get(Rota, rota.id).ligada is True


def test_desligar_rota_removida_sob_o_lock(_db, gestor, rota):
    _db.session.execute(
        update(Rota).where(Rota.id == rota.id).values(ativa=False),
        execution_options={"synchronize_session": False},
    )

    with pytest.raises(NotFoundError):
        rotas_service.update_rota(str(gestor.user.id), str(rota.id), {"ligada": False})


def test_rota_apagada_sob_o_lock_da_404(_db, rota):
    # A route without trips is hard-deleted while we wait: 404, not a refresh error (500).
    _db.session.execute(
        delete(Rota).where(Rota.id == rota.id),
        execution_options={"synchronize_session": False},
    )

    with pytest.raises(NotFoundError):
        rotas_service.travar_e_reler_rota(rota)


def test_viagem_antiga_de_rota_desligada_nao_inicia(_db, gestor, motorista, horario_rota, relogio):
    # A past AGENDADA trip is not pending, so the switch-off goes through.
    viagem = ViagemFactory(
        horario_rota_id=horario_rota.id,
        rota_id=horario_rota.rota_id,
        motorista_id=motorista.user.id,
        status=StatusViagem.AGENDADA,
        data=date(2026, 10, 26),
    )
    _db.session.add(viagem)
    _db.session.commit()
    rota = _db.session.get(Rota, horario_rota.rota_id)
    assert _ligar(gestor, rota, False).status_code == 200

    r = motorista.client.put(f"/v1/viagens/{viagem.id}/acao", json={"acao": "INICIAR"})
    assert r.status_code == 400
    assert "Rota desligada" in r.get_data(as_text=True)
    _db.session.expire_all()
    assert _db.session.get(Viagem, viagem.id).status == StatusViagem.AGENDADA
