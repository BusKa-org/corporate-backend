"""Grupo de passageiros dentro de uma organização, com histórico de participação.

O grupo pode ter datas. Sem `data_fim`, vale até o gestor encerrar ou apagar.
Pode ter um pai (um nível só). Quem está num subgrupo conta como membro do pai.
Cada passagem de uma pessoa pelo grupo é uma linha em `grupo_membro`. Quem sai
ganha `data_fim`, e quem volta ganha uma linha nova.
"""

import uuid
from datetime import date

from sqlalchemy.dialects.postgresql import UUID

from .base import db


class Grupo(db.Model):
    __tablename__ = "grupo"
    __table_args__ = (
        db.UniqueConstraint("organizacao_id", "nome", name="uq_grupo_organizacao_nome"),
    )

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organizacao_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("organizacao.id", ondelete="CASCADE"), nullable=False
    )
    # Um nível só: o pai é um grupo raiz. O banco barra apagar pai que ainda tem filhos.
    grupo_pai_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("grupo.id", ondelete="RESTRICT", name="fk_grupo_grupo_pai"),
    )
    nome = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.String(255))
    data_inicio = db.Column(db.Date)
    data_fim = db.Column(db.Date)
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now(), nullable=False)

    @property
    def encerrado(self) -> bool:
        return self.data_fim is not None and self.data_fim < date.today()

    @property
    def ativo(self) -> bool:
        comecou = self.data_inicio is None or self.data_inicio <= date.today()
        return comecou and not self.encerrado


class GrupoMembro(db.Model):
    __tablename__ = "grupo_membro"
    __table_args__ = (
        # Só um vínculo aberto por pessoa e grupo.
        db.Index(
            "uq_grupo_membro_aberto",
            "grupo_id",
            "usuario_id",
            unique=True,
            postgresql_where=db.text("data_fim IS NULL"),
        ),
        db.Index("idx_grupo_membro_usuario", "usuario_id"),
    )

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    grupo_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("grupo.id", ondelete="CASCADE"), nullable=False
    )
    usuario_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("aluno.usuario_id", ondelete="CASCADE"), nullable=False
    )
    data_inicio = db.Column(db.Date, nullable=False, default=date.today)
    data_fim = db.Column(db.Date)


class RegraEmailGrupo(db.Model):
    """Domínio de e-mail que sugere um grupo no convite. A regra só sugere, nunca aplica."""

    __tablename__ = "regra_email_grupo"
    __table_args__ = (
        db.UniqueConstraint("grupo_id", "dominio", name="uq_regra_email_grupo_dominio"),
        db.Index("idx_regra_email_grupo_dominio", "dominio"),
    )

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    grupo_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("grupo.id", ondelete="CASCADE"), nullable=False
    )
    # Minúsculo e sem "@", por exemplo "nubank.com".
    dominio = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now(), nullable=False)


# Grupos em que a pessoa convidada entra ao concluir o cadastro.
convite_grupo = db.Table(
    "convite_grupo",
    db.Column(
        "convite_id",
        UUID(as_uuid=True),
        db.ForeignKey("convite.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    db.Column(
        "grupo_id",
        UUID(as_uuid=True),
        db.ForeignKey("grupo.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)
