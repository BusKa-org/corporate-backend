from marshmallow import fields

from app.schemas.common import BaseSchema


class SolicitacaoViagemResumoSchema(BaseSchema):
    id = fields.UUID()
    status = fields.Function(lambda v: v.status.value if v.status else None)
    rota_id = fields.UUID()
    motorista_id = fields.UUID(allow_none=True)
    buffer_fim = fields.DateTime(allow_none=True)


class SolicitacaoResponseSchema(BaseSchema):
    id = fields.UUID()
    viagem_id = fields.UUID()
    status = fields.Function(lambda s: s.status.value if s.status else None)
    created_at = fields.DateTime()
    viagem = fields.Nested(SolicitacaoViagemResumoSchema)


class PessoaResumoSchema(BaseSchema):
    id = fields.UUID()
    nome = fields.String()


class VeiculoResumoSchema(BaseSchema):
    id = fields.UUID()
    placa = fields.String()
    modelo = fields.String(allow_none=True)


class JanelaHojeSchema(BaseSchema):
    hora_inicio = fields.Time(format="%H:%M")
    hora_fim = fields.Time(format="%H:%M")


class RodadaViagemSchema(BaseSchema):
    id = fields.UUID()
    status = fields.String()
    rota_id = fields.UUID()
    created_at = fields.DateTime(allow_none=True)
    inicio_real = fields.DateTime(allow_none=True)
    buffer_fim = fields.DateTime(allow_none=True)
    segundos_restantes_buffer = fields.Integer(allow_none=True)
    motorista = fields.Nested(PessoaResumoSchema, allow_none=True)
    veiculo = fields.Nested(VeiculoResumoSchema, allow_none=True)


class MinhaSolicitacaoSchema(BaseSchema):
    id = fields.UUID()
    status = fields.Function(lambda s: s.status.value if s.status else None)


class RodadaAtivaResponseSchema(BaseSchema):
    viagem = fields.Nested(RodadaViagemSchema, allow_none=True)
    minha_solicitacao = fields.Nested(MinhaSolicitacaoSchema, allow_none=True)
    janelas_hoje = fields.List(fields.Nested(JanelaHojeSchema))
