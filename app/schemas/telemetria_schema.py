"""RF-22 — schemas de telemetria da bateria do veículo elétrico."""

from datetime import UTC

from marshmallow import fields, validate

from app.schemas.common import BaseSchema

# ==========================================
# Input Schemas (Validation)
# ==========================================


class AmostraTelemetriaSchema(BaseSchema):
    """Uma leitura do veículo.

    O `timestamp` é obrigatório: além de ser o eixo da série temporal, é metade
    da chave natural usada para deduplicar reenvios (ver `telemetria_service`).
    As faixas aqui reproduzem o CHECK do banco, para que uma amostra inválida
    volte como 400 e não como 500 vindo do Postgres.
    """

    timestamp = fields.AwareDateTime(required=True, default_timezone=UTC)
    viagem_id = fields.UUID(allow_none=True, load_default=None)
    nivel_bateria = fields.Float(
        allow_none=True, load_default=None, validate=validate.Range(min=0, max=100)
    )
    consumo_kwh = fields.Float(allow_none=True, load_default=None)
    autonomia_km = fields.Float(allow_none=True, load_default=None, validate=validate.Range(min=0))
    odometro_km = fields.Float(allow_none=True, load_default=None, validate=validate.Range(min=0))
    saude_bateria = fields.Float(
        allow_none=True, load_default=None, validate=validate.Range(min=0, max=100)
    )


class IngestaoTelemetriaRequestSchema(BaseSchema):
    """Lote de amostras de um único veículo — o leitor embarcado acumula e envia
    várias de uma vez quando recupera conectividade."""

    veiculo_id = fields.UUID(required=True)
    amostras = fields.List(
        fields.Nested(AmostraTelemetriaSchema), required=True, validate=validate.Length(min=1)
    )


class PeriodoQuerySchema(BaseSchema):
    """Filtro de período das consultas (ambos os limites inclusivos)."""

    veiculo_id = fields.UUID(required=False, load_default=None)
    inicio = fields.AwareDateTime(required=False, load_default=None, default_timezone=UTC)
    fim = fields.AwareDateTime(required=False, load_default=None, default_timezone=UTC)


# ==========================================
# Response Schemas (Serialization)
# ==========================================


class TelemetriaResponseSchema(BaseSchema):
    id = fields.UUID()
    veiculo_id = fields.UUID()
    viagem_id = fields.UUID(dump_default=None)
    timestamp = fields.DateTime()
    nivel_bateria = fields.Float(dump_default=None)
    consumo_kwh = fields.Float(dump_default=None)
    autonomia_km = fields.Float(dump_default=None)
    odometro_km = fields.Float(dump_default=None)
    saude_bateria = fields.Float(dump_default=None)


class TelemetriaListResponseSchema(BaseSchema):
    items = fields.List(fields.Nested(TelemetriaResponseSchema), required=True)
    total = fields.Integer(required=True)


class IngestaoResponseSchema(BaseSchema):
    recebidas = fields.Integer(required=True)
    armazenadas = fields.Integer(required=True)
    duplicadas = fields.Integer(required=True)


class ConsumoViagemSchema(BaseSchema):
    viagem_id = fields.UUID()
    veiculo_id = fields.UUID()
    amostras = fields.Integer()
    inicio = fields.DateTime(dump_default=None)
    fim = fields.DateTime(dump_default=None)
    consumo_kwh = fields.Float(dump_default=None)
    km = fields.Float(dump_default=None)
    bateria_max = fields.Float(dump_default=None)
    bateria_min = fields.Float(dump_default=None)


class ConsumoViagemListResponseSchema(BaseSchema):
    items = fields.List(fields.Nested(ConsumoViagemSchema), required=True)
    total = fields.Integer(required=True)
