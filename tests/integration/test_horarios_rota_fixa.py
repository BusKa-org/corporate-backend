"""RF-05: gestor updates and removes a fixed route's schedule."""

from app.models.enum import StatusViagem
from app.models.rota import HorarioRota
from app.models.viagem import Viagem
from tests.factories.viagem_factory import ViagemFactory

NOVO = {"horario_saida": "07:30", "sentido": "VOLTA", "dias": ["TER", "QUI"]}


def _url(horario):
    return f"/v1/rotas/{horario.rota_id}/horarios/{horario.id}"


def _viagem(_db, horario, status):
    v = ViagemFactory(horario_rota_id=horario.id, status=status)
    _db.session.add(v)
    _db.session.commit()
    return v


def test_gestor_altera_horario(gestor, horario_rota):
    r = gestor.client.put(_url(horario_rota), json=NOVO)
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["horario_saida"] == "07:30:00"
    assert r.get_json()["sentido"] == "VOLTA"
    assert sorted(r.get_json()["dias"]) == ["QUI", "TER"]

    itens = gestor.client.get(f"/v1/rotas/{horario_rota.rota_id}/horarios").get_json()["items"]
    assert sorted(itens[0]["dias"]) == ["QUI", "TER"]


def test_alterar_horario_valida_como_a_criacao(gestor, horario_rota):
    invalidos = (
        {**NOVO, "dias": []},
        {**NOVO, "sentido": "LADO"},
        {**NOVO, "dias": ["XYZ"]},
        {"sentido": "IDA", "dias": ["SEG"]},
    )
    for payload in invalidos:
        r = gestor.client.put(_url(horario_rota), json=payload)
        assert r.status_code == 400, payload


def test_gestor_remove_horario_mantendo_historico(gestor, _db, horario_rota):
    passada = _viagem(_db, horario_rota, StatusViagem.FINALIZADA)
    rota_id = horario_rota.rota_id

    r = gestor.client.delete(_url(horario_rota))
    assert r.status_code == 200, r.get_data(as_text=True)

    _db.session.expire_all()
    assert _db.session.get(HorarioRota, horario_rota.id) is None
    viagem = _db.session.get(Viagem, passada.id)
    assert viagem.horario_rota_id is None
    assert viagem.rota_id == rota_id


def test_horario_com_viagem_pendente_nao_muda(gestor, _db, horario_rota):
    _viagem(_db, horario_rota, StatusViagem.AGENDADA)

    assert gestor.client.put(_url(horario_rota), json=NOVO).status_code == 409
    assert gestor.client.delete(_url(horario_rota)).status_code == 409
    assert _db.session.get(HorarioRota, horario_rota.id) is not None


def test_apenas_gestor_da_organizacao_gerencia_horario(motorista, other_gestor, horario_rota):
    for ator in (motorista, other_gestor):
        assert ator.client.put(_url(horario_rota), json=NOVO).status_code == 403
        assert ator.client.delete(_url(horario_rota)).status_code == 403


def test_horario_de_outra_rota_nao_encontrado(gestor, horario_rota, rota_sob_demanda):
    url = f"/v1/rotas/{rota_sob_demanda.id}/horarios/{horario_rota.id}"
    assert gestor.client.put(url, json=NOVO).status_code == 404
    assert gestor.client.delete(url).status_code == 404
