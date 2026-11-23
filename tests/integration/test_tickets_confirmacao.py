from datetime import UTC, date, datetime, time, timedelta

import pytest

from app.models.enum import SentidoViagem, StatusViagem, TipoMovimentoTicket, TipoPoliticaTicket
from app.models.grupo import Grupo, GrupoMembro
from app.models.ticket import MovimentoTicket, PoliticaTicket, SaldoTicket
from app.models.viagem import AlunosConfirmados
from tests.factories.viagem_factory import ViagemFactory


@pytest.fixture(autouse=True)
def horario_conhecido(_db, horario_rota):
    horario_rota.sentido = SentidoViagem.IDA
    horario_rota.horario_saida = time(8, 0)
    _db.session.commit()


def _politica(_db, organizacao, **campos):
    valores = {
        "organizacao_id": organizacao.id,
        "nome": "Política de teste",
        "tipo": TipoPoliticaTicket.RECARGA,
        "teto": 1,
    }
    valores.update(campos)
    politica = PoliticaTicket(**valores)
    _db.session.add(politica)
    _db.session.commit()
    return politica


def _outra_viagem(_db, horario_rota, motorista, dias_a_frente=8):
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


def _saldo(_db, aluno, politica):
    _db.session.expire_all()
    return _db.session.get(SaldoTicket, (aluno.user.id, politica.id))


def _movimentos(_db, aluno, tipo):
    _db.session.expire_all()
    return MovimentoTicket.query.filter_by(usuario_id=aluno.user.id, tipo=tipo).all()


@pytest.fixture()
def pronto(rota_aluno, dia_operacao, rota_ponto):
    return rota_ponto


def test_sem_politica_confirma_sem_cobrar(_db, aluno, pronto, viagem_futura_agendada_com_motorista):
    r = _confirmar(aluno, viagem_futura_agendada_com_motorista, pronto)

    assert r.status_code == 200
    assert SaldoTicket.query.count() == 0


def test_confirmar_gasta_um_ticket_e_o_segundo_da_409(
    _db, organizacao, aluno, pronto, horario_rota, motorista, viagem_futura_agendada_com_motorista
):
    politica = _politica(_db, organizacao, teto=1)
    outra = _outra_viagem(_db, horario_rota, motorista)

    primeira = _confirmar(aluno, viagem_futura_agendada_com_motorista, pronto)
    segunda = _confirmar(aluno, outra, pronto)

    assert primeira.status_code == 200
    assert segunda.status_code == 409
    assert _saldo(_db, aluno, politica).quantidade == 0
    assert len(_movimentos(_db, aluno, TipoMovimentoTicket.GASTO)) == 1


def test_confirmar_de_novo_a_mesma_viagem_nao_cobra_outra_vez(
    _db, organizacao, aluno, pronto, viagem_futura_agendada_com_motorista
):
    politica = _politica(_db, organizacao, teto=3)

    _confirmar(aluno, viagem_futura_agendada_com_motorista, pronto)
    _confirmar(aluno, viagem_futura_agendada_com_motorista, pronto)

    assert _saldo(_db, aluno, politica).quantidade == 2


def test_desmarcar_devolve_o_ticket(
    _db, organizacao, aluno, pronto, viagem_futura_agendada_com_motorista
):
    politica = _politica(_db, organizacao, teto=1)
    _confirmar(aluno, viagem_futura_agendada_com_motorista, pronto)

    r = _confirmar(aluno, viagem_futura_agendada_com_motorista, pronto, confirmacao=False)

    assert r.status_code == 200
    assert _saldo(_db, aluno, politica).quantidade == 1
    assert len(_movimentos(_db, aluno, TipoMovimentoTicket.DEVOLUCAO)) == 1


def test_viagem_com_custo_dois_gasta_dois(
    _db, organizacao, aluno, pronto, viagem_futura_agendada_com_motorista
):
    politica = _politica(_db, organizacao, teto=3)
    viagem_futura_agendada_com_motorista.custo_tickets = 2
    _db.session.commit()

    r = _confirmar(aluno, viagem_futura_agendada_com_motorista, pronto)

    assert r.status_code == 200
    assert _saldo(_db, aluno, politica).quantidade == 1


def test_saldo_menor_que_o_custo_da_409(
    _db, organizacao, aluno, pronto, viagem_futura_agendada_com_motorista
):
    _politica(_db, organizacao, teto=1)
    viagem_futura_agendada_com_motorista.custo_tickets = 2
    _db.session.commit()

    r = _confirmar(aluno, viagem_futura_agendada_com_motorista, pronto)

    assert r.status_code == 409


