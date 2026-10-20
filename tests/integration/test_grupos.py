"""Grupos de passageiros: cadastro, membros com histórico e relatório de viagens."""

from datetime import date, timedelta

from app.models.convite import Convite
from app.models.enum import StatusViagem
from app.models.grupo import Grupo, GrupoMembro, RegraEmailGrupo
from tests.factories.viagem_factory import AlunosConfirmadosFactory, ViagemFactory

SENHA = "StrongPass123!"
HOJE = date.today()


def _criar_grupo(gestor, nome="Visitantes", **campos):
    resposta = gestor.client.post("/v1/grupos", json={"nome": nome, **campos})
    assert resposta.status_code == 201, resposta.get_data(as_text=True)
    return resposta.get_json()["id"]


def _adicionar(gestor, grupo_id, aluno):
    return gestor.client.post(f"/v1/grupos/{grupo_id}/membros", json={"usuario_id": str(aluno.id)})


def _membros(gestor, grupo_id):
    resposta = gestor.client.get(f"/v1/grupos/{grupo_id}/membros")
    assert resposta.status_code == 200, resposta.get_data(as_text=True)
    return resposta.get_json()["items"]


def _vinculo(_db, grupo_id, aluno, inicio, fim=None):
    """Vínculo com datas escolhidas, para testar períodos sem esperar dias passarem."""
    vinculo = GrupoMembro(grupo_id=grupo_id, usuario_id=aluno.id, data_inicio=inicio, data_fim=fim)
    _db.session.add(vinculo)
    _db.session.commit()
    return vinculo


def _confirmar(_db, aluno, dias_atras, status, confirmacao=True, embarcou=False):
    viagem = ViagemFactory(data=HOJE - timedelta(days=dias_atras), status=status)
    _db.session.add(viagem)
    _db.session.commit()
    registro = AlunosConfirmadosFactory(
        viagem_id=viagem.id, aluno_id=aluno.id, confirmacao=confirmacao
    )
    registro.embarcou = embarcou
    _db.session.add(registro)
    _db.session.commit()
    return viagem


# ---------- grupos ----------


def test_gestor_cria_lista_edita_e_apaga_grupo(gestor):
    grupo_id = _criar_grupo(gestor, "Evento", descricao="Visita de outubro")

    listagem = gestor.client.get("/v1/grupos").get_json()
    assert listagem["total"] == 1
    assert listagem["items"][0]["nome"] == "Evento"
    assert listagem["items"][0]["ativo"] is True

    editado = gestor.client.put(f"/v1/grupos/{grupo_id}", json={"nome": "Evento 2"}).get_json()
    assert editado["nome"] == "Evento 2"
    assert editado["descricao"] == "Visita de outubro"

    assert gestor.client.delete(f"/v1/grupos/{grupo_id}").status_code == 200
    assert gestor.client.get("/v1/grupos").get_json()["total"] == 0


def test_so_gestor_mexe_em_grupos(aluno, motorista):
    assert aluno.client.post("/v1/grupos", json={"nome": "X"}).status_code == 403
    assert aluno.client.get("/v1/grupos").status_code == 403
    assert motorista.client.get("/v1/grupos").status_code == 403


def test_outra_organizacao_nao_ve_nem_altera(gestor, other_gestor):
    grupo_id = _criar_grupo(gestor)

    assert other_gestor.client.get("/v1/grupos").get_json()["total"] == 0
    assert other_gestor.client.put(f"/v1/grupos/{grupo_id}", json={"nome": "Y"}).status_code == 404
    assert other_gestor.client.delete(f"/v1/grupos/{grupo_id}").status_code == 404
    assert other_gestor.client.get(f"/v1/grupos/{grupo_id}/membros").status_code == 404


