from marshmallow import fields

from app.schemas.common import BaseSchema


class SolicitacaoViagemResumoSchema(BaseSchema):
    id = fields.UUID()
    status = fields.Function(lambda v: v.status.value if v.status else None)
    rota_id = fields.UUID()
    motorista_id = fields.UUID(allow_none=True)
    buffer_fim = fields.DateTime(allow_none=True)


class SolicitacaoResponseSchema(BaseSchema):
    id = fields.UUID()
    viagem_id = fields.UUID()
    status = fields.Function(lambda s: s.status.value if s.status else None)
    created_at = fields.DateTime()
    viagem = fields.Nested(SolicitacaoViagemResumoSchema)
