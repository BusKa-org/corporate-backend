"""Código rotativo do QR de embarque (RF-15): TOTP da RFC 6238 com HMAC-SHA1."""

import uuid
from datetime import UTC, datetime

import pytest
from flask import Flask

from app.models.credencial_embarque import CredencialEmbarque
from app.services import credencial_embarque_service as servico

# Apêndice B da RFC 6238, coluna SHA1: o segredo é o ASCII "12345678901234567890".
SEGREDO_RFC = b"12345678901234567890"
VETORES_RFC = [
    (59, "94287082"),
    (1111111109, "07081804"),
    (1111111111, "14050471"),
    (1234567890, "89005924"),
    (2000000000, "69279037"),
    (20000000000, "65353130"),
]


@pytest.mark.unit
@pytest.mark.parametrize(("segundos", "esperado"), VETORES_RFC)
def test_codigo_bate_com_os_vetores_da_rfc_6238(segundos, esperado):
    assert servico.gerar_codigo(SEGREDO_RFC, segundos // 30, 8) == esperado


@pytest.fixture()
def contexto():
    app = Flask(__name__)
    app.config.update(QR_PASSO_SEGUNDOS=30, QR_DIGITOS=8, QR_JANELA_PASSOS=1)
    with app.app_context():
        yield


def _no_segundo(segundos: int) -> datetime:
    return datetime.fromtimestamp(segundos, UTC)


@pytest.mark.unit
def test_janela_aceita_um_passo_de_cada_lado_e_recusa_dois(contexto):
    credencial = CredencialEmbarque(segredo=SEGREDO_RFC.hex())
    codigo = servico.gerar_codigo(SEGREDO_RFC, 1111111109 // 30, 8)
    passo = 1111111109 // 30 * 30

    assert servico.codigo_confere(credencial, codigo, _no_segundo(passo))
    assert servico.codigo_confere(credencial, codigo, _no_segundo(passo - 30))
    assert servico.codigo_confere(credencial, codigo, _no_segundo(passo + 59))
    assert not servico.codigo_confere(credencial, codigo, _no_segundo(passo + 60))
    assert not servico.codigo_confere(credencial, codigo, _no_segundo(passo - 31))


@pytest.mark.unit
def test_qr_e_separado_em_id_e_codigo():
    credencial_id = uuid.uuid4()

    assert servico.separar_qr(f" {credencial_id}.123456 ") == (credencial_id, "123456")
    assert servico.separar_qr(str(credencial_id)) is None
    assert servico.separar_qr("token-estatico-antigo") is None
    assert servico.separar_qr("nao-e-uuid.123456") is None
    assert servico.separar_qr(f"{credencial_id}.12ab56") is None
