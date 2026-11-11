"""RF-05: gestor updates and removes a fixed route's schedule."""

from datetime import date, time

import pytest

from app.core.exceptions import NotFoundError
from app.models.enum import DiaDaSemana, SentidoViagem, StatusViagem
from app.models.rota import DiasOperacao, HorarioRota
from app.models.viagem import Viagem
from app.schemas.viagem_schema import ViagemResponseSchema
from app.services import rotas_service, viagens_service
from tests.factories.rota_factory import RotaFactory
from tests.factories.viagem_factory import ViagemFactory

NOVO = {"horario_saida": "07:30", "sentido": "VOLTA", "dias": ["TER", "QUI"]}
# relogio pins "today" to Monday 2026-11-02 (local time).
PASSADO = date(2026, 10, 26)
FUTURO = date(2026, 11, 9)


def _url(horario):
    return f"/v1/rotas/{horario.rota_id}/horarios/{horario.id}"


def _viagem(_db, horario, status, data=PASSADO):
    v = ViagemFactory(horario_rota_id=horario.id, rota_id=horario.rota_id, status=status, data=data)
    _db.session.add(v)
    _db.session.commit()
    return v


def _horario(_db, rota, dias, saida=time(6, 0), sentido=SentidoViagem.IDA):
    h = HorarioRota(rota_id=rota.id, horario_saida=saida, sentido=sentido)
    for dia in dias:
        h.dias.append(DiasOperacao(dia=dia))
    _db.session.add(h)
    _db.session.commit()
    return h


def _listar(ator, rota_id):
    return ator.client.get(f"/v1/rotas/{rota_id}/horarios").get_json()["items"]


def test_alterar_horario_sem_viagens_mantem_o_id(gestor, horario_rota, relogio):
    r = gestor.client.put(_url(horario_rota), json=NOVO)
    assert r.status_code == 200, r.get_data(as_text=True)
    corpo = r.get_json()
    assert corpo["id"] == str(horario_rota.id)
    assert corpo["horario_saida"] == "07:30:00"
    assert corpo["sentido"] == "VOLTA"
    assert sorted(corpo["dias"]) == ["QUI", "TER"]

    itens = _listar(gestor, horario_rota.rota_id)
    assert len(itens) == 1
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


def test_alterar_horario_com_viagem_passada_cria_nova_versao(_db, gestor, rota, relogio):
    antigo = _horario(_db, rota, [DiaDaSemana.SEG])
    passada = _viagem(_db, antigo, StatusViagem.FINALIZADA)

    r = gestor.client.put(_url(antigo), json=NOVO)
    assert r.status_code == 200, r.get_data(as_text=True)
    novo_id = r.get_json()["id"]
    assert novo_id != str(antigo.id)

    _db.session.expire_all()
    viagem = ViagemResponseSchema().dump(_db.session.get(Viagem, passada.id))
    assert viagem["horario_inicio"] == "06:00:00"
    assert viagem["tipo"] == "IDA"
    assert _db.session.get(HorarioRota, antigo.id).ativo is False

    itens = _listar(gestor, rota.id)
    assert [i["id"] for i in itens] == [novo_id]


def test_remover_horario_com_viagem_passada_so_desativa(_db, gestor, rota, relogio):
    horario = _horario(_db, rota, [DiaDaSemana.SEG])
    passada = _viagem(_db, horario, StatusViagem.FINALIZADA)

    r = gestor.client.delete(_url(horario))
    assert r.status_code == 200, r.get_data(as_text=True)

    _db.session.expire_all()
    viagem = _db.session.get(Viagem, passada.id)
    assert viagem.horario_rota_id == horario.id
    assert ViagemResponseSchema().dump(viagem)["horario_inicio"] == "06:00:00"

    assert _listar(gestor, rota.id) == []
    detalhe = gestor.client.get(f"/v1/rotas/{rota.id}").get_json()
    assert detalhe["horarios"] == []

    with pytest.raises(NotFoundError):
        viagens_service.gerar_viagem(str(gestor.user.id), {"rota_id": rota.id, "data": FUTURO})


def test_remover_horario_sem_viagens_apaga(_db, gestor, horario_rota, relogio):
    assert gestor.client.delete(_url(horario_rota)).status_code == 200
    _db.session.expire_all()
    assert _db.session.get(HorarioRota, horario_rota.id) is None


