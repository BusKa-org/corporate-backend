from datetime import UTC, datetime

from marshmallow import fields, validate

from app.schemas.common import BaseSchema


class ConvitesCreateRequestSchema(BaseSchema):
    """Lote de convites. Cada item é validado linha a linha pelo serviço."""

    convites = fields.List(fields.Dict(), required=True, validate=validate.Length(min=1, max=500))


class ConviteListQuerySchema(BaseSchema):
    estado = fields.String(load_default=None, allow_none=True)


class ConviteAceiteRequestSchema(BaseSchema):
    """Dados da pessoa ao concluir. Nome, CPF e instituição podem vir do convite."""

    nome = fields.String(load_default=None, allow_none=True)
    cpf = fields.String(load_default=None, allow_none=True)
    telefone = fields.String(load_default=None, allow_none=True)
    instituicao_id = fields.String(load_default=None, allow_none=True)
    senha = fields.String(required=True, load_only=True)


class PinSolicitarRequestSchema(BaseSchema):
    email = fields.String(required=True)


class PinValidarRequestSchema(BaseSchema):
    email = fields.String(required=True)
    pin = fields.String(required=True, load_only=True)


class ConviteResponseSchema(BaseSchema):
    id = fields.String()
    email = fields.String()
    nome = fields.String(allow_none=True)
    cpf = fields.String(allow_none=True)
    telefone = fields.String(allow_none=True)
    instituicao_id = fields.String(allow_none=True)
    estado = fields.String()
    envio_estado = fields.String()
    expira_em = fields.DateTime()
    vencido = fields.Method("get_vencido")
    created_at = fields.DateTime()
    concluido_em = fields.DateTime(allow_none=True)

    def get_vencido(self, convite):
        return convite.estado == "PENDENTE" and convite.expira_em <= datetime.now(UTC)
