import uuid

import factory

from app.models.organizacao import Organizacao


class OrganizacaoFactory(factory.Factory):
    class Meta:
        model = Organizacao

    id = factory.LazyFunction(uuid.uuid4)
    nome = factory.Sequence(lambda n: f"Organizacao Teste {n}")
    sigla = factory.Sequence(lambda n: f"ORG{n}")
    estado = "PB"
    ativo = True
