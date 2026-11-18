"""Who may start, finish and cancel a trip (RNF/SEG-02)."""

import uuid

import pytest

from app.models.enum import StatusViagem

INICIAR = {"acao": "INICIAR"}
FINALIZAR = {"acao": "FINALIZAR"}


@pytest.mark.integration
def test_gestor_da_organizacao_inicia_e_finaliza(gestor, viagem_futura_agendada_com_motorista):
    url = f"/v1/viagens/{viagem_futura_agendada_com_motorista.id}/acao"
    r = gestor.client.put(url, json=INICIAR)
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["status"] == "EM_ANDAMENTO"

    r = gestor.client.put(url, json=FINALIZAR)
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["status"] == "FINALIZADA"


@pytest.mark.integration
@pytest.mark.parametrize("corpo", [INICIAR, FINALIZAR])
def test_aluno_nao_controla_viagem(aluno, viagem_futura_iniciada_com_motorista, corpo, _db):
    r = aluno.client.put(f"/v1/viagens/{viagem_futura_iniciada_com_motorista.id}/acao", json=corpo)
    assert r.status_code == 403, r.get_data(as_text=True)
    _db.session.refresh(viagem_futura_iniciada_com_motorista)
    assert viagem_futura_iniciada_com_motorista.status == StatusViagem.EM_ANDAMENTO


@pytest.mark.integration
@pytest.mark.parametrize("ator", ["other_gestor", "other_motorista"])
def test_outra_organizacao_recebe_404_ao_controlar(
    request, ator, viagem_futura_agendada_com_motorista, _db
):
    usuario = request.getfixturevalue(ator)
    r = usuario.client.put(
        f"/v1/viagens/{viagem_futura_agendada_com_motorista.id}/acao", json=INICIAR
    )
    assert r.status_code == 404, r.get_data(as_text=True)
    _db.session.refresh(viagem_futura_agendada_com_motorista)
    assert viagem_futura_agendada_com_motorista.status == StatusViagem.AGENDADA


@pytest.mark.integration
def test_cancelar_viagem_inexistente_e_de_outra_organizacao_respondem_igual(
    gestor, other_gestor, viagem_futura_agendada_com_motorista
):
    inexistente = gestor.client.put(f"/v1/viagens/{uuid.uuid4()}/cancelar")
    alheia = other_gestor.client.put(
        f"/v1/viagens/{viagem_futura_agendada_com_motorista.id}/cancelar"
    )
    assert inexistente.status_code == 404
    assert alheia.status_code == 404
    assert alheia.get_json()["error"]["message"] == inexistente.get_json()["error"]["message"]
