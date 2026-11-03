from marshmallow import fields

from app.schemas.common import BaseSchema


class CredencialEmbarqueResponseSchema(BaseSchema):
    credencial_id = fields.UUID()
    segredo = fields.String()
    algoritmo = fields.String()
    passo_segundos = fields.Integer()
    digitos = fields.Integer()
    ponto_embarque_id = fields.UUID()
    expira_em = fields.DateTime(attribute="expires_at")
    usado = fields.Boolean()
