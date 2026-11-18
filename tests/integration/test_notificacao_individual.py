import pytest

from app.models.notificacao import Notificacao


@pytest.mark.integration
def test_gestor_notifica_so_o_destinatario(gestor, aluno, motorista, _db):
    r = gestor.client.post(
        "/v1/notificacoes/",
        json={"titulo": "Aviso", "mensagem": "Só para você", "destinatario_id": str(aluno.user.id)},
    )
    assert r.status_code == 201

    notificacoes = Notificacao.query.all()
    assert len(notificacoes) == 1
    assert notificacoes[0].usuario_id == aluno.user.id


@pytest.mark.integration
def test_gestor_nao_notifica_usuario_de_outra_organizacao(gestor, other_aluno, _db):
    r = gestor.client.post(
        "/v1/notificacoes/",
        json={"titulo": "Aviso", "mensagem": "Teste", "destinatario_id": str(other_aluno.user.id)},
    )
    assert r.status_code == 404
    assert Notificacao.query.count() == 0
