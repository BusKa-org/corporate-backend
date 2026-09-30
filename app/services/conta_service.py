"""Exclusão de conta do passageiro (Art. 18 da LGPD).

A linha de usuário é mantida e anonimizada para que o histórico de viagens
finalizadas continue ligado a um id sem dado pessoal. O que não tem valor
estatístico é apagado.
"""

import logging
from datetime import UTC, datetime, timedelta

from werkzeug.security import check_password_hash

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, UnauthorizedError
from app.core.transaction import transactional
from app.models.base import db
from app.models.consentimento import REVOGACAO, Consentimento
from app.models.enum import StatusViagem, UserRole, UserStatus
from app.models.geo import Endereco, Ponto
from app.models.notificacao import Notificacao
from app.models.password_reset import PasswordResetToken
from app.models.retencao_legal import RetencaoLegal
from app.models.rota import RotaAluno
from app.models.user import Aluno, User
from app.models.viagem import AlunosConfirmados, Viagem
from app.services.consentimento_service import VERSAO_TERMO_VIGENTE
from app.utils import audit_logger
from app.utils.email_sender import send_email

logger = logging.getLogger(__name__)

# ponytail: 10 anos, prazo geral de prescrição civil (art. 205 do Código Civil). Decisão da
# equipe, sem validação jurídica formal. Falta a limpeza automática de `reter_ate`.
ANOS_DE_RETENCAO = 10


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
    """Único lugar que conhece quais campos guardam dado pessoal."""
    user.nome = "Usuário removido"
    user.email = f"removido-{user.id}@removido.invalid"
    # ponytail: 40 bits do uuid, colisão vira ConflictError. Coluna cpf é única e obrigatória.
    user.cpf = f"del-{user.id.hex[:10]}"
    user.telefone = None
    user.fcm_token = None
    user.receber_notificacoes = False
    # Valor que nenhum hash válido produz, então o login nunca confere.
    user.senha_hash = "!"
    user.status = UserStatus.DELETED

    if isinstance(user, Aluno):
        user.matricula = None
        user.foto_url = None
        user.data_nascimento = None
        user.nome_responsavel = None
        user.cpf_responsavel = None
        user.email_responsavel = None
        user.guardian_token = None
        user.guardian_consented_at = None


def _apagar_ponto_casa(user: User) -> None:
    """Latitude, longitude e endereço da casa do aluno não têm valor estatístico."""
    if not isinstance(user, Aluno) or user.ponto_casa_id is None:
        return
    ponto_id = user.ponto_casa_id
    user.ponto_casa_id = None
    db.session.flush()
    Endereco.query.filter_by(ponto_id=ponto_id).delete()
    Ponto.query.filter_by(id=ponto_id).delete()


def _apagar_dados_sem_valor_estatistico(aluno_id) -> None:
    Notificacao.query.filter_by(usuario_id=aluno_id).delete()
    PasswordResetToken.query.filter_by(user_id=aluno_id).delete()
    RotaAluno.query.filter_by(aluno_id=aluno_id).delete()

    # Presença em viagem finalizada fica (estatística). O resto sai.
    viagens_finalizadas = db.session.query(Viagem.id).filter(
        Viagem.status == StatusViagem.FINALIZADA
    )
    AlunosConfirmados.query.filter(
        AlunosConfirmados.aluno_id == aluno_id,
        AlunosConfirmados.viagem_id.notin_(viagens_finalizadas),
    ).delete(synchronize_session=False)


def excluir_conta(user_id: str, email: str, senha: str) -> None:
    user = db.session.get(User, user_id)
    if user is None:
        raise NotFoundError("Usuário não encontrado")
    if user.role != UserRole.ALUNO:
        raise ForbiddenError("Somente passageiros podem excluir a própria conta")

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
        raise ConflictError(
            "Você está em uma viagem em andamento. Conclua ou cancele a participação "
            "antes de excluir a conta."
        )

    email_original = user.email
    aluno_id = user.id

    with transactional():
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

    # Só o id, nunca o e-mail (o e-mail original não pode virar novo vestígio no log).
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
