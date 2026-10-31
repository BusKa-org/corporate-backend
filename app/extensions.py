"""Flask extensions module to prevent circular imports."""

import hashlib
from collections.abc import Mapping
from typing import Any

from flask import current_app, request
from flask_apscheduler import APScheduler
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

scheduler = APScheduler()

# Tamanho máximo de um e-mail (RFC 5321); acima disso não vira chave no Redis.
_EMAIL_MAX = 254
_TOKEN_MAX = 512


def _chave_do_cliente() -> str:
    """Conta por usuário quando há um JWT válido; senão, pelo IP de conexão.

    O IP só sobra para rotas sem JWT e sem e-mail/token (o limite padrão das
    anônimas). Sem ProxyFix no app, o X-Forwarded-For não é confiável e fica de fora.
    """
    try:
        verify_jwt_in_request(optional=True)
        identidade = get_jwt_identity()
    except Exception:
        # Token expirado ou inválido: a rota responde 401 depois; aqui só conta pelo IP.
        identidade = None

    if identidade:
        return f"user:{identidade}"
    return f"ip:{get_remote_address()}"


def _corpo() -> Mapping[str, Any]:
    """Corpo JSON ou formulário, sem quebrar e sem consumir o corpo da view.

    get_json(silent=True) fica em cache no Flask, e o form também, então a view
    lê o mesmo corpo depois.
    """
    dados = request.get_json(silent=True)
    if isinstance(dados, dict):
        return dados
    return request.form


def _email_do_corpo() -> str | None:
    email = _corpo().get("email")
    if not isinstance(email, str):
        return None
    email = email.strip().lower()
    if "@" not in email or len(email) > _EMAIL_MAX:
        return None
    return email


def _token_da_requisicao() -> str | None:
    """Token do convite (na URL) ou do reset de senha (query string ou corpo)."""
    token = None
    if request.view_args:
        token = request.view_args.get("token")
    if not token:
        token = request.args.get("token")
    if not token:
        token = _corpo().get("token")
    if not isinstance(token, str):
        return None
    token = token.strip()
    if not token or len(token) > _TOKEN_MAX:
        return None
    return token


def _hash(valor: str) -> str:
    """Token de reset/convite e e-mail não podem aparecer em claro nas chaves do Redis."""
    return hashlib.sha256(valor.encode()).hexdigest()[:32]


def _chave_por_email() -> str:
    """Conta por e-mail: Wi-Fi do campus e NAT da operadora põem muitos alunos no
    mesmo IP. Sem e-mail válido, todos caem num balde só (vão falhar na validação)."""
    email = _email_do_corpo()
    if email is None:
        return "sem-email"
    return f"email:{_hash(email)}"


def _chave_por_token() -> str:
    token = _token_da_requisicao()
    if token is None:
        return "sem-token"
    return f"token:{_hash(token)}"


def _chave_por_email_ou_token() -> str:
    email = _email_do_corpo()
    if email is not None:
        return f"email:{_hash(email)}"
    return _chave_por_token()


def _limite(chave: str):
    """Lê o limite do config do app em cada requisição, e não na importação."""

    def ler() -> str:
        return current_app.config[chave]

    return ler


# per_method: GET e POST no mesmo caminho contam cada um no seu contador.
limiter = Limiter(
    key_func=_chave_do_cliente,
    default_limits=[_limite("RATELIMIT_DEFAULT")],
    default_limits_per_method=True,
)

limite_auth_por_email = limiter.limit(
    _limite("RATELIMIT_AUTH"), key_func=_chave_por_email, per_method=True
)
limite_auth_por_token = limiter.limit(
    _limite("RATELIMIT_AUTH"), key_func=_chave_por_token, per_method=True
)
limite_sensivel_por_email = limiter.limit(
    _limite("RATELIMIT_SENSITIVE"), key_func=_chave_por_email, per_method=True
)
limite_sensivel_por_email_ou_token = limiter.limit(
    _limite("RATELIMIT_SENSITIVE"), key_func=_chave_por_email_ou_token, per_method=True
)
# Rotas autenticadas: conta pela identidade do JWT.
limite_sensivel = limiter.limit(_limite("RATELIMIT_SENSITIVE"), per_method=True)
limite_tempo_real = limiter.limit(_limite("RATELIMIT_REALTIME"), per_method=True)


# Sondas de liveness/readiness batem a cada poucos segundos e não podem levar 429.
_ROTAS_ISENTAS = {"health", "ready"}


@limiter.request_filter
def _fora_do_limite() -> bool:
    # O Limiter é global: ler o flag do app deixa a suíte desligada mesmo que outro
    # create_app() do mesmo processo tenha ligado o limitador.
    if not current_app.config.get("RATELIMIT_ENABLED", True):
        return True
    # Preflight do CORS não conta: o navegador manda um antes de cada chamada.
    if request.method == "OPTIONS":
        return True
    return request.endpoint in _ROTAS_ISENTAS
