import secrets
import uuid
from datetime import UTC, datetime, timedelta

import factory

from app.models.credencial_embarque import CredencialEmbarque


class CredencialEmbarqueFactory(factory.Factory):
    class Meta:
        model = CredencialEmbarque

    id = factory.LazyFunction(uuid.uuid4)
    viagem_id = None
    aluno_id = None
    ponto_embarque_id = None
    token = factory.LazyFunction(lambda: secrets.token_urlsafe(32))
    expires_at = factory.LazyFunction(lambda: datetime.now(UTC) + timedelta(hours=4))
    usado = False
