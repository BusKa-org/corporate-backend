"""User endpoint documentation models."""

from flask_restx import fields


def register_models(api):
    """Register user models with the API namespace."""

    user_response = api.model(
        "UserResponse",
        {
            "id": fields.String(description="UUID do usuário"),
            "organizacao_id": fields.String(description="UUID da organização"),
            "nome": fields.String(description="Nome completo"),
            "email": fields.String(description="Email"),
            "telefone": fields.String(description="Telefone"),
            "cpf": fields.String(description="CPF"),
            "role": fields.String(description="Perfil (ALUNO, MOTORISTA, GESTOR)"),
            "status": fields.String(
                description="Status (PENDING_SIGNUP, PENDING_APPROVAL, ACTIVE, DISABLED, DELETED)"
            ),
            "signup_completed_at": fields.DateTime(description="Data de conclusão do cadastro"),
            "municipio_nome": fields.String(description="Nome do município (organização)"),
            "municipio_uf": fields.String(description="UF do município"),
            "matricula": fields.String(description="Matrícula (aluno)"),
            "nome_pai": fields.String(description="Nome do pai (aluno)"),
            "nome_mae": fields.String(description="Nome da mãe (aluno)"),
            "cnh": fields.String(description="CNH (motorista)"),
            "horario_inicio": fields.String(description="Início do horário de trabalho (HH:MM)"),
            "horario_fim": fields.String(description="Fim do horário de trabalho (HH:MM)"),
            "dias_trabalho": fields.List(fields.String, description="Dias de trabalho (SEG..DOM)"),
            "status_motorista": fields.String(
                description="Estado do motorista, calculado (ATIVO, EM_ROTA, EM_DESCANSO_OBRIGATORIO)"
            ),
            "descanso_ate": fields.DateTime(
                description="Fim do descanso obrigatório (só quando EM_DESCANSO_OBRIGATORIO)"
            ),
        },
    )

    # Clone, not a new field on UserResponse: /users/motoristas marshals with
    # UserResponse, so a new field there would also show up in that response.
    user_me_response = api.clone(
        "UserMeResponse",
        user_response,
        {
            "consentimento_pendente": fields.Boolean(
                description="true quando o usuário ainda não aceitou a versão vigente do termo"
            ),
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
            "horario_inicio": fields.String(description="Início do horário de trabalho (HH:MM)"),
            "horario_fim": fields.String(description="Fim do horário de trabalho (HH:MM)"),
            "dias_trabalho": fields.List(fields.String, description="Dias de trabalho (SEG..DOM)"),
        },
    )

    motorista_update_request = api.model(
        "MotoristaUpdateRequest",
        {
            "nome": fields.String(description="Nome completo"),
            "telefone": fields.String(description="Telefone"),
            "cnh": fields.String(description="CNH"),
            "horario_inicio": fields.String(description="Início do horário de trabalho (HH:MM)"),
            "horario_fim": fields.String(description="Fim do horário de trabalho (HH:MM)"),
            "dias_trabalho": fields.List(fields.String, description="Dias de trabalho (SEG..DOM)"),
        },
    )

    excluir_conta_request = api.model(
        "ExcluirContaRequest",
        {
            "email": fields.String(required=True, description="E-mail da conta"),
            "senha": fields.String(required=True, description="Senha atual"),
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
        "user_me_response": user_me_response,
        "excluir_conta_request": excluir_conta_request,
        "user_list_response": user_list_response,
        "motorista_create_request": motorista_create_request,
        "motorista_update_request": motorista_update_request,
        "change_password_request": change_password_request,
        "change_password_response": change_password_response,
        "fcm_token_response": fcm_token_response,
        "update_profile_request": update_profile_request,
    }
