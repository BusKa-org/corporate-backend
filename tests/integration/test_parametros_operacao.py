"""On-demand operation parameters per organization and their checks on iniciar-percurso."""

from datetime import timedelta

import pytest

from app.models.enum import StatusMotorista, StatusViagem
from app.models.parametros_operacao import ParametrosOperacao
from app.models.user import Motorista
from app.services.viagens_service import disponibilidade_motorista, status_motorista
from tests.factories.viagem_factory import ViagemFactory

URL = "/v1/parametros-operacao"

VALORES = {
    "minimo_alunos": 3,
    "pausa_entre_viagens_minutos": 15,
    "antecedencia_motorista_minutos": 20,
}


def _salvar(_db, organizacao_id, minimo_alunos=1, pausa=0, antecedencia=0):
    _db.session.add(
        ParametrosOperacao(
            organizacao_id=organizacao_id,
            minimo_alunos=minimo_alunos,
            pausa_entre_viagens_minutos=pausa,
            antecedencia_motorista_minutos=antecedencia,
        )
    )
    _db.session.commit()


def _iniciar(motorista, viagem):
    return motorista.client.post(f"/v1/viagens/{viagem.id}/iniciar-percurso")


def test_sem_registro_retorna_padroes_do_settings(gestor, app):
    resp = gestor.client.get(URL)

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["minimo_alunos"] == app.config["OPERACAO_MINIMO_ALUNOS_PADRAO"]
    assert body["pausa_entre_viagens_minutos"] == (
        app.config["OPERACAO_PAUSA_ENTRE_VIAGENS_MINUTOS_PADRAO"]
    )
    assert body["antecedencia_motorista_minutos"] == (
        app.config["OPERACAO_ANTECEDENCIA_MOTORISTA_MINUTOS_PADRAO"]
    )
    assert body["updated_at"] is None


def test_motorista_le_e_aluno_recebe_403(motorista, aluno):
    assert motorista.client.get(URL).status_code == 200
    assert aluno.client.get(URL).status_code == 403


def test_gestor_salva_e_vale_so_para_a_propria_organizacao(gestor, other_gestor, motorista):
    resp = gestor.client.put(URL, json=VALORES)

    assert resp.status_code == 200
    assert resp.get_json()["updated_at"] is not None
    for campo, valor in VALORES.items():
        assert motorista.client.get(URL).get_json()[campo] == valor
    assert other_gestor.client.get(URL).get_json()["minimo_alunos"] == 1

    resp = gestor.client.put(URL, json={**VALORES, "minimo_alunos": 2})
    assert resp.get_json()["minimo_alunos"] == 2


def test_motorista_nao_altera(motorista):
    assert motorista.client.put(URL, json=VALORES).status_code == 403


@pytest.mark.parametrize(
    "alteracao",
    [
        {"minimo_alunos": 0},
        {"pausa_entre_viagens_minutos": -1},
        {"antecedencia_motorista_minutos": 1441},
        {"minimo_alunos": "muitos"},
        {"pausa_entre_viagens_minutos": None},
    ],
)
def test_valores_invalidos_400(gestor, alteracao):
    assert gestor.client.put(URL, json={**VALORES, **alteracao}).status_code == 400


def test_campo_ausente_400(gestor):
    body = dict(VALORES)
    del body["antecedencia_motorista_minutos"]
    assert gestor.client.put(URL, json=body).status_code == 400


def test_iniciar_percurso_exige_minimo_de_alunos(
    _db, organizacao, motorista, viagem_solicitada, relogio
):
    _salvar(_db, organizacao.id, minimo_alunos=2)

    resp = _iniciar(motorista, viagem_solicitada)

    assert resp.status_code == 409
    assert "pelo menos 2 aluno" in resp.get_json()["error"]["message"]
    _db.session.refresh(viagem_solicitada)
    assert viagem_solicitada.status == StatusViagem.SOLICITADA


def test_pausa_entre_viagens_vira_descanso_do_motorista(
    _db, organizacao, motorista, rota_sob_demanda, viagem_solicitada, relogio
):
    _salvar(_db, organizacao.id, pausa=10)
    anterior = ViagemFactory(
        rota_id=rota_sob_demanda.id,
        data=relogio.agora.date(),
        status=StatusViagem.EM_ANDAMENTO,
        motorista_id=motorista.user.id,
        inicio_real=relogio.agora - timedelta(minutes=30),
    )
    _db.session.add(anterior)
    _db.session.commit()
    resp = motorista.client.put(f"/v1/viagens/{anterior.id}/acao", json={"acao": "FINALIZAR"})
    assert resp.status_code == 200, resp.get_json()

    m = _db.session.get(Motorista, motorista.user.id, populate_existing=True)
    assert m.descanso_ate == relogio.agora + timedelta(minutes=10)
    assert status_motorista(m, relogio.agora) == StatusMotorista.EM_DESCANSO_OBRIGATORIO
    pode, motivo, livre = disponibilidade_motorista(m, relogio.agora)
    assert pode is False
    assert livre == relogio.agora + timedelta(minutes=10)

    resp = _iniciar(motorista, viagem_solicitada)
    assert resp.status_code == 403
    assert "pausa mínima entre viagens" in resp.get_json()["error"]["message"]

    relogio.avancar(minutes=10)
    assert _iniciar(motorista, viagem_solicitada).status_code == 200


def test_motorista_em_outra_viagem_nao_inicia_percurso(_db, motorista, viagem_solicitada, relogio):
    _db.session.add(
        ViagemFactory(
            data=relogio.agora.date(),
            status=StatusViagem.EM_ANDAMENTO,
            motorista_id=motorista.user.id,
            inicio_real=relogio.agora - timedelta(minutes=5),
        )
    )
    _db.session.commit()

    resp = _iniciar(motorista, viagem_solicitada)

    assert resp.status_code == 409
    _db.session.refresh(viagem_solicitada)
    assert viagem_solicitada.status == StatusViagem.SOLICITADA
