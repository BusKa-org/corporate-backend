"""RF-05 — validação e serialização das janelas de disponibilidade."""

from typing import Any

from marshmallow import ValidationError as MarshmallowValidationError, fields, validates_schema
from marshmallow.validate import Range

from app.models.enum import DiaDaSemana
from app.schemas.common import BaseSchema
from app.schemas.viagem_schema import EnumByNameField

# ==========================================
# Input Schemas (Validation)
# ==========================================


class JanelaCreateRequestSchema(BaseSchema):
    """POST /janelas"""

    rota_id = fields.UUID(required=True)
    motorista_id = fields.UUID(required=True)
    veiculo_id = fields.UUID(load_default=None, allow_none=True)
    dia = EnumByNameField(DiaDaSemana, required=True)
    hora_inicio = fields.Time(required=True)
    hora_fim = fields.Time(required=True)
    buffer_minutos = fields.Integer(load_default=5, validate=Range(min=1))
    ativo = fields.Boolean(load_default=True)

    @validates_schema
    def validate_horas(self, data: dict[str, Any], **kwargs) -> None:
        if data.get("hora_inicio") and data.get("hora_fim"):
            if data["hora_fim"] <= data["hora_inicio"]:
                raise MarshmallowValidationError(
                    {"hora_fim": ["A hora final precisa ser maior que a inicial."]}
                )


class JanelaUpdateRequestSchema(JanelaCreateRequestSchema):
    """PATCH /janelas/<id> — todos os campos opcionais."""

    rota_id = fields.UUID(required=False)
    motorista_id = fields.UUID(required=False)
    veiculo_id = fields.UUID(required=False, allow_none=True)
    dia = EnumByNameField(DiaDaSemana, required=False)
    hora_inicio = fields.Time(required=False)
    hora_fim = fields.Time(required=False)
    buffer_minutos = fields.Integer(required=False, validate=Range(min=1))
    ativo = fields.Boolean(required=False)


class JanelaListQuerySchema(BaseSchema):
    """GET /janelas?rota_id=...&dia=SEG"""

    rota_id = fields.String(required=False, allow_none=True)
    dia = EnumByNameField(DiaDaSemana, required=False, allow_none=True)


# ==========================================
# Response Schemas (Serialization)
# ==========================================


class JanelaResponseSchema(BaseSchema):
    id = fields.String()
    rota_id = fields.String()
    rota_nome = fields.String(attribute="rota.nome")
    motorista_id = fields.String()
    motorista_nome = fields.String(attribute="motorista.nome")
    veiculo_id = fields.String(allow_none=True)
    dia = fields.Method("get_dia")
    hora_inicio = fields.Time()
    hora_fim = fields.Time()
    buffer_minutos = fields.Integer()
    ativo = fields.Boolean()

    def get_dia(self, obj) -> str | None:
        return obj.dia.name if obj.dia else None


class JanelaListResponseSchema(BaseSchema):
    items = fields.List(fields.Nested(JanelaResponseSchema))
    total = fields.Integer()


class JanelaVigenteResponseSchema(BaseSchema):
    """A janela em vigor agora e os horários de operação do dia (RF-10)."""

    em_operacao = fields.Boolean()
    janela = fields.Nested(JanelaResponseSchema, allow_none=True)
    horarios_hoje = fields.List(fields.Nested(JanelaResponseSchema))


class MessageResponseSchema(BaseSchema):
    message = fields.String()
