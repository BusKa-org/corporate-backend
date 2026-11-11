from typing import Any

from marshmallow import fields, post_load, validate

from app.models.enum import SentidoViagem
from app.schemas.common import BaseSchema


class HorarioCreateRequestSchema(BaseSchema):
    horario_saida = fields.Time(required=True, metadata={"description": "Horário de saída (HH:MM)"})
    sentido = fields.String(
        required=True,
        validate=validate.OneOf(["IDA", "VOLTA", "CIRCULAR"]),
        metadata={"description": "Sentido da viagem"},
    )
    dias = fields.List(
        fields.String(validate=validate.OneOf(["SEG", "TER", "QUA", "QUI", "SEX", "SAB", "DOM"])),
        required=True,
        metadata={"description": "Lista de dias da semana"},
    )

    @post_load
    def remover_dias_repetidos(self, data: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        dias_unicos: list[str] = []
        for dia in data["dias"]:
            if dia not in dias_unicos:
                dias_unicos.append(dia)
        data["dias"] = dias_unicos
        return data


class HorarioResponseSchema(BaseSchema):
    id = fields.String()
    horario_saida = fields.Time()
    sentido = fields.Enum(SentidoViagem)
    dias = fields.Method("get_dias")

    def get_dias(self, obj):
        return [d.dia.value if hasattr(d.dia, "value") else d.dia for d in obj.dias]


class HorarioListResponseSchema(BaseSchema):
    items = fields.List(fields.Nested(HorarioResponseSchema), required=True)
    total = fields.Integer(required=True)
