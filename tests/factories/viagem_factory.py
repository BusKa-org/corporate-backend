import uuid

import factory

from app.models.enum import StatusViagem
from app.models.viagem import AlunosConfirmados, Viagem, ViagemPonto


class ViagemFactory(factory.Factory):
    class Meta:
        model = Viagem

    id = factory.LazyFunction(uuid.uuid4)
    data = factory.Faker("date", locale="pt_BR")
    horario_rota_id = None
    motorista_id = None
    veiculo_id = None
    status = factory.Faker("random_element", elements=StatusViagem)


class ViagemPontoFactory(factory.Factory):
    class Meta:
        model = ViagemPonto

    viagem_id = None
    ponto_id = None
    ordem = factory.Faker("random_int", min=1, max=10)
    visitado = factory.Faker("boolean")


class AlunosConfirmadosFactory(factory.Factory):
    class Meta:
        model = AlunosConfirmados

    viagem_id = None
    aluno_id = None
    confirmacao = factory.Faker("boolean")
    ponto_embarque_id = None
    ponto_destino_id = None
