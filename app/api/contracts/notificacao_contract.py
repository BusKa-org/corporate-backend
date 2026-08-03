from flask_restx import fields


def get_notificacao_input_model(api):
    return api.model(
        "NotificacaoInput",
        {
            "titulo": fields.String(
                required=True, description="Título do aviso", example="Aviso Importante"
            ),
            "mensagem": fields.String(
                required=True,
                description="Corpo da mensagem",
                example="O ônibus vai atrasar 10 minutos hoje.",
            ),
            "rota_id": fields.String(
                description="ID da rota (opcional se enviar viagem_id)",
                example="COLE_O_UUID_DA_ROTA_AQUI",
            ),
            "viagem_id": fields.String(description="ID da viagem (opcional)", example=""),
        },
    )
