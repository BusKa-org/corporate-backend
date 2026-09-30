"""Convites de cadastro de passageiro: o gestor convida, a pessoa conclui."""

import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from flask import current_app
from werkzeug.security import generate_password_hash

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.transaction import transactional
from app.models.base import db
from app.models.convite import (
    CANCELADO,
    CONCLUIDO,
    ENVIADO,
    ENVIO_PENDENTE,
    FALHOU,
    PENDENTE,
    Convite,
)
from app.models.enum import UserRole, UserStatus
from app.models.geo import Instituicao
from app.models.user import Aluno, User
from app.services.user_service import _get_gestor_or_403
from app.utils import (
    audit_logger,
    validate_cpf,
    validate_email,
    validate_password,
    validate_phone,
    validate_uuid,
)
from app.utils.email_sender import send_email

logger = logging.getLogger(__name__)

VALIDADE_DIAS = 7
LIMITE_LOTE = 500
LIMITE_ENVIO_POR_EXECUCAO = 50
MAX_TENTATIVAS_ENVIO = 3
ESTADOS_DO_CONVITE = (PENDENTE, CONCLUIDO, CANCELADO)


def _agora() -> datetime:
    return datetime.now(UTC)


def _renovar(convite: Convite) -> None:
    """Token novo, validade nova e envio do e-mail de volta para a fila."""
    convite.token = secrets.token_urlsafe(32)
    convite.expira_em = _agora() + timedelta(days=VALIDADE_DIAS)
    convite.envio_estado = ENVIO_PENDENTE
    convite.envio_tentativas = 0
    convite.enviado_em = None


def _texto(dados: dict[str, Any], campo: str) -> str | None:
    """Texto sem espaços nas pontas, ou None se não veio ou veio vazio."""
    valor = dados.get(campo)
    if valor is None:
        return None
    if not isinstance(valor, str):
        raise ValidationError(f"O campo {campo} deve ser texto")
    valor = valor.strip()
    if valor == "":
        return None
    return valor


def _instituicao_da_organizacao(instituicao_id: str, organizacao_id) -> Instituicao:
    instituicao = db.session.get(Instituicao, validate_uuid(instituicao_id, "Instituição"))
    if instituicao is None or str(instituicao.organizacao_id) != str(organizacao_id):
        raise ValidationError("Instituição inválida")
    return instituicao


def _validar_nome(nome: str | None) -> str | None:
    if nome is not None and len(nome) > 100:
        raise ValidationError("Nome deve ter no máximo 100 caracteres")
    return nome


# ─── Gestor: convidar ──────────────────────────────────────────────────────────


def _validar_item(gestor, item: dict[str, Any]) -> dict[str, Any]:
    """Valida uma linha do lote. Levanta ValidationError se algo estiver errado."""
    email = validate_email(_texto(item, "email") or "")
    nome = _validar_nome(_texto(item, "nome"))

    cpf = _texto(item, "cpf")
    if cpf is not None:
        cpf = validate_cpf(cpf)

    telefone = _texto(item, "telefone")
    if telefone is not None:
        telefone = validate_phone(telefone)

    instituicao_id = None
    instituicao_texto = _texto(item, "instituicao_id")
    if instituicao_texto is not None:
        instituicao_id = _instituicao_da_organizacao(instituicao_texto, gestor.organizacao_id).id

    return {
        "email": email,
        "nome": nome,
        "cpf": cpf,
        "telefone": telefone,
        "instituicao_id": instituicao_id,
    }


def _processar_item(gestor, item: dict[str, Any]) -> dict[str, str]:
    email_informado = ""
    if isinstance(item.get("email"), str):
        email_informado = item["email"]

    try:
        dados = _validar_item(gestor, item)
    except ValidationError as erro:
        return {"email": email_informado, "resultado": "INVALIDO", "motivo": erro.message}

    email = dados["email"]

    if User.query.filter_by(email=email).first():
        return {"email": email, "resultado": "PULADO", "motivo": "E-mail já possui conta"}

    if dados["cpf"] and User.query.filter_by(cpf=dados["cpf"]).first():
        return {"email": email, "resultado": "INVALIDO", "motivo": "CPF já pertence a um usuário"}

    existente = Convite.query.filter_by(email=email, estado=PENDENTE).first()

    if existente and existente.expira_em > _agora():
        return {
            "email": email,
            "resultado": "PULADO",
            "motivo": "Já existe um convite pendente para este e-mail",
        }

    if existente:
        convite = existente
        resultado = "RENOVADO"
    else:
        convite = Convite(email=email, estado=PENDENTE)
        db.session.add(convite)
        resultado = "CRIADO"

    convite.organizacao_id = gestor.organizacao_id
    convite.criado_por_id = gestor.id
    convite.nome = dados["nome"]
    convite.cpf = dados["cpf"]
    convite.telefone = dados["telefone"]
    convite.instituicao_id = dados["instituicao_id"]
    _renovar(convite)

    return {"email": email, "resultado": resultado, "motivo": ""}


