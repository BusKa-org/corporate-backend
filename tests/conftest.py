import os
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from flask_jwt_extended import create_access_token
from sqlalchemy.pool import StaticPool

from app import create_app
from app.models.base import db
from app.models.enum import DiaDaSemana, StatusViagem, UserStatus
from tests.factories.geo_factory import PontoFactory
from tests.factories.onibus_factory import OnibusFactory
from tests.factories.prefeitura_factory import PrefeituraFactory
from tests.factories.rota_factory import (
    DiasOperacaoFactory,
    HorarioRotaFactory,
    RotaAlunoFactory,
    RotaFactory,
    RotaPontoFactory,
)
from tests.factories.user_factory import AlunoFactory, GestorFactory, MotoristaFactory
from tests.factories.viagem_factory import AlunosConfirmadosFactory, ViagemFactory


class AuthenticatedClient:
    def __init__(self, flask_client, default_headers: dict[str, str]):
        self._client = flask_client
        self._default_headers = default_headers

    def _merge(self, headers: dict[str, str] | None):
        merged = dict(self._default_headers)
        if headers:
            merged.update(headers)
        return merged

    def get(self, *a, headers=None, **kw):
        return self._client.get(*a, headers=self._merge(headers), **kw)

    def post(self, *a, headers=None, **kw):
        return self._client.post(*a, headers=self._merge(headers), **kw)

    def put(self, *a, headers=None, **kw):
        return self._client.put(*a, headers=self._merge(headers), **kw)

    def patch(self, *a, headers=None, **kw):
        return self._client.patch(*a, headers=self._merge(headers), **kw)

    def delete(self, *a, headers=None, **kw):
        return self._client.delete(*a, headers=self._merge(headers), **kw)


@dataclass
class Actor:
    user: Any
    headers: dict[str, str]
    client: AuthenticatedClient


# A suíte nunca deve iniciar o scheduler. A variável pode vazar do shell do dev.
os.environ.pop("RUN_SCHEDULER", None)


@pytest.fixture(scope="session")
def app():
    app = create_app()
    app.config.update(
        TESTING=True,
        DEBUG=True,
        JWT_SECRET_KEY="change_this_secret_key_use_long_random_string",
        SQLALCHEMY_DATABASE_URI="sqlite://",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={
            "connect_args": {"check_same_thread": False},
            "poolclass": StaticPool,
        },
    )
    return app


@pytest.fixture()
def _db(app):
    with app.app_context():
        db.create_all()
        yield db
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app, _db):
    return app.test_client()


@pytest.fixture()
def prefeitura(_db):
    p = PrefeituraFactory()
    _db.session.add(p)
    _db.session.commit()
    return p


@pytest.fixture()
def other_prefeitura(_db):
    p = PrefeituraFactory()
    _db.session.add(p)
    _db.session.commit()
    return p


@pytest.fixture()
def gestor(client, app, _db, prefeitura):
    u = GestorFactory(prefeitura_id=prefeitura.id)
    _db.session.add(u)
    _db.session.commit()

    with app.app_context():
        token = create_access_token(identity=str(u.id))

    headers = {"Authorization": f"Bearer {token}"}
    return Actor(user=u, headers=headers, client=AuthenticatedClient(client, headers))


@pytest.fixture()
def other_gestor(client, app, _db, other_prefeitura):
    u = GestorFactory(prefeitura_id=other_prefeitura.id)
    _db.session.add(u)
    _db.session.commit()

    with app.app_context():
        token = create_access_token(identity=str(u.id))

    headers = {"Authorization": f"Bearer {token}"}
    return Actor(user=u, headers=headers, client=AuthenticatedClient(client, headers))


@pytest.fixture()
def aluno(client, app, _db, prefeitura):
    u = AlunoFactory(prefeitura_id=prefeitura.id)
    _db.session.add(u)
    _db.session.commit()

    with app.app_context():
        token = create_access_token(identity=str(u.id))

    headers = {"Authorization": f"Bearer {token}"}
    return Actor(user=u, headers=headers, client=AuthenticatedClient(client, headers))


@pytest.fixture()
def aluno_pending(client, app, _db, prefeitura):
    u = AlunoFactory(prefeitura_id=prefeitura.id)
    u.status = UserStatus.PENDING_SIGNUP
    u.signup_completed_at = None
    _db.session.add(u)
    _db.session.commit()

    with app.app_context():
        token = create_access_token(identity=str(u.id))

    headers = {"Authorization": f"Bearer {token}"}
    return Actor(user=u, headers=headers, client=AuthenticatedClient(client, headers))


