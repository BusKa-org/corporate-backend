"""Convites de cadastro de passageiro, pela API HTTP e pela tarefa de envio."""

from datetime import UTC, datetime, timedelta

import pytest

from app.models.convite import (
    CANCELADO,
    CONCLUIDO,
    ENVIADO,
    ENVIO_PENDENTE,
    FALHOU,
    PENDENTE,
    Convite,
)
from app.models.enum import TipoInstituicao, UserStatus
from app.models.geo import Instituicao
from app.models.user import Aluno
from app.services import convite_service
from app.tasks.convite_tasks import enviar_convites_pendentes

CPF_A = "52998224725"
CPF_B = "11144477735"
SENHA = "StrongPass123!"


@pytest.fixture()
def instituicao(_db, organizacao):
    inst = Instituicao(
        fonte="MANUAL",
        codigo_externo="UFCG-1",
        nome="Universidade Federal de Campina Grande",
        sigla="UFCG",
        tipo=TipoInstituicao.UNIVERSIDADE_PUBLICA,
        uf="PB",
        organizacao_id=organizacao.id,
    )
    _db.session.add(inst)
    _db.session.commit()
    return inst


@pytest.fixture()
def instituicao_de_outra_organizacao(_db, other_organizacao):
    inst = Instituicao(
        fonte="MANUAL",
        codigo_externo="UEPB-1",
        nome="Universidade Estadual da Paraíba",
        sigla="UEPB",
        tipo=TipoInstituicao.UNIVERSIDADE_PUBLICA,
        uf="PB",
        organizacao_id=other_organizacao.id,
    )
    _db.session.add(inst)
    _db.session.commit()
    return inst


def _convidar(gestor, itens):
    response = gestor.client.post("/v1/convites", json={"convites": itens})
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()["resultados"]


def _convite(_db, email):
    _db.session.expire_all()
    return Convite.query.filter_by(email=email).order_by(Convite.created_at.desc()).first()


def _vencer(_db, convite):
    convite.expira_em = datetime.now(UTC) - timedelta(days=1)
    _db.session.commit()


def _concluir(client, token, **campos):
    return client.post(f"/v1/convites/aceite/{token}", json=campos)


# ---------- convidar ----------


def test_convidar_so_com_email_cria_convite_pendente(gestor, _db):
    resultados = _convidar(gestor, [{"email": "Ana@Parque.test"}])

    assert resultados == [{"email": "ana@parque.test", "resultado": "CRIADO", "motivo": ""}]
    convite = _convite(_db, "ana@parque.test")
    assert convite.estado == PENDENTE
    assert convite.envio_estado == ENVIO_PENDENTE
    assert convite.organizacao_id == gestor.user.organizacao_id
    assert convite.expira_em > datetime.now(UTC) + timedelta(days=6)


def test_convidar_guarda_os_dados_opcionais(gestor, instituicao, _db):
    _convidar(
        gestor,
        [
            {
                "email": "bia@parque.test",
                "nome": "Bia Souza",
                "cpf": "529.982.247-25",
                "telefone": "(83) 99999-9999",
                "instituicao_id": str(instituicao.id),
            }
        ],
    )

    convite = _convite(_db, "bia@parque.test")
    assert convite.nome == "Bia Souza"
    assert convite.cpf == CPF_A
    assert convite.telefone == "83999999999"
    assert convite.instituicao_id == instituicao.id


def test_so_gestor_convida(aluno, motorista, client):
    corpo = {"convites": [{"email": "x@parque.test"}]}

    assert aluno.client.post("/v1/convites", json=corpo).status_code == 403
    assert motorista.client.post("/v1/convites", json=corpo).status_code == 403
    assert client.post("/v1/convites", json=corpo).status_code in (401, 422)


def test_lote_misto_devolve_um_resultado_por_linha(
    gestor, aluno, instituicao_de_outra_organizacao, _db
):
    aluno.user.cpf = CPF_B  # a fábrica grava o CPF com pontuação, o sistema guarda só dígitos
    _db.session.commit()
    resultados = _convidar(
        gestor,
        [
            {"email": "novo@parque.test"},
            {"email": aluno.user.email},
            {"email": "novo@parque.test"},
            {"email": "sem-arroba"},
            {"email": "cpf-ruim@parque.test", "cpf": "123"},
            {"email": "cpf-usado@parque.test", "cpf": CPF_B},
            {
                "email": "outra-org@parque.test",
                "instituicao_id": str(instituicao_de_outra_organizacao.id),
            },
        ],
    )

    assert [linha["resultado"] for linha in resultados] == [
        "CRIADO",
        "PULADO",
        "PULADO",
        "INVALIDO",
        "INVALIDO",
        "INVALIDO",
        "INVALIDO",
    ]
    for linha in resultados[1:]:
        assert linha["motivo"] != ""
    # Só a primeira linha virou convite.
    assert Convite.query.count() == 1