def criar_convites(gestor_id: str, itens: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Cria convites em lote. Uma linha com problema não impede as outras."""
    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem convidar")

    if len(itens) == 0:
        raise ValidationError("Envie ao menos um convite")
    if len(itens) > LIMITE_LOTE:
        raise ValidationError(f"O lote aceita no máximo {LIMITE_LOTE} convites")

    resultados: list[dict[str, str]] = []
    # ponytail: uma transação para o lote. Se dois gestores convidarem o mesmo e-mail no mesmo
    # instante, o índice único derruba o lote inteiro com conflito. Savepoint por linha se doer.
    with transactional():
        for item in itens:
            resultados.append(_processar_item(gestor, item))

    audit_logger.log_user_action(
        action="criar_convites",
        user_id=gestor_id,
        resource_type="convite",
        details={"linhas": len(itens)},
    )
    return resultados


# ─── Gestor: listar, reenviar, cancelar ────────────────────────────────────────


def listar_convites(gestor_id: str, estado: str | None = None) -> list[Convite]:
    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem listar convites")

    consulta = Convite.query.filter_by(organizacao_id=gestor.organizacao_id)
    if estado is not None:
        if estado not in ESTADOS_DO_CONVITE:
            raise ValidationError(f"Estado inválido. Use: {', '.join(ESTADOS_DO_CONVITE)}")
        consulta = consulta.filter_by(estado=estado)

    return consulta.order_by(Convite.created_at.desc()).all()


def _convite_da_organizacao(gestor, convite_id: str) -> Convite:
    convite = db.session.get(Convite, validate_uuid(convite_id, "Convite"))
    if convite is None or str(convite.organizacao_id) != str(gestor.organizacao_id):
        raise NotFoundError("Convite não encontrado")
    return convite


def reenviar_convite(gestor_id: str, convite_id: str) -> Convite:
    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem reenviar convites")
    convite = _convite_da_organizacao(gestor, convite_id)
    if convite.estado != PENDENTE:
        raise ConflictError("Só convites pendentes podem ser reenviados")

    with transactional():
        _renovar(convite)

    audit_logger.log_user_action(
        action="reenviar_convite",
        user_id=gestor_id,
        resource_type="convite",
        resource_id=str(convite.id),
    )
    return convite


def cancelar_convite(gestor_id: str, convite_id: str) -> None:
    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem cancelar convites")
    convite = _convite_da_organizacao(gestor, convite_id)
    if convite.estado != PENDENTE:
        raise ConflictError("Só convites pendentes podem ser cancelados")

    with transactional():
        convite.estado = CANCELADO

    audit_logger.log_user_action(
        action="cancelar_convite",
        user_id=gestor_id,
        resource_type="convite",
        resource_id=str(convite.id),
    )


# ─── Pessoa convidada: consultar e concluir pelo link ──────────────────────────


def _convite_valido_por_token(token: str) -> Convite:
    convite = Convite.query.filter_by(token=token, estado=PENDENTE).first()
    if convite is None or convite.expira_em <= _agora():
        raise NotFoundError("Convite inválido ou expirado")
    return convite


def consultar_por_token(token: str) -> dict[str, Any]:
    convite = _convite_valido_por_token(token)

    instituicao_id = str(convite.instituicao_id) if convite.instituicao_id else None
    dados = {
        "email": convite.email,
        "nome": convite.nome,
        "cpf": convite.cpf,
        "telefone": convite.telefone,
        "instituicao_id": instituicao_id,
    }

    faltando: list[str] = []
    for campo in ("nome", "cpf", "instituicao_id"):
        if not dados[campo]:
            faltando.append(campo)
    dados["campos_faltando"] = faltando

    return dados


def concluir_convite(token: str, dados: dict[str, Any]) -> Aluno:
    convite = _convite_valido_por_token(token)

    # O que a pessoa informa vale mais do que o que o gestor preencheu.
    nome = _validar_nome(_texto(dados, "nome") or convite.nome)
    cpf = _texto(dados, "cpf") or convite.cpf
    telefone = _texto(dados, "telefone") or convite.telefone
    instituicao_texto = _texto(dados, "instituicao_id")
    if instituicao_texto is None and convite.instituicao_id is not None:
        instituicao_texto = str(convite.instituicao_id)

    if not nome or not cpf or not instituicao_texto:
        faltando: list[str] = []
        if not nome:
            faltando.append("nome")
        if not cpf:
            faltando.append("cpf")
        if not instituicao_texto:
            faltando.append("instituicao_id")
        raise ValidationError("Campos obrigatórios faltando", details={"campos": faltando})

    cpf = validate_cpf(cpf)
    if telefone:
        telefone = validate_phone(telefone)
    instituicao = _instituicao_da_organizacao(instituicao_texto, convite.organizacao_id)
    senha = validate_password(dados.get("senha") or "")

    if User.query.filter_by(email=convite.email).first():
        raise ConflictError("Este e-mail já está cadastrado.", field="email")
    if User.query.filter_by(cpf=cpf).first():
        raise ConflictError("Este CPF já está cadastrado.", field="cpf")

    # Só conta como alteração quando o gestor tinha preenchido e a pessoa mudou.
    alterados: list[str] = []
    if convite.nome and nome != convite.nome:
        alterados.append("nome")
    if convite.cpf and cpf != convite.cpf:
        alterados.append("cpf")
    if convite.telefone and telefone != convite.telefone:
        alterados.append("telefone")
    if convite.instituicao_id and instituicao.id != convite.instituicao_id:
        alterados.append("instituicao_id")

    with transactional():
        aluno = Aluno(
            organizacao_id=convite.organizacao_id,
            nome=nome,
            email=convite.email,
            senha_hash=generate_password_hash(senha),
            cpf=cpf,
            telefone=telefone,
            role=UserRole.ALUNO,
            status=UserStatus.ACTIVE,
            signup_completed_at=_agora(),
            instituicao_id=instituicao.id,
        )
        db.session.add(aluno)
        db.session.flush()

        convite.estado = CONCLUIDO
        convite.concluido_em = _agora()
        convite.usuario_id = aluno.id
        # Os dados pessoais agora moram no usuário.
        convite.nome = None
        convite.cpf = None
        convite.telefone = None

    audit_logger.log_user_action(
        action="concluir_convite",
        user_id=str(aluno.id),
        resource_type="convite",
        resource_id=str(convite.id),
        details={"campos_alterados": alterados},
    )
    return aluno


# ─── Envio do e-mail (chamado pela tarefa do agendador) ────────────────────────


def _mail_configurado() -> bool:
    config = current_app.config
    return bool(
        config.get("MAIL_SERVER") and config.get("MAIL_USERNAME") and config.get("MAIL_PASSWORD")
    )


def _enviar_email_do_convite(convite: Convite) -> None:
    frontend_url = current_app.config.get("FRONTEND_URL", "http://localhost:8081")
    link = f"{frontend_url.rstrip('/')}/convite?token={convite.token}"
    link_do_app = current_app.config.get("APP_DOWNLOAD_URL") or ""

    texto = (
        "Olá!\n\n"
        "Você foi cadastrado(a) para usar o transporte. "
        f"Para terminar o cadastro, acesse o link abaixo (válido por {VALIDADE_DIAS} dias):\n"
        f"{link}\n\n"
    )
    html = (
        "<p>Olá!</p>"
        "<p>Você foi cadastrado(a) para usar o transporte.</p>"
        f'<p><a href="{link}">Terminar meu cadastro</a> (válido por {VALIDADE_DIAS} dias)</p>'
    )
    if link_do_app:
        texto += f"Baixe o app:\n{link_do_app}\n\n"
        html += f'<p><a href="{link_do_app}">Baixar o app</a></p>'
    texto += "Se você não esperava este convite, ignore este e-mail."
    html += "<p>Se você não esperava este convite, ignore este e-mail.</p>"

    send_email(
        to=convite.email,
        subject="Você foi cadastrado(a) para usar o transporte",
        body_plain=texto,
        body_html=html,
    )


def processar_envios() -> int:
    """Envia os e-mails de convite pendentes. Devolve quantos saíram."""
    if not _mail_configurado():
        # Sem isso o envio "funcionaria" sem mandar nada e o convite ficaria como ENVIADO.
        logger.warning("E-mail não configurado: convites continuam na fila de envio.")
        return 0

    pendentes = (
        Convite.query.filter(
            Convite.estado == PENDENTE,
            Convite.envio_estado == ENVIO_PENDENTE,
            Convite.expira_em > _agora(),
        )
        .order_by(Convite.created_at.asc())
        .limit(LIMITE_ENVIO_POR_EXECUCAO)
        .all()
    )

    enviados = 0
    for convite in pendentes:
        try:
            _enviar_email_do_convite(convite)
            convite.envio_estado = ENVIADO
            convite.enviado_em = _agora()
            enviados += 1
        except Exception:
            convite.envio_tentativas += 1
            if convite.envio_tentativas >= MAX_TENTATIVAS_ENVIO:
                convite.envio_estado = FALHOU
            logger.exception("Falha ao enviar o convite %s", convite.id)
        # Um commit por convite: se o processo cair, quem já saiu não é reenviado.
        db.session.commit()

    return enviados
