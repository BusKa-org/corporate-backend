"""Follow-ups from the reviews of PRs #58-#67 (gestor flows)."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import update

from app.core.exceptions import NotFoundError
from app.models.enum import StatusViagem, UserStatus
from app.models.notificacao import Notificacao
from app.models.viagem import AlunosConfirmados, Viagem
from app.services import viagens_service
from app.services.notificacao_service import NotificacaoService


def _cancelar(gestor, viagem):
    return gestor.client.put(f"/v1/viagens/{viagem.id}/cancelar", json={})


@pytest.mark.integration
def test_travar_viagem_removida_da_404(_db):
    with pytest.raises(NotFoundError):
        viagens_service._travar_viagem(uuid.uuid4())


@pytest.mark.integration
def test_cancelar_trava_rota_antes_da_viagem_e_rele_o_status(
    gestor, viagem_solicitada, monkeypatch, _db
):
    ordem: list[str] = []
    travar_rota_original = viagens_service.travar_rota
    travar_viagem_original = viagens_service._travar_viagem

    def travar_rota(rota_id):
        ordem.append("rota")
        resultado = travar_rota_original(rota_id)
        # Someone else cancels the trip while we wait for the route lock.
        _db.session.execute(
            update(Viagem)
            .where(Viagem.id == viagem_solicitada.id)
            .values(status=StatusViagem.CANCELADA)
        )
        return resultado

    def travar_viagem(viagem_id):
        ordem.append("viagem")
        return travar_viagem_original(viagem_id)

    monkeypatch.setattr(viagens_service, "travar_rota", travar_rota)
    monkeypatch.setattr(viagens_service, "_travar_viagem", travar_viagem)

    r = _cancelar(gestor, viagem_solicitada)
    assert r.status_code == 409, r.get_data(as_text=True)
    assert ordem == ["rota", "viagem"]


@pytest.mark.integration
def test_localizacao_de_viagem_de_outra_organizacao_da_404(
    viagem_futura_iniciada_com_motorista, other_aluno, other_motorista
):
    url = f"/v1/viagens/{viagem_futura_iniciada_com_motorista.id}/localizacao"
    assert other_aluno.client.get(url).status_code == 404
    assert other_motorista.client.get(url).status_code == 404


@pytest.mark.integration
def test_aluno_excluido_sai_da_lista_do_projeto(gestor, aluno, _db):
    projeto = gestor.client.post("/v1/projetos", json={"nome": "Projeto Alfa"}).get_json()
    r = gestor.client.put(f"/v1/alunos/{aluno.user.id}/projeto", json={"projeto_id": projeto["id"]})
    assert r.status_code == 200, r.get_data(as_text=True)
    aluno.user.status = UserStatus.DELETED
    _db.session.commit()

    listagem = gestor.client.get(f"/v1/alunos/?projeto_id={projeto['id']}")
    assert listagem.status_code == 200
    assert listagem.get_json()["items"] == []


@pytest.mark.integration
def test_push_so_e_enviado_depois_do_commit(aluno, _db):
    aluno.user.fcm_token = "token-fcm-de-teste"
    _db.session.commit()

    with patch("app.services.notificacao_service.messaging.send") as send:
        NotificacaoService._criar_notificacao_interna(aluno.user.id, "Título", "Mensagem")
        assert send.call_count == 0
        _db.session.rollback()
        assert send.call_count == 0

        NotificacaoService._criar_notificacao_interna(aluno.user.id, "Título", "Mensagem")
        _db.session.commit()
        assert send.call_count == 1


@pytest.mark.integration
def test_erro_500_nao_vaza_detalhes(gestor, viagem_futura_agendada_com_motorista, monkeypatch):
    def falha(*args, **kwargs):
        raise RuntimeError("detalhe-interno-do-banco")

    monkeypatch.setattr(NotificacaoService, "_criar_notificacao_interna", falha)
    r = _cancelar(gestor, viagem_futura_agendada_com_motorista)

    assert r.status_code == 500
    assert "detalhe-interno-do-banco" not in r.get_data(as_text=True)
    assert r.get_json()["error"]["message"] == "Erro interno do servidor"


@pytest.mark.integration
def test_cancelar_sob_demanda_em_andamento_avisa_o_passageiro_uma_vez(
    gestor, aluno, viagem_solicitada, _db
):
    # After the buffer closes the passenger is confirmed and keeps the active request.
    viagem_solicitada.status = StatusViagem.EM_ANDAMENTO
    viagem_solicitada.inicio_real = datetime.now(UTC) - timedelta(minutes=10)
    _db.session.add(
        AlunosConfirmados(viagem_id=viagem_solicitada.id, aluno_id=aluno.user.id, confirmacao=True)
    )
    _db.session.commit()

    r = _cancelar(gestor, viagem_solicitada)
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["alunos_notificados"] == 1
    assert Notificacao.query.filter_by(usuario_id=aluno.user.id).count() == 1