def test_datas_invalidas_e_nome_repetido(gestor, other_gestor):
    resposta = gestor.client.post(
        "/v1/grupos", json={"nome": "A", "data_inicio": "2026-10-10", "data_fim": "2026-10-01"}
    )
    assert resposta.status_code == 400

    _criar_grupo(gestor, "Repetido")
    outro_id = _criar_grupo(gestor, "Outro")
    assert gestor.client.post("/v1/grupos", json={"nome": "Repetido"}).status_code == 409
    assert gestor.client.put(f"/v1/grupos/{outro_id}", json={"nome": "Repetido"}).status_code == 409
    # O mesmo nome em outra organização é permitido.
    _criar_grupo(other_gestor, "Repetido")


def test_grupo_ativo_depende_das_datas(gestor):
    futuro = _criar_grupo(gestor, "Futuro", data_inicio=(HOJE + timedelta(days=5)).isoformat())
    encerrado = _criar_grupo(gestor, "Passado", data_fim=(HOJE - timedelta(days=1)).isoformat())
    sem_datas = _criar_grupo(gestor, "Aberto")

    ativos = {}
    for item in gestor.client.get("/v1/grupos").get_json()["items"]:
        ativos[item["id"]] = item["ativo"]

    assert ativos == {futuro: False, encerrado: False, sem_datas: True}


# ---------- membros ----------


def test_adicionar_remover_e_readicionar_guarda_o_historico(gestor, aluno, _db):
    grupo_id = _criar_grupo(gestor)

    assert _adicionar(gestor, grupo_id, aluno.user).status_code == 201
    membros = _membros(gestor, grupo_id)
    assert len(membros) == 1
    assert membros[0]["atual"] is True
    assert membros[0]["data_inicio"] == HOJE.isoformat()

    resposta = gestor.client.delete(f"/v1/grupos/{grupo_id}/membros/{aluno.user.id}")
    assert resposta.status_code == 200
    membros = _membros(gestor, grupo_id)
    assert membros[0]["atual"] is False
    assert membros[0]["data_fim"] == HOJE.isoformat()

    assert _adicionar(gestor, grupo_id, aluno.user).status_code == 201
    membros = _membros(gestor, grupo_id)
    assert len(membros) == 2
    atuais = 0
    for membro in membros:
        if membro["atual"]:
            atuais += 1
    assert atuais == 1


def test_membro_invalido_e_recusado(gestor, aluno, other_aluno, motorista, _db):
    grupo_id = _criar_grupo(gestor)
    assert _adicionar(gestor, grupo_id, aluno.user).status_code == 201

    assert _adicionar(gestor, grupo_id, aluno.user).status_code == 409
    assert _adicionar(gestor, grupo_id, other_aluno.user).status_code == 404
    assert _adicionar(gestor, grupo_id, motorista.user).status_code == 404
    assert gestor.client.post(f"/v1/grupos/{grupo_id}/membros", json={}).status_code == 400
    sem_vinculo = gestor.client.delete(f"/v1/grupos/{grupo_id}/membros/{other_aluno.user.id}")
    assert sem_vinculo.status_code == 404


def test_grupo_encerrado_nao_aceita_membro_ate_ser_renovado(gestor, aluno):
    grupo_id = _criar_grupo(gestor, data_fim=(HOJE - timedelta(days=1)).isoformat())

    assert _adicionar(gestor, grupo_id, aluno.user).status_code == 409

    renovado = gestor.client.put(f"/v1/grupos/{grupo_id}", json={"data_fim": None})
    assert renovado.get_json()["ativo"] is True
    assert _adicionar(gestor, grupo_id, aluno.user).status_code == 201


def test_apagar_grupo_leva_os_vinculos(gestor, aluno, _db):
    grupo_id = _criar_grupo(gestor)
    _adicionar(gestor, grupo_id, aluno.user)

    gestor.client.delete(f"/v1/grupos/{grupo_id}")

    _db.session.expire_all()
    assert Grupo.query.count() == 0
    assert GrupoMembro.query.count() == 0


# ---------- relatório de viagens ----------


