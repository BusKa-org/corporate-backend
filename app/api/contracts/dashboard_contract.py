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

    # ==========================================
    # RF-21 — indicadores agregados do período
    # ==========================================

    viagem_por_status = api.model(
        "IndicadorViagensPorStatus",
        {
            "status": fields.String(description="Status da viagem"),
            "total": fields.Integer(description="Viagens nesse status no período"),
        },
    )

    negacao_por_ponto = api.model(
        "IndicadorNegacaoPorPonto",
        {
            "ponto_id": fields.String(description="ID do ponto de embarque"),
            "apelido": fields.String(description="Nome do ponto"),
            "negacoes": fields.Integer(description="Solicitações negadas por capacidade"),
        },
    )

    tempo_trecho = api.model(
        "IndicadorTempoTrecho",
        {
            "ponto_origem_id": fields.String,
            "ponto_origem": fields.String,
            "ponto_destino_id": fields.String,
            "ponto_destino": fields.String,
            "minutos_medio": fields.Float(description="Tempo médio do trecho, em minutos"),
            "amostras": fields.Integer(description="Passagens usadas na média"),
            "ordem": fields.Integer(description="Posição do trecho no circuito"),
        },
    )

    ocupacao = api.model(
        "IndicadorOcupacao",
        {
            "viagens_consideradas": fields.Integer(
                description="Viagens operadas com veículo e capacidade conhecidos"
            ),
            "passageiros_media": fields.Float(description="Média de embarques por viagem"),
            "capacidade_media": fields.Float(description="Capacidade média dos veículos"),
            "taxa_ocupacao": fields.Float(
                description="Média de passageiros/capacidade (nulo sem viagens)"
            ),
        },
    )

    ipk = api.model(
        "IndicadorIPK",
        {
            "passageiros": fields.Integer(description="Embarques nas viagens com km registrado"),
            "km": fields.Float(description="Quilometragem somada dessas viagens"),
            "ipk": fields.Float(
                description="Passageiros por quilômetro; nulo se nenhuma viagem tem km_real"
            ),
            "viagens_consideradas": fields.Integer(description="Viagens com km_real > 0"),
            "viagens_sem_km": fields.Integer(
                description="Viagens operadas sem km_real, excluídas do IPK"
            ),
        },
    )

    periodo = api.model(
        "IndicadorPeriodo",
        {"inicio": fields.String, "fim": fields.String},
    )

    indicadores_periodo = api.model(
        "IndicadoresPeriodo",
        {
            "periodo": fields.Nested(periodo),
            "sem_dados": fields.Boolean(description="Verdadeiro se o período não tem viagens"),
            "mensagem": fields.String(description="Mensagem informativa quando não há dados"),
            "periodo_sugerido": fields.Nested(
                periodo, allow_null=True, description="Intervalo com dados, quando existe"
            ),
            "total_viagens": fields.Integer,
            "viagens_por_status": fields.List(fields.Nested(viagem_por_status)),
            "negacoes_por_ponto": fields.List(fields.Nested(negacao_por_ponto)),
            "tempo_medio_por_trecho": fields.List(fields.Nested(tempo_trecho)),
            "ocupacao": fields.Nested(ocupacao),
            "ipk": fields.Nested(ipk),
        },
    )

    return {
        "ponto_progresso": ponto_progresso,
        "relatorio_estatisticas": relatorio_estatisticas,
        "ponto_telemetria": ponto_telemetria,
        "indicadores_periodo": indicadores_periodo,
    }
