from marshmallow import fields, validate

from app.schemas.common import BaseSchema


class LoginRequestSchema(BaseSchema):
    email = fields.Email(required=True)
    password = fields.String(required=True, load_only=True, validate=validate.Length(min=1))


class UserInfoSchema(BaseSchema):
    id = fields.String(required=True)
    nome = fields.String(required=True)
    email = fields.Email(required=True)
    role = fields.String(required=True)


class TokenResponseSchema(BaseSchema):
    message = fields.String(required=True)
    token = fields.String(required=True)
    user = fields.Nested(UserInfoSchema(), required=True)
