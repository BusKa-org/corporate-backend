from marshmallow import fields

from app.models.enum import DiaDaSemana
from app.schemas.common import BaseSchema


class JanelaCreateRequestSchema(BaseSchema):
    motorista_id = fields.UUID(required=True)
    dia = fields.Enum(DiaDaSemana, required=True)
    hora_inicio = fields.Time(required=True, format="%H:%M")
    hora_fim = fields.Time(required=True, format="%H:%M")


class JanelaResponseSchema(BaseSchema):
    id = fields.UUID()
    onibus_id = fields.UUID()
    motorista_id = fields.UUID()
    motorista_nome = fields.Method("get_motorista_nome")
    dia = fields.Enum(DiaDaSemana)
    hora_inicio = fields.Time(format="%H:%M")
    hora_fim = fields.Time(format="%H:%M")
    created_at = fields.DateTime()

    def get_motorista_nome(self, obj):
        return obj.motorista.nome


class JanelaListResponseSchema(BaseSchema):
    items = fields.List(fields.Nested(JanelaResponseSchema), required=True)
    total = fields.Integer(required=True)
