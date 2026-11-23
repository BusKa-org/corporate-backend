from datetime import date, timedelta

import pytest

from app.models.enum import TipoMovimentoTicket, TipoPoliticaTicket
from app.models.grupo import Grupo, GrupoMembro
from app.models.ticket import MovimentoTicket, PoliticaTicket, SaldoTicket
from tests.factories.user_factory import AlunoFactory

CONCESSOES = "/v1/tickets/concessoes"
MOVIMENTOS = "/v1/tickets/movimentos"


def _politica(_db, organizacao, **campos):
    valores = {
        "organizacao_id": organizacao.id,
        "nome": "Padrão",
        "tipo": TipoPoliticaTicket.RECARGA,
        "teto": 2,
    }
    valores.update(campos)
    politica = PoliticaTicket(**valores)
    _db.session.add(politica)
    _db.session.commit()
    return politica


def _bonus(_db, usuario_id, politica):
    _db.session.expire_all()
    saldo = _db.session.get(SaldoTicket, (usuario_id, politica.id))
    return saldo.bonus if saldo else None


def test_gestor_concede_a_uma_pessoa(_db, gestor, aluno, organizacao):
    politica = _politica(_db, organizacao)

    r = gestor.client.post(
        CONCESSOES,
        json={
            "politica_id": str(politica.id),
            "usuario_id": str(aluno.user.id),
            "quantidade": 3,
            "motivo": "Reunião de sexta",
        },
    )

    assert r.status_code == 201, r.get_data(as_text=True)
    assert r.get_json()["passageiros"] == 1
    assert _bonus(_db, aluno.user.id, politica) == 3
    movimento = MovimentoTicket.query.filter_by(tipo=TipoMovimentoTicket.CONCESSAO).one()
    assert (movimento.quantidade, movimento.motivo) == (3, "Reunião de sexta")
    assert movimento.criado_por == gestor.user.id


def test_concessao_nao_passa_pelo_teto(_db, gestor, aluno, organizacao):
    politica = _politica(_db, organizacao, teto=1)

    gestor.client.post(
        CONCESSOES,
        json={
            "politica_id": str(politica.id),
            "usuario_id": str(aluno.user.id),
            "quantidade": 10,
        },
    )

    _db.session.expire_all()
    saldo = _db.session.get(SaldoTicket, (aluno.user.id, politica.id))
    assert (saldo.quantidade, saldo.bonus) == (1, 10)


def test_concessao_a_um_grupo_vai_para_membros_atuais_e_subgrupos(_db, gestor, organizacao):
    pai = Grupo(organizacao_id=organizacao.id, nome="Projeto X")
    _db.session.add(pai)
    _db.session.commit()
    filho = Grupo(organizacao_id=organizacao.id, nome="Time A", grupo_pai_id=pai.id)
    _db.session.add(filho)
    _db.session.commit()

    no_pai = AlunoFactory(organizacao_id=organizacao.id)
    no_filho = AlunoFactory(organizacao_id=organizacao.id)
    ex_membro = AlunoFactory(organizacao_id=organizacao.id)
    de_fora = AlunoFactory(organizacao_id=organizacao.id)
    _db.session.add_all([no_pai, no_filho, ex_membro, de_fora])
    _db.session.commit()
    _db.session.add_all(
        [
            GrupoMembro(grupo_id=pai.id, usuario_id=no_pai.id),
            GrupoMembro(grupo_id=filho.id, usuario_id=no_filho.id),
            GrupoMembro(
                grupo_id=pai.id,
                usuario_id=ex_membro.id,
                data_inicio=date.today() - timedelta(days=9),
                data_fim=date.today() - timedelta(days=1),
            ),
        ]
    )
    _db.session.commit()
    politica = _politica(_db, organizacao)

    r = gestor.client.post(
        CONCESSOES,
        json={"politica_id": str(politica.id), "grupo_id": str(pai.id), "quantidade": 2},
    )

    assert r.get_json()["passageiros"] == 2
    assert _bonus(_db, no_pai.id, politica) == 2
    assert _bonus(_db, no_filho.id, politica) == 2
    assert _bonus(_db, ex_membro.id, politica) is None
    assert _bonus(_db, de_fora.id, politica) is None


