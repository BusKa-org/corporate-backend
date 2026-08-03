"""Send email via SMTP using app config."""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import current_app

logger = logging.getLogger(__name__)


def send_email(
    to: str,
    subject: str,
    body_plain: str,
    body_html: str | None = None,
) -> None:
    """Send an email using Flask app config."""
    mail_server = current_app.config.get("MAIL_SERVER")
    mail_port = current_app.config.get("MAIL_PORT", 587)
    mail_username = current_app.config.get("MAIL_USERNAME")
    mail_password = current_app.config.get("MAIL_PASSWORD")
    mail_use_tls = current_app.config.get("MAIL_USE_TLS", True)

    if not mail_server or not mail_username or not mail_password:
        logger.warning(
            "Mail not configured (MAIL_SERVER/MAIL_USERNAME/MAIL_PASSWORD). Skipping send."
        )
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = mail_username
    msg["To"] = to
    msg.attach(MIMEText(body_plain, "plain", "utf-8"))

    if body_html:
        msg.attach(MIMEText(body_html, "html", "utf-8"))

    logger.info("Sending email to %s", to)
    logger.info("Mail server: %s", mail_server)
    logger.info("Mail port: %s", mail_port)
    logger.info("Mail username: %s", mail_username)
    logger.info("Mail password: %s", mail_password)
    logger.info("Mail use TLS: %s", mail_use_tls)

    try:
        with smtplib.SMTP(mail_server, mail_port) as server:
            if mail_use_tls:
                server.starttls()
            server.login(mail_username, mail_password)
            server.sendmail(mail_username, to, msg.as_string())

        logger.info("Email sent to %s", to)

    except Exception:
        logger.exception("Failed to send email to %s", to)
        raise