def test_bonus_e_gasto_antes_da_quantidade(
    _db, organizacao, aluno, pronto, viagem_futura_agendada_com_motorista
):
    politica = _politica(_db, organizacao, teto=2)
    _db.session.add(
        SaldoTicket(
            usuario_id=aluno.user.id,
            politica_id=politica.id,
            quantidade=2,
            bonus=1,
            referencia_em=datetime.now(UTC),
        )
    )
    _db.session.commit()

    _confirmar(aluno, viagem_futura_agendada_com_motorista, pronto)

    saldo = _saldo(_db, aluno, politica)
    assert (saldo.bonus, saldo.quantidade) == (0, 2)


def test_devolucao_que_passa_do_teto_vai_para_o_bonus(
    _db, organizacao, aluno, pronto, viagem_futura_agendada_com_motorista
):
    politica = _politica(_db, organizacao, teto=1)
    _confirmar(aluno, viagem_futura_agendada_com_motorista, pronto)
    saldo = _saldo(_db, aluno, politica)
    saldo.quantidade = 1  # recarregou enquanto a viagem estava confirmada
    _db.session.commit()

    _confirmar(aluno, viagem_futura_agendada_com_motorista, pronto, confirmacao=False)

    saldo = _saldo(_db, aluno, politica)
    assert (saldo.quantidade, saldo.bonus) == (1, 1)


def test_gestor_cancela_a_viagem_e_devolve(
    _db, organizacao, aluno, gestor, pronto, viagem_futura_agendada_com_motorista
):
    politica = _politica(_db, organizacao, teto=1)
    _confirmar(aluno, viagem_futura_agendada_com_motorista, pronto)

    r = gestor.client.put(f"/v1/viagens/{viagem_futura_agendada_com_motorista.id}/cancelar")

    assert r.status_code == 200
    assert _saldo(_db, aluno, politica).quantidade == 1


@pytest.mark.parametrize("devolve", [True, False])
def test_finalizar_devolve_so_a_quem_embarcou_e_se_a_politica_manda(
    _db, organizacao, aluno, motorista, pronto, viagem_futura_agendada_com_motorista, devolve
):
    politica = _politica(_db, organizacao, teto=1, devolve_ao_finalizar=devolve)
    viagem = viagem_futura_agendada_com_motorista
    _confirmar(aluno, viagem, pronto)
    viagem.status = StatusViagem.EM_ANDAMENTO
    registro = _db.session.get(AlunosConfirmados, (viagem.id, aluno.user.id))
    registro.embarcou = True
    _db.session.commit()

    r = motorista.client.put(f"/v1/viagens/{viagem.id}/acao", json={"acao": "FINALIZAR"})

    assert r.status_code == 200, r.get_data(as_text=True)
    esperado = 1 if devolve else 0
    assert _saldo(_db, aluno, politica).quantidade == esperado


def test_finalizar_nao_devolve_a_quem_nao_embarcou(
    _db, organizacao, aluno, motorista, pronto, viagem_futura_agendada_com_motorista
):
    politica = _politica(_db, organizacao, teto=1, devolve_ao_finalizar=True)
    viagem = viagem_futura_agendada_com_motorista
    _confirmar(aluno, viagem, pronto)
    viagem.status = StatusViagem.EM_ANDAMENTO
    _db.session.commit()

    motorista.client.put(f"/v1/viagens/{viagem.id}/acao", json={"acao": "FINALIZAR"})

    assert _saldo(_db, aluno, politica).quantidade == 0


# Qual política vale


def test_politica_da_pessoa_vence_a_da_organizacao(
    _db, organizacao, aluno, pronto, horario_rota, motorista, viagem_futura_agendada_com_motorista
):
    _politica(_db, organizacao, teto=1)
    _politica(
        _db,
        organizacao,
        usuario_id=aluno.user.id,
        tipo=TipoPoliticaTicket.ILIMITADO,
        teto=None,
    )
    outra = _outra_viagem(_db, horario_rota, motorista)

    primeira = _confirmar(aluno, viagem_futura_agendada_com_motorista, pronto)
    segunda = _confirmar(aluno, outra, pronto)

    assert (primeira.status_code, segunda.status_code) == (200, 200)


def test_politica_do_grupo_vence_a_da_organizacao_e_so_para_membro_atual(
    _db, organizacao, aluno, pronto, horario_rota, motorista, viagem_futura_agendada_com_motorista
):
    _politica(_db, organizacao, teto=1)
    grupo = Grupo(organizacao_id=organizacao.id, nome="Projeto X")
    _db.session.add(grupo)
    _db.session.commit()
    _politica(_db, organizacao, grupo_id=grupo.id, teto=3)
    vinculo = GrupoMembro(grupo_id=grupo.id, usuario_id=aluno.user.id)
    _db.session.add(vinculo)
    _db.session.commit()
    outra = _outra_viagem(_db, horario_rota, motorista)

    com_vinculo = [
        _confirmar(aluno, viagem_futura_agendada_com_motorista, pronto).status_code,
        _confirmar(aluno, outra, pronto).status_code,
    ]

    assert com_vinculo == [200, 200]