def test_lote_acima_do_limite_e_recusado(gestor):
    itens = [{"email": f"p{numero}@parque.test"} for numero in range(501)]

    response = gestor.client.post("/v1/convites", json={"convites": itens})

    assert response.status_code == 400
    assert Convite.query.count() == 0


def test_convidar_de_novo_pula_convite_pendente_e_renova_o_vencido(gestor, _db):
    _convidar(gestor, [{"email": "lia@parque.test"}])
    convite = _convite(_db, "lia@parque.test")
    token_antigo = convite.token

    repetido = _convidar(gestor, [{"email": "lia@parque.test"}])
    assert repetido[0]["resultado"] == "PULADO"

    _vencer(_db, convite)
    renovado = _convidar(gestor, [{"email": "lia@parque.test", "nome": "Lia"}])
    assert renovado[0]["resultado"] == "RENOVADO"

    convite = _convite(_db, "lia@parque.test")
    assert Convite.query.count() == 1
    assert convite.token != token_antigo
    assert convite.nome == "Lia"
    assert convite.expira_em > datetime.now(UTC)


# ---------- listar, reenviar, cancelar ----------


def test_listar_mostra_so_a_propria_organizacao_e_filtra_por_estado(gestor, other_gestor, _db):
    _convidar(gestor, [{"email": "um@parque.test"}, {"email": "dois@parque.test"}])
    _convidar(other_gestor, [{"email": "outro@parque.test"}])
    cancelado = _convite(_db, "dois@parque.test")
    cancelado.estado = CANCELADO
    _db.session.commit()

    todos = gestor.client.get("/v1/convites").get_json()
    assert sorted(item["email"] for item in todos["items"]) == [
        "dois@parque.test",
        "um@parque.test",
    ]

    pendentes = gestor.client.get("/v1/convites?estado=PENDENTE").get_json()
    assert [item["email"] for item in pendentes["items"]] == ["um@parque.test"]
    assert pendentes["items"][0]["vencido"] is False

    assert gestor.client.get("/v1/convites?estado=XPTO").status_code == 400


def test_reenviar_troca_o_token_e_o_antigo_deixa_de_valer(gestor, client, _db):
    _convidar(gestor, [{"email": "rui@parque.test"}])
    convite = _convite(_db, "rui@parque.test")
    token_antigo = convite.token
    convite.envio_estado = FALHOU
    convite.envio_tentativas = 3
    _db.session.commit()

    response = gestor.client.post(f"/v1/convites/{convite.id}/reenviar")

    assert response.status_code == 200
    convite = _convite(_db, "rui@parque.test")
    assert convite.token != token_antigo
    assert convite.envio_estado == ENVIO_PENDENTE
    assert convite.envio_tentativas == 0
    assert client.get(f"/v1/convites/aceite/{token_antigo}").status_code == 404
    assert client.get(f"/v1/convites/aceite/{convite.token}").status_code == 200


def test_cancelar_invalida_o_link_e_so_vale_para_pendente(gestor, client, _db):
    _convidar(gestor, [{"email": "tom@parque.test"}])
    convite = _convite(_db, "tom@parque.test")

    assert gestor.client.delete(f"/v1/convites/{convite.id}").status_code == 200

    convite = _convite(_db, "tom@parque.test")
    assert convite.estado == CANCELADO
    assert client.get(f"/v1/convites/aceite/{convite.token}").status_code == 404
    assert gestor.client.delete(f"/v1/convites/{convite.id}").status_code == 409
    assert gestor.client.post(f"/v1/convites/{convite.id}/reenviar").status_code == 409


def test_gestor_de_outra_organizacao_nao_mexe_no_convite(gestor, other_gestor, _db):
    _convidar(gestor, [{"email": "zeca@parque.test"}])
    convite = _convite(_db, "zeca@parque.test")

    assert other_gestor.client.post(f"/v1/convites/{convite.id}/reenviar").status_code == 404
    assert other_gestor.client.delete(f"/v1/convites/{convite.id}").status_code == 404
    assert _convite(_db, "zeca@parque.test").estado == PENDENTE


# ---------- concluir pelo link ----------


