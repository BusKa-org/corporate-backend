from datetime import date, time, timedelta

import pytest

from app.models.enum import SentidoViagem, StatusViagem, TipoMovimentoTicket, TipoPoliticaTicket
from app.models.grupo import Grupo
from app.models.ticket import MovimentoTicket, PoliticaTicket
from tests.factories.user_factory import AlunoFactory
from tests.factories.viagem_factory import ViagemFactory

CONSUMO = "/v1/tickets/consumo"


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
        "nome": "Consumo",
        "tipo": TipoPoliticaTicket.RECARGA,
        "teto": 5,
    }
    valores.update(campos)
    politica = PoliticaTicket(**valores)
    _db.session.add(politica)
    _db.session.commit()
    return politica


def _viagem(_db, horario_rota, motorista, dias_a_frente):
    viagem = ViagemFactory(
        horario_rota_id=horario_rota.id,
        data=date.today() + timedelta(days=dias_a_frente),
        status=StatusViagem.AGENDADA,
        motorista_id=motorista.user.id,
    )
    _db.session.add(viagem)
    _db.session.commit()
    return viagem


def _confirmar(aluno, viagem, rota_ponto, confirmacao=True):
    corpo = {"confirmacao": confirmacao}
    if confirmacao:
        corpo["ponto_embarque_id"] = str(rota_ponto.ponto_id)
    return aluno.client.put(f"/v1/viagens/{viagem.id}/confirmacao", json=corpo)


@pytest.fixture()
def cenario(_db, gestor, aluno, organizacao, pronto, horario_rota, motorista):
    """Duas viagens confirmadas e uma desmarcada, mais 2 tickets concedidos."""
    politica = _politica(_db, organizacao)
    primeira = _viagem(_db, horario_rota, motorista, 7)
    segunda = _viagem(_db, horario_rota, motorista, 8)
    _confirmar(aluno, primeira, pronto)
    _confirmar(aluno, segunda, pronto)
    _confirmar(aluno, segunda, pronto, confirmacao=False)
    gestor.client.post(
        "/v1/tickets/concessoes",
        json={"politica_id": str(politica.id), "usuario_id": str(aluno.user.id), "quantidade": 2},
    )
    return politica


def _linha(resposta, politica):
    itens = resposta.get_json()["items"]
    for item in itens:
        if item["politica_id"] == str(politica.id):
            return item
    raise AssertionError(f"política {politica.id} fora do relatório")


def test_consumo_por_politica(gestor, cenario):
    r = gestor.client.get(CONSUMO)

    assert r.status_code == 200, r.get_data(as_text=True)
    linha = _linha(r, cenario)
    assert linha["gastos"] == 2
    assert linha["devolvidos"] == 1
    assert linha["concedidos"] == 2
    assert linha["consumo_liquido"] == 1
    assert linha["no_shows"] == 0
    assert linha["passageiros"] == 1
    assert linha["viagens"] == 1
    assert linha["alvo"] == "ORGANIZACAO"


def test_politica_sem_movimento_aparece_zerada(_db, gestor, organizacao, cenario):
    vazia = _politica(_db, organizacao, nome="Vazia")

    linha = _linha(gestor.client.get(CONSUMO), vazia)

    assert (linha["gastos"], linha["viagens"], linha["passageiros"]) == (0, 0, 0)


def test_politica_ilimitada_conta_viagens_sem_tickets(
    _db, gestor, aluno, organizacao, pronto, viagem_futura_agendada_com_motorista
):
    ilimitada = _politica(_db, organizacao, tipo=TipoPoliticaTicket.ILIMITADO, teto=None)
    _confirmar(aluno, viagem_futura_agendada_com_motorista, pronto)

    linha = _linha(gestor.client.get(CONSUMO), ilimitada)

    assert (linha["gastos"], linha["viagens"]) == (0, 1)


def test_periodo_filtra_tickets_pela_data_do_movimento_e_viagens_pela_da_viagem(gestor, cenario):
    hoje = date.today()
    depois = (hoje + timedelta(days=30)).isoformat()
    ate_ontem = (hoje - timedelta(days=1)).isoformat()

    no_futuro = _linha(gestor.client.get(f"{CONSUMO}?de={depois}"), cenario)
    no_passado = _linha(gestor.client.get(f"{CONSUMO}?ate={ate_ontem}"), cenario)
    hoje_em_diante = _linha(gestor.client.get(f"{CONSUMO}?de={hoje.isoformat()}"), cenario)

    assert (no_futuro["gastos"], no_futuro["viagens"]) == (0, 0)
    assert (no_passado["gastos"], no_passado["viagens"]) == (0, 0)
    assert (hoje_em_diante["gastos"], hoje_em_diante["viagens"]) == (2, 1)


def test_filtro_por_grupo(_db, gestor, organizacao, cenario):
    grupo = Grupo(organizacao_id=organizacao.id, nome="Projeto X")
    _db.session.add(grupo)
    _db.session.commit()
    do_grupo = _politica(_db, organizacao, nome="Do grupo", grupo_id=grupo.id)

    itens = gestor.client.get(f"{CONSUMO}?grupo_id={grupo.id}").get_json()["items"]

    assert [i["politica_id"] for i in itens] == [str(do_grupo.id)]


def test_detalhe_por_passageiro(_db, gestor, aluno, organizacao, cenario):
    outro = AlunoFactory(organizacao_id=organizacao.id, nome="Zeca")
    _db.session.add(outro)
    _db.session.commit()
    _db.session.add(
        MovimentoTicket(
            usuario_id=outro.id,
            politica_id=cenario.id,
            tipo=TipoMovimentoTicket.NO_SHOW,
            quantidade=0,
        )
    )
    _db.session.commit()

    itens = gestor.client.get(f"{CONSUMO}?politica_id={cenario.id}").get_json()["items"]

    por_usuario = {i["usuario_id"]: i for i in itens}
    assert len(itens) == 2
    dele = por_usuario[str(aluno.user.id)]
    assert (dele["gastos"], dele["devolvidos"], dele["concedidos"], dele["viagens"]) == (2, 1, 2, 1)
    assert por_usuario[str(outro.id)]["no_shows"] == 1


def test_outra_organizacao_nao_ve_nada(other_gestor, gestor, cenario):
    assert other_gestor.client.get(CONSUMO).get_json()["items"] == []
    assert other_gestor.client.get(f"{CONSUMO}?politica_id={cenario.id}").status_code == 404


def test_passageiro_nao_ve_o_relatorio(aluno):
    assert aluno.client.get(CONSUMO).status_code == 403


def test_periodo_invertido_da_400(gestor):
    r = gestor.client.get(f"{CONSUMO}?de=2026-12-10&ate=2026-12-01")
    assert r.status_code == 400
