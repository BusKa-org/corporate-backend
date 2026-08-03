import uuid

import factory

from app.models.enum import DiaDaSemana, SentidoViagem
from app.models.rota import DiasOperacao, HorarioRota, Rota, RotaAluno, RotaPonto
from tests.factories.onibus_factory import OnibusFactory
from tests.factories.prefeitura_factory import PrefeituraFactory
from tests.factories.user_factory import MotoristaFactory


class RotaFactory(factory.Factory):
    class Meta:
        model = Rota

    id = factory.LazyFunction(uuid.uuid4)
    prefeitura_id = factory.SubFactory(PrefeituraFactory)
    nome = factory.Faker("name", locale="pt_BR")
    motorista_padrao_id = factory.SubFactory(MotoristaFactory)
    veiculo_padrao_id = factory.SubFactory(OnibusFactory)


class RotaPontoFactory(factory.Factory):
    class Meta:
        model = RotaPonto

    rota_id = None
    ponto_id = None
    ordem = factory.Faker("random_int", min=1, max=10)


class DiasOperacaoFactory(factory.Factory):
    class Meta:
        model = DiasOperacao

    id = factory.LazyFunction(uuid.uuid4)
    horario_rota_id = None
    dia = factory.Faker("random_element", elements=DiaDaSemana)


class HorarioRotaFactory(factory.Factory):
    class Meta:
        model = HorarioRota

    id = factory.LazyFunction(uuid.uuid4)
    rota_id = None
    horario_saida = factory.Faker("time", locale="pt_BR")
    sentido = factory.Faker("random_element", elements=list(SentidoViagem))
    dias = factory.RelatedFactoryList(DiasOperacaoFactory, size=3)


class RotaAlunoFactory(factory.Factory):
    class Meta:
        model = RotaAluno

    rota_id = None
    aluno_id = None