@pytest.mark.parametrize("alvo", ["nenhum", "ambos"])
def test_concessao_exige_exatamente_um_alvo(_db, gestor, aluno, organizacao, alvo):
    politica = _politica(_db, organizacao)
    grupo = Grupo(organizacao_id=organizacao.id, nome="G")
    _db.session.add(grupo)
    _db.session.commit()
    corpo = {"politica_id": str(politica.id), "quantidade": 1}
    if alvo == "ambos":
        corpo["usuario_id"] = str(aluno.user.id)
        corpo["grupo_id"] = str(grupo.id)

    r = gestor.client.post(CONCESSOES, json=corpo)

    assert r.status_code == 400


def test_politica_ilimitada_recusa_concessao(_db, gestor, aluno, organizacao):
    politica = _politica(_db, organizacao, tipo=TipoPoliticaTicket.ILIMITADO, teto=None)

    r = gestor.client.post(
        CONCESSOES,
        json={"politica_id": str(politica.id), "usuario_id": str(aluno.user.id), "quantidade": 1},
    )

    assert r.status_code == 400


@pytest.mark.parametrize("quantidade", [0, -1, 1001])
def test_quantidade_fora_do_intervalo_da_400(_db, gestor, aluno, organizacao, quantidade):
    politica = _politica(_db, organizacao)

    r = gestor.client.post(
        CONCESSOES,
        json={
            "politica_id": str(politica.id),
            "usuario_id": str(aluno.user.id),
            "quantidade": quantidade,
        },
    )

    assert r.status_code == 400


def test_outra_organizacao_e_passageiro_comum_nao_concedem(
    _db, gestor, other_gestor, other_aluno, aluno, organizacao
):
    politica = _politica(_db, organizacao)
    corpo = {"politica_id": str(politica.id), "usuario_id": str(aluno.user.id), "quantidade": 1}

    de_outra_organizacao = other_gestor.client.post(CONCESSOES, json=corpo)
    passageiro = aluno.client.post(CONCESSOES, json=corpo)
    para_outra_organizacao = gestor.client.post(
        CONCESSOES, json={**corpo, "usuario_id": str(other_aluno.user.id)}
    )

    assert de_outra_organizacao.status_code == 404
    assert passageiro.status_code == 403
    assert para_outra_organizacao.status_code == 404


# Histórico


def test_gestor_filtra_o_historico_e_nao_ve_outra_organizacao(
    _db, gestor, other_gestor, aluno, organizacao
):
    politica = _politica(_db, organizacao)
    gestor.client.post(
        CONCESSOES,
        json={"politica_id": str(politica.id), "usuario_id": str(aluno.user.id), "quantidade": 2},
    )

    todos = gestor.client.get(MOVIMENTOS).get_json()
    do_passageiro = gestor.client.get(f"{MOVIMENTOS}?usuario_id={aluno.user.id}").get_json()
    de_outra_politica = gestor.client.get(
        f"{MOVIMENTOS}?politica_id=00000000-0000-0000-0000-000000000001"
    ).get_json()
    outra_organizacao = other_gestor.client.get(MOVIMENTOS).get_json()

    assert todos["total"] == 1
    assert todos["items"][0]["tipo"] == "CONCESSAO"
    assert todos["items"][0]["politica_nome"] == "Padrão"
    assert do_passageiro["total"] == 1
    assert de_outra_politica["total"] == 0
    assert outra_organizacao["total"] == 0


def test_passageiro_ve_so_o_proprio_historico(_db, gestor, aluno, other_aluno, organizacao):
    politica = _politica(_db, organizacao)
    gestor.client.post(
        CONCESSOES,
        json={"politica_id": str(politica.id), "usuario_id": str(aluno.user.id), "quantidade": 2},
    )

    meu = aluno.client.get("/v1/alunos/me/tickets/movimentos").get_json()
    de_outro = other_aluno.client.get("/v1/alunos/me/tickets/movimentos").get_json()

    assert meu["total"] == 1
    assert de_outro["total"] == 0
