import os
import uuid

import pytest
from flask import request
from flask_jwt_extended import create_access_token

from app import create_app
from app.core.config import ConfigurationError, Settings
from app.extensions import (
    _chave_do_cliente,
    _chave_por_email,
    _chave_por_email_ou_token,
    _chave_por_token,
    _hash,
    limiter,
)
from app.models.enum import UserStatus

PIN_VALIDAR = "/v1/convites/pin/validar"
LOGIN = "/v1/auth/login"


def _app_com_limite(app, **extra):
    """App próprio com limites minúsculos; o da suíte tem o limitador desligado."""
    config = {
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": app.config["SQLALCHEMY_DATABASE_URI"],
        "JWT_SECRET_KEY": app.config["JWT_SECRET_KEY"],
        "RATELIMIT_ENABLED": True,
        "RATELIMIT_STORAGE_URI": "memory://",
        "RATELIMIT_DEFAULT": "3 per minute",
        "RATELIMIT_AUTH": "2 per minute",
        "RATELIMIT_SENSITIVE": "1 per minute",
        "RATELIMIT_REALTIME": "2 per minute",
    }
    config.update(extra)
    novo_app = create_app(config_overrides=config, plugins=[])
    # O Limiter é global: sem isso, o teste do Redis caído deixa os seguintes em memória.
    # O flask-limiter não tem API pública para isso; o assert falha alto se o nome mudar.
    assert hasattr(limiter, "_storage_dead")
    limiter._storage_dead = False
    return novo_app


@pytest.fixture()
def limitado(app):
    return _app_com_limite(app).test_client()


def _corpo_do_429(r):
    assert r.status_code == 429
    corpo = r.get_json()
    # Um formato só: nada de "message" no topo (o flask-restx acrescenta se deixar).
    assert set(corpo) == {"error"}
    assert corpo["error"]["code"] == "RATE_LIMITED"
    assert corpo["error"]["details"]["limit"]
    assert int(r.headers["Retry-After"]) > 0


@pytest.mark.integration
def test_limite_estourado_devolve_429_no_formato_padrao(limitado):
    primeira = limitado.post(PIN_VALIDAR, json={})
    assert primeira.status_code == 400

    _corpo_do_429(limitado.post(PIN_VALIDAR, json={}))


@pytest.mark.integration
def test_limite_padrao_devolve_o_mesmo_429(limitado):
    # /v1/users/me não tem limite próprio: cai no RATELIMIT_DEFAULT (3 por minuto).
    for _ in range(3):
        assert limitado.get("/v1/users/me").status_code == 401

    _corpo_do_429(limitado.get("/v1/users/me"))


@pytest.mark.integration
def test_login_conta_por_email_e_nao_por_ip(limitado):
    for ip in ("10.0.0.1", "10.0.0.2"):
        limitado.post(
            LOGIN, json={"email": "A@x.com", "password": "e"}, environ_base={"REMOTE_ADDR": ip}
        )
    # Mesmo e-mail (normalizado) vindo de um terceiro IP: já estourou.
    bloqueado = limitado.post(
        LOGIN,
        json={"email": " a@X.com ", "password": "e"},
        environ_base={"REMOTE_ADDR": "10.0.0.3"},
    )
    # Outro aluno atrás do mesmo IP (Wi-Fi do campus) segue entrando.
    outro_email = limitado.post(
        LOGIN, json={"email": "b@x.com", "password": "e"}, environ_base={"REMOTE_ADDR": "10.0.0.1"}
    )

    assert bloqueado.status_code == 429
    assert outro_email.status_code != 429


@pytest.mark.integration
def test_aceite_conta_por_token_e_por_metodo(limitado):
    url = f"/v1/convites/aceite/{uuid.uuid4()}"
    limitado.get(url)
    limitado.get(url)
    assert limitado.get(url).status_code == 429

    # POST no mesmo caminho tem contador próprio, e outro token também.
    assert limitado.post(url, json={}).status_code != 429
    assert limitado.get(f"/v1/convites/aceite/{uuid.uuid4()}").status_code != 429


@pytest.mark.integration
def test_rotas_diferentes_nao_dividem_contagem(limitado):
    limitado.post(LOGIN, json={})
    limitado.post(LOGIN, json={})
    assert limitado.post(LOGIN, json={}).status_code == 429

    assert limitado.post("/v1/convites/pin", json={}).status_code == 400


@pytest.mark.integration
def test_preflight_do_cors_nao_conta(limitado):
    preflight = {
        "Origin": "http://front.example",
        "Access-Control-Request-Method": "GET",
    }
    # /v1/users/me cai no limite padrão (3 por minuto), que é checado antes da view.
    for _ in range(5):
        assert limitado.options("/v1/users/me", headers=preflight).status_code == 200

    assert limitado.get("/v1/users/me").status_code == 401


@pytest.mark.integration
def test_cors_expoe_os_headers_do_limite(limitado):
    r = limitado.post(PIN_VALIDAR, json={}, headers={"Origin": "http://front.example"})

    expostos = r.headers["Access-Control-Expose-Headers"]
    for nome in ("Retry-After", "X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"):
        assert nome in expostos


@pytest.mark.integration
@pytest.mark.parametrize(
    "kwargs",
    [
        {"data": "nao e json", "content_type": "application/json"},
        {"data": "email=a@x.com", "content_type": "text/plain"},
        {"json": ["a@x.com"]},
        {"json": {"email": 123}},
        {"json": {"email": "sem-arroba"}},
        {"json": {"email": "a" * 300 + "@x.com"}},
    ],
)
def test_corpo_sem_email_valido_cai_num_balde_so(app, kwargs):
    with app.test_request_context(LOGIN, method="POST", **kwargs):
        assert _chave_por_email() == "sem-email"


