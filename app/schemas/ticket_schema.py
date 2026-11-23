from marshmallow import fields, validate

from app.schemas.common import BaseSchema

TIPOS = ["RECARGA", "COTA", "ILIMITADO"]
JANELAS = ["DIA", "SEMANA", "MES", "HORAS"]
SENTIDOS = ["IDA", "VOLTA", "CIRCULAR"]


class PoliticaTicketCreateRequestSchema(BaseSchema):
    """O alvo vem de `grupo_id` ou `usuario_id`. Sem nenhum dos dois, vale para a organização."""

    nome = fields.String(required=True, validate=validate.Length(min=1, max=100))
    tipo = fields.String(required=True, validate=validate.OneOf(TIPOS))
    grupo_id = fields.String(load_default=None, allow_none=True)
    usuario_id = fields.String(load_default=None, allow_none=True)

    vigencia_inicio = fields.Date(load_default=None, allow_none=True)
    vigencia_fim = fields.Date(load_default=None, allow_none=True)

    teto = fields.Integer(load_default=None, allow_none=True)
    recarga_quantidade = fields.Integer(load_default=None, allow_none=True)
    recarga_intervalo_minutos = fields.Integer(load_default=None, allow_none=True)
    recarga_dias_semana = fields.List(fields.Integer(), load_default=None, allow_none=True)
    janela = fields.String(load_default=None, allow_none=True, validate=validate.OneOf(JANELAS))
    janela_horas = fields.Integer(load_default=None, allow_none=True)

    devolve_ao_finalizar = fields.Boolean(load_default=False)
    no_show_penalidade = fields.Integer(load_default=0)
    cancelamento_prazo_horas = fields.Integer(load_default=None, allow_none=True)
    antecedencia_min_horas = fields.Integer(load_default=None, allow_none=True)
    antecedencia_max_dias = fields.Integer(load_default=None, allow_none=True)

    rota_id = fields.String(load_default=None, allow_none=True)
    sentido = fields.String(load_default=None, allow_none=True, validate=validate.OneOf(SENTIDOS))
    horario_de = fields.Time(load_default=None, allow_none=True)
    horario_ate = fields.Time(load_default=None, allow_none=True)


class PoliticaTicketUpdateRequestSchema(BaseSchema):
    """Sem load_default: o que não vier no corpo continua como está. O alvo não muda."""

    nome = fields.String(validate=validate.Length(min=1, max=100))
    tipo = fields.String(validate=validate.OneOf(TIPOS))

    vigencia_inicio = fields.Date(allow_none=True)
    vigencia_fim = fields.Date(allow_none=True)

    teto = fields.Integer(allow_none=True)
    recarga_quantidade = fields.Integer(allow_none=True)
    recarga_intervalo_minutos = fields.Integer(allow_none=True)
    recarga_dias_semana = fields.List(fields.Integer(), allow_none=True)
    janela = fields.String(allow_none=True, validate=validate.OneOf(JANELAS))
    janela_horas = fields.Integer(allow_none=True)

    devolve_ao_finalizar = fields.Boolean()
    no_show_penalidade = fields.Integer()
    cancelamento_prazo_horas = fields.Integer(allow_none=True)
    antecedencia_min_horas = fields.Integer(allow_none=True)
    antecedencia_max_dias = fields.Integer(allow_none=True)

    rota_id = fields.String(allow_none=True)
    sentido = fields.String(allow_none=True, validate=validate.OneOf(SENTIDOS))
    horario_de = fields.Time(allow_none=True)
    horario_ate = fields.Time(allow_none=True)