def test_relatorio_conta_so_as_viagens_do_periodo_do_vinculo(gestor, aluno, _db):
    grupo_id = _criar_grupo(gestor)
    _vinculo(_db, grupo_id, aluno.user, HOJE - timedelta(days=10))

    _confirmar(_db, aluno.user, 12, StatusViagem.FINALIZADA, embarcou=True)  # antes do vínculo
    _confirmar(_db, aluno.user, 5, StatusViagem.FINALIZADA, embarcou=True)
    _confirmar(_db, aluno.user, 3, StatusViagem.CANCELADA)
    _confirmar(_db, aluno.user, 2, StatusViagem.AGENDADA)
    _confirmar(_db, aluno.user, 1, StatusViagem.FINALIZADA, confirmacao=False)

    membro = _membros(gestor, grupo_id)[0]

    assert membro["viagens_confirmadas"] == 2
    assert membro["viagens_finalizadas"] == 1
    assert membro["viagens_com_presenca"] == 1


def test_relatorio_para_no_fim_do_grupo_e_volta_a_contar_ao_estender(gestor, aluno, _db):
    grupo_id = _criar_grupo(gestor)
    _vinculo(_db, grupo_id, aluno.user, HOJE - timedelta(days=10))
    _confirmar(_db, aluno.user, 5, StatusViagem.FINALIZADA)
    _confirmar(_db, aluno.user, 1, StatusViagem.FINALIZADA)

    fim = (HOJE - timedelta(days=3)).isoformat()
    gestor.client.put(f"/v1/grupos/{grupo_id}", json={"data_fim": fim})
    membro = _membros(gestor, grupo_id)[0]
    assert membro["viagens_finalizadas"] == 1
    assert membro["atual"] is False

    gestor.client.put(f"/v1/grupos/{grupo_id}", json={"data_fim": None})
    membro = _membros(gestor, grupo_id)[0]
    assert membro["viagens_finalizadas"] == 2
    assert membro["atual"] is True


def test_vinculos_antigos_contam_cada_um_o_seu_periodo(gestor, aluno, _db):
    grupo_id = _criar_grupo(gestor)
    _vinculo(_db, grupo_id, aluno.user, HOJE - timedelta(days=20), HOJE - timedelta(days=15))
    _vinculo(_db, grupo_id, aluno.user, HOJE - timedelta(days=5))
    _confirmar(_db, aluno.user, 18, StatusViagem.FINALIZADA)
    _confirmar(_db, aluno.user, 10, StatusViagem.FINALIZADA)  # entre os dois vínculos
    _confirmar(_db, aluno.user, 2, StatusViagem.FINALIZADA)

    membros = _membros(gestor, grupo_id)

    # Ordem: o vínculo mais recente primeiro.
    assert membros[0]["viagens_finalizadas"] == 1
    assert membros[1]["viagens_finalizadas"] == 1


def test_pessoa_em_dois_grupos_tem_a_viagem_contada_nos_dois(gestor, aluno, _db):
    grupo_a = _criar_grupo(gestor, "A")
    grupo_b = _criar_grupo(gestor, "B")
    _vinculo(_db, grupo_a, aluno.user, HOJE - timedelta(days=10))
    _vinculo(_db, grupo_b, aluno.user, HOJE - timedelta(days=10))
    _confirmar(_db, aluno.user, 2, StatusViagem.FINALIZADA)

    assert _membros(gestor, grupo_a)[0]["viagens_finalizadas"] == 1
    assert _membros(gestor, grupo_b)[0]["viagens_finalizadas"] == 1


# ---------- exclusão de conta ----------


def test_excluir_conta_fecha_os_vinculos_abertos(gestor, aluno, _db):
    grupo_id = _criar_grupo(gestor)
    _adicionar(gestor, grupo_id, aluno.user)

    resposta = aluno.client.delete("/v1/users/me", json={"email": aluno.user.email, "senha": SENHA})
    assert resposta.status_code == 200, resposta.get_data(as_text=True)

    membros = _membros(gestor, grupo_id)
    assert len(membros) == 1
    assert membros[0]["atual"] is False
    assert membros[0]["data_fim"] == HOJE.isoformat()


# ---------- subgrupos ----------


