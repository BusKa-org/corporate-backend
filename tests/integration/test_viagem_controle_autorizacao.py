"""Who may start, finish and cancel a trip (RNF/SEG-02)."""

import uuid

import pytest

from app.models.enum import StatusViagem, UserStatus
from tests.factories.user_factory import MotoristaFactory

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


@pytest.mark.integration
def test_motorista_da_mesma_organizacao_nao_controla_viagem_de_colega(
    motorista, organizacao, viagem_futura_agendada_com_motorista, _db
):
    colega = MotoristaFactory(organizacao_id=organizacao.id)
    _db.session.add(colega)
    viagem_futura_agendada_com_motorista.motorista_id = colega.id
    _db.session.commit()

    r = motorista.client.put(
        f"/v1/viagens/{viagem_futura_agendada_com_motorista.id}/acao", json=INICIAR
    )
    assert r.status_code == 404, r.get_data(as_text=True)


@pytest.mark.integration
def test_gestor_nao_inicia_viagem_sem_motorista(gestor, viagem_futura_agendada_com_motorista, _db):
    viagem_futura_agendada_com_motorista.motorista_id = None
    _db.session.commit()

    r = gestor.client.put(
        f"/v1/viagens/{viagem_futura_agendada_com_motorista.id}/acao", json=INICIAR
    )
    assert r.status_code == 409, r.get_data(as_text=True)
    _db.session.refresh(viagem_futura_agendada_com_motorista)
    assert viagem_futura_agendada_com_motorista.status == StatusViagem.AGENDADA


@pytest.mark.integration
def test_gestor_nao_inicia_viagem_de_motorista_desativado(
    gestor, motorista, viagem_futura_agendada_com_motorista, _db
):
    motorista.user.status = UserStatus.DISABLED
    _db.session.commit()

    r = gestor.client.put(
        f"/v1/viagens/{viagem_futura_agendada_com_motorista.id}/acao", json=INICIAR
    )
    assert r.status_code == 409, r.get_data(as_text=True)


@pytest.mark.integration
def test_outra_organizacao_recebe_404_ao_finalizar(
    other_gestor, viagem_futura_iniciada_com_motorista, _db
):
    r = other_gestor.client.put(
        f"/v1/viagens/{viagem_futura_iniciada_com_motorista.id}/acao", json=FINALIZAR
    )
    assert r.status_code == 404, r.get_data(as_text=True)
    _db.session.refresh(viagem_futura_iniciada_com_motorista)
    assert viagem_futura_iniciada_com_motorista.status == StatusViagem.EM_ANDAMENTO
