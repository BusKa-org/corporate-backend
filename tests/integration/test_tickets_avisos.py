from datetime import UTC, datetime, time, timedelta

import pytest

from app.models.enum import SentidoViagem, StatusViagem, TipoPoliticaTicket
from app.models.notificacao import Notificacao
from app.models.ticket import PoliticaTicket, SaldoTicket
from app.models.viagem import AlunosConfirmados
from app.tasks.ticket_tasks import avisar_tickets_recarregados


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
        "nome": "Avisos",
        "tipo": TipoPoliticaTicket.RECARGA,
        "teto": 1,
    }
    valores.update(campos)
    politica = PoliticaTicket(**valores)
    _db.session.add(politica)
    _db.session.commit()
    return politica


def _confirmar(aluno, viagem, rota_ponto):
    return aluno.client.put(
        f"/v1/viagens/{viagem.id}/confirmacao",
        json={"confirmacao": True, "ponto_embarque_id": str(rota_ponto.ponto_id)},
    )


def _titulos(_db, aluno):
    _db.session.expire_all()
    notificacoes = Notificacao.query.filter_by(usuario_id=aluno.user.id).all()
    return [n.titulo for n in notificacoes]


def _saldo(_db, aluno, politica):
    _db.session.expire_all()
    return _db.session.get(SaldoTicket, (aluno.user.id, politica.id))


def test_gastar_o_ultimo_ticket_avisa_e_marca_a_espera(
    _db, organizacao, aluno, pronto, viagem_futura_agendada_com_motorista
):
    politica = _politica(_db, organizacao, recarga_quantidade=1, recarga_intervalo_minutos=60)

    _confirmar(aluno, viagem_futura_agendada_com_motorista, pronto)

    assert "Seus tickets acabaram" in _titulos(_db, aluno)
    assert _saldo(_db, aluno, politica).aguardando_aviso is True


def test_sem_recarga_avisa_mas_nao_fica_esperando(
    _db, organizacao, aluno, pronto, viagem_futura_agendada_com_motorista
):
    politica = _politica(_db, organizacao)

    _confirmar(aluno, viagem_futura_agendada_com_motorista, pronto)

    assert "Seus tickets acabaram" in _titulos(_db, aluno)
    assert _saldo(_db, aluno, politica).aguardando_aviso is False


def test_sobrando_ticket_nao_avisa(
    _db, organizacao, aluno, pronto, viagem_futura_agendada_com_motorista
):
    _politica(_db, organizacao, teto=2)

    _confirmar(aluno, viagem_futura_agendada_com_motorista, pronto)

    assert _titulos(_db, aluno) == []


def test_quem_desligou_as_notificacoes_nao_recebe(
    _db, organizacao, aluno, pronto, viagem_futura_agendada_com_motorista
):
    aluno.user.receber_notificacoes = False
    _db.session.commit()
    _politica(_db, organizacao)

    _confirmar(aluno, viagem_futura_agendada_com_motorista, pronto)

    assert _titulos(_db, aluno) == []


# Tarefa de recarga


def _saldo_zerado(_db, aluno, politica, referencia_em, aguardando=True):
    _db.session.add(
        SaldoTicket(
            usuario_id=aluno.user.id,
            politica_id=politica.id,
            quantidade=0,
            bonus=0,
            referencia_em=referencia_em,
            aguardando_aviso=aguardando,
        )
    )
    _db.session.commit()


def test_tarefa_avisa_uma_vez_quando_a_recarga_chega(app, _db, organizacao, aluno):
    politica = _politica(
        _db, organizacao, teto=3, recarga_quantidade=1, recarga_intervalo_minutos=60
    )
    _saldo_zerado(_db, aluno, politica, datetime.now(UTC) - timedelta(minutes=130))

    avisar_tickets_recarregados(app)
    avisar_tickets_recarregados(app)

    assert _titulos(_db, aluno) == ["Tickets recarregados"]
    saldo = _saldo(_db, aluno, politica)
    assert (saldo.quantidade, saldo.aguardando_aviso) == (2, False)


def test_tarefa_espera_enquanto_a_recarga_nao_chega(app, _db, organizacao, aluno):
    politica = _politica(
        _db, organizacao, teto=3, recarga_quantidade=1, recarga_intervalo_minutos=60
    )
    _saldo_zerado(_db, aluno, politica, datetime.now(UTC) - timedelta(minutes=10))

    avisar_tickets_recarregados(app)

    assert _titulos(_db, aluno) == []
    assert _saldo(_db, aluno, politica).aguardando_aviso is True


def test_tarefa_avisa_quando_a_cota_vira_a_janela(app, _db, organizacao, aluno):
    politica = _politica(_db, organizacao, tipo=TipoPoliticaTicket.COTA, teto=2, janela="DIA")
    _saldo_zerado(_db, aluno, politica, datetime.now(UTC) - timedelta(days=2))

    avisar_tickets_recarregados(app)

    assert _titulos(_db, aluno) == ["Tickets recarregados"]
    assert _saldo(_db, aluno, politica).quantidade == 2


def test_tarefa_ignora_quem_nao_esta_esperando(app, _db, organizacao, aluno):
    politica = _politica(
        _db, organizacao, teto=3, recarga_quantidade=1, recarga_intervalo_minutos=60
    )
    _saldo_zerado(_db, aluno, politica, datetime.now(UTC) - timedelta(hours=5), aguardando=False)

    avisar_tickets_recarregados(app)

    assert _titulos(_db, aluno) == []


# Concessão e no-show


def test_concessao_avisa_o_passageiro(_db, gestor, organizacao, aluno):
    politica = _politica(_db, organizacao)

    gestor.client.post(
        "/v1/tickets/concessoes",
        json={"politica_id": str(politica.id), "usuario_id": str(aluno.user.id), "quantidade": 2},
    )

    assert _titulos(_db, aluno) == ["Você recebeu tickets"]


def test_no_show_avisa_o_passageiro(
    _db, organizacao, aluno, motorista, pronto, viagem_futura_agendada_com_motorista
):
    _politica(_db, organizacao, teto=3, no_show_penalidade=1)
    viagem = viagem_futura_agendada_com_motorista
    _confirmar(aluno, viagem, pronto)
    viagem.status = StatusViagem.EM_ANDAMENTO
    _db.session.commit()

    motorista.client.put(f"/v1/viagens/{viagem.id}/acao", json={"acao": "FINALIZAR"})

    assert "Viagem sem embarque" in _titulos(_db, aluno)
    registro = _db.session.get(AlunosConfirmados, (viagem.id, aluno.user.id))
    assert registro.embarcou is False
