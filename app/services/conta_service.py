"""Passenger account deletion (LGPD Art. 18).

The user row is kept and anonymized so the history of finished trips stays
linked to an id without personal data. Whatever has no statistical value is deleted.
"""

import hashlib
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from werkzeug.security import check_password_hash

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, UnauthorizedError
from app.core.transaction import transactional
from app.models.base import db
from app.models.consentimento import REVOGACAO, Consentimento
from app.models.credencial_embarque import CredencialEmbarque
from app.models.enum import StatusSolicitacao, StatusViagem, UserRole, UserStatus
from app.models.geo import Endereco, Ponto
from app.models.notificacao import Notificacao
from app.models.password_reset import PasswordResetToken
from app.models.retencao_legal import RetencaoLegal
from app.models.rota import RotaAluno
from app.models.user import Aluno, User
from app.models.viagem import AlunosConfirmados, SolicitacaoViagem, Viagem
from app.services import solicitacoes_service, viagens_service
from app.services.aluno_service import apagar_foto
from app.services.consentimento_service import VERSAO_TERMO_VIGENTE
from app.utils import audit_logger
from app.utils.email_sender import send_email

logger = logging.getLogger(__name__)

# ponytail: 10 anos, prazo geral de prescrição civil (art. 205 do Código Civil). Decisão da
# equipe, sem validação jurídica formal. Passado o prazo, e-mail e CPF viram hashes.
ANOS_DE_RETENCAO = 10
LIMITE_ANONIMIZACAO_POR_EXECUCAO = 500
EM_VIAGEM = (
    "Você está em uma viagem em andamento. Conclua ou cancele a participação "
    "antes de excluir a conta."
)


def _tem_viagem_em_andamento(aluno_id) -> bool:
    registro = (
        db.session.query(AlunosConfirmados)
        .join(Viagem, Viagem.id == AlunosConfirmados.viagem_id)
        .filter(
            AlunosConfirmados.aluno_id == aluno_id,
            AlunosConfirmados.confirmacao.is_(True),
            Viagem.status == StatusViagem.EM_ANDAMENTO,
        )
        .first()
    )
    return registro is not None


def _anonimizar(user: User) -> None:
    """The only place that knows which fields hold personal data."""
    user.nome = "Usuário removido"
    user.email = f"removido-{user.id}@removido.invalid"
    # ponytail: 40 bits do uuid, colisão vira ConflictError. Coluna cpf é única e obrigatória.
    user.cpf = f"del-{user.id.hex[:10]}"
    user.telefone = None
    user.fcm_token = None
    user.receber_notificacoes = False
    # A value no valid hash produces, so the login never matches.
    user.senha_hash = "!"
    user.status = UserStatus.DELETED

    if isinstance(user, Aluno):
        user.matricula = None
        user.foto_url = None
        # Health data (LGPD art. 11), with no statistical value after deletion.
        user.necessidades_acessibilidade = []
        user.observacao_acessibilidade = None
        user.data_nascimento = None
        user.nome_responsavel = None
        user.cpf_responsavel = None


def _apagar_ponto_casa(user: User) -> None:
    """The student's home latitude, longitude and address have no statistical value."""
    if not isinstance(user, Aluno) or user.ponto_casa_id is None:
        return
    ponto_id = user.ponto_casa_id
    user.ponto_casa_id = None
    db.session.flush()
    Endereco.query.filter_by(ponto_id=ponto_id).delete()
    Ponto.query.filter_by(id=ponto_id).delete()


def _apagar_dados_sem_valor_estatistico(aluno_id) -> None:
    Notificacao.query.filter_by(usuario_id=aluno_id).delete()
    CredencialEmbarque.query.filter_by(aluno_id=aluno_id).delete()
    PasswordResetToken.query.filter_by(user_id=aluno_id).delete()
    RotaAluno.query.filter_by(aluno_id=aluno_id).delete()

    # Presence on a finished trip stays (statistics). The rest goes.
    viagens_finalizadas = db.session.query(Viagem.id).filter(
        Viagem.status == StatusViagem.FINALIZADA
    )
    AlunosConfirmados.query.filter(
        AlunosConfirmados.aluno_id == aluno_id,
        AlunosConfirmados.viagem_id.notin_(viagens_finalizadas),
    ).delete(synchronize_session=False)


def _solicitacoes_ativas(aluno_id) -> list[SolicitacaoViagem]:
    return (
        db.session.query(SolicitacaoViagem)
        .join(Viagem, Viagem.id == SolicitacaoViagem.viagem_id)
        .filter(
            SolicitacaoViagem.aluno_id == aluno_id,
            SolicitacaoViagem.status == StatusSolicitacao.ATIVA,
            Viagem.status.in_(viagens_service.ESTADOS_ATIVOS_SOB_DEMANDA),
        )
        .order_by(SolicitacaoViagem.viagem_id)
        .populate_existing()
        .all()
    )


