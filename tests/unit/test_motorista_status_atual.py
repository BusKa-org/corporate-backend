from datetime import UTC, datetime, timedelta

from app.models.enum import StatusMotorista
from app.models.user import Motorista

AGORA = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)


def _motorista(status, descanso_ate=None):
    return Motorista(status_motorista=status, descanso_ate=descanso_ate)


def test_ativo_e_em_rota_nao_mudam():
    assert _motorista(StatusMotorista.ATIVO).status_atual(AGORA) == StatusMotorista.ATIVO
    assert _motorista(StatusMotorista.EM_ROTA).status_atual(AGORA) == StatusMotorista.EM_ROTA


def test_descanso_vale_ate_descanso_ate():
    m = _motorista(StatusMotorista.EM_DESCANSO, AGORA + timedelta(seconds=1))
    assert m.status_atual(AGORA) == StatusMotorista.EM_DESCANSO


def test_descanso_termina_exatamente_em_descanso_ate():
    m = _motorista(StatusMotorista.EM_DESCANSO, AGORA)
    assert m.status_atual(AGORA) == StatusMotorista.ATIVO


def test_descanso_sem_data_conta_como_ativo():
    m = _motorista(StatusMotorista.EM_DESCANSO)
    assert m.status_atual(AGORA) == StatusMotorista.ATIVO
