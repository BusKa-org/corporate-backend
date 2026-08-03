from marshmallow import fields

from app.schemas.common import BaseSchema

# ==========================================
# Input Schemas (Validation)
# ==========================================


class ExclusaoContaRequestSchema(BaseSchema):
    """RF-20: confirmação da exclusão com as credenciais do próprio titular."""

    email = fields.Email(required=True)
    password = fields.String(required=True, load_only=True)


# ==========================================
# Output Schemas
# ==========================================


class ConsentimentoStatusResponseSchema(BaseSchema):
    """Situação do titular perante a versão vigente do termo (RF-09)."""

    versao_termo = fields.String()
    aceito = fields.Boolean()
    aceito_em = fields.DateTime(allow_none=True)


class ConsentimentoResponseSchema(BaseSchema):
    """Aceite registrado."""

    id = fields.String()
    versao_termo = fields.String()
    aceito_em = fields.DateTime()


class MessageResponseSchema(BaseSchema):
    message = fields.String()
