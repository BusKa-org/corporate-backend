from datetime import date, timedelta

import pytest

from app.models.enum import DiaDaSemana, StatusViagem, TipoMovimentoTicket
from app.models.grupo import Grupo
from app.models.ticket import MovimentoTicket, PoliticaTicket
from app.models.viagem import Viagem

URL = "/v1/politicas-ticket"
DIAS = [e.value for e in DiaDaSemana]  # SEG ... DOM, na ordem de date.weekday()


def _corpo(**campos):
    corpo = {"nome": "Padrão", "tipo": "RECARGA", "teto": 3}
    corpo.update(campos)
    return corpo


def test_gestor_cria_politica_da_organizacao(gestor):
    r = gestor.client.post(URL, json=_corpo(recarga_quantidade=1, recarga_intervalo_minutos=120))

    assert r.status_code == 201, r.get_data(as_text=True)
    dados = r.get_json()
    assert dados["alvo"] == "ORGANIZACAO"
    assert dados["tipo"] == "RECARGA"
    assert dados["teto"] == 3


def test_passageiro_nao_cria_politica(aluno):
    r = aluno.client.post(URL, json=_corpo())
    assert r.status_code == 403


def test_politica_de_grupo_e_de_pessoa(_db, gestor, aluno, organizacao):
    grupo = Grupo(organizacao_id=organizacao.id, nome="Projeto X")
    _db.session.add(grupo)
    _db.session.commit()

    do_grupo = gestor.client.post(URL, json=_corpo(nome="G", grupo_id=str(grupo.id)))
    da_pessoa = gestor.client.post(
        URL, json=_corpo(nome="P", tipo="ILIMITADO", teto=None, usuario_id=str(aluno.user.id))
    )

    assert do_grupo.get_json()["alvo"] == "GRUPO"
    assert da_pessoa.get_json()["alvo"] == "PESSOA"


def test_grupo_ou_pessoa_de_outra_organizacao_da_404(_db, gestor, other_aluno, other_organizacao):
    grupo = Grupo(organizacao_id=other_organizacao.id, nome="De fora")
    _db.session.add(grupo)
    _db.session.commit()

    com_grupo = gestor.client.post(URL, json=_corpo(grupo_id=str(grupo.id)))
    com_pessoa = gestor.client.post(URL, json=_corpo(usuario_id=str(other_aluno.user.id)))

    assert (com_grupo.status_code, com_pessoa.status_code) == (404, 404)


@pytest.mark.parametrize(
    "campos",
    [
        {"tipo": "ILIMITADO", "teto": 3},
        {"tipo": "RECARGA", "teto": None},
        {"tipo": "RECARGA", "recarga_quantidade": 1},
        {"tipo": "RECARGA", "recarga_quantidade": 1, "recarga_intervalo_minutos": 0},
        {"tipo": "RECARGA", "recarga_dias_semana": [7]},
        {"tipo": "RECARGA", "recarga_dias_semana": []},
        {"tipo": "RECARGA", "janela": "DIA"},
        {"tipo": "COTA"},
        {"tipo": "COTA", "janela": "HORAS"},
        {"tipo": "COTA", "janela": "DIA", "janela_horas": 6},
        {"tipo": "COTA", "janela": "DIA", "recarga_quantidade": 1},
        {"vigencia_inicio": "2026-12-10", "vigencia_fim": "2026-12-01"},
        {"horario_de": "18:00", "horario_ate": "08:00"},
        {"antecedencia_max_dias": 0},
        {"no_show_penalidade": -1},
        {"tipo": "FOO"},
    ],
)
def test_combinacoes_invalidas_dao_400(gestor, campos):
    r = gestor.client.post(URL, json=_corpo(**campos))
    assert r.status_code == 400, r.get_data(as_text=True)


def test_cota_por_mes_valida(gestor):
    r = gestor.client.post(URL, json=_corpo(tipo="COTA", janela="MES", teto=20))
    assert r.status_code == 201


