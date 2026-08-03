"""Boarding endpoint documentation models (RF-15 a RF-18)."""

from flask_restx import fields


def register_models(api):
    """Register boarding models with the API namespace."""

    credencial_response = api.model(
        "CredencialResponse",
        {
            "viagem_id": fields.String(description="UUID da viagem"),
            "aluno_id": fields.String(description="UUID do aluno"),
            "qr_token": fields.String(description="Credencial opaca; o app a desenha como QR"),
            "ponto_embarque_id": fields.String(description="UUID do ponto de embarque"),
            "ponto_destino_id": fields.String(description="UUID do ponto de destino"),
            "embarcou": fields.Boolean(description="Embarque já registrado"),
            "embarcado_em": fields.DateTime(description="Momento do embarque"),
        },
    )

    passageiro_ponto = api.model(
        "PassageiroDoPonto",
        {
            "aluno_id": fields.String(description="UUID do aluno"),
            "nome": fields.String(description="Nome do passageiro"),
            "qr_token": fields.String(description="Credencial válida (matriz de permissões)"),
            "embarcou": fields.Boolean(description="Embarque já registrado"),
            "ponto_destino_id": fields.String(description="UUID do ponto de desembarque"),
        },
    )

    ponto_roteiro = api.model(
        "PontoRoteiro",
        {
            "ponto_id": fields.String(description="UUID do ponto"),
            "apelido": fields.String(description="Nome do ponto"),
            "ordem": fields.Integer(description="Posição no circuito"),
            "visitado": fields.Boolean(description="Parada já transposta"),
            "chegada_real": fields.DateTime(description="Horário de chegada"),
            "embarcam": fields.Integer(description="Quantos embarcam neste ponto"),
            "desembarcam": fields.Integer(description="Quantos desembarcam neste ponto"),
            "instrucao": fields.String(description="Instrução textual exibida ao motorista"),
            "passageiros": fields.List(fields.Nested(passageiro_ponto)),
        },
    )

    roteiro_response = api.model(
        "RoteiroResponse",
        {
            "viagem_id": fields.String(description="UUID da viagem"),
            "status": fields.String(description="Status da viagem"),
            "pontos": fields.List(fields.Nested(ponto_roteiro)),
            "ponto_atual_id": fields.String(description="Parada em atendimento"),
            "instrucao_atual": fields.String(description="Instrução da parada em atendimento"),
        },
    )

    validar_request = api.model(
        "ValidarEmbarqueRequest",
        {
            "qr_token": fields.String(required=True, description="Credencial lida do QR Code"),
            "ocorrido_em": fields.DateTime(description="Momento da leitura (ISO 8601)"),
        },
    )

    manual_request = api.model(
        "EmbarqueManualRequest",
        {
            "aluno_id": fields.String(required=True, description="UUID do aluno na lista do ponto"),
            "ocorrido_em": fields.DateTime(description="Momento do embarque (ISO 8601)"),
        },
    )

    avancar_request = api.model(
        "AvancarPontoRequest",
        {"ocorrido_em": fields.DateTime(description="Horário de chegada à parada (ISO 8601)")},
    )

    embarque_response = api.model(
        "EmbarqueResponse",
        {
            "viagem_id": fields.String(description="UUID da viagem"),
            "aluno_id": fields.String(description="UUID do aluno"),
            "nome": fields.String(description="Nome do passageiro"),
            "ponto_embarque_id": fields.String(description="UUID do ponto de embarque"),
            "embarcado_em": fields.DateTime(description="Momento do embarque"),
            "manual": fields.Boolean(description="Embarque registrado pelo fallback manual"),
        },
    )

    evento_offline = api.model(
        "EventoOffline",
        {
            "evento_id": fields.String(required=True, description="Identificador gerado no app"),
            "tipo": fields.String(
                required=True,
                description="EMBARQUE, EMBARQUE_MANUAL, CHEGADA_PONTO ou POSICAO",
            ),
            "ocorrido_em": fields.DateTime(required=True, description="Carimbo local do evento"),
            "qr_token": fields.String(description="Credencial lida (EMBARQUE)"),
            "aluno_id": fields.String(description="UUID do aluno (EMBARQUE_MANUAL)"),
            "ponto_id": fields.String(description="UUID do ponto (CHEGADA_PONTO, embarques)"),
            "latitude": fields.Float(description="Latitude (POSICAO)"),
            "longitude": fields.Float(description="Longitude (POSICAO)"),
        },
    )

    sincronizacao_request = api.model(
        "SincronizacaoRequest",
        {"eventos": fields.List(fields.Nested(evento_offline), required=True)},
    )

    resultado_evento = api.model(
        "ResultadoEvento",
        {
            "evento_id": fields.String(description="Identificador do evento"),
            "situacao": fields.String(description="aplicado, ja_aplicado ou recusado"),
            "codigo": fields.String(description="Código da recusa"),
            "mensagem": fields.String(description="Motivo da recusa"),
        },
    )

    sincronizacao_response = api.model(
        "SincronizacaoResponse",
        {
            "recebidos": fields.Integer(description="Eventos no lote"),
            "aplicados": fields.Integer(description="Eventos aplicados agora"),
            "ja_aplicados": fields.Integer(description="Eventos já aplicados antes"),
            "recusados": fields.Integer(description="Eventos recusados"),
            "resultados": fields.List(fields.Nested(resultado_evento)),
        },
    )

    return {
        "credencial_response": credencial_response,
        "roteiro_response": roteiro_response,
        "validar_request": validar_request,
        "manual_request": manual_request,
        "avancar_request": avancar_request,
        "embarque_response": embarque_response,
        "sincronizacao_request": sincronizacao_request,
        "sincronizacao_response": sincronizacao_response,
    }
