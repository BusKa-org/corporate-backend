"""Testes de integração para o Dashboard do Gestor."""

from datetime import date, datetime, time, timedelta

import pytest

from app.core.exceptions import ForbiddenError
from app.models.enum import SentidoViagem, StatusViagem, UserRole
from app.models.geo import Ponto
from app.models.rota import HorarioRota, Rota
from app.models.user import Aluno, Gestor, Motorista
from app.models.viagem import AlunosConfirmados, TelemetriaViagem, Viagem, ViagemPonto
from app.services.dashboard_service import (
    obter_progresso_viagem,
    obter_telemetria_viagem,
    relatorio_periodo_gestor,
)


def test_dashboard_relatorio_e_progresso_viagem(app, _db, prefeitura):
    """
    Simula uma viagem completa com embarques e faltas para validar
    os cálculos matemáticos e a ordenação de progresso do dashboard.
    """
    with app.app_context():
        hoje = date.today()

        gestor = Gestor(
            prefeitura_id=prefeitura.id,
            nome="Gestor Teste",
            email="gestor.dash@teste.com",
            senha_hash="123",
            cpf="11111111111",
            role=UserRole.GESTOR,
        )
        motorista = Motorista(
            prefeitura_id=prefeitura.id,
            nome="Mot Teste",
            email="mot.dash@teste.com",
            senha_hash="123",
            cpf="22222222222",
            cnh="123",
            role=UserRole.MOTORISTA,
        )
        _db.session.add_all([gestor, motorista])
        _db.session.flush()

        rota = Rota(prefeitura_id=prefeitura.id, nome="Rota do Dashboard")
        _db.session.add(rota)
        _db.session.flush()

        horario = HorarioRota(rota_id=rota.id, horario_saida=time(7, 0), sentido=SentidoViagem.IDA)
        _db.session.add(horario)
        _db.session.flush()

        viagem = Viagem(
            data=hoje,
            motorista_id=motorista.id,
            horario_rota_id=horario.id,
            status=StatusViagem.FINALIZADA,
            km_real=15.5,
        )
        _db.session.add(viagem)
        _db.session.flush()

        ponto_a = Ponto(
            prefeitura_id=prefeitura.id, latitude=-23.1, longitude=-46.1, apelido="Ponto A"
        )
        ponto_b = Ponto(
            prefeitura_id=prefeitura.id, latitude=-23.2, longitude=-46.2, apelido="Ponto B"
        )
        _db.session.add_all([ponto_a, ponto_b])
        _db.session.flush()

        vp1 = ViagemPonto(
            viagem_id=viagem.id,
            ponto_id=ponto_a.id,
            ordem=1,
            chegada_real=datetime.now() - timedelta(minutes=30),
        )
        vp2 = ViagemPonto(
            viagem_id=viagem.id,
            ponto_id=ponto_b.id,
            ordem=2,
            chegada_real=datetime.now() - timedelta(minutes=10),
        )
        _db.session.add_all([vp1, vp2])

        aluno1 = Aluno(
            prefeitura_id=prefeitura.id,
            nome="A1",
            email="a1@t.com",
            senha_hash="1",
            cpf="33",
            role=UserRole.ALUNO,
        )
        aluno2 = Aluno(
            prefeitura_id=prefeitura.id,
            nome="A2",
            email="a2@t.com",
            senha_hash="1",
            cpf="44",
            role=UserRole.ALUNO,
        )
        aluno_falta = Aluno(
            prefeitura_id=prefeitura.id,
            nome="A3",
            email="a3@t.com",
            senha_hash="1",
            cpf="55",
            role=UserRole.ALUNO,
        )
        _db.session.add_all([aluno1, aluno2, aluno_falta])
        _db.session.flush()

        conf1 = AlunosConfirmados(
            viagem_id=viagem.id, aluno_id=aluno1.id, confirmacao=True, embarcou=True
        )
        conf2 = AlunosConfirmados(
            viagem_id=viagem.id, aluno_id=aluno2.id, confirmacao=True, embarcou=True
        )
        conf_falta = AlunosConfirmados(
            viagem_id=viagem.id, aluno_id=aluno_falta.id, confirmacao=True, embarcou=False
        )  # No-Show!

        _db.session.add_all([conf1, conf2, conf_falta])
        _db.session.commit()

        progresso = obter_progresso_viagem(gestor_id=str(gestor.id), viagem_id=str(viagem.id))

        assert len(progresso) == 2, "Deveria retornar os 2 pontos visitados"
        assert progresso[0]["apelido"] == "Ponto A", "A ordenação cronológica falhou"
        assert progresso[1]["apelido"] == "Ponto B"

        data_str = hoje.strftime("%Y-%m-%d")
        relatorio = relatorio_periodo_gestor(
            gestor_id=str(gestor.id), data_inicio=data_str, data_fim=data_str
        )

        assert relatorio["viagens_realizadas"] == 1
        assert relatorio["km_total_rodado"] == 15.5
        assert relatorio["alunos_transportados"] == 2
        assert relatorio["vagas_desperdicadas"] == 1

        assert relatorio["media_alunos_por_km"] == round(2 / 15.5, 2)


