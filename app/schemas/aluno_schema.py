from marshmallow import fields

from app.schemas.common import BaseSchema
from app.schemas.endereco_schema import EnderecoInputSchema
from app.schemas.validators import (
    validate_optional_cpf,
    validate_optional_phone,
    validate_optional_string,
)


class AlunoMeUpdateRequestSchema(BaseSchema):
    """Aluno updates their profile (partial update)."""

    nome = fields.String(load_default=None, allow_none=True, validate=validate_optional_string)
    telefone = fields.String(load_default=None, allow_none=True, validate=validate_optional_phone)

    matricula = fields.String(load_default=None, allow_none=True, validate=validate_optional_string)
    nome_responsavel = fields.String(
        load_default=None, allow_none=True, validate=validate_optional_string
    )
    cpf_responsavel = fields.String(
        load_default=None, allow_none=True, validate=validate_optional_cpf
    )

    endereco_casa = fields.Nested(EnderecoInputSchema, load_default=None, allow_none=True)


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

    # Minor / guardian
    data_nascimento = fields.Date(dump_default=None)
    is_minor = fields.Boolean(dump_default=False)
    email_responsavel = fields.Email(dump_default=None)
    nome_responsavel = fields.String(dump_default=None)
    cpf_responsavel = fields.String(dump_default=None)
    guardian_consented_at = fields.DateTime(dump_default=None)


class AlunoListResponseSchema(BaseSchema):
    """Gestor views a list of Alunos (pagination)."""

    items = fields.List(fields.Nested(AlunoResponseSchema()), required=True)
    total = fields.Integer(required=True)
