from marshmallow import fields, validate

from app.schemas.common import BaseSchema

MINUTOS_EM_UM_DIA = 1440


class ParametrosOperacaoRequestSchema(BaseSchema):
    minimo_alunos = fields.Integer(required=True, validate=validate.Range(min=1, max=1000))
    pausa_entre_viagens_minutos = fields.Integer(
        required=True, validate=validate.Range(min=0, max=MINUTOS_EM_UM_DIA)
    )
    antecedencia_motorista_minutos = fields.Integer(
        required=True, validate=validate.Range(min=0, max=MINUTOS_EM_UM_DIA)
    )


class ParametrosOperacaoResponseSchema(BaseSchema):
    organizacao_id = fields.String()
    minimo_alunos = fields.Integer()
    pausa_entre_viagens_minutos = fields.Integer()
    antecedencia_motorista_minutos = fields.Integer()
    updated_at = fields.DateTime(allow_none=True)