def excluir_conta(user_id: str, email: str, senha: str) -> None:
    # Same lock order as the rest of the system: vehicle and trip before the student.
    viagens_travadas: dict[uuid.UUID, Viagem] = {}
    for solicitacao in _solicitacoes_ativas(user_id):
        viagem = solicitacoes_service.travar_viagem(solicitacao.viagem)
        viagens_travadas[viagem.id] = viagem

    # Lock the account: a second simultaneous request waits and already sees it anonymized.
    db.session.execute(select(User.id).where(User.id == user_id).with_for_update(key_share=True))
    user = db.session.get(User, user_id, populate_existing=True)
    if user is None:
        raise NotFoundError("Usuário não encontrado")
    if user.role != UserRole.ALUNO:
        raise ForbiddenError("Somente passageiros podem excluir a própria conta")
    assert isinstance(user, Aluno)

    email_confere = email.strip().lower() == user.email.lower()
    senha_confere = check_password_hash(user.senha_hash, senha)
    if not email_confere or not senha_confere:
        audit_logger.log_security_event(
            event_type="failed_account_deletion",
            severity="medium",
            user_id=str(user.id),
            details={"reason": "invalid_credentials"},
        )
        raise UnauthorizedError("Credenciais inválidas")

    if _tem_viagem_em_andamento(user.id):
        raise ConflictError(EM_VIAGEM)

    # With the account locked no new request appears; re-read the existing ones.
    solicitacoes = _solicitacoes_ativas(user.id)
    for solicitacao in solicitacoes:
        travada = viagens_travadas.get(solicitacao.viagem_id)
        if travada is None:
            # Joined a trip between the read and the lock: it cannot be locked now without
            # inverting the lock order.
            raise ConflictError("Sua solicitação de viagem mudou. Tente novamente.")
        if travada.status == StatusViagem.EM_ANDAMENTO:
            raise ConflictError(EM_VIAGEM)

    email_original = user.email
    aluno_id = user.id

    with transactional():
        # Same effect as DELETE /v1/viagens/<id>/solicitacao: gives the leg back and
        # cancels the trip left with no one.
        for solicitacao in solicitacoes:
            solicitacoes_service.cancelar_na_viagem_travada(
                user, viagens_travadas[solicitacao.viagem_id]
            )
        _apagar_ponto_casa(user)
        _apagar_dados_sem_valor_estatistico(aluno_id)
        db.session.add(
            RetencaoLegal(
                usuario_id=aluno_id,
                email=email_original,
                cpf=user.cpf,
                reter_ate=datetime.now(UTC) + timedelta(days=ANOS_DE_RETENCAO * 365),
            )
        )
        db.session.add(
            Consentimento(usuario_id=aluno_id, versao=VERSAO_TERMO_VIGENTE, acao=REVOGACAO)
        )
        _anonimizar(user)

    # After the commit: if the transaction fails, the photo is still valid.
    try:
        apagar_foto(str(aluno_id))
    except OSError:
        logger.exception("Falha ao apagar a foto do usuário %s", aluno_id)

    # Only the id, never the e-mail (the original e-mail must not leave a new trace in the log).
    audit_logger.log_user_action(
        action="delete_account", user_id=str(aluno_id), resource_type="user"
    )

    try:
        send_email(
            to=email_original,
            subject="Conta excluída",
            body_plain=(
                "Sua conta e seus dados pessoais foram excluídos. "
                "O histórico de viagens foi mantido apenas de forma anonimizada. "
                "Por obrigação legal, seu e-mail e seu CPF ficam guardados com acesso "
                f"restrito por {ANOS_DE_RETENCAO} anos, para eventual apuração de "
                "ocorrências, e depois são apagados."
            ),
        )
    except Exception:
        logger.exception("Falha ao enviar confirmação de exclusão para o usuário %s", aluno_id)


def _hash_irreversivel(valor: str) -> str:
    """SHA-256 hash with a random salt that is thrown away.

    A plain CPF hash could be brute-forced (there are only about 10^9 possible CPFs).
    With the salt discarded, no one can recover the value or check a guess.
    """
    sal = secrets.token_bytes(16)
    return hashlib.sha256(sal + valor.encode()).hexdigest()


def anonimizar_retencoes_vencidas() -> int:
    """Replace retained e-mail and CPF with hashes once the retention period is over.

    Returns how many rows were anonymized. Runs every 3 months and is safe to
    re-run on rows already anonymized.
    """
    agora = datetime.now(UTC)
    vencidas = (
        RetencaoLegal.query.filter(
            RetencaoLegal.reter_ate <= agora,
            RetencaoLegal.anonimizado_em.is_(None),
        )
        .limit(LIMITE_ANONIMIZACAO_POR_EXECUCAO)
        .all()
    )

    for retencao in vencidas:
        retencao.email = _hash_irreversivel(retencao.email)
        retencao.cpf = _hash_irreversivel(retencao.cpf)
        retencao.anonimizado_em = agora

    db.session.commit()
    return len(vencidas)
