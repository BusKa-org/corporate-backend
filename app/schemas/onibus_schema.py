from marshmallow import fields

from app.schemas.common import BaseSchema


class OnibusCreateRequestSchema(BaseSchema):
    placa = fields.String(required=True)
    modelo = fields.String(required=False)
    capacidade = fields.Integer(required=True)


class OnibusUpdateRequestSchema(BaseSchema):
    placa = fields.String(required=False)
    modelo = fields.String(required=False)
    capacidade = fields.Integer(required=False)


class OnibusResponseSchema(BaseSchema):
    id = fields.UUID()
    placa = fields.String()
    modelo = fields.String()
    capacidade = fields.Integer()
    prefeitura_id = fields.UUID()


class OnibusListResponseSchema(BaseSchema):
    items = fields.List(fields.Nested(OnibusResponseSchema), required=True)
    total = fields.Integer(required=True)
