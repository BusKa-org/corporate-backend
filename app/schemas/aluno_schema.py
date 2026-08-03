from marshmallow import ValidationError, fields, validate, validates_schema

from app.schemas.common import BaseSchema
from app.schemas.endereco_schema import EnderecoInputSchema
from app.schemas.validators import (
    validate_cpf,
    validate_optional_cpf,
    validate_optional_phone,
    validate_optional_string,
)


class AlunoProvisionAccountRequestSchema(BaseSchema):
    """Gestor creates a minimal Aluno account (credentials + identity)."""

    nome = fields.String(required=True, validate=validate.Length(min=1))
    email = fields.Email(required=True, error_messages={"invalid": "Email inválido"})
    password = fields.String(required=True, load_only=True, validate=validate.Length(min=1))
    cpf = fields.String(required=True, validate=validate_cpf)
    telefone = fields.String(load_default=None, allow_none=True, validate=validate_optional_phone)


class AlunoSelfSignupRequestSchema(BaseSchema):
    """Autocadastro do usuário vinculado a uma instituição (RF-02).

    Obrigatórios pelo requisito: nome completo, e-mail institucional,
    instituição de vínculo, senha e confirmação de senha. O CPF continua
    obrigatório porque `usuario.cpf` é NOT NULL/UNIQUE no banco — ver TODO.
    O restante (matrícula, data de nascimento, endereço) é herança do fluxo
    escolar municipal e ficou opcional.
    """

    nome = fields.String(required=True, validate=validate.Length(min=1))
    email = fields.Email(required=True, error_messages={"invalid": "Email inválido"})
    password = fields.String(required=True, load_only=True, validate=validate.Length(min=1))
    password_confirm = fields.String(required=True, load_only=True, validate=validate.Length(min=1))
    cpf = fields.String(required=True, validate=validate_cpf)
    telefone = fields.String(load_default=None, allow_none=True, validate=validate_optional_phone)

    matricula = fields.String(load_default=None, allow_none=True, validate=validate_optional_string)
    instituicao_id = fields.UUID(required=True)

    # Data de nascimento — define se o consentimento do responsável é exigido
    data_nascimento = fields.Date(load_default=None, allow_none=True, format="%Y-%m-%d")

    # Responsável (obrigatório quando menor, opcional para maiores)
    nome_responsavel = fields.String(
        load_default=None, allow_none=True, validate=validate_optional_string
    )
    cpf_responsavel = fields.String(
        load_default=None, allow_none=True, validate=validate_optional_cpf
    )
    email_responsavel = fields.Email(load_default=None, allow_none=True)

    endereco_casa = fields.Nested(EnderecoInputSchema, load_default=None, allow_none=True)

    @validates_schema
    def validar_confirmacao_de_senha(self, data: dict, **kwargs: object) -> None:
        if data.get("password") != data.get("password_confirm"):
            raise ValidationError("As senhas não conferem", field_name="password_confirm")


class AlunoRejeitarRequestSchema(BaseSchema):
    """Gestor rejeita um cadastro pendente, informando o motivo (RF-02)."""

    motivo = fields.String(required=True, validate=validate.Length(min=1))


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


class AlunoGuardianConsentPublicSchema(BaseSchema):
    """Public info returned to the guardian consent screen."""

    nome = fields.String()
    data_nascimento = fields.Date(dump_default=None)
    is_minor = fields.Boolean()
    guardian_consented_at = fields.DateTime(dump_default=None)


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