@pytest.mark.integration
def test_chave_do_email_nao_consome_o_corpo(app):
    with app.test_request_context(LOGIN, method="POST", json={"email": " A@X.com "}):
        assert _chave_por_email() == f"email:{_hash('a@x.com')}"
        assert request.get_json() == {"email": " A@X.com "}


@pytest.mark.integration
def test_reset_de_senha_conta_pelo_token_sem_email(app):
    with app.test_request_context(
        "/v1/auth/reset-password", method="POST", data={"token": "abc", "new_password": "x"}
    ):
        assert _chave_por_email_ou_token() == f"token:{_hash('abc')}"
        assert request.form["new_password"] == "x"


@pytest.mark.integration
def test_chave_nao_guarda_token_nem_email_em_claro(app):
    token = str(uuid.uuid4())
    url = f"/v1/convites/aceite/{token}"
    with app.test_request_context(url):
        chave = _chave_por_token()
    with app.test_request_context(url, method="POST"):
        mesma_chave = _chave_por_token()
    with app.test_request_context(f"/v1/convites/aceite/{uuid.uuid4()}"):
        outra_chave = _chave_por_token()
    assert token not in chave
    assert chave == mesma_chave
    assert chave != outra_chave

    with app.test_request_context(LOGIN, method="POST", json={"email": "a@x.com"}):
        assert "a@x.com" not in _chave_por_email()


@pytest.mark.integration
def test_jwt_invalido_conta_pelo_ip(app):
    with app.test_request_context(
        "/v1/users/me",
        headers={"Authorization": "Bearer nao-e-um-jwt"},
        environ_base={"REMOTE_ADDR": "10.0.0.9"},
    ):
        assert _chave_do_cliente() == f"ip:{_hash('10.0.0.9')}"


@pytest.mark.integration
def test_token_de_conta_excluida_conta_pelo_ip(app, aluno, _db):
    """O token revogado não pode virar 500 na chave do limitador: cai para o IP."""
    aluno.user.status = UserStatus.DELETED
    _db.session.commit()
    with app.test_request_context(
        "/v1/users/me", headers=aluno.headers, environ_base={"REMOTE_ADDR": "10.0.0.9"}
    ):
        assert _chave_do_cliente() == f"ip:{_hash('10.0.0.9')}"


@pytest.mark.integration
def test_usuarios_diferentes_nao_dividem_contagem(app, limitado, aluno, other_aluno):
    with app.app_context():
        token_a = create_access_token(identity=str(aluno.user.id))
        token_b = create_access_token(identity=str(other_aluno.user.id))
    url = f"/v1/viagens/{uuid.uuid4()}/localizacao"

    for _ in range(2):
        limitado.get(url, headers={"Authorization": f"Bearer {token_a}"})
    bloqueado = limitado.get(url, headers={"Authorization": f"Bearer {token_a}"})
    outro_usuario = limitado.get(url, headers={"Authorization": f"Bearer {token_b}"})

    assert bloqueado.status_code == 429
    assert outro_usuario.status_code != 429


@pytest.mark.integration
def test_health_e_ready_ficam_fora_do_limite(limitado):
    for _ in range(5):
        assert limitado.get("/health").status_code == 200
        assert limitado.get("/ready").status_code != 429


@pytest.mark.integration
def test_limitador_desligado_na_suite(client):
    for _ in range(5):
        assert client.post(PIN_VALIDAR, json={}).status_code == 400


@pytest.mark.integration
def test_storage_fora_do_ar_nao_derruba_a_api(app):
    # Porta 1 recusa conexão na hora: simula o Redis caído.
    cliente = _app_com_limite(app, RATELIMIT_STORAGE_URI="redis://127.0.0.1:1/0").test_client()

    assert cliente.post(PIN_VALIDAR, json={}).status_code == 400
    assert cliente.post(PIN_VALIDAR, json={}).status_code == 429


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("REDIS_URL"), reason="REDIS_URL não definido")
def test_contagem_fica_no_redis(app, _db):
    import redis

    redis_url = os.environ["REDIS_URL"]
    conexao = redis.from_url(redis_url)
    conexao.flushdb()
    cliente = _app_com_limite(app, RATELIMIT_STORAGE_URI=redis_url).test_client()

    cliente.post(PIN_VALIDAR, json={})
    r = cliente.post(PIN_VALIDAR, json={})

    assert r.status_code == 429
    # A chave no Redis é o que faz todos os workers do gunicorn verem a mesma contagem.
    assert conexao.keys("LIMITS:*")

    token = str(uuid.uuid4())
    cliente.get(f"/v1/convites/aceite/{token}")
    cliente.post(LOGIN, json={"email": "segredo@x.com", "password": "e"})
    # Rota anônima sem limite próprio: conta pelo IP no limite padrão.
    cliente.get("/v1/users/me")
    chaves = conexao.keys("*")
    # Sem estas chaves o laço abaixo passaria sem checar nada.
    for prefixo in (b"token:", b"email:", b"ip:"):
        assert any(prefixo in chave for chave in chaves), prefixo
    for chave in chaves:
        assert token.encode() not in chave
        assert b"segredo@x.com" not in chave
        assert b"127.0.0.1" not in chave


@pytest.mark.integration
def test_producao_recusa_storage_em_memoria(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 40)
    monkeypatch.setenv("RATELIMIT_STORAGE_URI", "memory://")

    with pytest.raises(ConfigurationError, match="RATELIMIT_STORAGE_URI"):
        Settings()
