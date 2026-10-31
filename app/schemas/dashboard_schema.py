"""RF-21 — validação do período consultado no painel do gestor.

Só o filtro de entrada precisa de schema: os indicadores já saem do serviço
como dicionários de tipos primitivos, prontos para o `jsonify`, e um schema de
dump seria uma segunda cópia do contrato Swagger sem ganho nenhum.
"""

from marshmallow import ValidationError, fields, validates_schema

from app.schemas.common import BaseSchema


class PeriodoRelatorioQuerySchema(BaseSchema):
    """Período de análise. Ambos os limites são inclusivos e comparados como
    data civil — `Viagem.data` é `DATE`, então não há fuso envolvido."""

    inicio = fields.Date(required=True)
    fim = fields.Date(required=True)

    @validates_schema
    def valida_intervalo(self, data, **kwargs):
        if data.get("inicio") and data.get("fim") and data["inicio"] > data["fim"]:
            raise ValidationError("A data inicial não pode ser posterior à final", "inicio")
