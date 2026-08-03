import uuid

import factory

from app.models.prefeitura import Prefeitura


class PrefeituraFactory(factory.Factory):
    class Meta:
        model = Prefeitura

    id = factory.LazyFunction(uuid.uuid4)
    nome = factory.Sequence(lambda n: f"Prefeitura Teste {n}")
    estado = "PB"
    codigo_ibge = factory.Sequence(lambda n: f"{2500000 + n:07d}")
    ativo = True
