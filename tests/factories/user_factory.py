import uuid

import factory
from werkzeug.security import generate_password_hash

from app.models.enum import UserRole
from app.models.user import Aluno, Gestor, Motorista

SENHA_PADRAO = "StrongPass123!"


class GestorFactory(factory.Factory):
    class Meta:
        model = Gestor

    id = factory.LazyFunction(uuid.uuid4)
    organizacao_id = None
    nome = factory.Faker("name", locale="pt_BR")
    email = factory.Sequence(lambda n: f"gestor{n}@buska.test")
    senha_hash = factory.LazyAttribute(lambda o: generate_password_hash(o.raw_password))
    cpf = factory.Faker("cpf", locale="pt_BR")
    telefone = factory.Faker("phone_number", locale="pt_BR")
    role = UserRole.GESTOR

    class Params:
        # Params fica fora dos kwargs do modelo. A versão anterior passava
        # `_raw_password` direto para o construtor e estourava TypeError —
        # não aparecia porque nada chamava `create_with_password`.
        raw_password = SENHA_PADRAO

    @classmethod
    def create_with_password(cls, password: str, **kwargs):
        """Cria o usuário com uma senha conhecida, para testes que fazem login."""
        return cls(raw_password=password, **kwargs)


class AlunoFactory(factory.Factory):
    class Meta:
        model = Aluno

    id = factory.LazyFunction(uuid.uuid4)
    organizacao_id = None
    nome = factory.Faker("name", locale="pt_BR")
    email = factory.Sequence(lambda n: f"aluno{n}@buska.test")
    senha_hash = factory.LazyAttribute(lambda o: generate_password_hash(o.raw_password))
    cpf = factory.Faker("cpf", locale="pt_BR")
    telefone = factory.Faker("phone_number", locale="pt_BR")
    role = UserRole.ALUNO
    matricula = factory.Faker("random_int", min=100000, max=999999)
    instituicao_id = None
    ponto_casa_id = None
    nome_responsavel = factory.Faker("name", locale="pt_BR")
    cpf_responsavel = factory.Faker("cpf", locale="pt_BR")

    class Params:
        # Params fica fora dos kwargs do modelo. A versão anterior passava
        # `_raw_password` direto para o construtor e estourava TypeError —
        # não aparecia porque nada chamava `create_with_password`.
        raw_password = SENHA_PADRAO

    @classmethod
    def create_with_password(cls, password: str, **kwargs):
        """Cria o usuário com uma senha conhecida, para testes que fazem login."""
        return cls(raw_password=password, **kwargs)


class MotoristaFactory(factory.Factory):
    class Meta:
        model = Motorista

    id = factory.LazyFunction(uuid.uuid4)
    organizacao_id = None
    nome = factory.Faker("name", locale="pt_BR")
    email = factory.Sequence(lambda n: f"motorista{n}@buska.test")
    senha_hash = factory.LazyAttribute(lambda o: generate_password_hash(o.raw_password))
    cpf = factory.Faker("cpf", locale="pt_BR")
    telefone = factory.Faker("phone_number", locale="pt_BR")
    role = UserRole.MOTORISTA

    cnh = factory.Faker("random_int", min=10000000000, max=99999999999)

    class Params:
        raw_password = SENHA_PADRAO

    @classmethod
    def create_with_password(cls, password: str, **kwargs):
        """Cria o motorista com uma senha conhecida, para testes que fazem login."""
        return cls(raw_password=password, **kwargs)
