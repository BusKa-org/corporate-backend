"""Dashboard endpoint documentation models."""

from flask_restx import fields


def register_models(api):
    """Register dashboard models with the API namespace."""

    ponto_progresso = api.model(
        "PontoProgresso",
        {
            "ponto_id": fields.String(description="ID do ponto"),
            "apelido": fields.String(description="Nome/Apelido do ponto"),
            "horario_passagem": fields.String(description="Horário real da passagem (ISO)"),
        },
    )

    relatorio_estatisticas = api.model(
        "RelatorioEstatisticas",
        {
            "periodo": fields.String(description="Período analisado"),
            "viagens_realizadas": fields.Integer(description="Total de viagens finalizadas"),
            "alunos_transportados": fields.Integer(description="Total de embarques reais"),
            "vagas_desperdicadas": fields.Integer(
                description="Alunos que confirmaram mas não embarcaram"
            ),
            "km_total_rodado": fields.Float(description="Quilometragem total gasta"),
            "media_alunos_por_km": fields.Float(description="Eficiência da operação"),
        },
    )

    ponto_telemetria = api.model(
        "PontoTelemetria",
        {
            "latitude": fields.Float(description="Latitude"),
            "longitude": fields.Float(description="Longitude"),
            "timestamp": fields.String(description="Horário exato do registro (ISO)"),
        },
    )

    return {
        "ponto_progresso": ponto_progresso,
        "relatorio_estatisticas": relatorio_estatisticas,
        "ponto_telemetria": ponto_telemetria,
    }
