"""The gestor only points a route at a vehicle of their own organization (closest: RF-06)."""

import pytest

from app.models.rota import Rota
from tests.factories.onibus_factory import OnibusFactory

pytestmark = pytest.mark.integration


@pytest.fixture()
def onibus_de_outra_org(_db, other_organizacao):
    o = OnibusFactory(organizacao_id=other_organizacao.id)
    _db.session.add(o)
    _db.session.commit()
    return o


def test_veiculo_de_outra_organizacao_responde_404(_db, gestor, rota, onibus_de_outra_org):
    r = gestor.client.put(
        f"/v1/rotas/{rota.id}", json={"veiculo_padrao_id": str(onibus_de_outra_org.id)}
    )
    assert r.status_code == 404, r.get_data(as_text=True)

    r = gestor.client.post(
        "/v1/rotas/", json={"nome": "Nova", "veiculo_padrao_id": str(onibus_de_outra_org.id)}
    )
    assert r.status_code == 404, r.get_data(as_text=True)

    _db.session.expire_all()
    assert _db.session.get(Rota, rota.id).veiculo_padrao_id != onibus_de_outra_org.id


def test_veiculo_com_id_invalido_responde_400(gestor, rota):
    r = gestor.client.put(f"/v1/rotas/{rota.id}", json={"veiculo_padrao_id": "nao-e-uuid"})
    assert r.status_code == 400, r.get_data(as_text=True)

    r = gestor.client.post("/v1/rotas/", json={"nome": "Nova", "veiculo_padrao_id": "nao-e-uuid"})
    assert r.status_code == 400, r.get_data(as_text=True)


def test_veiculo_da_propria_organizacao_e_aceito(_db, gestor, rota, organizacao):
    novo = OnibusFactory(organizacao_id=organizacao.id)
    _db.session.add(novo)
    _db.session.commit()

    r = gestor.client.put(f"/v1/rotas/{rota.id}", json={"veiculo_padrao_id": str(novo.id)})
    assert r.status_code == 200, r.get_data(as_text=True)
    _db.session.expire_all()
    assert _db.session.get(Rota, rota.id).veiculo_padrao_id == novo.id

    r = gestor.client.post("/v1/rotas/", json={"nome": "Nova", "veiculo_padrao_id": str(novo.id)})
    assert r.status_code == 201, r.get_data(as_text=True)
