"""Testes de integração do serviço de credencial de embarque (RF-15)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.enum import StatusViagem
from app.services import credencial_embarque_service
from tests.factories.credencial_embarque_factory import CredencialEmbarqueFactory
from tests.factories.viagem_factory import ViagemFactory


def test_gerar_credencial_sucesso(_db, aluno, ponto, viagem_futura_agendada_com_motorista):
    credencial = credencial_embarque_service.gerar_credencial(
        viagem_id=viagem_futura_agendada_com_motorista.id,
        aluno_id=aluno.user.id,
        ponto_embarque_id=ponto.id,
    )

    assert credencial.token
    assert credencial.viagem_id == viagem_futura_agendada_com_motorista.id
    assert credencial.aluno_id == aluno.user.id
    assert credencial.ponto_embarque_id == ponto.id
    assert credencial.usado is False
    assert credencial.expires_at > datetime.now(UTC)


def test_gerar_credencial_duplicada_levanta_conflict(
    _db, aluno, ponto, viagem_futura_agendada_com_motorista
):
    credencial_embarque_service.gerar_credencial(
        viagem_id=viagem_futura_agendada_com_motorista.id,
        aluno_id=aluno.user.id,
        ponto_embarque_id=ponto.id,
    )

    with pytest.raises(ConflictError):
        credencial_embarque_service.gerar_credencial(
            viagem_id=viagem_futura_agendada_com_motorista.id,
            aluno_id=aluno.user.id,
            ponto_embarque_id=ponto.id,
        )


@pytest.mark.parametrize("status", [StatusViagem.CANCELADA, StatusViagem.FINALIZADA])
def test_gerar_credencial_viagem_nao_ativa_levanta_validation(_db, aluno, ponto, status):
    viagem = ViagemFactory(status=status)
    _db.session.add(viagem)
    _db.session.commit()

    with pytest.raises(ValidationError):
        credencial_embarque_service.gerar_credencial(
            viagem_id=viagem.id,
            aluno_id=aluno.user.id,
            ponto_embarque_id=ponto.id,
        )


def test_gerar_credencial_viagem_nao_encontrada(_db, aluno, ponto):
    with pytest.raises(NotFoundError):
        credencial_embarque_service.gerar_credencial(
            viagem_id="00000000-0000-0000-0000-000000000000",
            aluno_id=aluno.user.id,
            ponto_embarque_id=ponto.id,
        )


def test_validar_credencial_sucesso(_db, aluno, ponto, viagem_futura_agendada_com_motorista):
    credencial = credencial_embarque_service.gerar_credencial(
        viagem_id=viagem_futura_agendada_com_motorista.id,
        aluno_id=aluno.user.id,
        ponto_embarque_id=ponto.id,
    )

    encontrada = credencial_embarque_service.validar_credencial(credencial.token)

    assert encontrada.id == credencial.id


def test_validar_credencial_token_inexistente(_db):
    with pytest.raises(NotFoundError):
        credencial_embarque_service.validar_credencial("token-que-nao-existe")


def test_validar_credencial_ja_usada_levanta_validation(
    _db, aluno, ponto, viagem_futura_agendada_com_motorista
):
    credencial = CredencialEmbarqueFactory(
        viagem_id=viagem_futura_agendada_com_motorista.id,
        aluno_id=aluno.user.id,
        ponto_embarque_id=ponto.id,
        usado=True,
    )
    _db.session.add(credencial)
    _db.session.commit()

    with pytest.raises(ValidationError):
        credencial_embarque_service.validar_credencial(credencial.token)


def test_validar_credencial_expirada_levanta_validation(
    _db, aluno, ponto, viagem_futura_agendada_com_motorista
):
    credencial = CredencialEmbarqueFactory(
        viagem_id=viagem_futura_agendada_com_motorista.id,
        aluno_id=aluno.user.id,
        ponto_embarque_id=ponto.id,
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    _db.session.add(credencial)
    _db.session.commit()

    with pytest.raises(ValidationError):
        credencial_embarque_service.validar_credencial(credencial.token)


def test_validar_credencial_nao_altera_estado(
    _db, aluno, ponto, viagem_futura_agendada_com_motorista
):
    credencial = credencial_embarque_service.gerar_credencial(
        viagem_id=viagem_futura_agendada_com_motorista.id,
        aluno_id=aluno.user.id,
        ponto_embarque_id=ponto.id,
    )

    credencial_embarque_service.validar_credencial(credencial.token)
    credencial_embarque_service.validar_credencial(credencial.token)

    _db.session.refresh(credencial)
    assert credencial.usado is False
