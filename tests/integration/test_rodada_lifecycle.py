"""RF-10 a RF-13 e RF-19 — ciclo da rodada sob demanda.

OCIOSA -> SOLICITADA -> BUFFER_ABERTO -> EM_ROTA, mais os fluxos secundários:
solicitação fora da janela, sem consentimento, segundo interessado sem nova
notificação ao motorista, e os dois cancelamentos do RF-19.
"""

from datetime import UTC, datetime, time, timedelta

import pytest

from app.models.enum import StatusSolicitacao, StatusViagem
from app.models.notificacao import Notificacao
from app.models.viagem import AlunosConfirmados
from app.services import consentimento_service, janela_service
from tests.factories.user_factory import AlunoFactory


@pytest.fixture()
def com_consentimento(_db, aluno):
    """RF-10 exige consentimento vigente (RF-09)."""
    consentimento_service.registrar_aceite(str(aluno.user.id))
    return aluno


@pytest.fixture()
def outro_aluno_consentido(_db, app, organizacao):
    from flask_jwt_extended import create_access_token

    from tests.conftest import Actor, AuthenticatedClient

    u = AlunoFactory(organizacao_id=organizacao.id)
    _db.session.add(u)
    _db.session.commit()
    consentimento_service.registrar_aceite(str(u.id))

    with app.app_context():
        token = create_access_token(identity=str(u.id))
    headers = {"Authorization": f"Bearer {token}"}
    return Actor(user=u, headers=headers, client=AuthenticatedClient(app.test_client(), headers))


@pytest.fixture()
def aluno_sem_consentimento(_db, organizacao):
    """Aluno da organização que nunca aceitou o termo — inapto ao RF-12."""
    u = AlunoFactory(organizacao_id=organizacao.id)
    _db.session.add(u)
    _db.session.commit()
    return u


def _notificacoes(_db, usuario_id):
    return _db.session.query(Notificacao).filter_by(usuario_id=usuario_id).all()


# ==========================================
# RF-10 — solicitar viagem
# ==========================================


@pytest.mark.integration
def test_solicitar_requer_autenticacao(client, viagem_ociosa):
    assert client.post("/v1/viagens/solicitar").status_code in (401, 422)


@pytest.mark.integration
def test_solicitar_sem_consentimento_e_recusado(aluno, viagem_ociosa):
    r = aluno.client.post("/v1/viagens/solicitar")
    assert r.status_code == 403, r.get_data(as_text=True)
    assert "termo" in (r.get_json() or {})["error"]["message"]


@pytest.mark.integration
def test_gestor_nao_solicita_viagem(gestor, viagem_ociosa):
    assert gestor.client.post("/v1/viagens/solicitar").status_code == 403


@pytest.mark.integration
def test_primeira_solicitacao_transita_para_solicitada_e_chama_o_motorista(
    com_consentimento, viagem_ociosa, motorista, _db
):
    r = com_consentimento.client.post("/v1/viagens/solicitar")
    assert r.status_code == 201, r.get_data(as_text=True)

    body = r.get_json() or {}
    assert body["status"] == "SOLICITADA"
    assert body["minha_situacao"] == "INTERESSADO"
    assert body["motorista_notificado"] is True

    _db.session.refresh(viagem_ociosa)
    assert viagem_ociosa.status == StatusViagem.SOLICITADA
    assert len(_notificacoes(_db, motorista.user.id)) == 1

    registro = _db.session.get(AlunosConfirmados, (viagem_ociosa.id, com_consentimento.user.id))
    assert registro.status == StatusSolicitacao.INTERESSADO


@pytest.mark.integration
def test_segundo_interessado_nao_notifica_o_motorista_de_novo(
    com_consentimento, outro_aluno_consentido, viagem_ociosa, motorista, _db
):
    """RF-10 fluxo secundário 1."""
    com_consentimento.client.post("/v1/viagens/solicitar")

    segunda = outro_aluno_consentido.client.post("/v1/viagens/solicitar")
    assert segunda.status_code == 201, segunda.get_data(as_text=True)

    body = segunda.get_json() or {}
    assert body["status"] == "SOLICITADA"
    assert body["motorista_notificado"] is False
    assert len(_notificacoes(_db, motorista.user.id)) == 1

    _db.session.refresh(viagem_ociosa)
    assert len(viagem_ociosa.alunos_confirmados) == 2


