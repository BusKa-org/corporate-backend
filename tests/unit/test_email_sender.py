import logging
from unittest.mock import patch

from flask import Flask

from app.utils.email_sender import send_email


def test_senha_smtp_nao_vai_para_o_log(caplog):
    app = Flask(__name__)
    app.config.update(
        MAIL_SERVER="smtp.exemplo.test",
        MAIL_PORT=587,
        MAIL_USERNAME="envio@exemplo.test",
        MAIL_PASSWORD="senha-secreta-do-smtp",
        MAIL_USE_TLS=True,
    )

    with app.app_context(), patch("app.utils.email_sender.smtplib.SMTP"):
        with caplog.at_level(logging.DEBUG):
            send_email(to="aluno@exemplo.test", subject="Teste", body_plain="Oi")

    assert "senha-secreta-do-smtp" not in caplog.text
