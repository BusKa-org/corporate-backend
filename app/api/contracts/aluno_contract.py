"""Aluno endpoint documentation models."""

from flask_restx import fields


def register_models(api):
    """Register aluno models with the API namespace."""

    endereco_input = api.model(
        "EnderecoInput",
        {
            "rua": fields.String(required=True, description="Nome da rua"),
            "numero": fields.String(required=True, description="Número"),
            "bairro": fields.String(required=True, description="Bairro"),
            "cidade": fields.String(required=True, description="Cidade"),
            "estado": fields.String(required=True, description="Estado (UF)"),
            "cep": fields.String(required=True, description="CEP"),
            "complemento": fields.String(required=False, description="Complemento"),
        },
    )

    me_update_request = api.model(
        "AlunoMeUpdateRequest",
        {
            "nome": fields.String(required=False, description="Nome completo"),
            "telefone": fields.String(required=False, description="Telefone"),
            "matricula": fields.String(required=False, description="Matrícula escolar"),
            "nome_responsavel": fields.String(required=False, description="Nome do responsável"),
            "cpf_responsavel": fields.String(required=False, description="CPF do responsável"),
            "endereco_casa": fields.Nested(endereco_input, required=False),
        },
    )

    aluno_response = api.model(
        "AlunoResponse",
        {
            "id": fields.String(description="UUID do aluno"),
            "nome": fields.String(description="Nome completo"),
            "email": fields.String(description="E-mail"),
            "telefone": fields.String(description="Telefone"),
            "cpf": fields.String(description="CPF"),
            "matricula": fields.String(description="Matrícula"),
            "escola": fields.String(description="Nome da escola"),
            "instituicao_id": fields.String(description="UUID da instituição"),
            "status": fields.String(
                description="Status (PENDING_SIGNUP, PENDING_APPROVAL, ACTIVE, DISABLED)"
            ),
            "signup_completed_at": fields.DateTime(description="Data de conclusão do cadastro"),
            "data_nascimento": fields.String(description="Data de nascimento"),
            "is_minor": fields.Boolean(description="Menor de idade"),
            "email_responsavel": fields.String(description="E-mail do responsável"),
            "nome_responsavel": fields.String(description="Nome do responsável"),
            "cpf_responsavel": fields.String(description="CPF do responsável"),
            "guardian_consented_at": fields.DateTime(
                description="Data/hora do consentimento do responsável"
            ),
        },
    )

    aluno_list_response = api.model(
        "AlunoListResponse",
        {
            "items": fields.List(fields.Nested(aluno_response)),
            "total": fields.Integer(description="Total de alunos"),
        },
    )

    return {
        "me_update_request": me_update_request,
        "aluno_response": aluno_response,
        "aluno_list_response": aluno_list_response,
    }