@pytest.mark.integration
def test_solicitar_de_novo_e_idempotente(com_consentimento, viagem_ociosa, motorista, _db):
    assert com_consentimento.client.post("/v1/viagens/solicitar").status_code == 201
    assert com_consentimento.client.post("/v1/viagens/solicitar").status_code == 201

    _db.session.refresh(viagem_ociosa)
    assert len(viagem_ociosa.alunos_confirmados) == 1
    assert len(_notificacoes(_db, motorista.user.id)) == 1


@pytest.mark.integration
def test_solicitar_fora_da_janela_nao_registra_e_devolve_os_horarios(
    com_consentimento, viagem_ociosa, janela_hoje, _db
):
    """RF-10 fluxo secundário 2."""
    agora = janela_service.agora_local()
    if agora.time() <= time(0, 1):
        janela_hoje.hora_inicio, janela_hoje.hora_fim = time(23, 58), time(23, 59)
    else:
        janela_hoje.hora_inicio, janela_hoje.hora_fim = time(0, 0), time(0, 1)
    _db.session.commit()

    r = com_consentimento.client.post("/v1/viagens/solicitar")
    assert r.status_code == 400, r.get_data(as_text=True)

    erro = (r.get_json() or {})["error"]
    assert erro["details"]["horarios_hoje"][0]["hora_inicio"] == janela_hoje.hora_inicio.strftime(
        "%H:%M"
    )

    _db.session.refresh(viagem_ociosa)
    assert viagem_ociosa.status == StatusViagem.OCIOSA
    assert viagem_ociosa.alunos_confirmados == []


@pytest.mark.integration
def test_solicitar_sem_rodada_criada_abre_uma(com_consentimento, janela_hoje, _db):
    """Sem viagem ociosa pré-existente a rodada nasce na primeira solicitação."""
    r = com_consentimento.client.post("/v1/viagens/solicitar")
    assert r.status_code == 201, r.get_data(as_text=True)
    assert (r.get_json() or {})["status"] == "SOLICITADA"


# ==========================================
# RF-11 / RF-12 — início do percurso e broadcast
# ==========================================


@pytest.mark.integration
def test_motorista_abre_o_buffer_e_dispara_o_broadcast(
    com_consentimento, outro_aluno_consentido, viagem_ociosa, motorista, _db
):
    com_consentimento.client.post("/v1/viagens/solicitar")

    r = motorista.client.post(f"/v1/viagens/{viagem_ociosa.id}/iniciar-percurso")
    assert r.status_code == 200, r.get_data(as_text=True)

    body = r.get_json() or {}
    assert body["status"] == "BUFFER_ABERTO"
    assert 0 < body["segundos_restantes"] <= 5 * 60

    _db.session.refresh(viagem_ociosa)
    assert viagem_ociosa.status == StatusViagem.BUFFER_ABERTO
    assert viagem_ociosa.buffer_expira_em is not None

    # RF-12: broadcast alcança todo aluno apto, não só quem solicitou.
    assert _notificacoes(_db, com_consentimento.user.id)
    assert _notificacoes(_db, outro_aluno_consentido.user.id)


@pytest.mark.integration
def test_broadcast_ignora_aluno_sem_consentimento(
    com_consentimento, aluno_sem_consentimento, viagem_ociosa, motorista, _db
):
    com_consentimento.client.post("/v1/viagens/solicitar")
    motorista.client.post(f"/v1/viagens/{viagem_ociosa.id}/iniciar-percurso")

    assert _notificacoes(_db, aluno_sem_consentimento.id) == []


@pytest.mark.integration
def test_so_o_motorista_da_rodada_inicia_o_percurso(
    com_consentimento, other_motorista, viagem_ociosa
):
    com_consentimento.client.post("/v1/viagens/solicitar")

    r = other_motorista.client.post(f"/v1/viagens/{viagem_ociosa.id}/iniciar-percurso")
    assert r.status_code == 403


@pytest.mark.integration
def test_aluno_nao_inicia_percurso(com_consentimento, viagem_ociosa):
    com_consentimento.client.post("/v1/viagens/solicitar")
    r = com_consentimento.client.post(f"/v1/viagens/{viagem_ociosa.id}/iniciar-percurso")
    assert r.status_code == 403


