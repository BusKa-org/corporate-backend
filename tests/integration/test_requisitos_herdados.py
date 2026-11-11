"""RF-01, RF-03, RF-06, RF-07, RF-08: post-rename check.

These requirements came ready from the municipal product; what is checked here
is that they still hold after replacing `Prefeitura` with `Organizacao`.
"""

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from app.models.enum import StatusViagem
from app.models.password_reset import PasswordResetToken
from app.models.viagem import AlunosConfirmados, TelemetriaViagem
from tests.factories.user_factory import MotoristaFactory

SENHA = "StrongPass123!"


# RF-01: login/logout


@pytest.mark.integration
def test_rf01_login_devolve_token_e_dados_da_organizacao(client, gestor):
    r = client.post("/v1/auth/login", json={"email": gestor.user.email, "password": SENHA})
    assert r.status_code == 200, r.get_data(as_text=True)

    body = r.get_json() or {}
    assert body.get("token")
    assert body["user"]["id"] == str(gestor.user.id)


@pytest.mark.integration
def test_rf01_credenciais_invalidas_sao_recusadas(client, gestor):
    r = client.post("/v1/auth/login", json={"email": gestor.user.email, "password": "errada"})
    assert r.status_code == 401


@pytest.mark.integration
def test_rf01_token_valido_da_acesso_a_rota_protegida(gestor):
    """Logout is client side (discarding the token); what is checked is that the
    issued token opens a protected resource.
    """
    assert gestor.client.get("/v1/users/me").status_code == 200


# RF-03: password recovery


@pytest.mark.integration
def test_rf03_recuperacao_gera_token_e_permite_nova_senha(client, gestor, _db):
    user = gestor.user

    with patch("app.services.auth_service.send_email") as mock_email:
        r = client.post("/v1/auth/forgot-password", json={"email": user.email})
    assert r.status_code == 200
    assert mock_email.called

    registro = _db.session.query(PasswordResetToken).filter_by(user_id=user.id).one()

    nova = "OutraSenha456!"
    reset = client.post(
        "/v1/auth/reset-password",
        json={"token": registro.token, "new_password": nova, "confirm_password": nova},
    )
    assert reset.status_code == 200, reset.get_data(as_text=True)

    assert (
        client.post("/v1/auth/login", json={"email": user.email, "password": nova}).status_code
        == 200
    )


@pytest.mark.integration
def test_rf03_email_desconhecido_nao_revela_cadastro(client):
    r = client.post("/v1/auth/forgot-password", json={"email": "ninguem@buska.test"})
    assert r.status_code == 200


# RF-06: manage driver and vehicle


@pytest.mark.integration
def test_rf06_gestor_cadastra_e_lista_motorista(gestor):
    criado = gestor.client.post(
        "/v1/users/motoristas",
        json={
            "nome": "Motorista Novo",
            "email": "motorista.novo@buska.test",
            "password": SENHA,
            "cpf": "529.982.247-25",
            "telefone": "83999990000",
            "cnh": "12345678900",
        },
    )
    assert criado.status_code == 201, criado.get_data(as_text=True)

    listagem = gestor.client.get("/v1/users/motoristas")
    assert listagem.status_code == 200
    assert (listagem.get_json() or {})["total"] >= 1


@pytest.mark.integration
def test_rf06_gestor_gerencia_o_veiculo_com_capacidade(gestor, _db):
    criado = gestor.client.post(
        "/v1/onibus/",
        json={"placa": "ABC1D23", "modelo": "Elétrico 17", "capacidade": 17},
    )
    assert criado.status_code == 201, criado.get_data(as_text=True)
    veiculo_id = (criado.get_json() or {})["id"]

    atualizado = gestor.client.patch(f"/v1/onibus/{veiculo_id}", json={"capacidade": 20})
    assert atualizado.status_code == 200
    assert (atualizado.get_json() or {})["capacidade"] == 20

    assert gestor.client.delete(f"/v1/onibus/{veiculo_id}").status_code == 200


# RF-07: real-time location


