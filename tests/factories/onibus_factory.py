import uuid

import factory

from app.models.onibus import Onibus
from tests.factories.organizacao_factory import OrganizacaoFactory


class OnibusFactory(factory.Factory):
    class Meta:
        model = Onibus

    id = factory.LazyFunction(uuid.uuid4)
    organizacao_id = factory.SubFactory(OrganizacaoFactory)
    placa = factory.Faker("license_plate", locale="pt_BR")
    modelo = factory.Faker("name", locale="pt_BR")
    capacidade = factory.Faker("random_int", min=1, max=100)
