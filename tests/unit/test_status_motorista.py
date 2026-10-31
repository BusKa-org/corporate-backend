from datetime import UTC, datetime, timedelta

from app.models.enum import StatusMotorista
from app.models.user import Motorista
from app.services.viagens_service import status_motorista

AGORA = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)


def test_sem_viagem_e_sem_descanso_esta_ativo():
    assert status_motorista(Motorista(), AGORA, em_viagem=False) == StatusMotorista.ATIVO


def test_viagem_em_andamento_esta_em_rota_mesmo_com_descanso():
    m = Motorista(descanso_ate=AGORA + timedelta(minutes=10))
    assert status_motorista(m, AGORA, em_viagem=True) == StatusMotorista.EM_ROTA


def test_descanso_vale_ate_descanso_ate():
    m = Motorista(descanso_ate=AGORA + timedelta(seconds=1))
    assert status_motorista(m, AGORA, em_viagem=False) == StatusMotorista.EM_DESCANSO_OBRIGATORIO


def test_descanso_termina_exatamente_em_descanso_ate():
    m = Motorista(descanso_ate=AGORA)
    assert status_motorista(m, AGORA, em_viagem=False) == StatusMotorista.ATIVO
