from datetime import UTC, datetime, timedelta

from app.services.viagens_service import calcular_fim_descanso

AGORA = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
MAX_DIRECAO = timedelta(hours=4)
DESCANSO = timedelta(minutes=30)
H = timedelta(hours=1)
M = timedelta(minutes=1)


def test_sem_viagens_pode_dirigir():
    assert calcular_fim_descanso([], AGORA, MAX_DIRECAO, DESCANSO) is None


def test_quatro_horas_seguidas_exige_descanso():
    periodos = [(AGORA - 4 * H, AGORA)]
    assert calcular_fim_descanso(periodos, AGORA, MAX_DIRECAO, DESCANSO) == AGORA + DESCANSO


def test_viagem_em_andamento_conta_ate_agora():
    periodos = [(AGORA - 4 * H, None)]
    assert calcular_fim_descanso(periodos, AGORA, MAX_DIRECAO, DESCANSO) == AGORA + DESCANSO


def test_intervalo_curto_entre_viagens_soma_direcao():
    periodos = [(AGORA - 5 * H, AGORA - 3 * H), (AGORA - 3 * H + 10 * M, AGORA - 5 * M)]
    assert calcular_fim_descanso(periodos, AGORA, MAX_DIRECAO, DESCANSO) == AGORA + 25 * M


def test_intervalo_de_descanso_entre_viagens_zera_contador():
    periodos = [(AGORA - 5 * H, AGORA - 3 * H), (AGORA - 150 * M, AGORA - 5 * M)]
    assert calcular_fim_descanso(periodos, AGORA, MAX_DIRECAO, DESCANSO) is None


def test_ja_descansou_depois_da_ultima_viagem():
    periodos = [(AGORA - 6 * H, AGORA - 30 * M)]
    assert calcular_fim_descanso(periodos, AGORA, MAX_DIRECAO, DESCANSO) is None
