"""RF-21: validation of the period queried in the manager dashboard.

Only the input filter needs a schema: the indicators already leave the service
as dicts of primitive types, ready for `jsonify`, and a dump schema would be a
second copy of the Swagger contract.
"""

from marshmallow import ValidationError, fields, validates_schema

from app.schemas.common import BaseSchema


class PeriodoRelatorioQuerySchema(BaseSchema):
    """Analysis period. Both bounds are inclusive and compared as calendar dates;
    `Viagem.data` is a `DATE`, so no time zone is involved.
    """

    inicio = fields.Date(required=True)
    fim = fields.Date(required=True)

    @validates_schema
    def valida_intervalo(self, data, **kwargs):
        if data.get("inicio") and data.get("fim") and data["inicio"] > data["fim"]:
            raise ValidationError("A data inicial não pode ser posterior à final", "inicio")
