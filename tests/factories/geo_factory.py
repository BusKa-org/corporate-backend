import uuid

import factory

from app.models.geo import Ponto
from tests.factories.organizacao_factory import OrganizacaoFactory


class PontoFactory(factory.Factory):
    class Meta:
        model = Ponto

    id = factory.LazyFunction(uuid.uuid4)
    organizacao_id = factory.SubFactory(OrganizacaoFactory)
    apelido = factory.Faker("name", locale="pt_BR")
    latitude = factory.Faker("latitude")
    longitude = factory.Faker("longitude")