@pytest.mark.integration
def test_rf07_motorista_publica_e_aluno_confirmado_le_a_localizacao(
    _db, viagem_futura_iniciada_com_motorista, motorista, aluno
):
    viagem = viagem_futura_iniciada_com_motorista
    _db.session.add(
        AlunosConfirmados(viagem_id=viagem.id, aluno_id=aluno.user.id, confirmacao=True)
    )
    _db.session.commit()

    envio = motorista.client.post(
        f"/v1/viagens/{viagem.id}/localizacao",
        json={"latitude": -7.2, "longitude": -35.9},
    )
    assert envio.status_code == 200, envio.get_data(as_text=True)

    leitura = aluno.client.get(f"/v1/viagens/{viagem.id}/localizacao")
    assert leitura.status_code == 200

    body = leitura.get_json() or {}
    assert body["latitude"] == pytest.approx(-7.2)
    assert body["atualizado_em"]


@pytest.mark.integration
def test_rf07_aluno_nao_confirmado_nao_ve_a_localizacao(
    viagem_futura_iniciada_com_motorista, aluno
):
    r = aluno.client.get(f"/v1/viagens/{viagem_futura_iniciada_com_motorista.id}/localizacao")
    assert r.status_code == 403


@pytest.mark.integration
def test_rf07_gestor_da_organizacao_le_a_localizacao(
    viagem_futura_iniciada_com_motorista, motorista, gestor
):
    viagem = viagem_futura_iniciada_com_motorista
    envio = motorista.client.post(
        f"/v1/viagens/{viagem.id}/localizacao",
        json={"latitude": -7.2, "longitude": -35.9},
    )
    assert envio.status_code == 200, envio.get_data(as_text=True)

    leitura = gestor.client.get(f"/v1/viagens/{viagem.id}/localizacao")
    assert leitura.status_code == 200, leitura.get_data(as_text=True)
    assert (leitura.get_json() or {})["longitude"] == pytest.approx(-35.9)


@pytest.mark.integration
def test_rf07_gestor_de_outra_organizacao_nao_ve_a_localizacao(
    viagem_futura_iniciada_com_motorista, other_gestor
):
    r = other_gestor.client.get(
        f"/v1/viagens/{viagem_futura_iniciada_com_motorista.id}/localizacao"
    )
    assert r.status_code == 403


@pytest.mark.integration
def test_rf07_gestor_de_outra_organizacao_nao_sonda_o_status_da_viagem(
    viagem_futura_agendada_com_motorista, other_gestor
):
    r = other_gestor.client.get(
        f"/v1/viagens/{viagem_futura_agendada_com_motorista.id}/localizacao"
    )
    assert r.status_code == 403


@pytest.mark.integration
def test_rf07_gestor_le_a_localizacao_de_viagem_sob_demanda(
    _db, viagem_solicitada, motorista, gestor
):
    viagem_solicitada.status = StatusViagem.EM_ANDAMENTO
    _db.session.commit()
    envio = motorista.client.post(
        f"/v1/viagens/{viagem_solicitada.id}/localizacao",
        json={"latitude": -7.2, "longitude": -35.9},
    )
    assert envio.status_code == 200, envio.get_data(as_text=True)

    leitura = gestor.client.get(f"/v1/viagens/{viagem_solicitada.id}/localizacao")
    assert leitura.status_code == 200, leitura.get_data(as_text=True)
    assert (leitura.get_json() or {})["latitude"] == pytest.approx(-7.2)


@pytest.mark.integration
def test_rf07_localizacao_com_id_invalido_e_recusada(gestor):
    r = gestor.client.get("/v1/viagens/abc/localizacao")
    assert r.status_code == 400


def _assert_localizacao_intacta(_db, viagem):
    _db.session.refresh(viagem)
    assert viagem.motorista_lat is None
    assert viagem.motorista_lon is None
    assert TelemetriaViagem.query.filter_by(viagem_id=viagem.id).count() == 0


@pytest.mark.integration
def test_rf07_motorista_de_outra_organizacao_nao_publica_a_localizacao(
    _db, viagem_futura_iniciada_com_motorista, other_motorista
):
    viagem = viagem_futura_iniciada_com_motorista
    r = other_motorista.client.post(
        f"/v1/viagens/{viagem.id}/localizacao", json={"latitude": -7.2, "longitude": -35.9}
    )
    assert r.status_code == 403
    _assert_localizacao_intacta(_db, viagem)


