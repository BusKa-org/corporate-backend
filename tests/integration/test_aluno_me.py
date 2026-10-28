"""PUT /v1/alunos/me é uma atualização parcial: o que não vem no corpo não muda."""

ENDERECO = {
    "logradouro": "Rua A",
    "numero": "1",
    "bairro": "Centro",
    "cidade": "Campina Grande",
    "cep": "58400000",
    "latitude": -7.2,
    "longitude": -35.9,
}


def test_atualizar_so_o_telefone_nao_apaga_nome_nem_matricula(aluno, _db):
    aluno.user.matricula = "123456"
    _db.session.commit()
    nome_antes = aluno.user.nome

    resposta = aluno.client.put("/v1/alunos/me", json={"telefone": "83999999999"})

    assert resposta.status_code == 200, resposta.get_data(as_text=True)
    _db.session.refresh(aluno.user)
    assert aluno.user.telefone == "83999999999"
    assert aluno.user.nome == nome_antes
    assert aluno.user.matricula == "123456"


def test_atualizar_so_o_endereco_nao_apaga_nome_nem_matricula(aluno, _db):
    aluno.user.matricula = "123456"
    _db.session.commit()
    nome_antes = aluno.user.nome

    resposta = aluno.client.put("/v1/alunos/me", json={"endereco_casa": ENDERECO})

    assert resposta.status_code == 200, resposta.get_data(as_text=True)
    _db.session.refresh(aluno.user)
    assert aluno.user.nome == nome_antes
    assert aluno.user.matricula == "123456"
    assert aluno.user.ponto_casa_id is not None


def test_campo_opcional_pode_ser_limpo_com_null(aluno, _db):
    aluno.user.matricula = "123456"
    _db.session.commit()

    resposta = aluno.client.put("/v1/alunos/me", json={"matricula": None})

    assert resposta.status_code == 200, resposta.get_data(as_text=True)
    _db.session.refresh(aluno.user)
    assert aluno.user.matricula is None


def test_nome_e_endereco_nao_aceitam_null(aluno, _db):
    nome_antes = aluno.user.nome

    assert aluno.client.put("/v1/alunos/me", json={"nome": None}).status_code == 400
    assert aluno.client.put("/v1/alunos/me", json={"endereco_casa": None}).status_code == 400

    _db.session.refresh(aluno.user)
    assert aluno.user.nome == nome_antes
