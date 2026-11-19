import pytest

from app.models.enum import StatusViagem, UserStatus
from app.models.notificacao import Notificacao
from app.models.rota import RotaAluno
from tests.factories.onibus_factory import OnibusFactory
from tests.factories.rota_factory import RotaFactory
from tests.factories.user_factory import AlunoFactory
from tests.factories.viagem_factory import AlunosConfirmadosFactory, ViagemFactory


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


@pytest.mark.integration
def test_motorista_nao_envia_aviso_individual(
    motorista, aluno, viagem_futura_iniciada_com_motorista
):
    r = motorista.client.post(
        "/v1/notificacoes/",
        json={
            "titulo": "Aviso",
            "mensagem": "Teste",
            "viagem_id": str(viagem_futura_iniciada_com_motorista.id),
            "destinatario_id": str(aluno.user.id),
        },
    )
    assert r.status_code == 403
    assert Notificacao.query.count() == 0


@pytest.mark.integration
def test_destinatario_id_invalido_retorna_400(gestor, _db):
    r = gestor.client.post(
        "/v1/notificacoes/",
        json={"titulo": "Aviso", "mensagem": "Teste", "destinatario_id": "nao-e-uuid"},
    )
    assert r.status_code == 400


def _rota_e_viagem_de_outra_organizacao(_db, other_organizacao, other_aluno):
    onibus = OnibusFactory(organizacao_id=other_organizacao.id)
    _db.session.add(onibus)
    _db.session.flush()
    rota = RotaFactory(
        organizacao_id=other_organizacao.id, motorista_padrao_id=None, veiculo_padrao_id=onibus.id
    )
    _db.session.add(rota)
    _db.session.flush()
    viagem = ViagemFactory(rota_id=rota.id)
    _db.session.add(viagem)
    _db.session.flush()
    _db.session.add(RotaAluno(rota_id=rota.id, aluno_id=other_aluno.user.id))
    _db.session.add(
        AlunosConfirmadosFactory(
            viagem_id=viagem.id, aluno_id=other_aluno.user.id, confirmacao=True
        )
    )
    _db.session.commit()
    return rota, viagem


@pytest.mark.integration
def test_gestor_nao_notifica_rota_de_outra_organizacao(gestor, other_organizacao, other_aluno, _db):
    rota, _ = _rota_e_viagem_de_outra_organizacao(_db, other_organizacao, other_aluno)
    r = gestor.client.post(
        "/v1/notificacoes/",
        json={"titulo": "Aviso", "mensagem": "Teste", "rota_id": str(rota.id)},
    )
    assert r.status_code == 404
    assert Notificacao.query.count() == 0


@pytest.mark.integration
def test_gestor_nao_notifica_viagem_de_outra_organizacao(
    gestor, other_organizacao, other_aluno, _db
):
    _, viagem = _rota_e_viagem_de_outra_organizacao(_db, other_organizacao, other_aluno)
    r = gestor.client.post(
        "/v1/notificacoes/",
        json={"titulo": "Aviso", "mensagem": "Teste", "viagem_id": str(viagem.id)},
    )
    assert r.status_code == 404
    assert Notificacao.query.count() == 0


@pytest.mark.integration
def test_gestor_nao_notifica_conta_excluida(gestor, aluno, _db):
    aluno.user.status = UserStatus.DELETED
    _db.session.commit()
    r = gestor.client.post(
        "/v1/notificacoes/",
        json={"titulo": "Aviso", "mensagem": "Teste", "destinatario_id": str(aluno.user.id)},
    )
    assert r.status_code == 404
    assert Notificacao.query.count() == 0


@pytest.mark.integration
def test_destinatario_com_rota_retorna_400(gestor, aluno, rota, _db):
    r = gestor.client.post(
        "/v1/notificacoes/",
        json={
            "titulo": "Aviso",
            "mensagem": "Teste",
            "destinatario_id": str(aluno.user.id),
            "rota_id": str(rota.id),
        },
    )
    assert r.status_code == 400
    assert Notificacao.query.count() == 0


def _confirmar_aluno(_db, viagem, aluno):
    _db.session.add(
        AlunosConfirmadosFactory(viagem_id=viagem.id, aluno_id=aluno.user.id, confirmacao=True)
    )
    _db.session.commit()


@pytest.mark.integration
def test_gestor_notifica_passageiros_e_motorista_da_viagem(
    gestor, aluno, organizacao, motorista, viagem_futura_iniciada_com_motorista, _db
):
    viagem = viagem_futura_iniciada_com_motorista
    # Subscribed to the route but not on this trip: must not receive the trip notice.
    so_inscrito = AlunoFactory(organizacao_id=organizacao.id)
    _db.session.add(so_inscrito)
    _db.session.flush()
    _db.session.add(RotaAluno(rota_id=viagem.horario_rota.rota_id, aluno_id=so_inscrito.id))
    _confirmar_aluno(_db, viagem, aluno)

    r = gestor.client.post(
        "/v1/notificacoes/",
        json={"titulo": "Aviso", "mensagem": "Atraso", "viagem_id": str(viagem.id)},
    )
    assert r.status_code == 201

    destinatarios = set()
    for notificacao in Notificacao.query.all():
        destinatarios.add(notificacao.usuario_id)
    assert destinatarios == {aluno.user.id, motorista.user.id}


@pytest.mark.integration
@pytest.mark.parametrize("status", [StatusViagem.FINALIZADA, StatusViagem.CANCELADA])
def test_gestor_nao_notifica_viagem_encerrada(
    gestor, aluno, viagem_futura_iniciada_com_motorista, _db, status
):
    viagem = viagem_futura_iniciada_com_motorista
    viagem.status = status
    _confirmar_aluno(_db, viagem, aluno)

    r = gestor.client.post(
        "/v1/notificacoes/",
        json={"titulo": "Aviso", "mensagem": "Teste", "viagem_id": str(viagem.id)},
    )
    assert r.status_code == 400
    assert Notificacao.query.count() == 0


@pytest.mark.integration
def test_motorista_nao_recebe_o_proprio_aviso(
    motorista, aluno, viagem_futura_iniciada_com_motorista, _db
):
    viagem = viagem_futura_iniciada_com_motorista
    _confirmar_aluno(_db, viagem, aluno)

    r = motorista.client.post(
        "/v1/notificacoes/",
        json={"titulo": "Aviso", "mensagem": "Teste", "viagem_id": str(viagem.id)},
    )
    assert r.status_code == 201
    notificacoes = Notificacao.query.all()
    assert len(notificacoes) == 1
    assert notificacoes[0].usuario_id == aluno.user.id


@pytest.mark.integration
def test_motorista_nao_usa_a_viagem_para_avisar_a_rota(
    motorista, viagem_futura_iniciada_com_motorista, _db
):
    viagem = viagem_futura_iniciada_com_motorista
    r = motorista.client.post(
        "/v1/notificacoes/",
        json={
            "titulo": "Aviso",
            "mensagem": "Teste",
            "viagem_id": str(viagem.id),
            "rota_id": str(viagem.horario_rota.rota_id),
        },
    )
    assert r.status_code == 400
    assert Notificacao.query.count() == 0
