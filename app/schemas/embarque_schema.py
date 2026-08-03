"""RF-15 a RF-18 — validação e serialização do embarque por credencial."""

from marshmallow import fields
from marshmallow.validate import Length, OneOf, Range

from app.schemas.common import BaseSchema
from app.services.embarque_service import TIPOS_EVENTO

# ==========================================
# Input Schemas (Validation)
# ==========================================


class ValidarEmbarqueRequestSchema(BaseSchema):
    """POST /embarque/viagens/<id>/validacao"""

    qr_token = fields.String(required=True, validate=Length(min=1, max=64))
    ocorrido_em = fields.DateTime(load_default=None, allow_none=True)


class EmbarqueManualRequestSchema(BaseSchema):
    """POST /embarque/viagens/<id>/manual"""

    aluno_id = fields.UUID(required=True)
    ocorrido_em = fields.DateTime(load_default=None, allow_none=True)


class AvancarPontoRequestSchema(BaseSchema):
    """POST /embarque/viagens/<id>/roteiro/avancar"""

    ocorrido_em = fields.DateTime(load_default=None, allow_none=True)


class EventoOfflineSchema(BaseSchema):
    """Um evento da fila local do app do motorista (RF-18, §2.3.2)."""

    evento_id = fields.String(required=True, validate=Length(min=1, max=64))
    tipo = fields.String(required=True, validate=OneOf(TIPOS_EVENTO))
    ocorrido_em = fields.DateTime(required=True)
    qr_token = fields.String(load_default=None, allow_none=True)
    aluno_id = fields.UUID(load_default=None, allow_none=True)
    ponto_id = fields.UUID(load_default=None, allow_none=True)
    latitude = fields.Decimal(load_default=None, allow_none=True, validate=Range(-90, 90))
    longitude = fields.Decimal(load_default=None, allow_none=True, validate=Range(-180, 180))


class SincronizacaoRequestSchema(BaseSchema):
    """POST /embarque/viagens/<id>/sincronizacao"""

    eventos = fields.List(
        fields.Nested(EventoOfflineSchema), required=True, validate=Length(min=1, max=500)
    )


# ==========================================
# Response Schemas (Serialization)
# ==========================================


class CredencialResponseSchema(BaseSchema):
    viagem_id = fields.String()
    aluno_id = fields.String()
    qr_token = fields.String()
    ponto_embarque_id = fields.String(allow_none=True)
    ponto_destino_id = fields.String(allow_none=True)
    embarcou = fields.Boolean()
    embarcado_em = fields.DateTime(allow_none=True)


class PassageiroDoPontoSchema(BaseSchema):
    aluno_id = fields.String()
    nome = fields.String(allow_none=True)
    qr_token = fields.String(allow_none=True)
    embarcou = fields.Boolean()
    ponto_destino_id = fields.String(allow_none=True)


class PontoRoteiroSchema(BaseSchema):
    ponto_id = fields.String()
    apelido = fields.String(allow_none=True)
    ordem = fields.Integer()
    visitado = fields.Boolean()
    chegada_real = fields.DateTime(allow_none=True)
    embarcam = fields.Integer()
    desembarcam = fields.Integer()
    instrucao = fields.String()
    passageiros = fields.List(fields.Nested(PassageiroDoPontoSchema))


class RoteiroResponseSchema(BaseSchema):
    viagem_id = fields.String()
    status = fields.String()
    pontos = fields.List(fields.Nested(PontoRoteiroSchema))
    ponto_atual_id = fields.String(allow_none=True)
    instrucao_atual = fields.String(allow_none=True)


class EmbarqueResponseSchema(BaseSchema):
    viagem_id = fields.String()
    aluno_id = fields.String()
    nome = fields.String(allow_none=True)
    ponto_embarque_id = fields.String(allow_none=True)
    embarcado_em = fields.DateTime(allow_none=True)
    manual = fields.Boolean()


class ResultadoEventoSchema(BaseSchema):
    evento_id = fields.String()
    situacao = fields.String()
    codigo = fields.String()
    mensagem = fields.String()


class SincronizacaoResponseSchema(BaseSchema):
    recebidos = fields.Integer()
    aplicados = fields.Integer()
    ja_aplicados = fields.Integer()
    recusados = fields.Integer()
    resultados = fields.List(fields.Nested(ResultadoEventoSchema))
