import os
import uuid

import pytest
from flask_jwt_extended import create_access_token

from app import create_app
from app.core.config import ConfigurationError, Settings
from app.extensions import limiter

PIN_VALIDAR = "/v1/convites/pin/validar"


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
    limiter._storage_dead = False
    return novo_app


@pytest.fixture()
def limitado(app):
    return _app_com_limite(app).test_client()


@pytest.mark.integration
def test_limite_estourado_devolve_429_no_formato_padrao(limitado):
    primeira = limitado.post(PIN_VALIDAR, json={})
    assert primeira.status_code == 400

    r = limitado.post(PIN_VALIDAR, json={})

    assert r.status_code == 429
    assert r.get_json()["error"]["code"] == "RATE_LIMITED"
    assert int(r.headers["Retry-After"]) > 0


@pytest.mark.integration
def test_ips_diferentes_nao_dividem_contagem(limitado):
    limitado.post(PIN_VALIDAR, json={}, environ_base={"REMOTE_ADDR": "10.0.0.1"})
    bloqueado = limitado.post(PIN_VALIDAR, json={}, environ_base={"REMOTE_ADDR": "10.0.0.1"})
    outro_ip = limitado.post(PIN_VALIDAR, json={}, environ_base={"REMOTE_ADDR": "10.0.0.2"})

    assert bloqueado.status_code == 429
    assert outro_ip.status_code == 400


@pytest.mark.integration
def test_rotas_diferentes_nao_dividem_contagem(limitado):
    limitado.post("/v1/auth/login", json={})
    limitado.post("/v1/auth/login", json={})
    assert limitado.post("/v1/auth/login", json={}).status_code == 429

    assert limitado.post("/v1/convites/pin", json={}).status_code == 400


@pytest.mark.integration
def test_usuarios_diferentes_nao_dividem_contagem(app, limitado, _db):
    with app.app_context():
        token_a = create_access_token(identity=str(uuid.uuid4()))
        token_b = create_access_token(identity=str(uuid.uuid4()))
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
def test_contagem_fica_no_redis(app):
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


@pytest.mark.integration
def test_producao_recusa_storage_em_memoria(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 40)
    monkeypatch.setenv("RATELIMIT_STORAGE_URI", "memory://")

    with pytest.raises(ConfigurationError, match="RATELIMIT_STORAGE_URI"):
        Settings()