@pytest.mark.integration
def test_nao_da_para_abrir_buffer_de_rodada_ociosa(motorista, viagem_ociosa):
    r = motorista.client.post(f"/v1/viagens/{viagem_ociosa.id}/iniciar-percurso")
    assert r.status_code == 400


@pytest.mark.integration
def test_rodada_ativa_mostra_a_contagem_regressiva(com_consentimento, viagem_ociosa, motorista):
    """RF-12 fluxo secundário 1: sem push, o app ainda vê a rodada."""
    com_consentimento.client.post("/v1/viagens/solicitar")
    motorista.client.post(f"/v1/viagens/{viagem_ociosa.id}/iniciar-percurso")

    body = com_consentimento.client.get("/v1/viagens/rodada-ativa").get_json() or {}
    assert body["em_operacao"] is True
    assert body["rodada"]["status"] == "BUFFER_ABERTO"
    assert body["rodada"]["segundos_restantes"] > 0


# ==========================================
# RF-13 — declaração de trajeto
# ==========================================


@pytest.fixture()
def buffer_aberto(com_consentimento, viagem_ociosa, motorista, _db):
    com_consentimento.client.post("/v1/viagens/solicitar")
    motorista.client.post(f"/v1/viagens/{viagem_ociosa.id}/iniciar-percurso")
    _db.session.refresh(viagem_ociosa)
    return viagem_ociosa


@pytest.mark.integration
def test_declarar_trajeto_confirma_o_embarque(
    com_consentimento, buffer_aberto, pontos_circuito, _db
):
    p1, p2, _, _ = pontos_circuito

    r = com_consentimento.client.post(
        f"/v1/viagens/{buffer_aberto.id}/declaracao",
        json={"ponto_origem_id": str(p1.id), "ponto_destino_id": str(p2.id)},
    )
    assert r.status_code == 201, r.get_data(as_text=True)

    body = r.get_json() or {}
    assert body["status"] == "CONFIRMADO"
    assert body["ponto_embarque_id"] == str(p1.id)


@pytest.mark.integration
def test_declaracao_sem_vaga_devolve_indisponibilidade_momentanea(
    com_consentimento, outro_aluno_consentido, buffer_aberto, pontos_circuito, onibus, _db
):
    """RF-13 fluxo secundário 1 / RF-14 fluxo secundário 1."""
    onibus.capacidade = 1
    _db.session.commit()

    p1, p2, _, _ = pontos_circuito
    trajeto = {"ponto_origem_id": str(p1.id), "ponto_destino_id": str(p2.id)}

    assert (
        com_consentimento.client.post(
            f"/v1/viagens/{buffer_aberto.id}/declaracao", json=trajeto
        ).status_code
        == 201
    )

    negada = outro_aluno_consentido.client.post(
        f"/v1/viagens/{buffer_aberto.id}/declaracao", json=trajeto
    )
    assert negada.status_code == 409, negada.get_data(as_text=True)
    assert "próxima rodada" in (negada.get_json() or {})["error"]["message"]


@pytest.mark.integration
def test_declaracao_fora_do_buffer_e_recusada(com_consentimento, viagem_ociosa, pontos_circuito):
    p1, p2, _, _ = pontos_circuito
    r = com_consentimento.client.post(
        f"/v1/viagens/{viagem_ociosa.id}/declaracao",
        json={"ponto_origem_id": str(p1.id), "ponto_destino_id": str(p2.id)},
    )
    assert r.status_code == 400


@pytest.mark.integration
def test_declaracao_com_buffer_expirado_e_recusada(
    com_consentimento, buffer_aberto, pontos_circuito, _db
):
    """RF-13 fluxo secundário 2."""
    buffer_aberto.buffer_expira_em = datetime.now(UTC) - timedelta(seconds=1)
    _db.session.commit()

    p1, p2, _, _ = pontos_circuito
    r = com_consentimento.client.post(
        f"/v1/viagens/{buffer_aberto.id}/declaracao",
        json={"ponto_origem_id": str(p1.id), "ponto_destino_id": str(p2.id)},
    )
    assert r.status_code == 400


