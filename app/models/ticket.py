"""Tickets de viagem: política (regra), saldo por pessoa e histórico de movimentos.

A política mora num de três níveis: organização, grupo ou pessoa. O saldo é por pessoa
e por política. A recarga é calculada na leitura (ver `app/services/ticket_saldo.py`).
"""

import uuid

from sqlalchemy.dialects.postgresql import ARRAY, UUID

from .base import db
from .enum import JanelaCota, SentidoViagem, TipoMovimentoTicket, TipoPoliticaTicket


class PoliticaTicket(db.Model):
    __tablename__ = "politica_ticket"
    __table_args__ = (
        # Alvo é a organização (os dois nulos), um grupo ou uma pessoa. Nunca os dois.
        db.CheckConstraint(
            "grupo_id IS NULL OR usuario_id IS NULL", name="ck_politica_ticket_um_alvo"
        ),
        db.Index("idx_politica_ticket_organizacao", "organizacao_id"),
        db.Index("idx_politica_ticket_grupo", "grupo_id"),
        db.Index("idx_politica_ticket_usuario", "usuario_id"),
    )

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organizacao_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("organizacao.id", ondelete="CASCADE"), nullable=False
    )
    grupo_id = db.Column(UUID(as_uuid=True), db.ForeignKey("grupo.id", ondelete="CASCADE"))
    usuario_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("aluno.usuario_id", ondelete="CASCADE")
    )
    nome = db.Column(db.String(100), nullable=False)
    tipo = db.Column(db.Enum(TipoPoliticaTicket, name="tipo_politica_ticket"), nullable=False)

    vigencia_inicio = db.Column(db.Date)
    vigencia_fim = db.Column(db.Date)

    # RECARGA: máximo de tickets. COTA: tickets por janela.
    teto = db.Column(db.Integer)

    # Só RECARGA. Dias de 0 (segunda) a 6 (domingo). Nulo: todos os dias.
    recarga_quantidade = db.Column(db.Integer)
    recarga_intervalo_minutos = db.Column(db.Integer)
    recarga_dias_semana = db.Column(ARRAY(db.Integer))

    # Só COTA. `janela_horas` vale só com a janela HORAS.
    janela = db.Column(db.Enum(JanelaCota, name="janela_cota_ticket"))
    janela_horas = db.Column(db.Integer)

    devolve_ao_finalizar = db.Column(db.Boolean, nullable=False, default=False)
    no_show_penalidade = db.Column(db.Integer, nullable=False, default=0)
    cancelamento_prazo_horas = db.Column(db.Integer)
    antecedencia_min_horas = db.Column(db.Integer)
    antecedencia_max_dias = db.Column(db.Integer)

    # Escopo: a política só vale para viagens que casam com todos os campos preenchidos.
    rota_id = db.Column(UUID(as_uuid=True), db.ForeignKey("rota.id", ondelete="CASCADE"))
    sentido = db.Column(db.Enum(SentidoViagem, name="sentido_viagem"))
    horario_de = db.Column(db.Time)
    horario_ate = db.Column(db.Time)

    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now(), nullable=False)


class SaldoTicket(db.Model):
    """Saldo de uma pessoa numa política. Política ILIMITADO não tem linha."""

    __tablename__ = "saldo_ticket"

    usuario_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("aluno.usuario_id", ondelete="CASCADE"), primary_key=True
    )
    politica_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("politica_ticket.id", ondelete="CASCADE"),
        primary_key=True,
    )
    quantidade = db.Column(db.Integer, nullable=False)
    # Gasto antes da quantidade e sem teto. Vem de concessão manual e de devolução que sobrou.
    bonus = db.Column(db.Integer, nullable=False, default=0)
    # RECARGA: última recarga já aplicada. COTA: início da janela já aplicada.
    referencia_em = db.Column(db.DateTime(timezone=True), nullable=False)
    aguardando_aviso = db.Column(db.Boolean, nullable=False, default=False)


class MovimentoTicket(db.Model):
    """Histórico. A quantidade é sempre positiva e o sinal vem do tipo.
    A recarga calculada na leitura fica fora do histórico."""

    __tablename__ = "movimento_ticket"
    __table_args__ = (
        db.Index("idx_movimento_ticket_politica", "politica_id", "created_at"),
        db.Index("idx_movimento_ticket_usuario", "usuario_id", "created_at"),
    )

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    usuario_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("aluno.usuario_id", ondelete="CASCADE"), nullable=False
    )
    # RESTRICT: política com histórico não se apaga, encerra-se com `vigencia_fim`.
    politica_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("politica_ticket.id", ondelete="RESTRICT"), nullable=False
    )
    viagem_id = db.Column(UUID(as_uuid=True), db.ForeignKey("viagem.id", ondelete="SET NULL"))
    tipo = db.Column(db.Enum(TipoMovimentoTicket, name="tipo_movimento_ticket"), nullable=False)
    quantidade = db.Column(db.Integer, nullable=False)
    motivo = db.Column(db.String(255))
    criado_por = db.Column(UUID(as_uuid=True), db.ForeignKey("usuario.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now(), nullable=False)
