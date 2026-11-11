from marshmallow import fields, validate

from app.core.config import (
    OPERACAO_MINIMO_ALUNOS_MAX,
    OPERACAO_MINIMO_ALUNOS_MIN,
    OPERACAO_MINUTOS_MAX,
)
from app.schemas.common import BaseSchema


class ParametrosOperacaoRequestSchema(BaseSchema):
    minimo_alunos = fields.Integer(
        required=True,
        validate=validate.Range(min=OPERACAO_MINIMO_ALUNOS_MIN, max=OPERACAO_MINIMO_ALUNOS_MAX),
    )
    pausa_entre_viagens_minutos = fields.Integer(
        required=True, validate=validate.Range(min=0, max=OPERACAO_MINUTOS_MAX)
    )
    antecedencia_motorista_minutos = fields.Integer(
        required=True, validate=validate.Range(min=0, max=OPERACAO_MINUTOS_MAX)
    )


class ParametrosOperacaoResponseSchema(BaseSchema):
    organizacao_id = fields.String()
    minimo_alunos = fields.Integer()
    pausa_entre_viagens_minutos = fields.Integer()
    antecedencia_motorista_minutos = fields.Integer()
    updated_at = fields.DateTime(allow_none=True)
