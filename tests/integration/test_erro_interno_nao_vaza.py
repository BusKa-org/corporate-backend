import pytest

from app.models.base import db


@pytest.mark.integration
def test_falha_de_banco_retorna_500_sem_detalhe_interno(gestor, onibus, monkeypatch):
    def commit_quebrado():
        raise RuntimeError("SELECT segredo FROM tabela_interna")

    monkeypatch.setattr(db.session, "commit", commit_quebrado)

    r = gestor.client.patch(f"/v1/onibus/{onibus.id}", json={"modelo": "Novo modelo"})

    assert r.status_code == 500
    corpo = r.get_data(as_text=True)
    assert "tabela_interna" not in corpo
    assert r.get_json()["error"]["message"] == "Erro interno do servidor"
