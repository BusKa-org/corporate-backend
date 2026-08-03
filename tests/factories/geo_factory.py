import uuid

import factory

from app.models.geo import Ponto
from tests.factories.prefeitura_factory import PrefeituraFactory


class PontoFactory(factory.Factory):
    class Meta:
        model = Ponto

    id = factory.LazyFunction(uuid.uuid4)
    prefeitura_id = factory.SubFactory(PrefeituraFactory)
    apelido = factory.Faker("name", locale="pt_BR")
    latitude = factory.Faker("latitude")
    longitude = factory.Faker("longitude")
