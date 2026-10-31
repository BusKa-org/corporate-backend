"""Convites de cadastro de passageiro, pela API HTTP e pela tarefa de envio."""

import re
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
        codigo_externo="UEX-1",
        nome="Universidade Exemplo",
        sigla="UEX",
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
        codigo_externo="UOUTRA-1",
        nome="Universidade Outra",
        sigla="UOUTRA",
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
    resultados = _convidar(gestor, [{"email": "Ana@Org.test"}])

    assert resultados == [{"email": "ana@org.test", "resultado": "CRIADO", "motivo": ""}]
    convite = _convite(_db, "ana@org.test")
    assert convite.estado == PENDENTE
    assert convite.envio_estado == ENVIO_PENDENTE
    assert convite.organizacao_id == gestor.user.organizacao_id
    assert convite.expira_em > datetime.now(UTC) + timedelta(days=6)


def test_convidar_guarda_os_dados_opcionais(gestor, instituicao, _db):
    _convidar(
        gestor,
        [
            {
                "email": "bia@org.test",
                "nome": "Bia Souza",
                "cpf": "529.982.247-25",
                "telefone": "(83) 99999-9999",
                "instituicao_id": str(instituicao.id),
            }
        ],
    )

    convite = _convite(_db, "bia@org.test")
    assert convite.nome == "Bia Souza"
    assert convite.cpf == CPF_A
    assert convite.telefone == "83999999999"
    assert convite.instituicao_id == instituicao.id


