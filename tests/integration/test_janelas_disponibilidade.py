import pytest

from app.models.enum import UserStatus
from app.models.onibus import JanelaDisponibilidade
from tests.factories.onibus_factory import OnibusFactory
from tests.factories.user_factory import MotoristaFactory


def _payload(motorista_id, dia="SEG", inicio="08:00", fim="12:00"):
    return {"motorista_id": str(motorista_id), "dia": dia, "hora_inicio": inicio, "hora_fim": fim}


def _url(onibus_id):
    return f"/v1/onibus/{onibus_id}/janelas"


@pytest.fixture()
def outro_onibus(_db, organizacao):
    o = OnibusFactory(organizacao_id=organizacao.id)
    _db.session.add(o)
    _db.session.commit()
    return o


@pytest.fixture()
def outro_motorista(_db, organizacao):
    m = MotoristaFactory(organizacao_id=organizacao.id)
    _db.session.add(m)
    _db.session.commit()
    return m


def test_cria_janela(gestor, onibus, motorista):
    r = gestor.client.post(_url(onibus.id), json=_payload(motorista.user.id))
    assert r.status_code == 201, r.get_data(as_text=True)
    body = r.get_json()
    assert body["onibus_id"] == str(onibus.id)
    assert body["motorista_id"] == str(motorista.user.id)
    assert body["motorista_nome"] == motorista.user.nome
    assert (body["dia"], body["hora_inicio"], body["hora_fim"]) == ("SEG", "08:00", "12:00")
    assert body["created_at"]


@pytest.mark.parametrize("inicio,fim", [("10:00", "10:00"), ("10:00", "09:00")])
def test_fim_nao_posterior_ao_inicio_e_rejeitado(gestor, onibus, motorista, inicio, fim):
    r = gestor.client.post(
        _url(onibus.id), json=_payload(motorista.user.id, inicio=inicio, fim=fim)
    )
    assert r.status_code == 400
    assert "posterior" in r.get_json()["error"]["message"]


def test_sobreposicao_no_mesmo_veiculo_e_dia(gestor, onibus, janela, outro_motorista):
    r = gestor.client.post(
        _url(onibus.id), json=_payload(outro_motorista.id, inicio="11:00", fim="13:00")
    )
    assert r.status_code == 409


def test_mesmo_horario_em_outro_dia_e_permitido(gestor, onibus, motorista, janela):
    r = gestor.client.post(_url(onibus.id), json=_payload(motorista.user.id, dia="TER"))
    assert r.status_code == 201, r.get_data(as_text=True)


def test_janelas_encostadas_sao_permitidas(gestor, onibus, motorista, janela):
    r = gestor.client.post(
        _url(onibus.id), json=_payload(motorista.user.id, inicio="12:00", fim="14:00")
    )
    assert r.status_code == 201, r.get_data(as_text=True)


def test_motorista_sobreposto_em_dois_veiculos(gestor, outro_onibus, motorista, janela):
    r = gestor.client.post(
        _url(outro_onibus.id), json=_payload(motorista.user.id, inicio="09:00", fim="10:00")
    )
    assert r.status_code == 409


def test_motorista_inativo_e_rejeitado(gestor, onibus, _db, organizacao):
    m = MotoristaFactory(organizacao_id=organizacao.id, status=UserStatus.DISABLED)
    _db.session.add(m)
    _db.session.commit()
    r = gestor.client.post(_url(onibus.id), json=_payload(m.id))
    assert r.status_code == 400
    assert r.get_json()["error"]["message"] == "Motorista sem cadastro ativo"


def test_motorista_inexistente(gestor, onibus):
    r = gestor.client.post(_url(onibus.id), json=_payload("00000000-0000-0000-0000-000000000000"))
    assert r.status_code == 404


def test_motorista_de_outra_organizacao_e_rejeitado(gestor, onibus, other_motorista):
    r = gestor.client.post(_url(onibus.id), json=_payload(other_motorista.user.id))
    assert r.status_code == 400


def test_veiculo_de_outra_organizacao(other_gestor, onibus, other_motorista):
    r = other_gestor.client.post(_url(onibus.id), json=_payload(other_motorista.user.id))
    assert r.status_code == 403


def test_veiculo_inexistente(gestor, motorista):
    r = gestor.client.post(
        _url("00000000-0000-0000-0000-000000000000"), json=_payload(motorista.user.id)
    )
    assert r.status_code == 404


@pytest.mark.parametrize("ator", ["aluno", "motorista"])
def test_nao_gestor_nao_cria(request, ator, onibus, motorista):
    actor = request.getfixturevalue(ator)
    r = actor.client.post(_url(onibus.id), json=_payload(motorista.user.id))
    assert r.status_code == 403


def test_lista_ordenada_por_dia_e_hora(gestor, aluno, onibus, motorista):
    criadas = [("DOM", "08:00", "09:00"), ("SEG", "14:00", "15:00"), ("QUA", "08:00", "09:00")]
    criadas.append(("SEG", "08:00", "09:00"))
    for dia, inicio, fim in criadas:
        r = gestor.client.post(
            _url(onibus.id), json=_payload(motorista.user.id, dia=dia, inicio=inicio, fim=fim)
        )
        assert r.status_code == 201, r.get_data(as_text=True)

    r = aluno.client.get(_url(onibus.id))
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["total"] == 4
    ordem = [(item["dia"], item["hora_inicio"]) for item in body["items"]]
    assert ordem == [("SEG", "08:00"), ("SEG", "14:00"), ("QUA", "08:00"), ("DOM", "08:00")]


def test_lista_de_outra_organizacao_e_proibida(other_gestor, onibus, janela):
    r = other_gestor.client.get(_url(onibus.id))
    assert r.status_code == 403


def test_remove_janela(gestor, onibus, janela, _db):
    r = gestor.client.delete(f"{_url(onibus.id)}/{janela.id}")
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["message"]
    _db.session.expire_all()
    assert _db.session.get(JanelaDisponibilidade, janela.id) is None


def test_remove_janela_de_outro_veiculo_e_404(gestor, outro_onibus, janela):
    r = gestor.client.delete(f"{_url(outro_onibus.id)}/{janela.id}")
    assert r.status_code == 404


@pytest.mark.parametrize("ator", ["aluno", "motorista"])
def test_nao_gestor_nao_remove(request, ator, onibus, janela):
    actor = request.getfixturevalue(ator)
    r = actor.client.delete(f"{_url(onibus.id)}/{janela.id}")
    assert r.status_code == 403
