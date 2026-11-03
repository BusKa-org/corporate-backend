from marshmallow import fields, validate

from app.schemas.common import BaseSchema


class EnderecoInputSchema(BaseSchema):
    # Lengths match the Endereco columns in app/models/geo.py.
    logradouro = fields.String(required=True, validate=validate.Length(max=150))
    numero = fields.String(required=True, validate=validate.Length(max=20))
    bairro = fields.String(required=True, validate=validate.Length(max=100))
    cidade = fields.String(required=True, validate=validate.Length(max=100))
    cep = fields.String(required=True, validate=validate.Length(max=10))
    uf = fields.String(
        load_default=None,
        validate=validate.Regexp(r"^[A-Za-z]{2}$", error="UF deve ter 2 letras"),
    )
    latitude = fields.Float(required=True, validate=validate.Range(min=-90, max=90))
    longitude = fields.Float(required=True, validate=validate.Range(min=-180, max=180))


class EnderecoResponseSchema(BaseSchema):
    logradouro = fields.String(dump_default=None)
    numero = fields.String(dump_default=None)
    bairro = fields.String(dump_default=None)
    cidade = fields.String(dump_default=None)
    cep = fields.String(dump_default=None)
    latitude = fields.Float(dump_default=None)
    longitude = fields.Float(dump_default=None)