def _por_grupo(membros, grupo_nome):
    achados = []
    for membro in membros:
        if membro["grupo_nome"] == grupo_nome:
            achados.append(membro)
    return achados


def test_subgrupo_guarda_o_pai_e_a_listagem_mostra(gestor):
    pai_id = _criar_grupo(gestor, "Nubank")
    filho_id = _criar_grupo(gestor, "Nubank Alunos", grupo_pai_id=pai_id)

    itens = {}
    for item in gestor.client.get("/v1/grupos").get_json()["items"]:
        itens[item["id"]] = item["grupo_pai_id"]

    assert itens == {pai_id: None, filho_id: pai_id}


def test_pai_invalido_e_recusado(gestor, other_gestor):
    raiz = _criar_grupo(gestor, "Raiz")
    filho = _criar_grupo(gestor, "Filho", grupo_pai_id=raiz)
    de_outra_org = _criar_grupo(other_gestor, "Outra")
    solto = _criar_grupo(gestor, "Solto")

    def criar_com_pai(pai):
        return gestor.client.post("/v1/grupos", json={"nome": "Novo", "grupo_pai_id": pai})

    assert criar_com_pai(de_outra_org).status_code == 400
    assert criar_com_pai(filho).status_code == 400  # neto
    assert criar_com_pai("nao-e-uuid").status_code == 400
    assert criar_com_pai("00000000-0000-4000-8000-000000000000").status_code == 400

    proprio = gestor.client.put(f"/v1/grupos/{solto}", json={"grupo_pai_id": solto})
    assert proprio.status_code == 400
    # Quem já tem filhos não pode virar filho.
    com_filhos = gestor.client.put(f"/v1/grupos/{raiz}", json={"grupo_pai_id": solto})
    assert com_filhos.status_code == 400


def test_trocar_e_remover_o_pai_pelo_put(gestor):
    pai_a = _criar_grupo(gestor, "A")
    pai_b = _criar_grupo(gestor, "B")
    filho = _criar_grupo(gestor, "Filho", grupo_pai_id=pai_a)

    trocado = gestor.client.put(f"/v1/grupos/{filho}", json={"grupo_pai_id": pai_b}).get_json()
    assert trocado["grupo_pai_id"] == pai_b

    removido = gestor.client.put(f"/v1/grupos/{filho}", json={"grupo_pai_id": None}).get_json()
    assert removido["grupo_pai_id"] is None


def test_apagar_pai_com_filhos_e_bloqueado(gestor):
    pai = _criar_grupo(gestor, "Pai")
    filho = _criar_grupo(gestor, "Filho", grupo_pai_id=pai)

    assert gestor.client.delete(f"/v1/grupos/{pai}").status_code == 409
    assert gestor.client.delete(f"/v1/grupos/{filho}").status_code == 200
    assert gestor.client.delete(f"/v1/grupos/{pai}").status_code == 200


def test_relatorio_do_pai_inclui_o_filho_e_o_do_filho_nao_inclui_o_pai(gestor, aluno, _db):
    pai = _criar_grupo(gestor, "Pai")
    filho = _criar_grupo(gestor, "Filho", grupo_pai_id=pai)
    assert _adicionar(gestor, filho, aluno.user).status_code == 201

    no_pai = _membros(gestor, pai)
    assert len(no_pai) == 1
    assert no_pai[0]["grupo_nome"] == "Filho"
    assert no_pai[0]["atual"] is True

    # Quem também entra no pai aparece em duas linhas, uma por vínculo.
    assert _adicionar(gestor, pai, aluno.user).status_code == 201
    no_pai = _membros(gestor, pai)
    assert len(no_pai) == 2
    assert len(_por_grupo(no_pai, "Pai")) == 1
    assert len(_por_grupo(no_pai, "Filho")) == 1

    no_filho = _membros(gestor, filho)
    assert len(no_filho) == 1
    assert no_filho[0]["grupo_nome"] == "Filho"