class PoliticaTicketResponseSchema(BaseSchema):
    id = fields.String()
    nome = fields.String()
    tipo = fields.Function(lambda obj: obj.tipo.value)
    alvo = fields.Method("get_alvo")
    grupo_id = fields.String(allow_none=True)
    usuario_id = fields.String(allow_none=True)

    vigencia_inicio = fields.Date(allow_none=True)
    vigencia_fim = fields.Date(allow_none=True)

    teto = fields.Integer(allow_none=True)
    recarga_quantidade = fields.Integer(allow_none=True)
    recarga_intervalo_minutos = fields.Integer(allow_none=True)
    recarga_dias_semana = fields.List(fields.Integer(), allow_none=True)
    janela = fields.Method("get_janela")
    janela_horas = fields.Integer(allow_none=True)

    devolve_ao_finalizar = fields.Boolean()
    no_show_penalidade = fields.Integer()
    cancelamento_prazo_horas = fields.Integer(allow_none=True)
    antecedencia_min_horas = fields.Integer(allow_none=True)
    antecedencia_max_dias = fields.Integer(allow_none=True)

    rota_id = fields.String(allow_none=True)
    sentido = fields.Method("get_sentido")
    horario_de = fields.Time(allow_none=True)
    horario_ate = fields.Time(allow_none=True)
    created_at = fields.DateTime()

    def get_alvo(self, obj):
        if obj.usuario_id is not None:
            return "PESSOA"
        if obj.grupo_id is not None:
            return "GRUPO"
        return "ORGANIZACAO"

    def get_janela(self, obj):
        return obj.janela.value if obj.janela is not None else None

    def get_sentido(self, obj):
        return obj.sentido.value if obj.sentido is not None else None


class SaldoTicketResponseSchema(BaseSchema):
    politica_id = fields.String()
    nome = fields.String()
    tipo = fields.String()
    teto = fields.Integer(allow_none=True)
    quantidade = fields.Integer(allow_none=True)
    bonus = fields.Integer()
    proxima_recarga_em = fields.DateTime(allow_none=True)
    rota_id = fields.String(allow_none=True)
    sentido = fields.String(allow_none=True)
    horario_de = fields.Time(allow_none=True)
    horario_ate = fields.Time(allow_none=True)


class CustoViagemRequestSchema(BaseSchema):
    custo_tickets = fields.Integer(required=True, validate=validate.Range(min=1, max=100))


class ConcessaoRequestSchema(BaseSchema):
    """Soma tickets ao bônus de uma pessoa ou de todos os membros atuais de um grupo."""

    politica_id = fields.String(required=True)
    usuario_id = fields.String(load_default=None, allow_none=True)
    grupo_id = fields.String(load_default=None, allow_none=True)
    quantidade = fields.Integer(required=True, validate=validate.Range(min=1, max=1000))
    motivo = fields.String(load_default=None, allow_none=True, validate=validate.Length(max=255))


class ConcessaoResponseSchema(BaseSchema):
    politica_id = fields.String()
    passageiros = fields.Integer()
    quantidade = fields.Integer()


class MovimentoTicketResponseSchema(BaseSchema):
    id = fields.String()
    usuario_id = fields.String()
    usuario_nome = fields.String()
    politica_id = fields.String()
    politica_nome = fields.String()
    viagem_id = fields.String(allow_none=True)
    tipo = fields.String()
    quantidade = fields.Integer()
    motivo = fields.String(allow_none=True)
    criado_por = fields.String(allow_none=True)
    created_at = fields.DateTime()


class ConsumoQuerySchema(BaseSchema):
    de = fields.Date(load_default=None)
    ate = fields.Date(load_default=None)
    grupo_id = fields.String(load_default=None)
    politica_id = fields.String(load_default=None)


class ConsumoPoliticaResponseSchema(BaseSchema):
    politica_id = fields.String()
    nome = fields.String()
    alvo = fields.String()
    tipo = fields.String()
    gastos = fields.Integer()
    devolvidos = fields.Integer()
    concedidos = fields.Integer()
    no_shows = fields.Integer()
    consumo_liquido = fields.Integer()
    passageiros = fields.Integer()
    viagens = fields.Integer()


class ConsumoPassageiroResponseSchema(BaseSchema):
    usuario_id = fields.String()
    nome = fields.String()
    gastos = fields.Integer()
    devolvidos = fields.Integer()
    concedidos = fields.Integer()
    no_shows = fields.Integer()
    consumo_liquido = fields.Integer()
    viagens = fields.Integer()
