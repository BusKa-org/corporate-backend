"""Aluno — BusKá-only user subtype (student), not part of the shared core.

PaqTcPB's passenger has no guardian, no minor-consent flow, and no school
link. This class existed inside `user.py` until the split documented in
ARQUITETURA_REPOSITORIOS.md §2/§4: `User`, `Motorista` and `Gestor` are core
roles every client needs, `Aluno` is BusKá-specific.

Still inherits from `User` via joined-table inheritance, unchanged — this is
a file move, not the polymorphic-inheritance redesign tracked as a separate,
higher-cost step (see the migration plan in ARQUITETURA_REPOSITORIOS.md §6).
"""

from datetime import date

from sqlalchemy.dialects.postgresql import UUID

from .base import db
from .enum import UserRole
from .user import User


class Aluno(User):
    __tablename__ = "aluno"

    usuario_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("usuario.id", ondelete="CASCADE"), primary_key=True
    )
    matricula = db.Column(db.String(50))

    # Guardian (single responsible person, replaces the old pai/mae pair)
    nome_responsavel = db.Column(db.String(100))
    cpf_responsavel = db.Column(db.String(14))

    # Minor / guardian consent flow
    data_nascimento = db.Column(db.Date)
    email_responsavel = db.Column(db.String(120))
    guardian_token = db.Column(db.String(64), unique=True)
    guardian_consented_at = db.Column(db.DateTime(timezone=True))

    instituicao_id = db.Column(UUID(as_uuid=True), db.ForeignKey("instituicao.id"))
    ponto_casa_id = db.Column(UUID(as_uuid=True), db.ForeignKey("ponto.id"))

    instituicao = db.relationship("Instituicao")
    ponto_casa = db.relationship("Ponto")

    __mapper_args__ = {
        "polymorphic_identity": UserRole.ALUNO,
    }

    @property
    def is_minor(self) -> bool:
        if not self.data_nascimento:
            return False
        today = date.today()
        age = (
            today.year
            - self.data_nascimento.year
            - ((today.month, today.day) < (self.data_nascimento.month, self.data_nascimento.day))
        )
        return age < 18
