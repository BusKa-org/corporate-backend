from marshmallow import fields

from app.schemas.common import BaseSchema


class EnderecoInputSchema(BaseSchema):
    logradouro = fields.String(required=True)
    numero = fields.String(required=True)
    bairro = fields.String(required=True)
    cidade = fields.String(required=True)
    cep = fields.String(required=True)
    latitude = fields.Float(required=True)
    longitude = fields.Float(required=True)


class EnderecoResponseSchema(BaseSchema):
    logradouro = fields.String(dump_default=None)
    numero = fields.String(dump_default=None)
    bairro = fields.String(dump_default=None)
    cidade = fields.String(dump_default=None)
    cep = fields.String(dump_default=None)
    latitude = fields.Float(dump_default=None)
    longitude = fields.Float(dump_default=None)
