"""RF-05 — janelas de disponibilidade do veículo.

Namespace registrado vazio de propósito: o registro em `app/__init__.py` é
feito uma vez, antes dos planos rodarem, para que nenhum deles precise editar
o app factory. Os recursos entram aqui.
"""

from flask_restx import Namespace

api = Namespace("janelas", description="Janelas de Disponibilidade do Veículo")
