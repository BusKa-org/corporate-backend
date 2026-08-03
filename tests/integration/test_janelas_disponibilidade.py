"""RF-05 — janelas de disponibilidade do veículo."""

from datetime import date, datetime, time, timedelta

import pytest

from app.models.enum import DiaDaSemana, UserStatus
from app.models.janela import JanelaDisponibilidade
from app.services import janela_service


def _payload(circuito, motorista, **overrides):
    dados = {
        "rota_id": str(circuito.id),
        "motorista_id": str(motorista.user.id),
        "dia": "SEG",
        "hora_inicio": "07:00",
        "hora_fim": "12:00",
        "buffer_minutos": 5,
    }
    dados.update(overrides)
    return dados


@pytest.mark.integration
def test_criar_janela_requer_autenticacao(client, circuito, motorista):
    r = client.post("/v1/janelas/", json=_payload(circuito, motorista))
    assert r.status_code in (401, 422)


@pytest.mark.integration
def test_aluno_nao_gerencia_janelas(aluno, circuito, motorista):
    r = aluno.client.post("/v1/janelas/", json=_payload(circuito, motorista))
    assert r.status_code == 403


@pytest.mark.integration
def test_gestor_cria_e_lista_janela(gestor, circuito, motorista, _db):
    r = gestor.client.post("/v1/janelas/", json=_payload(circuito, motorista))
    assert r.status_code == 201, r.get_data(as_text=True)

    body = r.get_json() or {}
    assert body["dia"] == "SEG"
    assert body["buffer_minutos"] == 5
    assert body["motorista_nome"] == motorista.user.nome

    listagem = gestor.client.get("/v1/janelas/").get_json() or {}
    assert listagem["total"] == 1


@pytest.mark.integration
def test_janela_sobreposta_no_mesmo_dia_e_recusada(gestor, circuito, motorista):
    assert gestor.client.post("/v1/janelas/", json=_payload(circuito, motorista)).status_code == 201

    conflito = gestor.client.post(
        "/v1/janelas/",
        json=_payload(circuito, motorista, hora_inicio="11:00", hora_fim="15:00"),
    )
    assert conflito.status_code == 409, conflito.get_data(as_text=True)


@pytest.mark.integration
def test_janela_encostada_na_anterior_e_aceita(gestor, circuito, motorista):
    """Fim às 12:00 e início às 12:00 não é sobreposição."""
    assert gestor.client.post("/v1/janelas/", json=_payload(circuito, motorista)).status_code == 201

    seguinte = gestor.client.post(
        "/v1/janelas/",
        json=_payload(circuito, motorista, hora_inicio="12:00", hora_fim="18:00"),
    )
    assert seguinte.status_code == 201, seguinte.get_data(as_text=True)


@pytest.mark.integration
def test_janela_em_outro_dia_nao_conflita(gestor, circuito, motorista):
    assert gestor.client.post("/v1/janelas/", json=_payload(circuito, motorista)).status_code == 201
    outra = gestor.client.post("/v1/janelas/", json=_payload(circuito, motorista, dia="TER"))
    assert outra.status_code == 201


@pytest.mark.integration
def test_janela_com_motorista_inativo_e_recusada(gestor, circuito, motorista, _db):
    motorista.user.status = UserStatus.DISABLED
    _db.session.commit()

    r = gestor.client.post("/v1/janelas/", json=_payload(circuito, motorista))
    assert r.status_code == 400
    assert "ativo" in (r.get_json() or {})["error"]["message"]


@pytest.mark.integration
def test_janela_com_motorista_de_outra_organizacao_e_recusada(gestor, circuito, other_motorista):
    r = gestor.client.post("/v1/janelas/", json=_payload(circuito, other_motorista))
    assert r.status_code == 404


@pytest.mark.integration
def test_hora_fim_precisa_ser_maior_que_inicio(gestor, circuito, motorista):
    r = gestor.client.post(
        "/v1/janelas/",
        json=_payload(circuito, motorista, hora_inicio="12:00", hora_fim="08:00"),
    )
    assert r.status_code == 400


@pytest.mark.integration
def test_gestor_atualiza_e_remove_janela(gestor, circuito, motorista, _db):
    criada = gestor.client.post("/v1/janelas/", json=_payload(circuito, motorista)).get_json()

    atualizada = gestor.client.patch(
        f"/v1/janelas/{criada['id']}", json={"buffer_minutos": 9, "ativo": False}
    )
    assert atualizada.status_code == 200
    assert (atualizada.get_json() or {})["buffer_minutos"] == 9

    removida = gestor.client.delete(f"/v1/janelas/{criada['id']}")
    assert removida.status_code == 200
    assert _db.session.get(JanelaDisponibilidade, criada["id"]) is None


@pytest.mark.integration
def test_gestor_de_outra_organizacao_nao_enxerga_a_janela(
    gestor, other_gestor, circuito, motorista
):
    criada = gestor.client.post("/v1/janelas/", json=_payload(circuito, motorista)).get_json()

    assert (other_gestor.client.get("/v1/janelas/").get_json() or {})["total"] == 0
    assert other_gestor.client.delete(f"/v1/janelas/{criada['id']}").status_code == 404


@pytest.mark.integration
def test_aluno_ve_a_janela_vigente(aluno, janela_hoje):
    r = aluno.client.get("/v1/janelas/vigente")
    assert r.status_code == 200, r.get_data(as_text=True)

    body = r.get_json() or {}
    assert body["em_operacao"] is True
    assert body["janela"]["id"] == str(janela_hoje.id)
    assert len(body["horarios_hoje"]) == 1


@pytest.mark.integration
def test_aluno_fora_da_janela_recebe_os_horarios_do_dia(aluno, janela_hoje, _db):
    """Fora do horário a resposta ainda informa quando o veículo opera."""
    agora = janela_service.agora_local()
    janela_hoje.hora_inicio = time(0, 0)
    janela_hoje.hora_fim = time(0, 1)
    if agora.time() <= time(0, 1):
        janela_hoje.hora_inicio = time(23, 58)
        janela_hoje.hora_fim = time(23, 59)
    _db.session.commit()

    body = aluno.client.get("/v1/janelas/vigente").get_json() or {}
    assert body["em_operacao"] is False
    assert body["janela"] is None
    assert len(body["horarios_hoje"]) == 1


@pytest.mark.integration
def test_janela_vigente_ignora_janela_desativada(_db, organizacao, janela_hoje):
    assert janela_service.janela_vigente(organizacao.id) is not None

    janela_hoje.ativo = False
    _db.session.commit()

    assert janela_service.janela_vigente(organizacao.id) is None


@pytest.mark.integration
def test_dia_da_semana_acompanha_o_weekday():
    # 2026-08-03 é uma segunda-feira.
    segunda = date(2026, 8, 3)
    assert janela_service.dia_da_semana(segunda) == DiaDaSemana.SEG
    assert janela_service.dia_da_semana(segunda + timedelta(days=6)) == DiaDaSemana.DOM


@pytest.mark.integration
def test_janela_de_outro_dia_nao_esta_vigente(_db, organizacao, janela_hoje):
    janela_hoje.dia = janela_service.dia_da_semana(datetime.now().date() + timedelta(days=1))
    _db.session.commit()

    assert janela_service.janela_vigente(organizacao.id) is None