def test_consultar_informa_o_que_falta(gestor, client, _db):
    _convidar(gestor, [{"email": "nina@parque.test", "nome": "Nina"}])
    convite = _convite(_db, "nina@parque.test")

    dados = client.get(f"/v1/convites/aceite/{convite.token}").get_json()

    assert dados["email"] == "nina@parque.test"
    assert dados["nome"] == "Nina"
    assert dados["campos_faltando"] == ["cpf", "instituicao_id"]


def test_link_desconhecido_vencido_ou_concluido_da_a_mesma_resposta(
    gestor, client, instituicao, _db
):
    _convidar(gestor, [{"email": "vencido@parque.test"}, {"email": "pronto@parque.test"}])
    vencido = _convite(_db, "vencido@parque.test")
    _vencer(_db, vencido)
    pronto = _convite(_db, "pronto@parque.test")
    token_do_pronto = pronto.token
    resposta = _concluir(
        client,
        token_do_pronto,
        nome="Pronto",
        cpf=CPF_A,
        instituicao_id=str(instituicao.id),
        senha=SENHA,
    )
    assert resposta.status_code == 201

    respostas = [
        client.get("/v1/convites/aceite/token-que-nao-existe"),
        client.get(f"/v1/convites/aceite/{vencido.token}"),
        client.get(f"/v1/convites/aceite/{token_do_pronto}"),
        _concluir(client, token_do_pronto, senha=SENHA),
    ]
    for resposta in respostas:
        assert resposta.status_code == 404
        assert resposta.get_json()["error"]["message"] == "Convite inválido ou expirado"


def test_concluir_convite_so_com_email_exige_os_dados_que_faltam(gestor, client, _db):
    _convidar(gestor, [{"email": "otto@parque.test"}])
    token = _convite(_db, "otto@parque.test").token

    resposta = _concluir(client, token, senha=SENHA)

    assert resposta.status_code == 400
    assert Aluno.query.count() == 0
    assert _convite(_db, "otto@parque.test").estado == PENDENTE


def test_concluir_cria_passageiro_ativo_que_consegue_entrar(gestor, client, instituicao, _db):
    _convidar(gestor, [{"email": "eva@parque.test"}])
    convite = _convite(_db, "eva@parque.test")

    resposta = _concluir(
        client,
        convite.token,
        nome="Eva Lima",
        cpf=CPF_A,
        telefone="83988887777",
        instituicao_id=str(instituicao.id),
        senha=SENHA,
    )

    assert resposta.status_code == 201
    aluno = Aluno.query.filter_by(email="eva@parque.test").one()
    assert aluno.status == UserStatus.ACTIVE
    assert aluno.organizacao_id == gestor.user.organizacao_id
    assert aluno.instituicao_id == instituicao.id
    assert aluno.cpf == CPF_A

    convite = _convite(_db, "eva@parque.test")
    assert convite.estado == CONCLUIDO
    assert convite.usuario_id == aluno.id
    assert convite.cpf is None and convite.nome is None and convite.telefone is None

    login = client.post("/v1/auth/login", json={"email": "eva@parque.test", "password": SENHA})
    assert login.status_code == 200


def test_concluir_com_dados_do_gestor_aceita_correcao(gestor, client, instituicao, _db, caplog):
    _convidar(
        gestor,
        [
            {
                "email": "caio@parque.test",
                "nome": "Caio Silvaa",
                "cpf": CPF_A,
                "instituicao_id": str(instituicao.id),
            }
        ],
    )
    token = _convite(_db, "caio@parque.test").token

    with caplog.at_level("INFO", logger="app.audit"):
        resposta = _concluir(client, token, nome="Caio Silva", senha=SENHA)

    assert resposta.status_code == 201
    aluno = Aluno.query.filter_by(email="caio@parque.test").one()
    assert aluno.nome == "Caio Silva"
    assert aluno.cpf == CPF_A
    assert aluno.instituicao_id == instituicao.id

    eventos = [r for r in caplog.records if getattr(r, "action", "") == "concluir_convite"]
    assert len(eventos) == 1
    assert eventos[0].details == {"campos_alterados": ["nome"]}