def test_listar_filtra_por_grupo_e_nao_mostra_outra_organizacao(
    _db, gestor, other_gestor, organizacao
):
    grupo = Grupo(organizacao_id=organizacao.id, nome="Projeto X")
    _db.session.add(grupo)
    _db.session.commit()
    gestor.client.post(URL, json=_corpo(nome="Org"))
    gestor.client.post(URL, json=_corpo(nome="Grupo", grupo_id=str(grupo.id)))
    other_gestor.client.post(URL, json=_corpo(nome="Outra"))

    todas = gestor.client.get(URL).get_json()
    do_grupo = gestor.client.get(f"{URL}?grupo_id={grupo.id}").get_json()

    assert sorted(p["nome"] for p in todas["items"]) == ["Grupo", "Org"]
    assert [p["nome"] for p in do_grupo["items"]] == ["Grupo"]


def test_atualizar_muda_so_o_enviado_e_revalida(gestor):
    criada = gestor.client.post(URL, json=_corpo()).get_json()

    ok = gestor.client.put(f"{URL}/{criada['id']}", json={"teto": 5})
    invalida = gestor.client.put(f"{URL}/{criada['id']}", json={"tipo": "COTA"})

    assert ok.status_code == 200
    assert ok.get_json()["teto"] == 5
    assert ok.get_json()["nome"] == "Padrão"
    assert invalida.status_code == 400


def test_outra_organizacao_nao_enxerga_a_politica(gestor, other_gestor):
    criada = gestor.client.post(URL, json=_corpo()).get_json()

    assert other_gestor.client.get(f"{URL}/{criada['id']}").status_code == 404
    assert other_gestor.client.put(f"{URL}/{criada['id']}", json={"teto": 9}).status_code == 404
    assert other_gestor.client.delete(f"{URL}/{criada['id']}").status_code == 404


def test_apagar_politica_sem_historico(_db, gestor):
    criada = gestor.client.post(URL, json=_corpo()).get_json()

    r = gestor.client.delete(f"{URL}/{criada['id']}")

    assert r.status_code == 200
    assert PoliticaTicket.query.count() == 0


def test_politica_com_historico_nao_se_apaga(_db, gestor, aluno):
    criada = gestor.client.post(URL, json=_corpo()).get_json()
    _db.session.add(
        MovimentoTicket(
            usuario_id=aluno.user.id,
            politica_id=criada["id"],
            tipo=TipoMovimentoTicket.CONCESSAO,
            quantidade=1,
        )
    )
    _db.session.commit()

    r = gestor.client.delete(f"{URL}/{criada['id']}")

    assert r.status_code == 409


# Saldo do passageiro


def test_passageiro_sem_politica_ve_lista_vazia(aluno):
    r = aluno.client.get("/v1/alunos/me/tickets")
    assert r.status_code == 200
    assert r.get_json() == {"items": [], "total": 0}


def test_passageiro_ve_saldo_cheio_e_depois_de_gastar(
    _db, gestor, aluno, rota_aluno, dia_operacao, rota_ponto, viagem_futura_agendada_com_motorista
):
    gestor.client.post(
        URL, json=_corpo(nome="Diária", teto=2, recarga_quantidade=1, recarga_intervalo_minutos=60)
    )

    antes = aluno.client.get("/v1/alunos/me/tickets").get_json()["items"][0]
    aluno.client.put(
        f"/v1/viagens/{viagem_futura_agendada_com_motorista.id}/confirmacao",
        json={"confirmacao": True, "ponto_embarque_id": str(rota_ponto.ponto_id)},
    )
    depois = aluno.client.get("/v1/alunos/me/tickets").get_json()["items"][0]

    assert (antes["nome"], antes["quantidade"], antes["proxima_recarga_em"]) == ("Diária", 2, None)
    assert depois["quantidade"] == 1
    assert depois["proxima_recarga_em"] is not None