@pytest.mark.integration
def test_rf07_motorista_nao_designado_nao_publica_a_localizacao(
    _db, organizacao, viagem_futura_iniciada_com_motorista, motorista
):
    viagem = viagem_futura_iniciada_com_motorista
    designado = MotoristaFactory(organizacao_id=organizacao.id)
    _db.session.add(designado)
    _db.session.commit()
    viagem.motorista_id = designado.id
    _db.session.commit()

    r = motorista.client.post(
        f"/v1/viagens/{viagem.id}/localizacao", json={"latitude": -7.2, "longitude": -35.9}
    )
    assert r.status_code == 403
    _assert_localizacao_intacta(_db, viagem)


@pytest.mark.integration
def test_rf07_motorista_de_outra_organizacao_nao_sonda_o_status_da_viagem(
    viagem_futura_agendada_com_motorista, other_motorista
):
    r = other_motorista.client.post(
        f"/v1/viagens/{viagem_futura_agendada_com_motorista.id}/localizacao",
        json={"latitude": -7.2, "longitude": -35.9},
    )
    assert r.status_code == 403
    assert "AGENDADA" not in r.get_data(as_text=True)


@pytest.mark.integration
def test_rf07_localizacao_so_com_viagem_em_andamento(
    viagem_futura_agendada_com_motorista, motorista
):
    r = motorista.client.post(
        f"/v1/viagens/{viagem_futura_agendada_com_motorista.id}/localizacao",
        json={"latitude": -7.2, "longitude": -35.9},
    )
    assert r.status_code == 400


# RF-08: notifications


@pytest.mark.integration
def test_rf08_gestor_envia_aviso_para_a_viagem_e_o_aluno_recebe(
    _db, viagem_futura_agendada_com_motorista, gestor, aluno
):
    viagem = viagem_futura_agendada_com_motorista
    _db.session.add(
        AlunosConfirmados(viagem_id=viagem.id, aluno_id=aluno.user.id, confirmacao=True)
    )
    _db.session.commit()

    envio = gestor.client.post(
        "/v1/notificacoes/",
        json={
            "titulo": "Aviso de teste",
            "mensagem": "O veículo vai atrasar 10 minutos.",
            "viagem_id": str(viagem.id),
        },
    )
    assert envio.status_code == 201, envio.get_data(as_text=True)

    caixa = aluno.client.get("/v1/notificacoes/").get_json() or []
    assert any(n["titulo"] == "Aviso de teste" for n in caixa)

    aviso_id = caixa[0]["id"]
    assert aluno.client.patch(f"/v1/notificacoes/{aviso_id}/lida").status_code == 200


@pytest.mark.integration
def test_rf08_aluno_registra_o_token_de_push(aluno):
    r = aluno.client.patch("/v1/users/fcm-token", json={"fcm_token": "token-fcm-de-teste"})
    assert r.status_code == 200, r.get_data(as_text=True)


@pytest.mark.integration
def test_rf08_aluno_nao_dispara_aviso_em_massa(aluno, viagem_futura_agendada_com_motorista):
    r = aluno.client.post(
        "/v1/notificacoes/",
        json={
            "titulo": "Aviso",
            "mensagem": "Tentativa indevida",
            "viagem_id": str(viagem_futura_agendada_com_motorista.id),
        },
    )
    assert r.status_code == 403


@pytest.mark.integration
def test_rf08_notificacao_de_viagem_iniciada_chega_ao_confirmado(
    _db, viagem_futura_agendada_com_motorista, motorista, aluno
):
    viagem = viagem_futura_agendada_com_motorista
    _db.session.add(
        AlunosConfirmados(viagem_id=viagem.id, aluno_id=aluno.user.id, confirmacao=True)
    )
    _db.session.commit()

    r = motorista.client.put(f"/v1/viagens/{viagem.id}/acao", json={"acao": "INICIAR"})
    assert r.status_code == 200, r.get_data(as_text=True)

    _db.session.refresh(viagem)
    assert viagem.status == StatusViagem.EM_ANDAMENTO
    assert viagem.inicio_real is not None and viagem.inicio_real <= datetime.now(UTC)

    caixa = aluno.client.get("/v1/notificacoes/").get_json() or []
    assert any("Viagem Iniciada" in n["titulo"] for n in caixa)
