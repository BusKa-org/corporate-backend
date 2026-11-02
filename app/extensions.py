"""Flask extensions module to prevent circular imports."""

import hashlib
import hmac
from collections.abc import Mapping
from typing import Any

from flask import current_app, request
from flask_apscheduler import APScheduler
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

scheduler = APScheduler()

# Max e-mail length (RFC 5321); longer values never become a Redis key.
_EMAIL_MAX = 254
_TOKEN_MAX = 512


def _chave_do_cliente() -> str:
    """Counts per user when there is a valid JWT; otherwise by connection IP.

    Without ProxyFix in the app, X-Forwarded-For is not trusted and is ignored.
    """
    try:
        verify_jwt_in_request(optional=True)
        identidade = get_jwt_identity()
    except Exception:
        # Expired or invalid token: the route answers 401 later; here we just count by IP.
        identidade = None

    if identidade:
        return f"user:{identidade}"
    # IP is personal data too (LGPD): it only enters the key as an HMAC.
    return f"ip:{_hash(get_remote_address())}"


def _corpo() -> Mapping[str, Any]:
    """JSON or form body, without failing and without consuming the view's body.

    Flask caches get_json(silent=True) and the form, so the view reads the same body later.
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
    """Invite token (in the URL) or password reset token (query string or body)."""
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
    """Token, e-mail and IP must not appear in clear text in the Redis keys.

    HMAC with the app secret: a plain SHA-256 of an e-mail can be reversed by dictionary.
    Reuses JWT_SECRET_KEY; rotating it only resets the counters, which last a minute.
    """
    chave = current_app.config["JWT_SECRET_KEY"].encode()
    return hmac.new(chave, valor.encode(), hashlib.sha256).hexdigest()[:32]


def _chave_por_email() -> str:
    """Counts per e-mail: campus Wi-Fi and carrier NAT put many students on the
    same IP. Without a valid e-mail, all fall into one bucket (they fail validation).
    """
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
    """Reads the limit from the app config on each request, not at import time."""

    def ler() -> str:
        return current_app.config[chave]

    return ler


# per_method: GET and POST on the same path each have their own counter.
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
# Authenticated routes: count by JWT identity.
limite_sensivel = limiter.limit(_limite("RATELIMIT_SENSITIVE"), per_method=True)
limite_tempo_real = limiter.limit(_limite("RATELIMIT_REALTIME"), per_method=True)


# Liveness/readiness probes hit every few seconds and must never get a 429.
_ROTAS_ISENTAS = {"health", "ready"}


@limiter.request_filter
def _fora_do_limite() -> bool:
    # The Limiter is global: reading the app flag keeps the suite disabled even if
    # another create_app() in the same process enabled the limiter.
    if not current_app.config.get("RATELIMIT_ENABLED", True):
        return True
    # CORS preflight does not count: the browser sends one before every call.
    if request.method == "OPTIONS":
        return True
    return request.endpoint in _ROTAS_ISENTAS
