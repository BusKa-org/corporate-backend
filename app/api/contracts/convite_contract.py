"""Convite endpoint documentation models."""

from flask_restx import fields

from app.api.contracts.aluno_contract import ACESSIBILIDADE_DESC


def register_models(api):
    """Register convite models with the API namespace."""

    convite_item_request = api.model(
        "ConviteItemRequest",
        {
            "email": fields.String(required=True, description="E-mail do convidado"),
            "nome": fields.String(description="Nome (até 100 caracteres)"),
            "cpf": fields.String(description="CPF"),
            "telefone": fields.String(description="Telefone"),
            "instituicao_id": fields.String(description="UUID da instituição da organização"),
        },
    )

    convites_create_request = api.model(
        "ConvitesCreateRequest",
        {
            "convites": fields.List(
                fields.Nested(convite_item_request),
                required=True,
                description="De 1 a 500 convites; cada linha é validada sozinha",
            ),
        },
    )

    convite_resultado = api.model(
        "ConviteResultado",
        {
            "email": fields.String(description="E-mail da linha"),
            "resultado": fields.String(enum=["CRIADO", "RENOVADO", "PULADO", "INVALIDO"]),
            "motivo": fields.String(description="Motivo quando PULADO ou INVALIDO"),
        },
    )

    convites_create_response = api.model(
        "ConvitesCreateResponse",
        {"resultados": fields.List(fields.Nested(convite_resultado))},
    )

    convite_response = api.model(
        "ConviteResponse",
        {
            "id": fields.String(description="UUID do convite"),
            "email": fields.String(description="E-mail"),
            "nome": fields.String(description="Nome"),
            "cpf": fields.String(description="CPF"),
            "telefone": fields.String(description="Telefone"),
            "instituicao_id": fields.String(description="UUID da instituição"),
            "estado": fields.String(enum=["PENDENTE", "CONCLUIDO", "CANCELADO"]),
            "envio_estado": fields.String(enum=["PENDENTE", "ENVIADO", "FALHOU"]),
            "expira_em": fields.DateTime(description="Validade do link"),
            "vencido": fields.Boolean(description="PENDENTE com a validade vencida"),
            "created_at": fields.DateTime(description="Data de criação"),
            "concluido_em": fields.DateTime(description="Data de conclusão do cadastro"),
        },
    )

    convite_list_response = api.model(
        "ConviteListResponse",
        {
            "items": fields.List(fields.Nested(convite_response)),
            "total": fields.Integer(description="Total de convites"),
        },
    )

    convite_dados_response = api.model(
        "ConviteDadosResponse",
        {
            "email": fields.String(description="E-mail"),
            "nome": fields.String(description="Nome preenchido pelo gestor"),
            "cpf": fields.String(description="CPF preenchido pelo gestor"),
            "telefone": fields.String(description="Telefone preenchido pelo gestor"),
            "instituicao_id": fields.String(description="UUID da instituição"),
            "campos_faltando": fields.List(
                fields.String, description="Campos que a pessoa ainda precisa enviar"
            ),
        },
    )

    convite_aceite_request = api.model(
        "ConviteAceiteRequest",
        {
            "senha": fields.String(required=True, description="Senha da nova conta"),
            "nome": fields.String(description="Obrigatório se o convite não trouxer"),
            "cpf": fields.String(description="Obrigatório se o convite não trouxer"),
            "telefone": fields.String(description="Telefone"),
            "instituicao_id": fields.String(description="Obrigatório se o convite não trouxer"),
            "necessidades_acessibilidade": fields.List(
                fields.String, description=ACESSIBILIDADE_DESC
            ),
            "observacao_acessibilidade": fields.String(description="Até 500 caracteres"),
        },
    )

    pin_solicitar_request = api.model(
        "PinSolicitarRequest",
        {"email": fields.String(required=True, description="E-mail convidado")},
    )

    pin_validar_request = api.model(
        "PinValidarRequest",
        {
            "email": fields.String(required=True, description="E-mail convidado"),
            "pin": fields.String(required=True, description="PIN de 8 dígitos"),
        },
    )

    pin_validar_response = api.model(
        "PinValidarResponse",
        {"token": fields.String(description="Token do convite, usado em /aceite/<token>")},
    )

    return {
        "convites_create_request": convites_create_request,
        "convites_create_response": convites_create_response,
        "convite_response": convite_response,
        "convite_list_response": convite_list_response,
        "convite_dados_response": convite_dados_response,
        "convite_aceite_request": convite_aceite_request,
        "pin_solicitar_request": pin_solicitar_request,
        "pin_validar_request": pin_validar_request,
        "pin_validar_response": pin_validar_response,
    }