@pytest.fixture()
def other_aluno(client, app, _db, other_prefeitura):
    u = AlunoFactory(prefeitura_id=other_prefeitura.id)
    _db.session.add(u)
    _db.session.commit()

    with app.app_context():
        token = create_access_token(identity=str(u.id))

    headers = {"Authorization": f"Bearer {token}"}
    return Actor(user=u, headers=headers, client=AuthenticatedClient(client, headers))


@pytest.fixture()
def ponto(_db, prefeitura):
    p = PontoFactory(prefeitura_id=prefeitura.id)
    _db.session.add(p)
    _db.session.commit()
    return p


@pytest.fixture()
def motorista(client, app, _db, prefeitura):
    m = MotoristaFactory(prefeitura_id=prefeitura.id)
    _db.session.add(m)
    _db.session.commit()

    with app.app_context():
        token = create_access_token(identity=str(m.id))

    headers = {"Authorization": f"Bearer {token}"}
    return Actor(user=m, headers=headers, client=AuthenticatedClient(client, headers))


@pytest.fixture()
def other_motorista(client, app, _db, other_prefeitura):
    m = MotoristaFactory(prefeitura_id=other_prefeitura.id)
    _db.session.add(m)
    _db.session.commit()

    with app.app_context():
        token = create_access_token(identity=str(m.id))

    headers = {"Authorization": f"Bearer {token}"}
    return Actor(user=m, headers=headers, client=AuthenticatedClient(client, headers))


@pytest.fixture()
def onibus(_db, prefeitura):
    o = OnibusFactory(prefeitura_id=prefeitura.id)
    _db.session.add(o)
    _db.session.commit()
    return o


@pytest.fixture()
def rota(_db, prefeitura, motorista, onibus):
    r = RotaFactory(
        prefeitura_id=prefeitura.id,
        motorista_padrao_id=motorista.user.id,
        veiculo_padrao_id=onibus.id,
    )
    _db.session.add(r)
    _db.session.commit()
    return r


@pytest.fixture()
def horario_rota(_db, rota):
    h = HorarioRotaFactory(rota_id=rota.id)
    _db.session.add(h)
    _db.session.commit()
    return h


@pytest.fixture()
def dia_operacao(_db, horario_rota):
    d = DiasOperacaoFactory(horario_rota_id=horario_rota.id, dia=DiaDaSemana.SEG)
    _db.session.add(d)
    _db.session.commit()
    return d


@pytest.fixture()
def dia_operacao_quarta(_db, horario_rota):
    d = DiasOperacaoFactory(horario_rota_id=horario_rota.id, dia=DiaDaSemana.QUA)
    _db.session.add(d)
    _db.session.commit()
    return d


@pytest.fixture()
def rota_ponto(_db, rota, ponto):
    rp = RotaPontoFactory(rota_id=rota.id, ponto_id=ponto.id, ordem=1)
    _db.session.add(rp)
    _db.session.commit()
    return rp


@pytest.fixture()
def rota_aluno(_db, rota, aluno):
    ra = RotaAlunoFactory(rota_id=rota.id, aluno_id=aluno.user.id)
    _db.session.add(ra)
    _db.session.commit()
    return ra


@pytest.fixture()
def viagem_futura_agendada_com_motorista(_db, horario_rota, motorista):
    v = ViagemFactory(
        horario_rota_id=horario_rota.id,
        data=date.today() + timedelta(days=7),
        status=StatusViagem.AGENDADA,
        motorista_id=motorista.user.id,
    )
    _db.session.add(v)
    _db.session.commit()
    return v


@pytest.fixture()
def viagem_futura_iniciada_com_motorista(_db, horario_rota, motorista):
    v = ViagemFactory(
        horario_rota_id=horario_rota.id,
        data=date.today() + timedelta(days=7),
        status=StatusViagem.EM_ANDAMENTO,
        motorista_id=motorista.user.id,
        inicio_real=datetime.now(UTC),
    )
    _db.session.add(v)
    _db.session.commit()
    return v


@pytest.fixture()
def confirmacao_aluno(_db, viagem_futura_agendada_com_motorista, aluno, ponto):
    conf = AlunosConfirmadosFactory(
        viagem_id=viagem_futura_agendada_com_motorista.id,
        aluno_id=aluno.user.id,
        confirmacao=False,
        ponto_embarque_id=None,
        ponto_destino_id=None,
    )
    _db.session.add(conf)
    _db.session.commit()
    return conf
