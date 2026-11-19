from typing import Any

from marshmallow import ValidationError, fields, validate, validates_schema

from app.schemas.common import BaseSchema


class ProjetoCreateRequestSchema(BaseSchema):
    nome = fields.String(required=True, validate=validate.Length(min=1, max=100))


class ProjetoUpdateRequestSchema(BaseSchema):
    """Partial update: rename, deactivate (ativo=false) or reactivate."""

    nome = fields.String(validate=validate.Length(min=1, max=100))
    ativo = fields.Boolean(truthy={True}, falsy={False})

    @validates_schema
    def exige_um_campo(self, data: dict[str, Any], **kwargs: Any) -> None:
        if not data:
            raise ValidationError("Informe nome e/ou ativo")


class AlunoProjetoRequestSchema(BaseSchema):
    """projeto_id null removes the aluno from their project."""

    projeto_id = fields.String(required=True, allow_none=True)


class ProjetoResponseSchema(BaseSchema):
    id = fields.UUID()
    nome = fields.String()
    ativo = fields.Boolean()
    created_at = fields.DateTime(dump_default=None)


class ProjetoListResponseSchema(BaseSchema):
    items = fields.List(fields.Nested(ProjetoResponseSchema()), required=True)
    total = fields.Integer(required=True)
