"""RF-05: gestor updates and removes a fixed route's schedule."""

import uuid
from datetime import date, time

import pytest

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
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


def test_ida_e_volta_no_mesmo_dia_sao_permitidas(_db, gestor, rota):
    _horario(_db, rota, [DiaDaSemana.SEG, DiaDaSemana.TER])
    r = gestor.client.post(
        f"/v1/rotas/{rota.id}/horarios",
        json={"horario_saida": "17:00", "sentido": "VOLTA", "dias": ["SEG", "TER"]},
    )
    assert r.status_code == 201, r.get_data(as_text=True)


def test_horario_identico_conflita(_db, gestor, rota):
    _horario(_db, rota, [DiaDaSemana.SEG])
    outro = _horario(_db, rota, [DiaDaSemana.TER], saida=time(7, 0))

    r = gestor.client.post(
        f"/v1/rotas/{rota.id}/horarios",
        json={"horario_saida": "06:00", "sentido": "IDA", "dias": ["SEG", "QUA"]},
    )
    assert r.status_code == 409
    duplicado = {"horario_saida": "06:00", "sentido": "IDA", "dias": ["SEG"]}
    assert gestor.client.put(_url(outro), json=duplicado).status_code == 409
    # Same time, other direction, is a different schedule.
    assert gestor.client.put(_url(outro), json={**duplicado, "sentido": "VOLTA"}).status_code == 200


def test_resalvar_horario_nos_proprios_dias_nao_conflita(_db, gestor, rota):
    seg = _horario(_db, rota, [DiaDaSemana.SEG])
    r = gestor.client.put(
        _url(seg), json={"horario_saida": "06:00", "sentido": "IDA", "dias": ["SEG", "TER"]}
    )
    assert r.status_code == 200, r.get_data(as_text=True)


def _criar_rota(gestor, horarios):
    return gestor.client.post("/v1/rotas/", json={"nome": "Circuito", "horarios": horarios})


def test_criar_rota_aplica_as_regras_de_horario(gestor):
    r = _criar_rota(
        gestor,
        [
            {"horario_saida": "06:00", "sentido": "IDA", "dias": ["SEG", "SEG"]},
            {"horario_saida": "17:00", "sentido": "VOLTA", "dias": ["SEG"]},
        ],
    )
    assert r.status_code == 201, r.get_data(as_text=True)
    horarios = gestor.client.get(f"/v1/rotas/{r.get_json()['id']}/horarios").get_json()["items"]
    assert len(horarios) == 2
    for h in horarios:
        assert h["dias"] == ["SEG"]

    duplicados = [
        {"horario_saida": "06:00", "sentido": "IDA", "dias": ["SEG"]},
        {"horario_saida": "06:00", "sentido": "IDA", "dias": ["SEG", "TER"]},
    ]
    assert _criar_rota(gestor, duplicados).status_code == 409
    invalido = [{"horario_saida": "06:00", "sentido": "IDA", "dias": ["XYZ"]}]
    assert _criar_rota(gestor, invalido).status_code == 400


def _gerar(gestor, rota, data=FUTURO, horario=None):
    entrada = {"rota_id": rota.id, "data": data}
    if horario is not None:
        entrada["horario_rota_id"] = horario.id
    return viagens_service.gerar_viagem(str(gestor.user.id), entrada)


def test_gerar_viagem_com_varios_horarios_no_dia_exige_horario(_db, gestor, rota):
    ida = _horario(_db, rota, [DiaDaSemana.SEG])
    volta = _horario(_db, rota, [DiaDaSemana.SEG], saida=time(17, 0), sentido=SentidoViagem.VOLTA)

    r = gestor.client.post("/v1/viagens/", json={"rota_id": str(rota.id), "data": str(FUTURO)})
    assert r.status_code == 400
    opcoes = r.get_json()["error"]["details"]["horarios"]
    assert [o["id"] for o in opcoes] == [str(ida.id), str(volta.id)]

    r = gestor.client.post(
        "/v1/viagens/",
        json={"rota_id": str(rota.id), "data": str(FUTURO), "horario_rota_id": str(volta.id)},
    )
    assert r.status_code == 201, r.get_data(as_text=True)
    assert r.get_json()["tipo"] == "VOLTA"
    assert _gerar(gestor, rota, horario=ida).horario_rota_id == ida.id


def test_gerar_viagem_valida_o_horario_informado(_db, gestor, rota, organizacao):
    ter = _horario(_db, rota, [DiaDaSemana.TER])
    with pytest.raises(ValidationError):
        _gerar(gestor, rota, horario=ter)

    outra = RotaFactory(
        organizacao_id=organizacao.id, motorista_padrao_id=None, veiculo_padrao_id=None
    )
    _db.session.add(outra)
    _db.session.commit()
    alheio = _horario(_db, outra, [DiaDaSemana.SEG])
    with pytest.raises(NotFoundError):
        _gerar(gestor, rota, horario=alheio)


def test_gerar_viagem_com_horario_versionado_usa_a_versao_ativa(_db, gestor, rota, relogio):
    antigo = _horario(_db, rota, [DiaDaSemana.TER])
    _viagem(_db, antigo, StatusViagem.FINALIZADA)
    r = gestor.client.put(
        _url(antigo), json={"horario_saida": "06:00", "sentido": "IDA", "dias": ["SEG"]}
    )
    novo_id = r.get_json()["id"]

    assert str(_gerar(gestor, rota, horario=antigo).horario_rota_id) == novo_id


def test_viagem_repetida_apos_versionar_horario_conflita(_db, gestor, rota, relogio):
    antigo = _horario(_db, rota, [DiaDaSemana.SEG])
    _viagem(_db, antigo, StatusViagem.FINALIZADA, data=FUTURO)
    r = gestor.client.put(
        _url(antigo), json={"horario_saida": "06:00", "sentido": "IDA", "dias": ["SEG", "TER"]}
    )
    assert r.get_json()["id"] != str(antigo.id)

    with pytest.raises(ConflictError):
        _gerar(gestor, rota)


def test_viagem_em_andamento_de_data_passada_bloqueia(gestor, _db, horario_rota, relogio):
    _viagem(_db, horario_rota, StatusViagem.EM_ANDAMENTO, data=PASSADO)
    assert gestor.client.put(_url(horario_rota), json=NOVO).status_code == 409
    assert gestor.client.delete(_url(horario_rota)).status_code == 409


def test_pontos_com_rota_id_invalido(gestor):
    r = gestor.client.post("/v1/rotas/nao-e-uuid/pontos", json={"pontos": []})
    assert r.status_code == 400
    r = gestor.client.delete(f"/v1/rotas/nao-e-uuid/pontos/{uuid.uuid4()}")
    assert r.status_code == 400


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
