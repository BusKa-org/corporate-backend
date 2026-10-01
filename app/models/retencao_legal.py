"""Dados retidos após a exclusão de conta, por obrigação legal.

Guarda só o necessário para contato e localização em uma eventual apuração
(auditoria, processo). Nenhum endpoint lê esta tabela. Quando `reter_ate`
passa, uma tarefa diária troca e-mail e CPF por hashes irreversíveis e marca
`anonimizado_em`. A linha não é apagada.
"""

from sqlalchemy.dialects.postgresql import UUID

from .base import db


class RetencaoLegal(db.Model):
    __tablename__ = "retencao_legal"

    usuario_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("usuario.id", ondelete="CASCADE"), primary_key=True
    )
    email = db.Column(db.String(120), nullable=False)
    # 64 caracteres: depois da anonimização guarda um hash SHA-256 em hexadecimal.
    cpf = db.Column(db.String(64), nullable=False)
    excluido_em = db.Column(
        db.DateTime(timezone=True), server_default=db.func.now(), nullable=False
    )
    reter_ate = db.Column(db.DateTime(timezone=True), nullable=False)
    anonimizado_em = db.Column(db.DateTime(timezone=True))
