"""RF-15 a RF-18 — credencial de embarque, roteiro do motorista e sincronização.

Namespace registrado vazio de propósito: o registro em `app/__init__.py` é
feito uma vez, antes dos planos rodarem, para que nenhum deles precise editar
o app factory. Os recursos entram aqui.
"""

from flask_restx import Namespace

api = Namespace("embarque", description="Embarque por QR Code e Roteiro do Motorista")
