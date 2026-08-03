"""RF-09 / RF-20 — consentimento LGPD e exclusão de conta.

Namespace registrado vazio de propósito: o registro em `app/__init__.py` é
feito uma vez, antes dos planos rodarem, para que nenhum deles precise editar
o app factory. Os recursos entram aqui.
"""

from flask_restx import Namespace

api = Namespace("consentimento", description="Consentimento LGPD e Direitos do Titular")
