"""Aluno endpoint documentation models."""

from flask_restx import fields

ACESSIBILIDADE_DESC = (
    "CADEIRA_DE_RODAS, MOBILIDADE_REDUZIDA, DEFICIENCIA_VISUAL, "
    "DEFICIENCIA_AUDITIVA, DEFICIENCIA_INTELECTUAL, OUTRA"
)


def register_models(api):
    """Register aluno models with the API namespace."""

    endereco_input = api.model(
        "EnderecoInput",
        {
            "logradouro": fields.String(required=True, description="Logradouro"),
            "numero": fields.String(required=True, description="Número"),
            "bairro": fields.String(required=True, description="Bairro"),
            "cidade": fields.String(required=True, description="Cidade"),
            "cep": fields.String(required=True, description="CEP"),
            "latitude": fields.Float(required=True, description="Latitude"),
            "longitude": fields.Float(required=True, description="Longitude"),
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
            "necessidades_acessibilidade": fields.List(
                fields.String,
                required=False,
                description=ACESSIBILIDADE_DESC,
            ),
            "observacao_acessibilidade": fields.String(
                required=False, description="Observação livre sobre acessibilidade"
            ),
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
                description="Status (PENDING_SIGNUP, PENDING_APPROVAL, ACTIVE, DISABLED, DELETED)"
            ),
            "signup_completed_at": fields.DateTime(description="Data de conclusão do cadastro"),
            "data_nascimento": fields.String(description="Data de nascimento"),
            "is_minor": fields.Boolean(description="Menor de idade"),
            "nome_responsavel": fields.String(description="Nome do responsável"),
            "cpf_responsavel": fields.String(description="CPF do responsável"),
            "foto_url": fields.String(description="Caminho da foto (GET autenticado)"),
            "necessidades_acessibilidade": fields.List(fields.String),
            "observacao_acessibilidade": fields.String(),
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
