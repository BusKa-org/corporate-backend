from typing import Any

from marshmallow import ValidationError, fields, validate, validates_schema

from app.schemas.common import BaseSchema


class LoginRequestSchema(BaseSchema):
    email = fields.Email(required=True)
    password = fields.String(required=True, load_only=True, validate=validate.Length(min=1))


class ForgotPasswordRequestSchema(BaseSchema):
    email = fields.Email(required=True)


class ResetPasswordRequestSchema(BaseSchema):
    token = fields.String(required=True, validate=validate.Length(min=1))
    new_password = fields.String(required=True, load_only=True, validate=validate.Length(min=1))
    confirm_password = fields.String(required=True, load_only=True, validate=validate.Length(min=1))

    @validates_schema
    def validate_passwords_match(self, data: dict[str, Any], **kwargs: Any) -> None:
        if data["new_password"] != data["confirm_password"]:
            raise ValidationError({"confirm_password": ["As senhas não coincidem"]})


class UserInfoSchema(BaseSchema):
    id = fields.String(required=True)
    nome = fields.String(required=True)
    email = fields.Email(required=True)
    role = fields.String(required=True)


class TokenResponseSchema(BaseSchema):
    message = fields.String(required=True)
    token = fields.String(required=True)
    consentimento_pendente = fields.Boolean(required=True)
    user = fields.Nested(UserInfoSchema(), required=True)
