import uuid

import factory
from werkzeug.security import generate_password_hash

from app.models.enum import UserRole
from app.models.user import Aluno, Gestor, Motorista


class GestorFactory(factory.Factory):
    class Meta:
        model = Gestor

    id = factory.LazyFunction(uuid.uuid4)
    prefeitura_id = None
    nome = factory.Faker("name", locale="pt_BR")
    email = factory.Sequence(lambda n: f"gestor{n}@buska.test")
    senha_hash = factory.LazyAttribute(
        lambda o: generate_password_hash(getattr(o, "_raw_password", "StrongPass123!"))
    )
    cpf = factory.Faker("cpf", locale="pt_BR")
    telefone = factory.Faker("phone_number", locale="pt_BR")
    role = UserRole.GESTOR

    @classmethod
    def create_with_password(cls, password: str, **kwargs):
        kwargs["_raw_password"] = password
        return cls(**kwargs)


class AlunoFactory(factory.Factory):
    class Meta:
        model = Aluno

    id = factory.LazyFunction(uuid.uuid4)
    prefeitura_id = None
    nome = factory.Faker("name", locale="pt_BR")
    email = factory.Sequence(lambda n: f"aluno{n}@buska.test")
    senha_hash = factory.LazyAttribute(
        lambda o: generate_password_hash(getattr(o, "_raw_password", "StrongPass123!"))
    )
    cpf = factory.Faker("cpf", locale="pt_BR")
    telefone = factory.Faker("phone_number", locale="pt_BR")
    role = UserRole.ALUNO
    matricula = factory.Faker("random_int", min=100000, max=999999)
    instituicao_id = None
    ponto_casa_id = None
    nome_responsavel = factory.Faker("name", locale="pt_BR")
    cpf_responsavel = factory.Faker("cpf", locale="pt_BR")

    @classmethod
    def create_with_password(cls, password: str, **kwargs):
        kwargs["_raw_password"] = password
        return cls(**kwargs)


class MotoristaFactory(factory.Factory):
    class Meta:
        model = Motorista

    id = factory.LazyFunction(uuid.uuid4)
    prefeitura_id = None
    nome = factory.Faker("name", locale="pt_BR")
    email = factory.Sequence(lambda n: f"motorista{n}@buska.test")
    senha_hash = factory.LazyAttribute(
        lambda o: generate_password_hash(getattr(o, "_raw_password", "StrongPass123!"))
    )
    cpf = factory.Faker("cpf", locale="pt_BR")
    telefone = factory.Faker("phone_number", locale="pt_BR")
    role = UserRole.MOTORISTA

    cnh = factory.Faker("random_int", min=10000000000, max=99999999999)
