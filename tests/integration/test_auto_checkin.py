from unittest.mock import MagicMock, patch

from app.tasks.viagem_tasks import realizar_auto_checkin


@patch("app.tasks.viagem_tasks.db")
@patch("app.tasks.viagem_tasks.AlunosConfirmados")
@patch("app.tasks.viagem_tasks.NotificacaoService")
@patch("app.tasks.viagem_tasks.scheduler")
def test_realizar_auto_checkin_sucesso(
    mock_scheduler, mock_notificacao, mock_alunos_conf, mock_db, app
):
    """Testa se o robô marca embarcou=True quando estão no mesmo lugar."""
    with app.app_context():
        mock_viagem = MagicMock()
        mock_viagem.motorista_lat = -23.550520
        mock_viagem.motorista_lon = -46.633308

        mock_aluno = MagicMock()
        mock_aluno.aluno_lat = -23.550520
        mock_aluno.aluno_lon = -46.633308
        mock_aluno.embarcou = False

        mock_db.session.get.return_value = mock_viagem
        mock_alunos_conf.query.filter_by.return_value.first.return_value = mock_aluno
        mock_scheduler.app = app

        realizar_auto_checkin(viagem_id="viagem-123", aluno_id="aluno-123", tentativa=1)

        assert mock_aluno.embarcou is True, "O aluno deveria ter sido marcado como embarcado!"
        mock_db.session.commit.assert_called()
        mock_notificacao._criar_notificacao_interna.assert_called_once()


@patch("app.tasks.viagem_tasks.db")
@patch("app.tasks.viagem_tasks.AlunosConfirmados")
@patch("app.tasks.viagem_tasks.scheduler")
def test_realizar_auto_checkin_longe_reagenda(mock_scheduler, mock_alunos_conf, mock_db, app):
    """Testa se o robô falha, consome uma tentativa e agenda a próxima."""
    with app.app_context():
        mock_viagem = MagicMock()
        mock_viagem.motorista_lat = -23.550520
        mock_viagem.motorista_lon = -46.633308

        mock_aluno = MagicMock()
        mock_aluno.aluno_lat = -23.990000
        mock_aluno.aluno_lon = -46.990000
        mock_aluno.embarcou = False
        mock_aluno.tentativas_auto_checkin = 0

        mock_db.session.get.return_value = mock_viagem
        mock_alunos_conf.query.filter_by.return_value.first.return_value = mock_aluno
        mock_scheduler.app = app

        realizar_auto_checkin(viagem_id="viagem-123", aluno_id="aluno-123", tentativa=1)

        assert mock_aluno.embarcou is False, "O aluno NÃO deveria embarcar!"
        assert mock_aluno.tentativas_auto_checkin == 1, "A tentativa deveria ter subido para 1!"
        mock_db.session.commit.assert_called()
        mock_scheduler.add_job.assert_called_once()
