import uuid

from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from .base import db


class Consentimento(db.Model):
    """RF-09: aceite versionado do Termo e da Política de Privacidade.

    Uma linha por aceite, nunca sobrescrita: a prova de consentimento sob a
    LGPD é o histórico, não o estado atual. Quando o termo muda de versão o
    usuário volta a *sem consentimento* para a nova versão e um novo registro
    é criado no aceite seguinte.
    """

    __tablename__ = "consentimento"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    usuario_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("usuario.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    versao_termo = db.Column(db.String(20), nullable=False)
    aceito_em = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.now())
    revogado_em = db.Column(db.DateTime(timezone=True), nullable=True)

    # Contexto do aceite, exigido para comprovar consentimento inequívoco.
    ip_origem = db.Column(db.String(45), nullable=True)

    usuario = relationship("User")

    __table_args__ = (db.Index("idx_consentimento_usuario_versao", "usuario_id", "versao_termo"),)