def test_quem_saiu_do_grupo_volta_para_a_politica_da_organizacao(
    _db, organizacao, aluno, pronto, horario_rota, motorista, viagem_futura_agendada_com_motorista
):
    _politica(_db, organizacao, teto=1)
    grupo = Grupo(organizacao_id=organizacao.id, nome="Projeto X")
    _db.session.add(grupo)
    _db.session.commit()
    _politica(_db, organizacao, grupo_id=grupo.id, teto=3)
    _db.session.add(
        GrupoMembro(
            grupo_id=grupo.id,
            usuario_id=aluno.user.id,
            data_inicio=date.today() - timedelta(days=5),
            data_fim=date.today() - timedelta(days=1),
        )
    )
    _db.session.commit()
    outra = _outra_viagem(_db, horario_rota, motorista)

    _confirmar(aluno, viagem_futura_agendada_com_motorista, pronto)
    segunda = _confirmar(aluno, outra, pronto)

    assert segunda.status_code == 409


def test_membro_de_subgrupo_recebe_a_politica_do_pai(
    _db, organizacao, aluno, pronto, horario_rota, motorista, viagem_futura_agendada_com_motorista
):
    pai = Grupo(organizacao_id=organizacao.id, nome="Projeto X")
    _db.session.add(pai)
    _db.session.commit()
    filho = Grupo(organizacao_id=organizacao.id, nome="Time A", grupo_pai_id=pai.id)
    _db.session.add(filho)
    _db.session.commit()
    _politica(_db, organizacao, grupo_id=pai.id, teto=2)
    _db.session.add(GrupoMembro(grupo_id=filho.id, usuario_id=aluno.user.id))
    _db.session.commit()
    outra = _outra_viagem(_db, horario_rota, motorista)

    primeira = _confirmar(aluno, viagem_futura_agendada_com_motorista, pronto)
    segunda = _confirmar(aluno, outra, pronto)

    assert (primeira.status_code, segunda.status_code) == (200, 200)


def test_entre_grupos_vence_a_politica_mais_generosa(
    _db, organizacao, aluno, pronto, horario_rota, motorista, viagem_futura_agendada_com_motorista
):
    pequeno = Grupo(organizacao_id=organizacao.id, nome="Pequeno")
    grande = Grupo(organizacao_id=organizacao.id, nome="Grande")
    _db.session.add_all([pequeno, grande])
    _db.session.commit()
    _politica(_db, organizacao, grupo_id=pequeno.id, teto=1)
    _politica(_db, organizacao, grupo_id=grande.id, teto=2)
    _db.session.add_all(
        [
            GrupoMembro(grupo_id=pequeno.id, usuario_id=aluno.user.id),
            GrupoMembro(grupo_id=grande.id, usuario_id=aluno.user.id),
        ]
    )
    _db.session.commit()
    outra = _outra_viagem(_db, horario_rota, motorista)

    primeira = _confirmar(aluno, viagem_futura_agendada_com_motorista, pronto)
    segunda = _confirmar(aluno, outra, pronto)

    assert (primeira.status_code, segunda.status_code) == (200, 200)


def test_politica_fora_da_vigencia_e_ignorada(
    _db, organizacao, aluno, pronto, horario_rota, motorista, viagem_futura_agendada_com_motorista
):
    _politica(
        _db,
        organizacao,
        teto=1,
        vigencia_fim=date.today() + timedelta(days=1),
    )
    outra = _outra_viagem(_db, horario_rota, motorista)

    # As duas viagens são depois do fim da vigência, então ninguém é cobrado.
    primeira = _confirmar(aluno, viagem_futura_agendada_com_motorista, pronto)
    segunda = _confirmar(aluno, outra, pronto)

    assert (primeira.status_code, segunda.status_code) == (200, 200)
    assert SaldoTicket.query.count() == 0


def test_politica_de_outro_sentido_nao_vale_para_a_viagem(
    _db, organizacao, aluno, pronto, viagem_futura_agendada_com_motorista
):
    _politica(_db, organizacao, teto=1, sentido=SentidoViagem.VOLTA)

    r = _confirmar(aluno, viagem_futura_agendada_com_motorista, pronto)

    assert r.status_code == 200
    assert SaldoTicket.query.count() == 0


def test_politica_com_faixa_de_horario_so_vale_dentro_dela(
    _db, organizacao, aluno, pronto, horario_rota, motorista, viagem_futura_agendada_com_motorista
):
    # A viagem sai às 8h.
    _politica(_db, organizacao, teto=1, horario_de=time(18, 0), horario_ate=time(23, 0))

    r = _confirmar(aluno, viagem_futura_agendada_com_motorista, pronto)

    assert r.status_code == 200
    assert SaldoTicket.query.count() == 0
