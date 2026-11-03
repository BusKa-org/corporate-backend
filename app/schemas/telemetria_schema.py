"""Electric vehicle battery telemetry schemas (RF-22)."""

from datetime import UTC

from marshmallow import fields, validate

from app.schemas.common import BaseSchema

# ==========================================
# Input Schemas (Validation)
# ==========================================


class AmostraTelemetriaSchema(BaseSchema):
    """One vehicle reading.

    `timestamp` is required: besides being the time series axis, it is half of the
    natural key used to dedupe resends (see `telemetria_service`). The ranges here
    mirror the database CHECK, so an invalid sample returns 400 instead of a 500
    from Postgres.
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
    """Batch of samples from a single vehicle: the onboard reader accumulates them and
    sends several at once when it regains connectivity.
    """

    veiculo_id = fields.UUID(required=True)
    amostras = fields.List(
        fields.Nested(AmostraTelemetriaSchema), required=True, validate=validate.Length(min=1)
    )


class PeriodoQuerySchema(BaseSchema):
    """Period filter for the queries (both bounds inclusive)."""

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