def test_concluir_com_cpf_ou_instituicao_invalidos_nao_cria_nada(
    gestor, aluno, client, instituicao, instituicao_de_outra_organizacao, _db
):
    aluno.user.cpf = CPF_A  # a fábrica grava o CPF com pontuação, o sistema guarda só dígitos
    _db.session.commit()
    _convidar(gestor, [{"email": "duda@parque.test"}])
    token = _convite(_db, "duda@parque.test").token
    base = {"nome": "Duda", "senha": SENHA}

    cpf_repetido = _concluir(client, token, cpf=CPF_A, instituicao_id=str(instituicao.id), **base)
    assert cpf_repetido.status_code == 409

    instituicao_errada = _concluir(
        client,
        token,
        cpf=CPF_B,
        instituicao_id=str(instituicao_de_outra_organizacao.id),
        **base,
    )
    assert instituicao_errada.status_code == 400

    senha_curta = _concluir(
        client, token, nome="Duda", cpf=CPF_B, instituicao_id=str(instituicao.id), senha="123"
    )
    assert senha_curta.status_code == 400

    assert Aluno.query.filter_by(email="duda@parque.test").count() == 0
    assert _convite(_db, "duda@parque.test").estado == PENDENTE


# ---------- tarefa de envio ----------


@pytest.fixture()
def email_configurado(app, monkeypatch):
    monkeypatch.setitem(app.config, "MAIL_SERVER", "smtp.teste")
    monkeypatch.setitem(app.config, "MAIL_USERNAME", "app@teste")
    monkeypatch.setitem(app.config, "MAIL_PASSWORD", "segredo")
    monkeypatch.setitem(app.config, "FRONTEND_URL", "http://front.teste")
    monkeypatch.setitem(app.config, "APP_DOWNLOAD_URL", "http://loja.teste/app")


@pytest.fixture()
def emails_enviados(monkeypatch):
    enviados = []

    def enviar(to, subject, body_plain, body_html=None):
        enviados.append({"to": to, "texto": body_plain})

    monkeypatch.setattr(convite_service, "send_email", enviar)
    return enviados


def test_tarefa_envia_os_pendentes_com_os_links(gestor, email_configurado, emails_enviados, _db):
    _convidar(gestor, [{"email": "lu@parque.test"}])
    token = _convite(_db, "lu@parque.test").token

    enviar_convites_pendentes()

    assert len(emails_enviados) == 1
    assert emails_enviados[0]["to"] == "lu@parque.test"
    assert f"http://front.teste/convite?token={token}" in emails_enviados[0]["texto"]
    assert "http://loja.teste/app" in emails_enviados[0]["texto"]
    convite = _convite(_db, "lu@parque.test")
    assert convite.envio_estado == ENVIADO
    assert convite.enviado_em is not None

    enviar_convites_pendentes()
    assert len(emails_enviados) == 1  # não reenvia quem já saiu


def test_tarefa_ignora_vencido_cancelado_e_concluido(
    gestor, email_configurado, emails_enviados, _db
):
    _convidar(gestor, [{"email": "a@parque.test"}, {"email": "b@parque.test"}])
    _convidar(gestor, [{"email": "c@parque.test"}, {"email": "d@parque.test"}])
    vencido = _convite(_db, "a@parque.test")
    cancelado = _convite(_db, "b@parque.test")
    concluido = _convite(_db, "c@parque.test")
    vencido.expira_em = datetime.now(UTC) - timedelta(days=1)
    cancelado.estado = CANCELADO
    concluido.estado = CONCLUIDO
    _db.session.commit()

    enviar_convites_pendentes()

    assert [email["to"] for email in emails_enviados] == ["d@parque.test"]


def test_tarefa_marca_falhou_na_terceira_tentativa(gestor, email_configurado, monkeypatch, _db):
    def quebrado(**kwargs):
        raise RuntimeError("smtp fora do ar")

    monkeypatch.setattr(convite_service, "send_email", quebrado)
    _convidar(gestor, [{"email": "f@parque.test"}])

    estados = []
    for _ in range(4):
        enviar_convites_pendentes()
        convite = _convite(_db, "f@parque.test")
        estados.append((convite.envio_tentativas, convite.envio_estado))

    assert estados == [(1, ENVIO_PENDENTE), (2, ENVIO_PENDENTE), (3, FALHOU), (3, FALHOU)]


def test_tarefa_respeita_o_limite_por_execucao(gestor, email_configurado, emails_enviados):
    itens = [{"email": f"p{numero}@parque.test"} for numero in range(60)]
    _convidar(gestor, itens)

    enviar_convites_pendentes()
    assert len(emails_enviados) == 50

    enviar_convites_pendentes()
    assert len(emails_enviados) == 60


def test_tarefa_sem_email_configurado_mantem_a_fila(gestor, app, monkeypatch, emails_enviados, _db):
    monkeypatch.setitem(app.config, "MAIL_SERVER", "")
    _convidar(gestor, [{"email": "g@parque.test"}])

    enviar_convites_pendentes()

    assert emails_enviados == []
    assert _convite(_db, "g@parque.test").envio_estado == ENVIO_PENDENTE