def test_remover_do_pai_quem_so_esta_no_filho(gestor, aluno):
    pai = _criar_grupo(gestor, "Pai")
    filho = _criar_grupo(gestor, "Filho", grupo_pai_id=pai)
    _adicionar(gestor, filho, aluno.user)

    resposta = gestor.client.delete(f"/v1/grupos/{pai}/membros/{aluno.user.id}")

    assert resposta.status_code == 404
    assert _membros(gestor, pai)[0]["atual"] is True


def test_periodo_de_cada_vinculo_usa_as_datas_do_grupo_dele(gestor, aluno, _db):
    pai = _criar_grupo(gestor, "Pai")
    filho = _criar_grupo(
        gestor, "Filho", grupo_pai_id=pai, data_fim=(HOJE - timedelta(days=3)).isoformat()
    )
    _vinculo(_db, filho, aluno.user, HOJE - timedelta(days=10))
    _confirmar(_db, aluno.user, 5, StatusViagem.FINALIZADA)
    _confirmar(_db, aluno.user, 1, StatusViagem.FINALIZADA)

    linha = _membros(gestor, pai)[0]

    assert linha["grupo_nome"] == "Filho"
    assert linha["viagens_finalizadas"] == 1
    assert linha["atual"] is False


def test_datas_do_filho_nao_dependem_das_do_pai(gestor):
    pai = _criar_grupo(gestor, "Pai", data_fim=(HOJE + timedelta(days=5)).isoformat())

    resposta = gestor.client.post(
        "/v1/grupos",
        json={
            "nome": "Filho",
            "grupo_pai_id": pai,
            "data_fim": (HOJE + timedelta(days=60)).isoformat(),
        },
    )

    assert resposta.status_code == 201


# ---------- regras de e-mail e sugestão de grupos ----------


def _regra(gestor, grupo_id, dominio):
    return gestor.client.post(f"/v1/grupos/{grupo_id}/regras-email", json={"dominio": dominio})


def _sugestao(gestor, email):
    return gestor.client.get("/v1/convites/sugestao-grupos", query_string={"email": email})


def _nomes_sugeridos(gestor, email):
    resposta = _sugestao(gestor, email)
    assert resposta.status_code == 200, resposta.get_data(as_text=True)
    nomes = []
    for item in resposta.get_json()["items"]:
        nomes.append(item["nome"])
    return nomes


def test_regra_guarda_o_dominio_sem_arroba_e_em_minusculo(gestor):
    textos = ["@Nubank.com", "NUBANK.com", "  nubank.com  "]
    for posicao, texto in enumerate(textos):
        grupo_id = _criar_grupo(gestor, f"Grupo {posicao}")

        resposta = _regra(gestor, grupo_id, texto)

        assert resposta.status_code == 201, resposta.get_data(as_text=True)
        assert resposta.get_json()["dominio"] == "nubank.com"


def test_regra_invalida_ou_repetida_e_recusada(gestor):
    grupo_id = _criar_grupo(gestor)

    assert _regra(gestor, grupo_id, "com").status_code == 400
    assert _regra(gestor, grupo_id, "nubank").status_code == 400
    assert _regra(gestor, grupo_id, "ana@nubank.com").status_code == 400
    assert _regra(gestor, grupo_id, "-nubank.com").status_code == 400
    assert gestor.client.post(f"/v1/grupos/{grupo_id}/regras-email", json={}).status_code == 400

    assert _regra(gestor, grupo_id, "nubank.com").status_code == 201
    assert _regra(gestor, grupo_id, "@NUBANK.com").status_code == 409


def test_listar_e_apagar_regra_respeita_a_organizacao(gestor, other_gestor, aluno):
    grupo_id = _criar_grupo(gestor)
    regra_id = _regra(gestor, grupo_id, "nubank.com").get_json()["id"]

    assert gestor.client.get(f"/v1/grupos/{grupo_id}/regras-email").get_json()["total"] == 1
    assert aluno.client.get(f"/v1/grupos/{grupo_id}/regras-email").status_code == 403
    assert other_gestor.client.get(f"/v1/grupos/{grupo_id}/regras-email").status_code == 404
    apagar_de_fora = other_gestor.client.delete(f"/v1/grupos/{grupo_id}/regras-email/{regra_id}")
    assert apagar_de_fora.status_code == 404

    assert gestor.client.delete(f"/v1/grupos/{grupo_id}/regras-email/{regra_id}").status_code == 200
    assert gestor.client.get(f"/v1/grupos/{grupo_id}/regras-email").get_json()["total"] == 0


