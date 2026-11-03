from marshmallow import fields, validate

from app.models.enum import NecessidadeAcessibilidade
from app.schemas.common import BaseSchema
from app.schemas.endereco_schema import EnderecoInputSchema
from app.schemas.validators import (
    validate_optional_cpf,
    validate_optional_phone,
    validate_optional_string,
)


class AcessibilidadeInputSchema(BaseSchema):
    """Accessibility fields, accepted at sign-up (invite) and when editing the profile."""

    necessidades_acessibilidade = fields.List(
        fields.String(validate=validate.OneOf([n.name for n in NecessidadeAcessibilidade]))
    )
    observacao_acessibilidade = fields.String(allow_none=True, validate=validate.Length(max=500))


class AlunoMeUpdateRequestSchema(AcessibilidadeInputSchema):
    """Aluno updates their profile (partial update).

    An omitted field is left untouched. There is no `load_default`: a None default
    would make the service write None to every field the client did not send.
    """

    # Name and address cannot be cleared. The others accept null to clear the field.
    nome = fields.String(validate=validate_optional_string)
    telefone = fields.String(allow_none=True, validate=validate_optional_phone)

    matricula = fields.String(allow_none=True, validate=validate_optional_string)
    nome_responsavel = fields.String(allow_none=True, validate=validate_optional_string)
    cpf_responsavel = fields.String(allow_none=True, validate=validate_optional_cpf)

    endereco_casa = fields.Nested(EnderecoInputSchema)


class AlunoResponseSchema(BaseSchema):
    id = fields.UUID()
    nome = fields.String()
    email = fields.Email(dump_default=None)
    telefone = fields.String(dump_default=None)
    cpf = fields.String(dump_default=None)
    matricula = fields.String()
    escola = fields.String(attribute="instituicao.nome", dump_default=None)
    instituicao_id = fields.UUID(dump_default=None)

    status = fields.String(attribute="status.value", dump_default=None)
    signup_completed_at = fields.DateTime(dump_default=None)

    data_nascimento = fields.Date(dump_default=None)
    is_minor = fields.Boolean(dump_default=False)
    nome_responsavel = fields.String(dump_default=None)
    cpf_responsavel = fields.String(dump_default=None)

    foto_url = fields.String(dump_default=None)
    necessidades_acessibilidade = fields.List(fields.String())
    observacao_acessibilidade = fields.String(dump_default=None)


class AlunoListResponseSchema(BaseSchema):
    """Gestor views a list of Alunos (pagination)."""

    items = fields.List(fields.Nested(AlunoResponseSchema()), required=True)
    total = fields.Integer(required=True)