def test_dashboard_protecao_seguranca_gestor(app, _db, prefeitura):
    """Garante que apenas Gestores podem acessar os dados do dashboard."""
    with app.app_context():
        motorista = Motorista(
            prefeitura_id=prefeitura.id,
            nome="Mot Intrometido",
            email="intrometido@teste.com",
            senha_hash="123",
            cpf="999",
            cnh="123",
            role=UserRole.MOTORISTA,
        )
        _db.session.add(motorista)
        _db.session.commit()

        hoje = date.today().strftime("%Y-%m-%d")

        with pytest.raises(ForbiddenError) as exc_info:
            relatorio_periodo_gestor(gestor_id=str(motorista.id), data_inicio=hoje, data_fim=hoje)

        assert "Apenas gestores" in str(exc_info.value)


def test_dashboard_trajeto_real_telemetria(app, _db, prefeitura):
    """
    Simula o envio de coordenadas GPS pelo motorista e valida se o gestor
    recebe o trajeto ordenado cronologicamente para plotar no mapa.
    """
    with app.app_context():
        gestor = Gestor(
            prefeitura_id=prefeitura.id,
            nome="Gestor Mapa",
            email="gestor.mapa@teste.com",
            senha_hash="123",
            cpf="66666666666",
            role=UserRole.GESTOR,
        )
        motorista = Motorista(
            prefeitura_id=prefeitura.id,
            nome="Mot Mapa",
            email="mot.mapa@teste.com",
            senha_hash="123",
            cpf="77777777777",
            cnh="123",
            role=UserRole.MOTORISTA,
        )
        _db.session.add_all([gestor, motorista])
        _db.session.flush()

        rota = Rota(prefeitura_id=prefeitura.id, nome="Rota do Mapa")
        _db.session.add(rota)
        _db.session.flush()

        horario = HorarioRota(rota_id=rota.id, horario_saida=time(12, 0), sentido=SentidoViagem.IDA)
        _db.session.add(horario)
        _db.session.flush()

        viagem = Viagem(
            data=date.today(),
            motorista_id=motorista.id,
            horario_rota_id=horario.id,
            status=StatusViagem.EM_ANDAMENTO,
        )
        _db.session.add(viagem)
        _db.session.flush()

        agora = datetime.now()

        gps_inicio = TelemetriaViagem(
            viagem_id=viagem.id,
            latitude=-23.001,
            longitude=-46.001,
            timestamp=agora - timedelta(minutes=20),
        )

        gps_meio = TelemetriaViagem(
            viagem_id=viagem.id,
            latitude=-23.002,
            longitude=-46.002,
            timestamp=agora - timedelta(minutes=10),
        )

        gps_fim = TelemetriaViagem(
            viagem_id=viagem.id, latitude=-23.003, longitude=-46.003, timestamp=agora
        )

        _db.session.add_all([gps_fim, gps_inicio, gps_meio])
        _db.session.commit()

        trajeto = obter_telemetria_viagem(gestor_id=str(gestor.id), viagem_id=str(viagem.id))

        assert len(trajeto) == 3, "Deveria retornar os 3 pontos de GPS"

        assert trajeto[0]["latitude"] == -23.001, "A ordenação cronológica do GPS falhou"
        assert trajeto[1]["latitude"] == -23.002
        assert trajeto[2]["latitude"] == -23.003

        assert trajeto[0]["timestamp"] is not None