def test_regra_de_outro_grupo_nao_e_apagada_pela_rota_errada(gestor):
    grupo_a = _criar_grupo(gestor, "A")
    grupo_b = _criar_grupo(gestor, "B")
    regra_de_a = _regra(gestor, grupo_a, "nubank.com").get_json()["id"]

    resposta = gestor.client.delete(f"/v1/grupos/{grupo_b}/regras-email/{regra_de_a}")

    assert resposta.status_code == 404


def test_apagar_o_grupo_apaga_as_regras(gestor, _db):
    grupo_id = _criar_grupo(gestor)
    _regra(gestor, grupo_id, "nubank.com")

    gestor.client.delete(f"/v1/grupos/{grupo_id}")

    _db.session.expire_all()
    assert RegraEmailGrupo.query.count() == 0


def test_sugestao_traz_o_dominio_e_os_dominios_pai_do_mais_especifico_ao_mais_geral(gestor):
    pai = _criar_grupo(gestor, "Nubank")
    filho = _criar_grupo(gestor, "Nubank Alunos", grupo_pai_id=pai)
    _regra(gestor, pai, "nubank.com")
    _regra(gestor, filho, "@aluno.nubank.com")

    assert _nomes_sugeridos(gestor, "ana@aluno.nubank.com") == ["Nubank Alunos", "Nubank"]
    assert _nomes_sugeridos(gestor, "Ana@NUBANK.com") == ["Nubank"]


def test_sugestao_so_casa_na_fronteira_do_ponto(gestor):
    grupo_id = _criar_grupo(gestor, "Nubank")
    _regra(gestor, grupo_id, "nubank.com")

    assert _nomes_sugeridos(gestor, "ana@fakenubank.com") == []
    assert _nomes_sugeridos(gestor, "ana@nubank.com.br") == []
    assert _nomes_sugeridos(gestor, "ana@outro.com") == []


def test_sugestao_ignora_encerrado_outra_organizacao_e_nao_repete(gestor, other_gestor):
    velho = _criar_grupo(gestor, "Velho")
    _regra(gestor, velho, "nubank.com")
    gestor.client.put(
        f"/v1/grupos/{velho}", json={"data_fim": (HOJE - timedelta(days=1)).isoformat()}
    )
    de_fora = _criar_grupo(other_gestor, "De fora")
    _regra(other_gestor, de_fora, "nubank.com")
    duas_regras = _criar_grupo(gestor, "Duas regras")
    _regra(gestor, duas_regras, "nubank.com")
    _regra(gestor, duas_regras, "aluno.nubank.com")

    assert _nomes_sugeridos(gestor, "ana@aluno.nubank.com") == ["Duas regras"]


def test_sugestao_recusa_email_invalido_e_quem_nao_e_gestor(gestor, aluno):
    assert _sugestao(gestor, "sem-arroba").status_code == 400
    assert gestor.client.get("/v1/convites/sugestao-grupos").status_code == 400
    assert _sugestao(aluno, "ana@nubank.com").status_code == 403


def test_sugestao_nao_aplica_nada_ao_convite(gestor, _db):
    grupo_id = _criar_grupo(gestor, "Nubank")
    _regra(gestor, grupo_id, "nubank.com")
    assert _nomes_sugeridos(gestor, "ana@nubank.com") == ["Nubank"]

    resposta = gestor.client.post("/v1/convites", json={"convites": [{"email": "ana@nubank.com"}]})

    assert resposta.status_code == 200
    _db.session.expire_all()
    convite = Convite.query.filter_by(email="ana@nubank.com").first()
    assert convite.grupos == []