def test_horario_com_viagem_pendente_nao_muda(gestor, _db, horario_rota, relogio):
    _viagem(_db, horario_rota, StatusViagem.AGENDADA, data=FUTURO)

    assert gestor.client.put(_url(horario_rota), json=NOVO).status_code == 409
    assert gestor.client.delete(_url(horario_rota)).status_code == 409
    assert _db.session.get(HorarioRota, horario_rota.id).ativo is True


def test_viagem_agendada_no_passado_nao_bloqueia(gestor, _db, horario_rota, relogio):
    _viagem(_db, horario_rota, StatusViagem.AGENDADA, data=PASSADO)
    assert gestor.client.put(_url(horario_rota), json=NOVO).status_code == 200


def test_dias_repetidos_gravados_uma_vez(gestor, rota):
    r = gestor.client.post(
        f"/v1/rotas/{rota.id}/horarios",
        json={"horario_saida": "06:00", "sentido": "IDA", "dias": ["SEG", "SEG"]},
    )
    assert r.status_code == 201, r.get_data(as_text=True)
    assert r.get_json()["dias"] == ["SEG"]

    url = f"/v1/rotas/{rota.id}/horarios/{r.get_json()['id']}"
    r = gestor.client.put(url, json={**NOVO, "dias": ["TER", "TER"]})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["dias"] == ["TER"]


def test_dois_horarios_ativos_no_mesmo_dia_conflitam(_db, gestor, rota):
    seg = _horario(_db, rota, [DiaDaSemana.SEG])
    ter = _horario(_db, rota, [DiaDaSemana.TER])

    # Trip generation matches by weekday only, so even another direction conflicts.
    r = gestor.client.post(
        f"/v1/rotas/{rota.id}/horarios",
        json={"horario_saida": "18:00", "sentido": "VOLTA", "dias": ["SEG"]},
    )
    assert r.status_code == 409
    assert gestor.client.put(_url(ter), json={**NOVO, "dias": ["SEG"]}).status_code == 409
    # Re-saving a schedule on its own days is not a conflict.
    assert gestor.client.put(_url(seg), json={**NOVO, "dias": ["SEG"]}).status_code == 200


def test_rota_sob_demanda_nao_tem_horario(gestor, horario_rota, rota_sob_demanda):
    url = f"/v1/rotas/{rota_sob_demanda.id}/horarios/{horario_rota.id}"
    assert gestor.client.put(url, json=NOVO).status_code == 400
    assert gestor.client.delete(url).status_code == 400


def test_horario_inativo_nao_encontrado(_db, gestor, rota, relogio):
    horario = _horario(_db, rota, [DiaDaSemana.SEG])
    _viagem(_db, horario, StatusViagem.FINALIZADA)
    assert gestor.client.delete(_url(horario)).status_code == 200

    assert gestor.client.put(_url(horario), json=NOVO).status_code == 404
    assert gestor.client.delete(_url(horario)).status_code == 404


def test_horario_de_outra_rota_nao_encontrado(_db, gestor, organizacao, horario_rota):
    outra = RotaFactory(
        organizacao_id=organizacao.id, motorista_padrao_id=None, veiculo_padrao_id=None
    )
    _db.session.add(outra)
    _db.session.commit()

    url = f"/v1/rotas/{outra.id}/horarios/{horario_rota.id}"
    assert gestor.client.put(url, json=NOVO).status_code == 404
    assert gestor.client.delete(url).status_code == 404


def test_apenas_gestor_da_organizacao_gerencia_horario(motorista, other_gestor, horario_rota):
    for ator in (motorista, other_gestor):
        assert ator.client.put(_url(horario_rota), json=NOVO).status_code == 403
        assert ator.client.delete(_url(horario_rota)).status_code == 403


def test_erro_interno_nao_vaza_detalhes(gestor, rota, monkeypatch):
    def falha(*args, **kwargs):
        raise RuntimeError("detalhe-interno-do-banco")

    monkeypatch.setattr(rotas_service, "_criar_horario", falha)
    r = gestor.client.post(
        f"/v1/rotas/{rota.id}/horarios",
        json={"horario_saida": "06:00", "sentido": "IDA", "dias": ["SEG"]},
    )
    assert r.status_code == 500
    assert "detalhe-interno-do-banco" not in r.get_data(as_text=True)