def test_so_gestor_convida(aluno, motorista, client):
    corpo = {"convites": [{"email": "x@org.test"}]}

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
            {"email": "novo@org.test"},
            {"email": aluno.user.email},
            {"email": "novo@org.test"},
            {"email": "sem-arroba"},
            {"email": "cpf-ruim@org.test", "cpf": "123"},
            {"email": "cpf-usado@org.test", "cpf": CPF_B},
            {
                "email": "outra-org@org.test",
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
    itens = [{"email": f"p{numero}@org.test"} for numero in range(501)]

    response = gestor.client.post("/v1/convites", json={"convites": itens})

    assert response.status_code == 400
    assert Convite.query.count() == 0


def test_convidar_de_novo_pula_convite_pendente_e_renova_o_vencido(gestor, _db):
    _convidar(gestor, [{"email": "lia@org.test"}])
    convite = _convite(_db, "lia@org.test")
    token_antigo = convite.token

    repetido = _convidar(gestor, [{"email": "lia@org.test"}])
    assert repetido[0]["resultado"] == "PULADO"

    _vencer(_db, convite)
    renovado = _convidar(gestor, [{"email": "lia@org.test", "nome": "Lia"}])
    assert renovado[0]["resultado"] == "RENOVADO"

    convite = _convite(_db, "lia@org.test")
    assert Convite.query.count() == 1
    assert convite.token != token_antigo
    assert convite.nome == "Lia"
    assert convite.expira_em > datetime.now(UTC)


# ---------- listar, reenviar, cancelar ----------


def test_listar_mostra_so_a_propria_organizacao_e_filtra_por_estado(gestor, other_gestor, _db):
    _convidar(gestor, [{"email": "um@org.test"}, {"email": "dois@org.test"}])
    _convidar(other_gestor, [{"email": "outro@org.test"}])
    cancelado = _convite(_db, "dois@org.test")
    cancelado.estado = CANCELADO
    _db.session.commit()

    todos = gestor.client.get("/v1/convites").get_json()
    assert sorted(item["email"] for item in todos["items"]) == [
        "dois@org.test",
        "um@org.test",
    ]

    pendentes = gestor.client.get("/v1/convites?estado=PENDENTE").get_json()
    assert [item["email"] for item in pendentes["items"]] == ["um@org.test"]
    assert pendentes["items"][0]["vencido"] is False

    assert gestor.client.get("/v1/convites?estado=XPTO").status_code == 400


def test_reenviar_troca_o_token_e_o_antigo_deixa_de_valer(gestor, client, _db):
    _convidar(gestor, [{"email": "rui@org.test"}])
    convite = _convite(_db, "rui@org.test")
    token_antigo = convite.token
    convite.envio_estado = FALHOU
    convite.envio_tentativas = 3
    _db.session.commit()

    response = gestor.client.post(f"/v1/convites/{convite.id}/reenviar")

    assert response.status_code == 200
    convite = _convite(_db, "rui@org.test")
    assert convite.token != token_antigo
    assert convite.envio_estado == ENVIO_PENDENTE
    assert convite.envio_tentativas == 0
    assert client.get(f"/v1/convites/aceite/{token_antigo}").status_code == 404
    assert client.get(f"/v1/convites/aceite/{convite.token}").status_code == 200


def test_cancelar_invalida_o_link_e_so_vale_para_pendente(gestor, client, _db):
    _convidar(gestor, [{"email": "tom@org.test"}])
    convite = _convite(_db, "tom@org.test")

    assert gestor.client.delete(f"/v1/convites/{convite.id}").status_code == 200

    convite = _convite(_db, "tom@org.test")
    assert convite.estado == CANCELADO
    assert client.get(f"/v1/convites/aceite/{convite.token}").status_code == 404
    assert gestor.client.delete(f"/v1/convites/{convite.id}").status_code == 409
    assert gestor.client.post(f"/v1/convites/{convite.id}/reenviar").status_code == 409


def test_gestor_de_outra_organizacao_nao_mexe_no_convite(gestor, other_gestor, _db):
    _convidar(gestor, [{"email": "zeca@org.test"}])
    convite = _convite(_db, "zeca@org.test")

    assert other_gestor.client.post(f"/v1/convites/{convite.id}/reenviar").status_code == 404
    assert other_gestor.client.delete(f"/v1/convites/{convite.id}").status_code == 404
    assert _convite(_db, "zeca@org.test").estado == PENDENTE


# ---------- concluir pelo link ----------


def test_consultar_informa_o_que_falta(gestor, client, _db):
    _convidar(gestor, [{"email": "nina@org.test", "nome": "Nina"}])
    convite = _convite(_db, "nina@org.test")

    dados = client.get(f"/v1/convites/aceite/{convite.token}").get_json()

    assert dados["email"] == "nina@org.test"
    assert dados["nome"] == "Nina"
    assert dados["campos_faltando"] == ["cpf", "instituicao_id"]


def test_link_desconhecido_vencido_ou_concluido_da_a_mesma_resposta(
    gestor, client, instituicao, _db
):
    _convidar(gestor, [{"email": "vencido@org.test"}, {"email": "pronto@org.test"}])
    vencido = _convite(_db, "vencido@org.test")
    _vencer(_db, vencido)
    pronto = _convite(_db, "pronto@org.test")
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
    _convidar(gestor, [{"email": "otto@org.test"}])
    token = _convite(_db, "otto@org.test").token

    resposta = _concluir(client, token, senha=SENHA)

    assert resposta.status_code == 400
    assert Aluno.query.count() == 0
    assert _convite(_db, "otto@org.test").estado == PENDENTE


def test_concluir_cria_passageiro_ativo_que_consegue_entrar(gestor, client, instituicao, _db):
    _convidar(gestor, [{"email": "eva@org.test"}])
    convite = _convite(_db, "eva@org.test")

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
    aluno = Aluno.query.filter_by(email="eva@org.test").one()
    assert aluno.status == UserStatus.ACTIVE
    assert aluno.organizacao_id == gestor.user.organizacao_id
    assert aluno.instituicao_id == instituicao.id
    assert aluno.cpf == CPF_A

    convite = _convite(_db, "eva@org.test")
    assert convite.estado == CONCLUIDO
    assert convite.usuario_id == aluno.id
    assert convite.cpf is None and convite.nome is None and convite.telefone is None

    login = client.post("/v1/auth/login", json={"email": "eva@org.test", "password": SENHA})
    assert login.status_code == 200


def test_concluir_guarda_a_acessibilidade_informada(gestor, client, instituicao, _db):
    _convidar(gestor, [{"email": "lia@org.test"}])
    convite = _convite(_db, "lia@org.test")

    resposta = _concluir(
        client,
        convite.token,
        nome="Lia Souza",
        cpf=CPF_A,
        instituicao_id=str(instituicao.id),
        senha=SENHA,
        necessidades_acessibilidade=["CADEIRA_DE_RODAS"],
        observacao_acessibilidade="Cadeira motorizada",
    )

    assert resposta.status_code == 201, resposta.get_data(as_text=True)
    aluno = Aluno.query.filter_by(email="lia@org.test").one()
    assert aluno.necessidades_acessibilidade == ["CADEIRA_DE_RODAS"]
    assert aluno.observacao_acessibilidade == "Cadeira motorizada"


def test_convite_aceite_com_necessidade_invalida_400(gestor, client, instituicao, _db):
    _convidar(gestor, [{"email": "rui@org.test"}])
    convite = _convite(_db, "rui@org.test")

    resposta = _concluir(
        client,
        convite.token,
        nome="Rui Lima",
        cpf=CPF_A,
        instituicao_id=str(instituicao.id),
        senha=SENHA,
        necessidades_acessibilidade=["VOAR"],
    )

    assert resposta.status_code == 400
    assert Aluno.query.filter_by(email="rui@org.test").first() is None


def test_concluir_com_dados_do_gestor_aceita_correcao(gestor, client, instituicao, _db, caplog):
    _convidar(
        gestor,
        [
            {
                "email": "caio@org.test",
                "nome": "Caio Silvaa",
                "cpf": CPF_A,
                "instituicao_id": str(instituicao.id),
            }
        ],
    )
    token = _convite(_db, "caio@org.test").token

    with caplog.at_level("INFO", logger="app.audit"):
        resposta = _concluir(client, token, nome="Caio Silva", senha=SENHA)

    assert resposta.status_code == 201
    aluno = Aluno.query.filter_by(email="caio@org.test").one()
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
    _convidar(gestor, [{"email": "duda@org.test"}])
    token = _convite(_db, "duda@org.test").token
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

    assert Aluno.query.filter_by(email="duda@org.test").count() == 0
    assert _convite(_db, "duda@org.test").estado == PENDENTE


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
    _convidar(gestor, [{"email": "lu@org.test"}])
    token = _convite(_db, "lu@org.test").token

    enviar_convites_pendentes()

    assert len(emails_enviados) == 1
    assert emails_enviados[0]["to"] == "lu@org.test"
    assert f"http://front.teste/convite?token={token}" in emails_enviados[0]["texto"]
    assert "http://loja.teste/app" in emails_enviados[0]["texto"]
    convite = _convite(_db, "lu@org.test")
    assert convite.envio_estado == ENVIADO
    assert convite.enviado_em is not None

    enviar_convites_pendentes()
    assert len(emails_enviados) == 1  # não reenvia quem já saiu


def test_tarefa_ignora_vencido_cancelado_e_concluido(
    gestor, email_configurado, emails_enviados, _db
):
    _convidar(gestor, [{"email": "a@org.test"}, {"email": "b@org.test"}])
    _convidar(gestor, [{"email": "c@org.test"}, {"email": "d@org.test"}])
    vencido = _convite(_db, "a@org.test")
    cancelado = _convite(_db, "b@org.test")
    concluido = _convite(_db, "c@org.test")
    vencido.expira_em = datetime.now(UTC) - timedelta(days=1)
    cancelado.estado = CANCELADO
    concluido.estado = CONCLUIDO
    _db.session.commit()

    enviar_convites_pendentes()

    assert [email["to"] for email in emails_enviados] == ["d@org.test"]


def test_tarefa_marca_falhou_na_terceira_tentativa(gestor, email_configurado, monkeypatch, _db):
    def quebrado(**kwargs):
        raise RuntimeError("smtp fora do ar")

    monkeypatch.setattr(convite_service, "send_email", quebrado)
    _convidar(gestor, [{"email": "f@org.test"}])

    estados = []
    for _ in range(4):
        enviar_convites_pendentes()
        convite = _convite(_db, "f@org.test")
        estados.append((convite.envio_tentativas, convite.envio_estado))

    assert estados == [(1, ENVIO_PENDENTE), (2, ENVIO_PENDENTE), (3, FALHOU), (3, FALHOU)]


def test_tarefa_respeita_o_limite_por_execucao(gestor, email_configurado, emails_enviados):
    itens = [{"email": f"p{numero}@org.test"} for numero in range(60)]
    _convidar(gestor, itens)

    enviar_convites_pendentes()
    assert len(emails_enviados) == 50

    enviar_convites_pendentes()
    assert len(emails_enviados) == 60


def test_tarefa_sem_email_configurado_mantem_a_fila(gestor, app, monkeypatch, emails_enviados, _db):
    monkeypatch.setitem(app.config, "MAIL_SERVER", "")
    _convidar(gestor, [{"email": "g@org.test"}])

    enviar_convites_pendentes()

    assert emails_enviados == []
    assert _convite(_db, "g@org.test").envio_estado == ENVIO_PENDENTE


# ---------- PIN para quem digita o e-mail no app ----------


def _pedir_pin(client, email):
    return client.post("/v1/convites/pin", json={"email": email})


def _validar_pin(client, email, pin):
    return client.post("/v1/convites/pin/validar", json={"email": email, "pin": pin})


def _pin_do_ultimo_email(emails_enviados):
    return re.search(r"\b(\d{6})\b", emails_enviados[-1]["texto"]).group(1)


def _liberar_novo_pin(_db, email):
    convite = _convite(_db, email)
    convite.pin_enviado_em = datetime.now(UTC) - timedelta(minutes=5)
    _db.session.commit()


def test_pin_certo_devolve_o_token_do_convite_e_so_vale_uma_vez(
    gestor, client, email_configurado, emails_enviados, _db
):
    _convidar(gestor, [{"email": "pin@org.test"}])
    convite = _convite(_db, "pin@org.test")

    resposta = _pedir_pin(client, "pin@org.test")
    assert resposta.status_code == 200
    assert len(emails_enviados) == 1
    assert emails_enviados[0]["to"] == "pin@org.test"
    pin = _pin_do_ultimo_email(emails_enviados)

    errado = "000000" if pin != "000000" else "111111"
    assert _validar_pin(client, "pin@org.test", errado).status_code == 400

    certo = _validar_pin(client, "pin@org.test", pin)
    assert certo.status_code == 200
    assert certo.get_json()["token"] == convite.token
    assert client.get(f"/v1/convites/aceite/{convite.token}").status_code == 200

    assert _validar_pin(client, "pin@org.test", pin).status_code == 400


def test_pin_nao_revela_se_o_email_esta_habilitado(
    gestor, client, email_configurado, emails_enviados, _db
):
    _convidar(gestor, [{"email": "cancelado@org.test"}, {"email": "vencido@org.test"}])
    cancelado = _convite(_db, "cancelado@org.test")
    vencido = _convite(_db, "vencido@org.test")
    cancelado.estado = CANCELADO
    vencido.expira_em = datetime.now(UTC) - timedelta(days=1)
    _db.session.commit()

    respostas = [
        _pedir_pin(client, "desconhecido@org.test"),
        _pedir_pin(client, "cancelado@org.test"),
        _pedir_pin(client, "vencido@org.test"),
        _pedir_pin(client, "isto-nao-e-email"),
    ]

    for resposta in respostas:
        assert resposta.status_code == 200
        assert resposta.get_json() == respostas[0].get_json()
    assert emails_enviados == []
    assert _validar_pin(client, "desconhecido@org.test", "123456").status_code == 400


def test_pin_expira_em_dez_minutos(gestor, client, email_configurado, emails_enviados, _db):
    _convidar(gestor, [{"email": "tempo@org.test"}])
    _pedir_pin(client, "tempo@org.test")
    pin = _pin_do_ultimo_email(emails_enviados)
    convite = _convite(_db, "tempo@org.test")
    assert convite.pin_expira_em > datetime.now(UTC) + timedelta(minutes=9)

    convite.pin_expira_em = datetime.now(UTC) - timedelta(seconds=1)
    _db.session.commit()

    assert _validar_pin(client, "tempo@org.test", pin).status_code == 400


def test_pin_e_invalidado_depois_de_cinco_erros(
    gestor, client, email_configurado, emails_enviados, _db
):
    _convidar(gestor, [{"email": "forca@org.test"}])
    _pedir_pin(client, "forca@org.test")
    pin = _pin_do_ultimo_email(emails_enviados)
    errado = "000000" if pin != "000000" else "111111"

    for _ in range(5):
        assert _validar_pin(client, "forca@org.test", errado).status_code == 400

    assert _validar_pin(client, "forca@org.test", pin).status_code == 400

    # Um PIN novo, depois do intervalo, funciona.
    _liberar_novo_pin(_db, "forca@org.test")
    _pedir_pin(client, "forca@org.test")
    novo_pin = _pin_do_ultimo_email(emails_enviados)
    assert _validar_pin(client, "forca@org.test", novo_pin).status_code == 200


def test_pin_tem_intervalo_minimo_entre_envios(
    gestor, client, email_configurado, emails_enviados, _db
):
    _convidar(gestor, [{"email": "spam@org.test"}])

    _pedir_pin(client, "spam@org.test")
    _pedir_pin(client, "spam@org.test")
    assert len(emails_enviados) == 1

    _liberar_novo_pin(_db, "spam@org.test")
    _pedir_pin(client, "spam@org.test")
    assert len(emails_enviados) == 2


def test_reenviar_o_convite_invalida_o_pin_anterior(
    gestor, client, email_configurado, emails_enviados, _db
):
    _convidar(gestor, [{"email": "novo-link@org.test"}])
    _pedir_pin(client, "novo-link@org.test")
    pin = _pin_do_ultimo_email(emails_enviados)
    convite = _convite(_db, "novo-link@org.test")

    gestor.client.post(f"/v1/convites/{convite.id}/reenviar")

    assert _validar_pin(client, "novo-link@org.test", pin).status_code == 400


def _errar_um_pin_inteiro(client, _db, email, emails_enviados):
    """Pede um PIN novo e erra as 5 tentativas dele."""
    _liberar_novo_pin(_db, email)
    _pedir_pin(client, email)
    pin = _pin_do_ultimo_email(emails_enviados)
    errado = "000000" if pin != "000000" else "111111"
    for _ in range(5):
        assert _validar_pin(client, email, errado).status_code == 400


def test_erros_somados_de_varios_pins_bloqueiam_o_convite(
    gestor, client, app, monkeypatch, email_configurado, emails_enviados, _db
):
    monkeypatch.setitem(app.config, "CONVITE_PIN_MAX_ERROS_TOTAL", 10)
    eventos = []
    monkeypatch.setattr(
        convite_service.audit_logger,
        "log_security_event",
        lambda **kwargs: eventos.append(kwargs["event_type"]),
    )
    _convidar(gestor, [{"email": "lento@org.test"}])

    _errar_um_pin_inteiro(client, _db, "lento@org.test", emails_enviados)
    assert eventos == []
    _errar_um_pin_inteiro(client, _db, "lento@org.test", emails_enviados)
    assert eventos == ["convite_pin_bloqueado"]
    assert _convite(_db, "lento@org.test").pin_erros_total == 10

    # Pedir de novo não manda nada, e a resposta é a mesma de sempre.
    _liberar_novo_pin(_db, "lento@org.test")
    enviados_antes = len(emails_enviados)
    resposta = _pedir_pin(client, "lento@org.test")
    assert resposta.status_code == 200
    assert len(emails_enviados) == enviados_antes

    # Nem um PIN certo gravado no convite passa.
    convite = _convite(_db, "lento@org.test")
    convite.pin_hash = convite_service._hash_do_pin(convite, "123456")
    convite.pin_expira_em = datetime.now(UTC) + timedelta(minutes=10)
    convite.pin_tentativas = 0
    _db.session.commit()
    resposta = _validar_pin(client, "lento@org.test", "123456")
    assert resposta.status_code == 400
    assert resposta.get_json()["error"]["message"] == "PIN inválido ou expirado"


def test_reenvio_pelo_gestor_libera_o_pin_bloqueado(
    gestor, client, app, monkeypatch, email_configurado, emails_enviados, _db
):
    monkeypatch.setitem(app.config, "CONVITE_PIN_MAX_ERROS_TOTAL", 5)
    _convidar(gestor, [{"email": "liberado@org.test"}])
    _errar_um_pin_inteiro(client, _db, "liberado@org.test", emails_enviados)
    convite = _convite(_db, "liberado@org.test")
    assert convite.pin_erros_total == 5

    assert gestor.client.post(f"/v1/convites/{convite.id}/reenviar").status_code == 200
    assert _convite(_db, "liberado@org.test").pin_erros_total == 0

    _pedir_pin(client, "liberado@org.test")
    pin = _pin_do_ultimo_email(emails_enviados)
    assert _validar_pin(client, "liberado@org.test", pin).status_code == 200


def test_pin_sem_email_configurado_nao_envia_nada(
    gestor, client, app, monkeypatch, emails_enviados, _db
):
    monkeypatch.setitem(app.config, "MAIL_SERVER", "")
    _convidar(gestor, [{"email": "sem-smtp@org.test"}])

    resposta = _pedir_pin(client, "sem-smtp@org.test")

    assert resposta.status_code == 200
    assert emails_enviados == []
