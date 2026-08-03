"""Testes de integração para as tarefas agendadas (cron jobs) no banco real."""

from datetime import date, time, timedelta
from unittest.mock import MagicMock, patch

from app.models.enum import SentidoViagem, StatusViagem, UserRole
from app.models.rota import HorarioRota, Rota
from app.models.user import Motorista
from app.models.viagem import Viagem
from app.tasks.notificacao_tasks import verificar_viagens_24h


def test_integracao_job_24h_banco_real(app, _db, prefeitura):
    """
    Verifica se a task roda sem erros no banco real e altera o status da viagem.
    """
    with app.app_context():
        motorista = Motorista(
            prefeitura_id=prefeitura.id,
            nome="Mot",
            email="m@m.com",
            senha_hash="1",
            cpf="1",
            cnh="1",
            role=UserRole.MOTORISTA,
        )
        _db.session.add(motorista)
        _db.session.flush()

        rota = Rota(prefeitura_id=prefeitura.id, nome="Rota Teste")
        _db.session.add(rota)
        _db.session.flush()

        horario = HorarioRota(rota_id=rota.id, horario_saida=time(6, 30), sentido=SentidoViagem.IDA)
        _db.session.add(horario)
        _db.session.flush()

        amanha = date.today() + timedelta(days=1)

        viagem = Viagem(
            data=amanha,
            motorista_id=motorista.id,
            horario_rota_id=horario.id,
            status=StatusViagem.AGENDADA,
            aviso_24h_enviado=False,
        )
        _db.session.add(viagem)
        _db.session.commit()

        with (
            patch("app.tasks.notificacao_tasks.RotaAluno.query") as mock_rota_query,
            patch("app.tasks.notificacao_tasks.db.session.get") as mock_get,
            patch("app.tasks.notificacao_tasks.NotificacaoService") as mock_notif,
        ):

            mock_insc = MagicMock()
            mock_insc.aluno_id = "fake-aluno"
            mock_rota_query.filter_by.return_value.all.return_value = [mock_insc]

            mock_aluno = MagicMock()
            mock_aluno.receber_notificacoes = True
            mock_get.return_value = mock_aluno

            verificar_viagens_24h(app)

        _db.session.refresh(viagem)
        assert viagem.aviso_24h_enviado is True, "A task falhou em atualizar a flag no banco"
        assert mock_notif.mock_calls, "O serviço de notificações não foi acionado"
