"""User endpoint documentation models."""

from flask_restx import fields


def register_models(api):
    """Register user models with the API namespace."""

    user_response = api.model(
        "UserResponse",
        {
            "id": fields.String(description="UUID do usuário"),
            "prefeitura_id": fields.String(description="UUID da prefeitura"),
            "nome": fields.String(description="Nome completo"),
            "email": fields.String(description="Email"),
            "telefone": fields.String(description="Telefone"),
            "cpf": fields.String(description="CPF"),
            "role": fields.String(description="Perfil (ALUNO, MOTORISTA, GESTOR)"),
            "status": fields.String(description="Status (PENDING_SIGNUP, ACTIVE, DISABLED)"),
            "signup_completed_at": fields.DateTime(description="Data de conclusão do cadastro"),
            "municipio_nome": fields.String(description="Nome do município (prefeitura)"),
            "municipio_uf": fields.String(description="UF do município"),
            "matricula": fields.String(description="Matrícula (aluno)"),
            "nome_pai": fields.String(description="Nome do pai (aluno)"),
            "nome_mae": fields.String(description="Nome da mãe (aluno)"),
            "cnh": fields.String(description="CNH (motorista)"),
        },
    )

    user_list_response = api.model(
        "UserListResponse",
        {
            "items": fields.List(fields.Nested(user_response)),
            "total": fields.Integer(description="Total de usuários"),
        },
    )

    motorista_create_request = api.model(
        "MotoristaCreateRequest",
        {
            "nome": fields.String(required=True, description="Nome completo"),
            "email": fields.String(required=True, description="Email"),
            "password": fields.String(required=True, description="Senha"),
            "cpf": fields.String(required=True, description="CPF"),
            "telefone": fields.String(description="Telefone"),
            "cnh": fields.String(required=True, description="CNH"),
            "salario": fields.Float(description="Salário"),
        },
    )

    change_password_request = api.model(
        "ChangePasswordRequest",
        {
            "current_password": fields.String(required=True, description="Senha atual"),
            "new_password": fields.String(required=True, description="Nova senha"),
        },
    )

    change_password_response = api.model(
        "ChangePasswordResponse",
        {
            "message": fields.String(description="Mensagem de sucesso"),
        },
    )

    fcm_token_request = api.model(
        "FcmTokenRequest",
        {
            "fcm_token": fields.String(
                required=True, description="Token do dispositivo gerado pelo Firebase no Frontend"
            )
        },
    )

    fcm_token_response = api.model(
        "FcmTokenResponse",
        {
            "message": fields.String(description="Mensagem de sucesso"),
        },
    )

    update_profile_request = api.model(
        "UpdateProfileRequest",
        {
            "nome": fields.String(description="Nome completo"),
            "telefone": fields.String(description="Telefone"),
            "receber_notificacoes": fields.Boolean(description="Aceitar notificações"),
            "cnh": fields.String(description="CNH (apenas motoristas)"),
        },
    )

    return {
        "fcm_token_request": fcm_token_request,
        "user_response": user_response,
        "user_list_response": user_list_response,
        "motorista_create_request": motorista_create_request,
        "change_password_request": change_password_request,
        "change_password_response": change_password_response,
        "fcm_token_response": fcm_token_response,
        "update_profile_request": update_profile_request,
    }
