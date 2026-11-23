"""Antecedência, prazo de cancelamento e no-show. A viagem dos fixtures sai daqui a uns 7 dias
às 8h, então os limites abaixo ficam longe da fronteira e o teste não depende da hora do dia."""

from datetime import time

import pytest

from app.models.enum import SentidoViagem, StatusViagem, TipoMovimentoTicket, TipoPoliticaTicket
from app.models.ticket import MovimentoTicket, PoliticaTicket, SaldoTicket
from app.models.viagem import AlunosConfirmados


@pytest.fixture(autouse=True)
def horario_conhecido(_db, horario_rota):
    horario_rota.sentido = SentidoViagem.IDA
    horario_rota.horario_saida = time(8, 0)
    _db.session.commit()


@pytest.fixture()
def pronto(rota_aluno, dia_operacao, rota_ponto):
    return rota_ponto


def _politica(_db, organizacao, **campos):
    valores = {
        "organizacao_id": organizacao.id,
        "nome": "Regras",
        "tipo": TipoPoliticaTicket.RECARGA,
        "teto": 3,
    }
    valores.update(campos)
    politica = PoliticaTicket(**valores)
    _db.session.add(politica)
    _db.session.commit()
    return politica


def _confirmar(aluno, viagem, rota_ponto, confirmacao=True):
    corpo = {"confirmacao": confirmacao}
    if confirmacao:
        corpo["ponto_embarque_id"] = str(rota_ponto.ponto_id)
    return aluno.client.put(f"/v1/viagens/{viagem.id}/confirmacao", json=corpo)


def _quantidade(_db, aluno, politica):
    _db.session.expire_all()
    return _db.session.get(SaldoTicket, (aluno.user.id, politica.id)).quantidade


# Antecedência


@pytest.mark.parametrize(
    "campos, status",
    [
        ({"antecedencia_min_horas": 24}, 200),
        ({"antecedencia_min_horas": 300}, 409),
        ({"antecedencia_max_dias": 30}, 200),
        ({"antecedencia_max_dias": 3}, 409),
    ],
)
def test_antecedencia(
    _db, organizacao, aluno, pronto, viagem_futura_agendada_com_motorista, campos, status
):
    _politica(_db, organizacao, **campos)

    r = _confirmar(aluno, viagem_futura_agendada_com_motorista, pronto)

    assert r.status_code == status
    if status == 409:
        assert SaldoTicket.query.count() == 0


def test_antecedencia_vale_tambem_para_ilimitado(
    _db, organizacao, aluno, pronto, viagem_futura_agendada_com_motorista
):
    _politica(
        _db, organizacao, tipo=TipoPoliticaTicket.ILIMITADO, teto=None, antecedencia_max_dias=3
    )

    r = _confirmar(aluno, viagem_futura_agendada_com_motorista, pronto)

    assert r.status_code == 409


# Prazo de cancelamento


def test_desmarcar_dentro_do_prazo_devolve(
    _db, organizacao, aluno, pronto, viagem_futura_agendada_com_motorista
):
    politica = _politica(_db, organizacao, cancelamento_prazo_horas=24)
    _confirmar(aluno, viagem_futura_agendada_com_motorista, pronto)

    _confirmar(aluno, viagem_futura_agendada_com_motorista, pronto, confirmacao=False)

    assert _quantidade(_db, aluno, politica) == 3


def test_desmarcar_depois_do_prazo_perde_o_ticket(
    _db, organizacao, aluno, pronto, viagem_futura_agendada_com_motorista
):
    politica = _politica(_db, organizacao, cancelamento_prazo_horas=300)
    _confirmar(aluno, viagem_futura_agendada_com_motorista, pronto)

    r = _confirmar(aluno, viagem_futura_agendada_com_motorista, pronto, confirmacao=False)

    assert r.status_code == 200
    assert _quantidade(_db, aluno, politica) == 2
    assert MovimentoTicket.query.filter_by(tipo=TipoMovimentoTicket.DEVOLUCAO).count() == 0
    registro = _db.session.get(
        AlunosConfirmados, (viagem_futura_agendada_com_motorista.id, aluno.user.id)
    )
    assert registro.politica_ticket_id is None


