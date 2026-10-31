import uuid
from datetime import time

import factory

from app.models.enum import DiaDaSemana
from app.models.onibus import JanelaDisponibilidade, Onibus
from tests.factories.organizacao_factory import OrganizacaoFactory


class OnibusFactory(factory.Factory):
    class Meta:
        model = Onibus

    id = factory.LazyFunction(uuid.uuid4)
    organizacao_id = factory.SubFactory(OrganizacaoFactory)
    placa = factory.Faker("license_plate", locale="pt_BR")
    modelo = factory.Faker("name", locale="pt_BR")
    capacidade = factory.Faker("random_int", min=1, max=100)


class JanelaDisponibilidadeFactory(factory.Factory):
    class Meta:
        model = JanelaDisponibilidade

    id = factory.LazyFunction(uuid.uuid4)
    onibus_id = None
    motorista_id = None
    dia = DiaDaSemana.SEG
    hora_inicio = time(8, 0)
    hora_fim = time(12, 0)
