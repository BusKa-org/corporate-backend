import pytest

from app.models.notificacao import Notificacao


@pytest.mark.integration
def test_notificacao_sem_data_envio_retorna_null(aluno, _db):
    _db.session.add(Notificacao(usuario_id=aluno.user.id, titulo="Aviso", mensagem="Teste"))
    _db.session.commit()

    r = aluno.client.get("/v1/notificacoes/")
    assert r.status_code == 200
    assert r.get_json()[0]["data_envio"] is None