def test_politica_ilimitada_aparece_sem_quantidade(gestor, aluno):
    gestor.client.post(URL, json=_corpo(tipo="ILIMITADO", teto=None))

    item = aluno.client.get("/v1/alunos/me/tickets").get_json()["items"][0]

    assert item["tipo"] == "ILIMITADO"
    assert item["quantidade"] is None


def test_politica_da_pessoa_esconde_a_da_organizacao(gestor, aluno):
    gestor.client.post(URL, json=_corpo(nome="Org"))
    gestor.client.post(URL, json=_corpo(nome="Pessoa", usuario_id=str(aluno.user.id)))

    itens = aluno.client.get("/v1/alunos/me/tickets").get_json()["items"]

    assert [i["nome"] for i in itens] == ["Pessoa"]


def test_politica_fora_da_vigencia_nao_aparece(gestor, aluno):
    ontem = (date.today() - timedelta(days=1)).isoformat()
    gestor.client.post(URL, json=_corpo(vigencia_fim=ontem))

    itens = aluno.client.get("/v1/alunos/me/tickets").get_json()["items"]

    assert itens == []


# Custo da viagem


def _proxima_data_da_semana(dia: DiaDaSemana) -> date:
    alvo = DIAS.index(dia.value)
    data = date.today() + timedelta(days=1)
    while data.weekday() != alvo:
        data += timedelta(days=1)
    return data


def test_viagem_gerada_herda_o_custo_do_horario(
    _db, gestor, rota, horario_rota, dia_operacao, motorista
):
    horario_rota.custo_tickets = 3
    _db.session.commit()
    data = _proxima_data_da_semana(dia_operacao.dia)

    r = gestor.client.post("/v1/viagens/", json={"rota_id": str(rota.id), "data": data.isoformat()})

    assert r.status_code == 201, r.get_data(as_text=True)
    assert r.get_json()["custo_tickets"] == 3
    assert _db.session.get(Viagem, r.get_json()["id"]).custo_tickets == 3


def test_horario_novo_aceita_custo(gestor, rota):
    r = gestor.client.post(
        f"/v1/rotas/{rota.id}/horarios",
        json={"horario_saida": "08:00", "sentido": "IDA", "dias": ["SEG"], "custo_tickets": 2},
    )

    assert r.status_code == 201, r.get_data(as_text=True)
    assert r.get_json()["custo_tickets"] == 2


def test_gestor_muda_o_custo_de_uma_viagem_agendada(
    _db, gestor, viagem_futura_agendada_com_motorista
):
    r = gestor.client.put(
        f"/v1/viagens/{viagem_futura_agendada_com_motorista.id}/custo", json={"custo_tickets": 4}
    )

    assert r.status_code == 200
    assert _db.session.get(Viagem, viagem_futura_agendada_com_motorista.id).custo_tickets == 4


def test_custo_invalido_ou_viagem_em_andamento_ou_nao_gestor(
    _db, gestor, aluno, viagem_futura_agendada_com_motorista
):
    url = f"/v1/viagens/{viagem_futura_agendada_com_motorista.id}/custo"

    invalido = gestor.client.put(url, json={"custo_tickets": 0})
    nao_gestor = aluno.client.put(url, json={"custo_tickets": 2})
    viagem_futura_agendada_com_motorista.status = StatusViagem.EM_ANDAMENTO
    _db.session.commit()
    em_andamento = gestor.client.put(url, json={"custo_tickets": 2})

    assert (invalido.status_code, nao_gestor.status_code, em_andamento.status_code) == (
        400,
        403,
        400,
    )


def test_gestor_de_outra_organizacao_nao_muda_o_custo(
    other_gestor, viagem_futura_agendada_com_motorista
):
    r = other_gestor.client.put(
        f"/v1/viagens/{viagem_futura_agendada_com_motorista.id}/custo", json={"custo_tickets": 2}
    )
    assert r.status_code == 404