@pytest.mark.integration
def test_origem_precisa_ser_diferente_do_destino(com_consentimento, buffer_aberto, pontos_circuito):
    p1, _, _, _ = pontos_circuito
    r = com_consentimento.client.post(
        f"/v1/viagens/{buffer_aberto.id}/declaracao",
        json={"ponto_origem_id": str(p1.id), "ponto_destino_id": str(p1.id)},
    )
    assert r.status_code == 400


# ==========================================
# RF-19 — cancelamento
# ==========================================


@pytest.mark.integration
def test_cancelar_durante_o_buffer_libera_a_vaga(
    com_consentimento, outro_aluno_consentido, buffer_aberto, pontos_circuito, onibus, _db
):
    onibus.capacidade = 1
    _db.session.commit()

    p1, p2, _, _ = pontos_circuito
    trajeto = {"ponto_origem_id": str(p1.id), "ponto_destino_id": str(p2.id)}
    com_consentimento.client.post(f"/v1/viagens/{buffer_aberto.id}/declaracao", json=trajeto)

    cancelamento = com_consentimento.client.delete(f"/v1/viagens/{buffer_aberto.id}/declaracao")
    assert cancelamento.status_code == 200, cancelamento.get_data(as_text=True)
    assert (cancelamento.get_json() or {})["vaga_liberada"] is True

    # A vaga liberada é imediatamente utilizável por outro aluno.
    outra = outro_aluno_consentido.client.post(
        f"/v1/viagens/{buffer_aberto.id}/declaracao", json=trajeto
    )
    assert outra.status_code == 201, outra.get_data(as_text=True)


@pytest.mark.integration
def test_cancelar_depois_da_partida_registra_no_show_sem_reabrir_a_vaga(
    com_consentimento,
    outro_aluno_consentido,
    buffer_aberto,
    pontos_circuito,
    onibus,
    motorista,
    _db,
):
    """RF-19 fluxo secundário 1."""
    onibus.capacidade = 1
    _db.session.commit()

    p1, p2, _, _ = pontos_circuito
    trajeto = {"ponto_origem_id": str(p1.id), "ponto_destino_id": str(p2.id)}
    com_consentimento.client.post(f"/v1/viagens/{buffer_aberto.id}/declaracao", json=trajeto)

    buffer_aberto.status = StatusViagem.EM_ROTA
    buffer_aberto.buffer_expira_em = None
    _db.session.commit()

    cancelamento = com_consentimento.client.delete(f"/v1/viagens/{buffer_aberto.id}/declaracao")
    assert cancelamento.status_code == 200, cancelamento.get_data(as_text=True)
    assert (cancelamento.get_json() or {})["vaga_liberada"] is False

    registro = _db.session.get(AlunosConfirmados, (buffer_aberto.id, com_consentimento.user.id))
    _db.session.refresh(registro)
    assert registro.status == StatusSolicitacao.CONFIRMADO  # a vaga segue ocupada
    assert registro.confirmacao is False  # mas o embarque não acontece

    # O motorista é avisado da desistência.
    assert any("desistiu" in n.titulo.lower() for n in _notificacoes(_db, motorista.user.id))


@pytest.mark.integration
def test_cancelar_sem_solicitacao_e_404(com_consentimento, buffer_aberto):
    r = com_consentimento.client.delete(f"/v1/viagens/{buffer_aberto.id}/declaracao")
    assert r.status_code == 200  # interessado da rodada: cancela o interesse

    de_novo = com_consentimento.client.delete(f"/v1/viagens/{buffer_aberto.id}/declaracao")
    assert de_novo.status_code == 404


@pytest.mark.integration
def test_cancelar_viagem_finalizada_e_recusado(
    com_consentimento, buffer_aberto, pontos_circuito, _db
):
    p1, p2, _, _ = pontos_circuito
    com_consentimento.client.post(
        f"/v1/viagens/{buffer_aberto.id}/declaracao",
        json={"ponto_origem_id": str(p1.id), "ponto_destino_id": str(p2.id)},
    )

    buffer_aberto.status = StatusViagem.FINALIZADA
    _db.session.commit()

    r = com_consentimento.client.delete(f"/v1/viagens/{buffer_aberto.id}/declaracao")
    assert r.status_code == 400
