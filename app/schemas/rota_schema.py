from marshmallow import fields, validate

from app.models.enum import TipoViagem
from app.schemas.common import BaseSchema

from .horario_schema import HorarioResponseSchema
from .ponto_schema import PontoFlatResponseSchema

# ==========================================
# Input Schemas (Validation)
# ==========================================


class RotaPontoAddRequestSchema(BaseSchema):
    """Schema for adding a point to a route."""

    ponto_id = fields.String(required=True)
    ordem = fields.Integer(required=True)


class RotaPontosAddRequestSchema(BaseSchema):
    """Schema for adding points to a route."""

    pontos = fields.List(fields.Nested(RotaPontoAddRequestSchema), required=True)


class RotaHorarioCreateRequestSchema(BaseSchema):
    """Schema for route schedule input."""

    horario_saida = fields.String(required=True)
    sentido = fields.String(required=True, validate=validate.OneOf(["IDA", "VOLTA", "CIRCULAR"]))
    dias = fields.List(fields.String(), required=True)


# Limites dos parâmetros sob demanda, em minutos.
BUFFER_MINUTOS_RANGE = validate.Range(min=1, max=30)
PRAZO_INICIO_MINUTOS_RANGE = validate.Range(min=1, max=120)


class RotaCreateRequestSchema(BaseSchema):
    """Schema for creating a new route."""

    nome = fields.String(required=True)
    tipo = fields.Enum(TipoViagem, load_default=TipoViagem.FIXA)
    buffer_minutos = fields.Integer(load_default=None, validate=BUFFER_MINUTOS_RANGE)
    prazo_inicio_minutos = fields.Integer(load_default=None, validate=PRAZO_INICIO_MINUTOS_RANGE)
    motorista_padrao_id = fields.String(load_default=None)
    veiculo_padrao_id = fields.String(load_default=None)
    pontos = fields.List(fields.Nested(RotaPontoAddRequestSchema), load_default=[])
    horarios = fields.List(fields.Nested(RotaHorarioCreateRequestSchema), load_default=[])


class RotaUpdateRequestSchema(BaseSchema):
    """Schema for updating a route.

    All fields are optional. Only fields present in the request body are updated.
    Pass null explicitly to clear an assignment (e.g. motorista_padrao_id=null).
    """

    nome = fields.String()
    motorista_padrao_id = fields.String(allow_none=True)
    veiculo_padrao_id = fields.String(allow_none=True)
    buffer_minutos = fields.Integer(validate=BUFFER_MINUTOS_RANGE)
    prazo_inicio_minutos = fields.Integer(validate=PRAZO_INICIO_MINUTOS_RANGE)


# ==========================================
# Response Schemas (Serialization)
# ==========================================


class RotaResponseSchema(BaseSchema):
    id = fields.String()
    nome = fields.String()
    tipo = fields.Enum(TipoViagem)
    buffer_minutos = fields.Integer()
    prazo_inicio_minutos = fields.Integer()
    motorista_id = fields.Method("get_motorista_id")
    veiculo_id = fields.Method("get_veiculo_id")
    organizacao_id = fields.String()
    municipio_nome = fields.Method("get_municipio_nome")
    municipio_uf = fields.Method("get_municipio_uf")

    def get_motorista_id(self, obj):
        return str(obj.motorista_padrao_id) if obj.motorista_padrao_id else None

    def get_veiculo_id(self, obj):
        return str(obj.veiculo_padrao_id) if obj.veiculo_padrao_id else None

    def get_municipio_nome(self, obj):
        if obj.organizacao:
            return obj.organizacao.nome
        return None

    def get_municipio_uf(self, obj):
        if obj.organizacao:
            return obj.organizacao.estado
        return None


class RotaDetailResponseSchema(RotaResponseSchema):
    """Extended schema with nested relationships."""

    pontos = fields.Method("get_pontos")
    horarios = fields.Nested(HorarioResponseSchema, many=True, attribute="grade_horarios")

    def get_pontos(self, obj):
        return PontoFlatResponseSchema(many=True).dump(
            [rota_ponto.ponto for rota_ponto in obj.pontos_padrao]
        )


class RotaListResponseSchema(BaseSchema):
    items = fields.List(fields.Nested(RotaResponseSchema), required=True)
    total = fields.Integer(required=True)
