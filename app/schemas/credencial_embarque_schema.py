from marshmallow import fields

from app.schemas.common import BaseSchema


class CredencialEmbarqueResponseSchema(BaseSchema):
    token = fields.String()
    ponto_embarque_id = fields.UUID()
    expira_em = fields.DateTime(attribute="expires_at")
    usado = fields.Boolean()
