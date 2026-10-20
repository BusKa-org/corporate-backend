from marshmallow import fields, validate

from app.schemas.common import BaseSchema


class GrupoCreateRequestSchema(BaseSchema):
    nome = fields.String(required=True, validate=validate.Length(min=1, max=100))
    grupo_pai_id = fields.String(load_default=None, allow_none=True)
    descricao = fields.String(load_default=None, allow_none=True, validate=validate.Length(max=255))
    data_inicio = fields.Date(load_default=None, allow_none=True)
    data_fim = fields.Date(load_default=None, allow_none=True)


class GrupoUpdateRequestSchema(BaseSchema):
    """Sem load_default: o que não vier no corpo continua como está."""

    nome = fields.String(validate=validate.Length(min=1, max=100))
    grupo_pai_id = fields.String(allow_none=True)
    descricao = fields.String(allow_none=True, validate=validate.Length(max=255))
    data_inicio = fields.Date(allow_none=True)
    data_fim = fields.Date(allow_none=True)


class MembroAddRequestSchema(BaseSchema):
    usuario_id = fields.String(required=True)


class GrupoResponseSchema(BaseSchema):
    id = fields.String()
    grupo_pai_id = fields.String(allow_none=True)
    nome = fields.String()
    descricao = fields.String(allow_none=True)
    data_inicio = fields.Date(allow_none=True)
    data_fim = fields.Date(allow_none=True)
    ativo = fields.Boolean()
    created_at = fields.DateTime()


class MembroResponseSchema(BaseSchema):
    grupo_id = fields.String()
    grupo_nome = fields.String()
    usuario_id = fields.String()
    nome = fields.String()
    data_inicio = fields.Date()
    data_fim = fields.Date(allow_none=True)
    atual = fields.Boolean()
    viagens_confirmadas = fields.Integer()
    viagens_finalizadas = fields.Integer()
    viagens_com_presenca = fields.Integer()
