"""RF-09 — consentimento LGPD versionado."""

import pytest

from app.models.consentimento import Consentimento
from app.services import consentimento_service


@pytest.mark.integration
def test_status_requer_autenticacao(client):
    r = client.get("/v1/consentimento")
    assert r.status_code in (401, 422)


@pytest.mark.integration
def test_status_sem_aceite(aluno):
    r = aluno.client.get("/v1/consentimento")
    assert r.status_code == 200, r.get_data(as_text=True)

    body = r.get_json() or {}
    assert body["aceito"] is False
    assert body["aceito_em"] is None
    assert body["versao_termo"] == "1.0"


@pytest.mark.integration
def test_registrar_aceite_grava_titular_versao_e_data(aluno, _db):
    r = aluno.client.post("/v1/consentimento")
    assert r.status_code == 201, r.get_data(as_text=True)

    body = r.get_json() or {}
    assert body["versao_termo"] == "1.0"
    assert body["aceito_em"]

    registro = _db.session.query(Consentimento).filter_by(usuario_id=aluno.user.id).one()
    assert registro.versao_termo == "1.0"
    assert registro.aceito_em is not None
    assert registro.revogado_em is None
    assert registro.ip_origem  # capturado da requisição

    r2 = aluno.client.get("/v1/consentimento")
    assert (r2.get_json() or {})["aceito"] is True


@pytest.mark.integration
def test_guarda_falsa_antes_e_verdadeira_depois_do_aceite(aluno):
    assert consentimento_service.tem_consentimento_vigente(str(aluno.user.id)) is False

    assert aluno.client.post("/v1/consentimento").status_code == 201

    assert consentimento_service.tem_consentimento_vigente(str(aluno.user.id)) is True


@pytest.mark.integration
def test_nova_versao_do_termo_invalida_aceite_anterior(aluno, app, _db, monkeypatch):
    assert aluno.client.post("/v1/consentimento").status_code == 201
    assert consentimento_service.tem_consentimento_vigente(str(aluno.user.id)) is True

    monkeypatch.setitem(app.config, "TERMO_VERSAO", "2.0")

    assert consentimento_service.tem_consentimento_vigente(str(aluno.user.id)) is False
    body = (aluno.client.get("/v1/consentimento")).get_json() or {}
    assert body["versao_termo"] == "2.0"
    assert body["aceito"] is False

    assert aluno.client.post("/v1/consentimento").status_code == 201
    assert consentimento_service.tem_consentimento_vigente(str(aluno.user.id)) is True

    # O aceite da versão anterior continua no histórico — é a prova do
    # consentimento dado à época.
    versoes = {
        c.versao_termo
        for c in _db.session.query(Consentimento).filter_by(usuario_id=aluno.user.id).all()
    }
    assert versoes == {"1.0", "2.0"}
