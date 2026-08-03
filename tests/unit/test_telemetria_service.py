"""RF-22 — regras de negócio da telemetria da bateria."""

from datetime import UTC, datetime, timedelta

import pytest

from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.telemetria import TelemetriaVeiculo
from app.services import telemetria_service

TS = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)


def _amostra(minuto: int, **campos):
    return {"timestamp": TS + timedelta(minutes=minuto), "nivel_bateria": 80.0, **campos}


def test_ingerir_deduplica_dentro_do_proprio_lote(app, _db, motorista, onibus):
    """Um lote com o mesmo carimbo repetido grava uma linha só."""
    with app.app_context():
        resultado = telemetria_service.ingerir(
            str(motorista.user.id),
            onibus.id,
            [_amostra(0, nivel_bateria=80.0), _amostra(0, nivel_bateria=79.0)],
        )

        assert resultado == {"recebidas": 2, "armazenadas": 1, "duplicadas": 1}
        assert _db.session.query(TelemetriaVeiculo).count() == 1


def test_ingerir_veiculo_de_outra_organizacao_404(app, _db, motorista, other_organizacao):
    from tests.factories.onibus_factory import OnibusFactory

    with app.app_context():
        alheio = OnibusFactory(organizacao_id=other_organizacao.id)
        _db.session.add(alheio)
        _db.session.commit()

        with pytest.raises(NotFoundError):
            telemetria_service.ingerir(str(motorista.user.id), alheio.id, [_amostra(0)])


def test_ingerir_com_viagem_inexistente_404(app, _db, motorista, onibus):
    import uuid

    with app.app_context():
        with pytest.raises(NotFoundError):
            telemetria_service.ingerir(
                str(motorista.user.id), onibus.id, [_amostra(0, viagem_id=uuid.uuid4())]
            )


def test_ingerir_por_aluno_e_proibido(app, _db, aluno, onibus):
    with app.app_context():
        with pytest.raises(ForbiddenError):
            telemetria_service.ingerir(str(aluno.user.id), onibus.id, [_amostra(0)])


def test_serie_respeita_os_limites_inclusivos(app, _db, motorista, onibus, gestor):
    with app.app_context():
        telemetria_service.ingerir(
            str(motorista.user.id), onibus.id, [_amostra(i) for i in range(5)]
        )

        leituras = telemetria_service.serie(
            str(gestor.user.id),
            veiculo_id=onibus.id,
            inicio=TS + timedelta(minutes=1),
            fim=TS + timedelta(minutes=3),
        )

        assert [leitura.timestamp for leitura in leituras] == [
            TS + timedelta(minutes=i) for i in (1, 2, 3)
        ]


def test_ultimo_por_veiculo_ignora_leituras_antigas(app, _db, motorista, onibus, gestor):
    with app.app_context():
        telemetria_service.ingerir(
            str(motorista.user.id),
            onibus.id,
            [_amostra(0, nivel_bateria=90.0), _amostra(9, nivel_bateria=42.0)],
        )

        leituras = telemetria_service.ultimo_por_veiculo(str(gestor.user.id))

        assert len(leituras) == 1
        assert float(leituras[0].nivel_bateria) == 42.0


def test_consulta_por_nao_gestor_e_proibida(app, _db, motorista):
    with app.app_context():
        with pytest.raises(ForbiddenError):
            telemetria_service.ultimo_por_veiculo(str(motorista.user.id))
        with pytest.raises(ForbiddenError):
            telemetria_service.serie(str(motorista.user.id))
        with pytest.raises(ForbiddenError):
            telemetria_service.consumo_por_viagem(str(motorista.user.id))
