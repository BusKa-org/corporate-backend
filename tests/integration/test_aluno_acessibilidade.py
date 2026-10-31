"""Necessidades de acessibilidade do aluno: cadastro no perfil e visão de gestor e motorista."""


def test_aluno_informa_acessibilidade_no_perfil(aluno, _db):
    resposta = aluno.client.put(
        "/v1/alunos/me",
        json={
            "necessidades_acessibilidade": ["CADEIRA_DE_RODAS", "DEFICIENCIA_VISUAL"],
            "observacao_acessibilidade": "Precisa da rampa do veículo",
        },
    )

    assert resposta.status_code == 200, resposta.get_data(as_text=True)
    _db.session.refresh(aluno.user)
    assert aluno.user.necessidades_acessibilidade == ["CADEIRA_DE_RODAS", "DEFICIENCIA_VISUAL"]
    assert aluno.user.observacao_acessibilidade == "Precisa da rampa do veículo"


def test_necessidade_desconhecida_e_recusada(aluno, _db):
    resposta = aluno.client.put("/v1/alunos/me", json={"necessidades_acessibilidade": ["VOAR"]})

    assert resposta.status_code == 400
    _db.session.refresh(aluno.user)
    assert aluno.user.necessidades_acessibilidade == []


def test_gestor_ve_a_acessibilidade_do_aluno(aluno, gestor, _db):
    aluno.user.necessidades_acessibilidade = ["MOBILIDADE_REDUZIDA"]
    aluno.user.observacao_acessibilidade = "Usa muletas"
    _db.session.commit()

    resposta = gestor.client.get(f"/v1/alunos/{aluno.user.id}")

    assert resposta.status_code == 200
    dados = resposta.get_json()
    assert dados["necessidades_acessibilidade"] == ["MOBILIDADE_REDUZIDA"]
    assert dados["observacao_acessibilidade"] == "Usa muletas"


def test_motorista_ve_acessibilidade_e_foto_dos_passageiros_da_viagem(
    aluno, motorista, confirmacao_aluno, _db
):
    aluno.user.necessidades_acessibilidade = ["DEFICIENCIA_AUDITIVA"]
    aluno.user.foto_url = f"/v1/alunos/{aluno.user.id}/foto"
    _db.session.commit()

    resposta = motorista.client.get("/v1/viagens/minhas")

    assert resposta.status_code == 200
    passageiros = resposta.get_json()["items"][0]["alunos"]
    assert passageiros[0]["aluno_id"] == str(aluno.user.id)
    assert passageiros[0]["necessidades_acessibilidade"] == ["DEFICIENCIA_AUDITIVA"]
    assert passageiros[0]["foto_url"] == f"/v1/alunos/{aluno.user.id}/foto"


def test_observacao_acima_de_500_caracteres_400(aluno, _db):
    resposta = aluno.client.put("/v1/alunos/me", json={"observacao_acessibilidade": "a" * 501})

    assert resposta.status_code == 400
    _db.session.refresh(aluno.user)
    assert aluno.user.observacao_acessibilidade is None


def test_necessidades_duplicadas_sao_removidas(aluno, _db):
    resposta = aluno.client.put(
        "/v1/alunos/me",
        json={"necessidades_acessibilidade": ["OUTRA", "CADEIRA_DE_RODAS", "OUTRA"]},
    )

    assert resposta.status_code == 200, resposta.get_data(as_text=True)
    _db.session.refresh(aluno.user)
    assert aluno.user.necessidades_acessibilidade == ["OUTRA", "CADEIRA_DE_RODAS"]


def test_excluir_conta_apaga_acessibilidade(aluno, _db):
    aluno.user.necessidades_acessibilidade = ["CADEIRA_DE_RODAS"]
    aluno.user.observacao_acessibilidade = "Precisa da rampa"
    _db.session.commit()

    resposta = aluno.client.delete(
        "/v1/users/me", json={"email": aluno.user.email, "senha": "StrongPass123!"}
    )

    assert resposta.status_code in (200, 204), resposta.get_data(as_text=True)
    _db.session.refresh(aluno.user)
    assert aluno.user.necessidades_acessibilidade == []
    assert aluno.user.observacao_acessibilidade is None
