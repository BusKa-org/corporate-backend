"""Peças puras do serviço de embarque (RF-15 a RF-18)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.core.exceptions import AppError
from app.models.enum import StatusViagem
from app.services import embarque_service


@pytest.mark.unit
def test_carimbo_sem_fuso_e_lido_como_utc():
    ingenuo = datetime(2026, 8, 3, 12, 0, 0)
    assert embarque_service._aware(ingenuo).tzinfo is UTC


@pytest.mark.unit
def test_carimbo_ausente_vira_agora():
    antes = datetime.now(UTC) - timedelta(seconds=1)
    assert embarque_service._aware(None) > antes


@pytest.mark.unit
def test_carimbo_com_fuso_e_preservado():
    momento = datetime(2026, 8, 3, 12, 0, 0, tzinfo=UTC)
    assert embarque_service._aware(momento) == momento


@pytest.mark.unit
def test_recusa_carrega_codigo_proprio_no_contrato_de_erro():
    erro = embarque_service.EmbarqueRecusado("nada feito", "CREDENCIAL_DE_OUTRO_PONTO")

    assert isinstance(erro, AppError)
    assert (erro.code, erro.status_code) == ("CREDENCIAL_DE_OUTRO_PONTO", 409)


@pytest.mark.unit
def test_sincronizacao_aceita_a_viagem_ja_encerrada():
    """A fila offline chega depois do fim do percurso — RF-18."""
    assert StatusViagem.FINALIZADA in embarque_service.SINCRONIZAVEL
    assert StatusViagem.FINALIZADA not in embarque_service.EM_PERCURSO


@pytest.mark.unit
def test_tipos_de_evento_cobrem_a_fila_do_app():
    assert set(embarque_service.TIPOS_EVENTO) == {
        "EMBARQUE",
        "EMBARQUE_MANUAL",
        "CHEGADA_PONTO",
        "POSICAO",
    }
