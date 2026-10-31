from marshmallow import fields

from app.schemas.common import BaseSchema


class AceiteRequestSchema(BaseSchema):
    versao = fields.String(required=True)


class ConsentimentoEstadoResponseSchema(BaseSchema):
    versao_vigente = fields.String()
    pendente = fields.Boolean()