def test_gestor_cancelando_a_viagem_ignora_o_prazo(
    _db, organizacao, aluno, gestor, pronto, viagem_futura_agendada_com_motorista
):
    politica = _politica(_db, organizacao, cancelamento_prazo_horas=300)
    _confirmar(aluno, viagem_futura_agendada_com_motorista, pronto)

    gestor.client.put(f"/v1/viagens/{viagem_futura_agendada_com_motorista.id}/cancelar")

    assert _quantidade(_db, aluno, politica) == 3


# No-show


def _finalizar(_db, motorista, viagem, embarcou: bool, aluno):
    viagem.status = StatusViagem.EM_ANDAMENTO
    registro = _db.session.get(AlunosConfirmados, (viagem.id, aluno.user.id))
    registro.embarcou = embarcou
    _db.session.commit()
    r = motorista.client.put(f"/v1/viagens/{viagem.id}/acao", json={"acao": "FINALIZAR"})
    assert r.status_code == 200, r.get_data(as_text=True)


def _no_shows(_db):
    _db.session.expire_all()
    return MovimentoTicket.query.filter_by(tipo=TipoMovimentoTicket.NO_SHOW).all()


def test_no_show_paga_a_penalidade(
    _db, organizacao, aluno, motorista, pronto, viagem_futura_agendada_com_motorista
):
    politica = _politica(_db, organizacao, no_show_penalidade=1)
    viagem = viagem_futura_agendada_com_motorista
    _confirmar(aluno, viagem, pronto)

    _finalizar(_db, motorista, viagem, embarcou=False, aluno=aluno)

    assert _quantidade(_db, aluno, politica) == 1  # 3, menos 1 da viagem, menos 1 da penalidade
    assert [m.quantidade for m in _no_shows(_db)] == [1]


def test_no_show_sem_penalidade_so_registra(
    _db, organizacao, aluno, motorista, pronto, viagem_futura_agendada_com_motorista
):
    politica = _politica(_db, organizacao, no_show_penalidade=0, devolve_ao_finalizar=True)
    viagem = viagem_futura_agendada_com_motorista
    _confirmar(aluno, viagem, pronto)

    _finalizar(_db, motorista, viagem, embarcou=False, aluno=aluno)

    assert _quantidade(_db, aluno, politica) == 2  # o ticket gasto não volta
    assert [m.quantidade for m in _no_shows(_db)] == [0]


def test_penalidade_nao_deixa_o_saldo_negativo(
    _db, organizacao, aluno, motorista, pronto, viagem_futura_agendada_com_motorista
):
    politica = _politica(_db, organizacao, teto=1, no_show_penalidade=5)
    viagem = viagem_futura_agendada_com_motorista
    _confirmar(aluno, viagem, pronto)

    _finalizar(_db, motorista, viagem, embarcou=False, aluno=aluno)

    assert _quantidade(_db, aluno, politica) == 0
    assert [m.quantidade for m in _no_shows(_db)] == [0]


def test_quem_embarcou_nao_e_no_show(
    _db, organizacao, aluno, motorista, pronto, viagem_futura_agendada_com_motorista
):
    _politica(_db, organizacao, no_show_penalidade=2)
    viagem = viagem_futura_agendada_com_motorista
    _confirmar(aluno, viagem, pronto)

    _finalizar(_db, motorista, viagem, embarcou=True, aluno=aluno)

    assert _no_shows(_db) == []


def test_no_show_em_politica_ilimitada_so_registra(
    _db, organizacao, aluno, motorista, pronto, viagem_futura_agendada_com_motorista
):
    _politica(_db, organizacao, tipo=TipoPoliticaTicket.ILIMITADO, teto=None, no_show_penalidade=2)
    viagem = viagem_futura_agendada_com_motorista
    _confirmar(aluno, viagem, pronto)

    _finalizar(_db, motorista, viagem, embarcou=False, aluno=aluno)

    assert [m.quantidade for m in _no_shows(_db)] == [0]
