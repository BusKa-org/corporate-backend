"""RF-13/RF-14 pela API: declarar origem e destino durante o buffer, e o efeito do
cancelamento (RF-19) e do fim do buffer (RF-15) sobre a capacidade."""

from datetime import timedelta

import pytest
from flask_jwt_extended import create_access_token

from app.models.consentimento import ACEITE, Consentimento
from app.models.enum import StatusSolicitacao, StatusViagem
from app.models.viagem import AlunosConfirmados, SolicitacaoViagem
from app.services import buffer_service, capacidade_service
from app.services.consentimento_service import VERSAO_TERMO_VIGENTE
from app.services.notificacao_service import NotificacaoService
from tests.conftest import Actor, AuthenticatedClient
from tests.factories.user_factory import AlunoFactory
from tests.factories.viagem_factory import SolicitacaoViagemFactory


def _passageiro(client, app, _db, organizacao) -> Actor:
    u = AlunoFactory(organizacao_id=organizacao.id)
    _db.session.add(u)
    _db.session.commit()
    _db.session.add(Consentimento(usuario_id=u.id, versao=VERSAO_TERMO_VIGENTE, acao=ACEITE))
    _db.session.commit()
    with app.app_context():
        token = create_access_token(identity=str(u.id))
    headers = {"Authorization": f"Bearer {token}"}
    return Actor(user=u, headers=headers, client=AuthenticatedClient(client, headers))


@pytest.fixture()
def buffer(_db, viagem_buffer_aberto, onibus, aluno):
    """Buffer aberto com capacidade 1 e o `aluno` já solicitado."""
    onibus.capacidade = 1
    _db.session.add(
        SolicitacaoViagemFactory(viagem_id=viagem_buffer_aberto.id, aluno_id=aluno.user.id)
    )
    _db.session.commit()
    return viagem_buffer_aberto


def _declarar(actor, viagem, origem, destino):
    return actor.client.post(
        f"/v1/viagens/{viagem.id}/declaracao",
        json={"ponto_origem_id": str(origem.id), "ponto_destino_id": str(destino.id)},
    )


def test_declarar_trajeto_garante_o_lugar(buffer, aluno, pontos_circuito):
    p1, _, p3, _ = pontos_circuito

    r = _declarar(aluno, buffer, p1, p3)

    assert r.status_code == 200, r.get_data(as_text=True)
    corpo = r.get_json()
    assert corpo["status"] == "ATIVA"
    assert corpo["ponto_embarque_id"] == str(p1.id)
    assert corpo["ponto_destino_id"] == str(p3.id)
    assert capacidade_service.vetor_carga(buffer.id) == [1, 1, 0]


def test_trecho_lotado_nega_e_sugere_a_proxima_rodada(
    client, app, _db, buffer, aluno, organizacao, pontos_circuito
):
    p1, p2, _, _ = pontos_circuito
    outro = _passageiro(client, app, _db, organizacao)
    _db.session.add(SolicitacaoViagemFactory(viagem_id=buffer.id, aluno_id=outro.user.id))
    _db.session.commit()
    assert _declarar(aluno, buffer, p1, p2).status_code == 200

    r = _declarar(outro, buffer, p1, p2)

    assert r.status_code == 409
    assert "próxima rodada" in r.get_json()["error"]["message"]
    negada = SolicitacaoViagem.query.filter_by(viagem_id=buffer.id, aluno_id=outro.user.id).one()
    assert negada.status == StatusSolicitacao.NEGADA
    assert negada.ponto_embarque_id == p1.id


def test_declaracao_fora_do_buffer_e_recusada(_db, buffer, aluno, pontos_circuito):
    buffer.status = StatusViagem.SOLICITADA
    _db.session.commit()

    assert _declarar(aluno, buffer, pontos_circuito[0], pontos_circuito[1]).status_code == 400


def test_declaracao_com_buffer_vencido_e_recusada(_db, buffer, aluno, pontos_circuito):
    buffer.buffer_fim = buffer.buffer_fim - timedelta(minutes=10)
    _db.session.commit()

    assert _declarar(aluno, buffer, pontos_circuito[0], pontos_circuito[1]).status_code == 400


def test_origem_igual_ao_destino_e_recusada(buffer, aluno, pontos_circuito):
    assert _declarar(aluno, buffer, pontos_circuito[0], pontos_circuito[0]).status_code == 400


def test_quem_so_recebeu_o_aviso_entra_ao_declarar(
    client, app, _db, viagem_buffer_aberto, janela, relogio, organizacao, pontos_circuito
):
    """O broadcast vai para toda a organização: declarar já solicita a viagem."""
    viagem_buffer_aberto.data = relogio.agora.date()
    viagem_buffer_aberto.buffer_fim = relogio.agora + timedelta(minutes=5)
    _db.session.commit()
    novo = _passageiro(client, app, _db, organizacao)

    r = _declarar(novo, viagem_buffer_aberto, pontos_circuito[0], pontos_circuito[1])

    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["viagem_id"] == str(viagem_buffer_aberto.id)


def test_cancelar_durante_o_buffer_devolve_o_trecho(buffer, aluno, pontos_circuito):
    p1, _, p3, _ = pontos_circuito
    assert _declarar(aluno, buffer, p1, p3).status_code == 200

    r = aluno.client.delete(f"/v1/viagens/{buffer.id}/solicitacao")

    assert r.status_code == 200
    assert capacidade_service.vetor_carga(buffer.id) == [0, 0, 0]


def test_desistir_depois_da_partida_tira_da_lista_de_embarque(
    _db, buffer, aluno, motorista, pontos_circuito
):
    p1, _, p3, _ = pontos_circuito
    assert _declarar(aluno, buffer, p1, p3).status_code == 200
    buffer.buffer_fim = buffer.buffer_fim - timedelta(minutes=10)
    _db.session.commit()
    buffer_service.fechar_buffers_expirados()

    r = aluno.client.delete(f"/v1/viagens/{buffer.id}/solicitacao")

    assert r.status_code == 200
    assert r.get_json()["status"] == "DESISTENCIA"
    assert _db.session.get(AlunosConfirmados, (buffer.id, aluno.user.id)).confirmacao is False
    roteiro = motorista.client.get(f"/v1/embarque/viagens/{buffer.id}/roteiro").get_json()
    assert roteiro["pontos"][0]["embarcam"] == 0


def test_aviso_do_gestor_por_viagem_alcanca_quem_solicitou(app, _db, buffer, aluno, gestor):
    with app.test_request_context():
        resultado = NotificacaoService.notificar_por_gestor(
            str(gestor.user.id), {"viagem_id": str(buffer.id), "titulo": "Aviso", "mensagem": "Oi"}
        )

    assert resultado["message"].startswith("Notificação enviada para 1 aluno(s)")
