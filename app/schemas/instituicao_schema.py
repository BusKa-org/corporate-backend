from marshmallow import fields, validate

from app.models.enum import TipoInstituicao
from app.schemas.common import BaseSchema
from app.schemas.endereco_schema import EnderecoInputSchema, EnderecoResponseSchema
from app.schemas.validators import validate_cnpj

# Built from the enum so the allowed list cannot drift from it.
TIPOS_INSTITUICAO: list[str] = []
for tipo_instituicao in TipoInstituicao:
    TIPOS_INSTITUICAO.append(tipo_instituicao.name)


class InstituicaoCreateRequestSchema(BaseSchema):
    nome = fields.String(required=True)
    # Loads as digits only, so "12.345.678/0001-99" and "12345678000199" match.
    cnpj = fields.Function(deserialize=validate_cnpj, required=True)
    tipo = fields.String(
        required=True,
        validate=validate.OneOf(TIPOS_INSTITUICAO),
        metadata={"description": "Tipo da instituição conforme modelo"},
    )
    endereco = fields.Nested(EnderecoInputSchema, required=True)


class InstituicaoResponseSchema(BaseSchema):
    id = fields.String(dump_default=None)
    nome = fields.String(dump_default=None)
    cnpj = fields.String(dump_default=None)
    tipo = fields.Method("get_tipo")

    def get_tipo(self, obj):
        return str(obj.tipo.value) if hasattr(obj.tipo, "value") else str(obj.tipo)

    sigla = fields.String(dump_default=None)
    uf = fields.String(dump_default=None)
    endereco = fields.Nested(EnderecoResponseSchema, attribute="ponto.endereco")
    latitude = fields.Float(attribute="ponto.latitude", dump_default=None)
    longitude = fields.Float(attribute="ponto.longitude", dump_default=None)


class InstituicaoListResponseSchema(BaseSchema):
    items = fields.List(fields.Nested(InstituicaoResponseSchema()), required=True)
    total = fields.Integer(required=True)


class InstituicaoListQuerySchema(BaseSchema):
    search = fields.String(required=False)
    limit = fields.Integer(required=False, dump_default=10)
