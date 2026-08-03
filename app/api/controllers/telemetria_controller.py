"""RF-22 — ingestão e consulta de telemetria da bateria.

Namespace registrado vazio de propósito: o registro em `app/__init__.py` é
feito uma vez, antes dos planos rodarem, para que nenhum deles precise editar
o app factory. Os recursos entram aqui.
"""

from flask_restx import Namespace

api = Namespace("telemetria", description="Telemetria do Veículo Elétrico")
