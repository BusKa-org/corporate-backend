from marshmallow import fields

from app.models.enum import DiaDaSemana
from app.schemas.common import BaseSchema

# ==========================================
# Input Schemas (Validation)
# ==========================================


class FcmTokenRequestSchema(BaseSchema):
    """Schema for updating the FCM token."""

    fcm_token = fields.String(required=True)


class FcmTokenResponseSchema(BaseSchema):
    """Schema for updating the FCM token response."""

    message = fields.String(required=True)


class UpdateProfileRequestSchema(BaseSchema):
    """Schema for updating user profile (PATCH /users/me)."""

    nome = fields.String(required=False)
    telefone = fields.String(required=False)
    receber_notificacoes = fields.Boolean(required=False)
    cnh = fields.String(required=False)


class JornadaMotoristaSchema(BaseSchema):
    """Working hours fields shared by driver create/update."""

    horario_inicio = fields.Time(allow_none=True)
    horario_fim = fields.Time(allow_none=True)
    dias_trabalho = fields.List(fields.Enum(DiaDaSemana), allow_none=True)


class MotoristaCreateRequestSchema(JornadaMotoristaSchema):
    """Schema for creating a new driver."""

    nome = fields.String(required=True)
    email = fields.Email(required=True)
    password = fields.String(required=True, load_only=True)
    cpf = fields.String(required=True)
    telefone = fields.String(load_default=None)
    cnh = fields.String(required=True)


class MotoristaUpdateRequestSchema(JornadaMotoristaSchema):
    """Schema for a gestor updating a driver (PATCH /users/motoristas/<id>)."""

    nome = fields.String()
    telefone = fields.String()
    cnh = fields.String()


class ExcluirContaRequestSchema(BaseSchema):
    """Schema for deleting the logged-in account."""

    email = fields.String(required=True)
    senha = fields.String(required=True)


class ChangePasswordRequestSchema(BaseSchema):
    """Schema for changing password."""

    current_password = fields.String(required=True)
    new_password = fields.String(required=True)


class ChangePasswordResponseSchema(BaseSchema):
    """Schema for changing password response."""

    message = fields.String()


class UserResponseSchema(BaseSchema):
    """Schema for user response."""

    id = fields.String()
    organizacao_id = fields.String()
    nome = fields.String()
    email = fields.String()
    telefone = fields.String()
    cpf = fields.String()

    role = fields.Method("get_role")
    status = fields.String(attribute="status.value")
    signup_completed_at = fields.DateTime(attribute="signup_completed_at")
    # Municipality info
    municipio_nome = fields.Method("get_municipio_nome")
    municipio_uf = fields.Method("get_municipio_uf")

    # Polymorphic fields (may not exist on all User subtypes)
    matricula = fields.String(dump_default=None)
    nome_pai = fields.String(dump_default=None)
    nome_mae = fields.String(dump_default=None)
    cnh = fields.String(dump_default=None)
    horario_inicio = fields.Time(dump_default=None)
    horario_fim = fields.Time(dump_default=None)
    dias_trabalho = fields.List(fields.String(), dump_default=None)
    status_motorista = fields.Method("get_status_motorista")
    descanso_ate = fields.Method("get_descanso_ate")

    def get_status_motorista(self, obj):
        # Preenchido pelo service (user_service._preencher_status_motoristas)
        status = getattr(obj, "status_motorista", None)
        if status is None:
            return None
        return status.value

    def get_descanso_ate(self, obj):
        # Só mostra enquanto o descanso vale, para nunca exibir um descanso vencido
        if self.get_status_motorista(obj) != "EM_DESCANSO_OBRIGATORIO":
            return None
        return obj.descanso_ate.isoformat()

    def get_role(self, obj):
        return str(obj.role.value) if hasattr(obj.role, "value") else str(obj.role)

    def get_municipio_nome(self, obj):
        if obj.organizacao:
            return obj.organizacao.nome
        return None

    def get_municipio_uf(self, obj):
        if obj.organizacao:
            return obj.organizacao.estado
        return None


class UserListResponseSchema(BaseSchema):
    """Schema for user list response."""

    items = fields.List(fields.Nested(UserResponseSchema()), required=True)
    total = fields.Integer(required=True)
