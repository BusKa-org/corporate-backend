"""Student (Aluno) service - registration, profile management."""

import logging
import secrets
from typing import Any, cast

from flask import current_app
from werkzeug.security import generate_password_hash

from app.core.exceptions import (
    AppError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.models.base import db
from app.models.enum import UserRole, UserStatus
from app.models.geo import Endereco, Instituicao, Ponto
from app.models.user import Aluno, User
from app.services.user_service import _get_gestor_or_403
from app.utils import audit_logger, validate_cpf, validate_email, validate_password
from app.utils.email_sender import send_email

logger = logging.getLogger(__name__)


# ─── Guardian email ────────────────────────────────────────────────────────────


def _send_guardian_consent_email(aluno: Aluno) -> None:
    """Send a consent request email to the aluno's guardian."""
    frontend_url = current_app.config.get("FRONTEND_URL", "http://localhost:8081")
    link = f"{frontend_url.rstrip('/')}/guardian-consent?token={aluno.guardian_token}"

    subject = "Autorização necessária — BusKa"
    body_plain = (
        f"Olá!\n\n"
        f"O(A) estudante {aluno.nome} solicitou cadastro no BusKa, "
        f"aplicativo de transporte escolar.\n\n"
        f"Como responsável legal, você precisa autorizar o uso do app antes que o cadastro "
        f"seja enviado para análise do gestor municipal.\n\n"
        f"Clique no link abaixo para confirmar ou recusar:\n{link}\n\n"
        f"Este link é válido por 7 dias.\n\n"
        f"Atenciosamente,\nEquipe BusKa"
    )
    body_html = f"""
    <div style="font-family:sans-serif;max-width:560px;margin:auto;padding:24px">
      <h2 style="color:#0347D0">Autorização de Cadastro — BusKa</h2>
      <p>Olá!</p>
      <p>O(A) estudante <strong>{aluno.nome}</strong> solicitou cadastro no BusKa,
         aplicativo de transporte escolar municipal.</p>
      <p>Como responsável legal, sua autorização é necessária para que o cadastro
         seja encaminhado ao gestor municipal.</p>
      <a href="{link}"
         style="display:inline-block;margin:16px 0;padding:14px 28px;
                background:#0347D0;color:#fff;border-radius:8px;
                text-decoration:none;font-weight:600">
        Clique aqui para responder
      </a>
      <p style="color:#666;font-size:13px">
        Se o botão não funcionar, copie e cole este link no seu navegador:<br>
        <a href="{link}">{link}</a>
      </p>
      <p style="color:#666;font-size:13px">Este link expira em 7 dias.</p>
    </div>
    """
    try:
        send_email(
            to=aluno.email_responsavel,
            subject=subject,
            body_plain=body_plain,
            body_html=body_html,
        )
    except Exception:
        logger.exception("Failed to send guardian consent email for aluno %s", aluno.id)


# ─── Guardian consent ──────────────────────────────────────────────────────────


def get_guardian_consent_info(token: str) -> Aluno:
    """Return public aluno info for the guardian consent screen (no auth)."""
    aluno = db.session.query(Aluno).filter_by(guardian_token=token).first()
    if not aluno:
        raise NotFoundError("Link de consentimento inválido ou já utilizado")
    return aluno


def record_guardian_consent(token: str) -> Aluno:
    """
    Record guardian consent and advance the aluno to PENDING_APPROVAL.

    Raises: NotFoundError, ValidationError, AppError
    """
    from datetime import UTC, datetime, timedelta

    aluno = db.session.query(Aluno).filter_by(guardian_token=token).first()
    if not aluno:
        raise NotFoundError("Link de consentimento inválido ou já utilizado")

    if aluno.guardian_consented_at:
        raise ValidationError("Consentimento já registrado anteriormente")

    # Token expires 7 days after signup
    if aluno.created_at:
        expires_at = aluno.created_at + timedelta(days=7)
        if datetime.now(UTC) > expires_at:
            raise ValidationError("Este link expirou. Peça ao estudante que refaça o cadastro.")

    try:
        from app.services.notificacao_service import NotificacaoService

        aluno.guardian_consented_at = db.func.now()
        aluno.guardian_token = None  # single-use
        aluno.status = UserStatus.PENDING_APPROVAL
        db.session.flush()

        # Notify the gestor(s) of the prefeitura
        from app.models.user import Gestor

        gestores = db.session.query(Gestor).filter_by(prefeitura_id=aluno.prefeitura_id).all()
        for gestor in gestores:
            NotificacaoService._criar_notificacao_interna(
                usuario_id=str(gestor.id),
                titulo="Novo cadastro aguardando aprovação",
                mensagem=(
                    f"O responsável do aluno {aluno.nome} autorizou o cadastro. "
                    "Acesse a tela Equipe para aprovar."
                ),
            )

        db.session.commit()
        return aluno

    except AppError:
        db.session.rollback()
        raise
    except Exception as e:
        db.session.rollback()
        logger.error("Error recording guardian consent: %s", e, exc_info=True)
        raise AppError("Erro ao registrar consentimento", 500)


# ─── Signup ────────────────────────────────────────────────────────────────────


def auto_cadastro(data: dict[str, Any]) -> Aluno:
    """
    Aluno se cadastra sozinho.
    - If minor (age < 18), requires email_responsavel; sends guardian consent email.
    - A prefeitura é inferida através da Instituição escolhida.

    Returns: Aluno object
    Raises: NotFoundError, ValidationError, AppError
    """
    inst_id = data.get("instituicao_id")
    instituicao = db.session.get(Instituicao, inst_id)
    if not instituicao:
        raise NotFoundError("Instituição não encontrada")

    prefeitura_id = instituicao.prefeitura_id
    if not prefeitura_id:
        raise NotFoundError("Prefeitura não encontrada")

    email = validate_email(data.get("email", ""))
    cpf_clean = validate_cpf(data.get("cpf", ""))

    if db.session.query(User).filter(User.email == email).first():
        raise ConflictError("Este e-mail já está cadastrado.", field="email")
    if db.session.query(User).filter(User.cpf == cpf_clean).first():
        raise ConflictError("Este CPF já está cadastrado.", field="cpf")

    try:
        end_data = data.get("endereco_casa")
        if not end_data:
            raise ValidationError(
                "Endereço de casa é obrigatório", details={"field": "endereco_casa"}
            )

        password = validate_password(data.get("password", ""))

        ponto_casa = Ponto(
            prefeitura_id=prefeitura_id,
            latitude=end_data.get("latitude"),
            longitude=end_data.get("longitude"),
            apelido=f"Casa: {data.get('nome')}",
        )
        db.session.add(ponto_casa)
        db.session.flush()

        novo_end = Endereco(
            logradouro=end_data.get("logradouro"),
            numero=end_data.get("numero"),
            bairro=end_data.get("bairro"),
            cidade=end_data.get("cidade"),
            cep=end_data.get("cep"),
            ponto_id=ponto_casa.id,
        )
        db.session.add(novo_end)

        novo_aluno = Aluno(
            prefeitura_id=prefeitura_id,
            nome=data.get("nome"),
            email=data.get("email"),
            senha_hash=generate_password_hash(password),
            cpf=data.get("cpf"),
            telefone=data.get("telefone"),
            role=UserRole.ALUNO,
            status=UserStatus.PENDING_SIGNUP,
            matricula=data.get("matricula"),
            instituicao_id=instituicao.id,
            ponto_casa_id=ponto_casa.id,
            nome_responsavel=data.get("nome_responsavel"),
            cpf_responsavel=data.get("cpf_responsavel"),
            data_nascimento=data.get("data_nascimento"),
        )

        db.session.add(novo_aluno)
        db.session.flush()  # get novo_aluno.id before checking is_minor

        if novo_aluno.is_minor:
            email_resp = data.get("email_responsavel")
            if not email_resp:
                raise ValidationError(
                    "E-mail do responsável é obrigatório para menores de 18 anos",
                    details={"field": "email_responsavel"},
                )
            novo_aluno.email_responsavel = email_resp.strip().lower()
            novo_aluno.guardian_token = secrets.token_urlsafe(32)
            # Status stays PENDING_SIGNUP until guardian consents

        db.session.commit()

        if novo_aluno.is_minor:
            _send_guardian_consent_email(novo_aluno)

        return novo_aluno

    except AppError:
        db.session.rollback()
        raise
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating student: {e}")
        raise AppError(f"Erro ao criar aluno: {str(e)}", 500)


def update_me(user_id: str, data: dict[str, Any]) -> Aluno:
    """
    Atualiza perfil do aluno.

    Returns: Aluno object
    Raises: NotFoundError, AppError
    """
    aluno = db.session.get(Aluno, user_id)
    if not aluno:
        raise NotFoundError("Aluno não encontrado")

    try:
        for field in (
            "nome",
            "telefone",
            "matricula",
            "nome_responsavel",
            "cpf_responsavel",
        ):
            if field in data:
                setattr(aluno, field, data[field])

        if "endereco_casa" in data:
            end_data = data["endereco_casa"]

            if aluno.ponto_casa:
                ponto_casa = cast(Ponto, aluno.ponto_casa)
                ponto_casa.latitude = end_data.get("latitude")
                ponto_casa.longitude = end_data.get("longitude")
                if "nome" in data:
                    ponto_casa.apelido = f"Casa: {data['nome']}"

                endereco_bd = Endereco.query.filter_by(ponto_id=aluno.ponto_casa_id).first()

                if endereco_bd:
                    endereco_bd.logradouro = end_data.get("logradouro")
                    endereco_bd.numero = end_data.get("numero")
                    endereco_bd.bairro = end_data.get("bairro")
                    endereco_bd.cidade = end_data.get("cidade")
                    endereco_bd.cep = end_data.get("cep")
                else:
                    novo_end = Endereco(
                        ponto_id=aluno.ponto_casa_id,
                        logradouro=end_data.get("logradouro"),
                        numero=end_data.get("numero"),
                        bairro=end_data.get("bairro"),
                        cidade=end_data.get("cidade"),
                        cep=end_data.get("cep"),
                    )
                    db.session.add(novo_end)
            else:
                novo_ponto = Ponto(
                    prefeitura_id=aluno.prefeitura_id,
                    latitude=end_data.get("latitude"),
                    longitude=end_data.get("longitude"),
                    apelido=f"Casa: {data.get('nome', aluno.nome)}",
                )
                db.session.add(novo_ponto)
                db.session.flush()

                novo_end = Endereco(
                    ponto_id=novo_ponto.id,
                    logradouro=end_data.get("logradouro"),
                    numero=end_data.get("numero"),
                    bairro=end_data.get("bairro"),
                    cidade=end_data.get("cidade"),
                    cep=end_data.get("cep"),
                )
                db.session.add(novo_end)

                aluno.ponto_casa_id = novo_ponto.id

        if aluno.status == UserStatus.PENDING_SIGNUP and not aluno.is_minor:
            missing = []
            if not aluno.matricula and not data.get("matricula"):
                missing.append("matricula")
            if not aluno.instituicao_id and not data.get("instituicao_id"):
                missing.append("instituicao_id")
            end_data = data.get("endereco_casa")
            if (
                not end_data
                or end_data.get("latitude") is None
                or end_data.get("longitude") is None
            ):
                missing.append("endereco_casa.latitude/longitude")

            if missing:
                raise ValidationError(
                    "Cadastro precisa ser finalizado antes de usar o app",
                    details={"missing": missing},
                )

            aluno.status = UserStatus.ACTIVE
            aluno.signup_completed_at = db.func.now()
            audit_logger.log_user_action(
                action="complete_signup",
                user_id=user_id,
                resource_type="aluno",
                resource_id=user_id,
            )

        db.session.commit()
        return aluno

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating student profile: {e}")
        raise AppError(f"Erro ao atualizar perfil: {str(e)}", 500)


def delete_me(user_id: str) -> None:
    """
    Aluno se auto-exclui.

    Raises: NotFoundError, AppError
    """
    aluno = db.session.get(Aluno, user_id)
    if not aluno:
        raise NotFoundError("Aluno não encontrado")

    try:
        if aluno.ponto_casa:
            db.session.delete(aluno.ponto_casa)

        db.session.delete(aluno)
        db.session.commit()

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting student account: {e}")
        raise AppError(f"Erro ao excluir conta: {str(e)}", 500)


def get_aluno_by_id(gestor_id: str, aluno_id: str) -> Aluno:
    """
    Gestor retrieves full details for a single aluno.

    Raises: ForbiddenError, NotFoundError
    """
    from app.core.exceptions import ForbiddenError

    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem consultar alunos")
    aluno = db.session.get(Aluno, aluno_id)

    if not aluno:
        raise NotFoundError("Aluno não encontrado")
    if str(aluno.prefeitura_id) != str(gestor.prefeitura_id):
        raise ForbiddenError("Aluno não pertence à sua prefeitura")

    return aluno


def list_alunos_gestor(gestor_id: str, status: str | None = None) -> list[Aluno]:
    """
    Lista alunos da prefeitura (apenas para gestores).
    Optionally filter by status (e.g. 'PENDING_APPROVAL').

    Returns: List of Aluno objects
    Raises: ForbiddenError
    """
    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem listar alunos")
    q = db.session.query(Aluno).filter_by(prefeitura_id=gestor.prefeitura_id)
    if status:
        try:
            q = q.filter(Aluno.status == UserStatus[status])
        except KeyError:
            pass
    return q.all()


def aprovar_aluno(gestor_id: str, aluno_id: str) -> Aluno:
    """
    Gestor aprova um aluno com PENDING_APPROVAL, ativando sua conta.

    Returns: Aluno object
    Raises: ForbiddenError, NotFoundError, ValidationError
    """
    from app.core.exceptions import ForbiddenError
    from app.services.notificacao_service import NotificacaoService

    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem aprovar alunos")
    aluno = db.session.get(Aluno, aluno_id)

    if not aluno:
        raise NotFoundError("Aluno não encontrado")
    if str(aluno.prefeitura_id) != str(gestor.prefeitura_id):
        raise ForbiddenError("Aluno não pertence à sua prefeitura")
    if aluno.status != UserStatus.PENDING_APPROVAL:
        raise ValidationError("Aluno não está aguardando aprovação")

    try:
        aluno.status = UserStatus.ACTIVE
        aluno.signup_completed_at = db.func.now()
        db.session.flush()

        NotificacaoService._criar_notificacao_interna(
            usuario_id=str(aluno.id),
            titulo="Cadastro Aprovado!",
            mensagem=(
                "Seu cadastro foi aprovado pelo gestor. "
                "Você já pode confirmar presença nas viagens."
            ),
        )

        db.session.commit()
        audit_logger.log_user_action(
            action="aprovar_aluno",
            user_id=gestor_id,
            resource_type="aluno",
            resource_id=aluno_id,
        )
        return aluno

    except AppError:
        db.session.rollback()
        raise
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error approving student: {e}")
        raise AppError(f"Erro ao aprovar aluno: {str(e)}", 500)
