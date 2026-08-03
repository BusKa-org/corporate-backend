"""Testes unitários para as regras de negócio de notificações."""

from unittest.mock import MagicMock, patch

import pytest

from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.enum import UserRole
from app.services.notificacao_service import NotificacaoService


def test_notificar_por_gestor_sucesso(app):
    """Testa se o gestor consegue disparar notificações em massa."""
    with app.app_context():

        with (
            patch("app.services.notificacao_service.db.session.get") as mock_get,
            patch("app.services.notificacao_service.RotaAluno.query") as mock_rota_query,
            patch("app.services.notificacao_service.db.session.commit") as mock_commit,
            patch("app.services.notificacao_service.audit_logger") as mock_audit,
            patch.object(NotificacaoService, "_criar_notificacao_interna") as mock_criar,
        ):

            mock_gestor = MagicMock()
            mock_gestor.role = UserRole.GESTOR
            mock_get.return_value = mock_gestor

            mock_aluno_1 = MagicMock()
            mock_aluno_1.aluno_id = "aluno-1"
            mock_aluno_2 = MagicMock()
            mock_aluno_2.aluno_id = "aluno-2"
            mock_rota_query.filter_by.return_value.all.return_value = [mock_aluno_1, mock_aluno_2]

            dados = {"titulo": "Aviso", "mensagem": "Teste de mensagem", "rota_id": "rota_123"}

            resultado = NotificacaoService.notificar_por_gestor("user_gestor_id", dados)

            assert resultado["message"] == "Notificação enviada para 2 aluno(s) com sucesso."
            assert mock_criar.call_count == 2
            mock_commit.assert_called_once()
            mock_audit.log_user_action.assert_called_once()


def test_notificar_por_gestor_falha_nao_eh_gestor(app):
    """Testa se o serviço bloqueia envio de notificações por quem não é gestor."""
    with app.app_context():

        with patch("app.services.notificacao_service.db.session.get") as mock_get:

            mock_aluno = MagicMock()
            mock_aluno.role = UserRole.ALUNO
            mock_get.return_value = mock_aluno

            dados = {"titulo": "Aviso", "mensagem": "Teste", "rota_id": "123"}

            with pytest.raises(ForbiddenError) as excinfo:
                NotificacaoService.notificar_por_gestor("user_aluno_id", dados)

            assert "Apenas gestores" in str(excinfo.value)


def test_notificar_por_gestor_falha_sem_alunos(app):
    """Testa se o serviço falha caso tente notificar uma rota/viagem vazia."""
    with app.app_context():

        with (
            patch("app.services.notificacao_service.db.session.get") as mock_get,
            patch("app.services.notificacao_service.RotaAluno.query") as mock_rota_query,
        ):

            mock_gestor = MagicMock()
            mock_gestor.role = UserRole.GESTOR
            mock_get.return_value = mock_gestor

            mock_rota_query.filter_by.return_value.all.return_value = []
            dados = {"titulo": "Aviso", "mensagem": "Teste", "rota_id": "123"}

            with pytest.raises(NotFoundError) as excinfo:
                NotificacaoService.notificar_por_gestor("user_gestor_id", dados)

            assert "Nenhum aluno encontrado" in str(excinfo.value)
