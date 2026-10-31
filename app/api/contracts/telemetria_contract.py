"""RF-22 — documentação dos endpoints de telemetria da bateria."""

from flask_restx import fields


def register_models(api):
    """Register telemetria models with the API namespace."""

    amostra = api.model(
        "TelemetriaAmostra",
        {
            "timestamp": fields.DateTime(
                required=True, description="Instante da leitura (ISO 8601, com fuso)"
            ),
            "viagem_id": fields.String(description="Viagem em curso, se houver"),
            "nivel_bateria": fields.Float(description="Carga da bateria em % (0 a 100)"),
            "consumo_kwh": fields.Float(description="Consumo no intervalo, em kWh"),
            "autonomia_km": fields.Float(description="Autonomia estimada em km"),
            "odometro_km": fields.Float(description="Odômetro acumulado em km"),
            "saude_bateria": fields.Float(description="SOH da bateria em % (0 a 100)"),
        },
    )

    ingestao_request = api.model(
        "TelemetriaIngestaoRequest",
        {
            "veiculo_id": fields.String(required=True, description="UUID do veículo"),
            "amostras": fields.List(
                fields.Nested(amostra), required=True, description="Lote de leituras"
            ),
        },
    )

    ingestao_response = api.model(
        "TelemetriaIngestaoResponse",
        {
            "recebidas": fields.Integer(description="Amostras no lote"),
            "armazenadas": fields.Integer(description="Amostras novas gravadas"),
            "duplicadas": fields.Integer(description="Amostras já conhecidas, descartadas"),
        },
    )

    telemetria_response = api.model(
        "TelemetriaResponse",
        {
            "id": fields.String,
            "veiculo_id": fields.String,
            "viagem_id": fields.String,
            "timestamp": fields.DateTime,
            "nivel_bateria": fields.Float,
            "consumo_kwh": fields.Float,
            "autonomia_km": fields.Float,
            "odometro_km": fields.Float,
            "saude_bateria": fields.Float,
        },
    )

    telemetria_list_response = api.model(
        "TelemetriaListResponse",
        {
            "items": fields.List(fields.Nested(telemetria_response)),
            "total": fields.Integer,
        },
    )

    consumo_viagem = api.model(
        "TelemetriaConsumoViagem",
        {
            "viagem_id": fields.String,
            "veiculo_id": fields.String,
            "amostras": fields.Integer,
            "inicio": fields.DateTime,
            "fim": fields.DateTime,
            "consumo_kwh": fields.Float(description="Soma do consumo das amostras da viagem"),
            "km": fields.Float(description="Diferença entre odômetro final e inicial"),
            "bateria_max": fields.Float,
            "bateria_min": fields.Float,
        },
    )

    consumo_viagem_list_response = api.model(
        "TelemetriaConsumoViagemListResponse",
        {
            "items": fields.List(fields.Nested(consumo_viagem)),
            "total": fields.Integer,
        },
    )

    return {
        "ingestao_request": ingestao_request,
        "ingestao_response": ingestao_response,
        "telemetria_response": telemetria_response,
        "telemetria_list_response": telemetria_list_response,
        "consumo_viagem_list_response": consumo_viagem_list_response,
    }
