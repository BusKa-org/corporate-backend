"""Flask extensions module to prevent circular imports."""

from flask import current_app, request
from flask_apscheduler import APScheduler
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

scheduler = APScheduler()


def _chave_do_cliente() -> str:
    """Conta por usuário quando há um JWT válido; senão, pelo IP de conexão.

    Sem ProxyFix no app, o X-Forwarded-For não é confiável e fica de fora.
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


def _limite(chave: str):
    """Lê o limite do config do app em cada requisição, e não na importação."""

    def ler() -> str:
        return current_app.config[chave]

    return ler


limiter = Limiter(key_func=_chave_do_cliente, default_limits=[_limite("RATELIMIT_DEFAULT")])

limite_auth = limiter.limit(_limite("RATELIMIT_AUTH"))
limite_sensivel = limiter.limit(_limite("RATELIMIT_SENSITIVE"))
limite_tempo_real = limiter.limit(_limite("RATELIMIT_REALTIME"))


# Sondas de liveness/readiness batem a cada poucos segundos e não podem levar 429.
_ROTAS_ISENTAS = {"health", "ready"}


@limiter.request_filter
def _fora_do_limite() -> bool:
    # O Limiter é global: ler o flag do app deixa a suíte desligada mesmo que outro
    # create_app() do mesmo processo tenha ligado o limitador.
    if not current_app.config.get("RATELIMIT_ENABLED", True):
        return True
    return request.endpoint in _ROTAS_ISENTAS
