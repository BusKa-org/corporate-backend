"""Testes para o cálculo de quilometragem e finalização de viagens."""

from datetime import UTC, date, datetime, time, timedelta

from app.models.enum import SentidoViagem, StatusViagem, UserRole
from app.models.rota import HorarioRota, Rota
from app.models.user import Motorista
from app.models.viagem import TelemetriaViagem, Viagem
from app.services.viagens_service import controlar_viagem


def test_finalizar_viagem_calcula_km_real_pela_telemetria(app, _db, prefeitura):
    """
    Simula uma viagem com pontos de telemetria reais e verifica se a
    ação FINALIZAR calcula corretamente a distância total em km.
    """
    with app.app_context():
        motorista = Motorista(
            prefeitura_id=prefeitura.id,
            nome="Mot KM",
            email="mot.km@teste.com",
            senha_hash="123",
            cpf="88888888888",
            cnh="123",
            role=UserRole.MOTORISTA,
        )
        _db.session.add(motorista)
        _db.session.flush()

        rota = Rota(prefeitura_id=prefeitura.id, nome="Rota do Cálculo de KM")
        _db.session.add(rota)
        _db.session.flush()

        horario = HorarioRota(rota_id=rota.id, horario_saida=time(14, 0), sentido=SentidoViagem.IDA)
        _db.session.add(horario)
        _db.session.flush()

        viagem = Viagem(
            data=date.today(),
            motorista_id=motorista.id,
            horario_rota_id=horario.id,
            status=StatusViagem.EM_ANDAMENTO,
            inicio_real=datetime.now(UTC) - timedelta(minutes=30),
        )
        _db.session.add(viagem)
        _db.session.flush()

        agora = datetime.now(UTC)

        gps1 = TelemetriaViagem(
            viagem_id=viagem.id,
            latitude=-23.000,
            longitude=-46.000,
            timestamp=agora - timedelta(minutes=20),
        )
        gps2 = TelemetriaViagem(
            viagem_id=viagem.id,
            latitude=-23.010,
            longitude=-46.000,
            timestamp=agora - timedelta(minutes=10),
        )
        gps3 = TelemetriaViagem(
            viagem_id=viagem.id, latitude=-23.020, longitude=-46.000, timestamp=agora
        )

        _db.session.add_all([gps1, gps2, gps3])
        _db.session.commit()

        viagem_atualizada = controlar_viagem(
            viagem_id=str(viagem.id), user_id=str(motorista.id), data={"acao": "FINALIZAR"}
        )
        assert viagem_atualizada.status == StatusViagem.FINALIZADA
        assert viagem_atualizada.fim_real is not None

        assert viagem_atualizada.km_real is not None
        assert (
            2.15 <= viagem_atualizada.km_real <= 2.30
        ), f"O km_real calculado foi {viagem_atualizada.km_real}, esperado ~2.22"


def test_finalizar_viagem_sem_telemetria_retorna_zero(app, _db, prefeitura):
    """
    Garante que se a viagem for finalizada, mas o telemóvel do motorista
    não enviou nenhum ponto (ou enviou apenas 1), o sistema não quebra e o KM fica zero.
    """
    with app.app_context():
        # Setup simplificado
        motorista = Motorista(
            prefeitura_id=prefeitura.id,
            nome="Mot Sem GPS",
            email="mot.nogps@teste.com",
            senha_hash="1",
            cpf="999",
            cnh="1",
            role=UserRole.MOTORISTA,
        )
        rota = Rota(prefeitura_id=prefeitura.id, nome="Rota Sem GPS")
        _db.session.add_all([motorista, rota])
        _db.session.flush()

        horario = HorarioRota(rota_id=rota.id, horario_saida=time(15, 0), sentido=SentidoViagem.IDA)
        _db.session.add(horario)
        _db.session.flush()

        viagem = Viagem(
            data=date.today(),
            motorista_id=motorista.id,
            horario_rota_id=horario.id,
            status=StatusViagem.EM_ANDAMENTO,
            inicio_real=datetime.now(UTC),
        )
        _db.session.add(viagem)
        _db.session.commit()

        viagem_atualizada = controlar_viagem(
            viagem_id=str(viagem.id), user_id=str(motorista.id), data={"acao": "FINALIZAR"}
        )
        # Assert
        assert viagem_atualizada.status == StatusViagem.FINALIZADA
        assert viagem_atualizada.km_real == 0.0
