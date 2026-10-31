"""GET /v1/rotas/<id>/viagem-ativa (RF-12, fluxo secundário)."""

from datetime import timedelta

from app.models.enum import StatusSolicitacao, StatusViagem
from tests.conftest import SEGUNDA_10H_LOCAL


def _rodada(actor, rota):
    return actor.client.get(f"/v1/rotas/{rota.id}/viagem-ativa")


def test_sem_rodada_retorna_viagem_null_e_janelas_de_hoje(aluno, rota_sob_demanda, janela, relogio):
    r = _rodada(aluno, rota_sob_demanda)
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["viagem"] is None
    assert body["minha_solicitacao"] is None
    assert body["janelas_hoje"] == [{"hora_inicio": "08:00", "hora_fim": "12:00"}]


def test_viagem_solicitada_com_solicitacao_do_aluno(
    aluno, rota_sob_demanda, janela, viagem_solicitada, motorista, onibus, relogio
):
    body = _rodada(aluno, rota_sob_demanda).get_json()
    viagem = body["viagem"]
    assert viagem["id"] == str(viagem_solicitada.id)
    assert viagem["status"] == "SOLICITADA"
    assert viagem["segundos_restantes_buffer"] is None
    assert viagem["motorista"] == {"id": str(motorista.user.id), "nome": motorista.user.nome}
    assert viagem["veiculo"]["placa"] == onibus.placa

    solicitacao = viagem_solicitada.solicitacoes[0]
    assert body["minha_solicitacao"] == {"id": str(solicitacao.id), "status": "ATIVA"}


def test_buffer_aberto_conta_segundos_pelo_relogio_do_servidor(
    _db, aluno, rota_sob_demanda, viagem_solicitada, relogio
):
    viagem_solicitada.status = StatusViagem.BUFFER_ABERTO
    viagem_solicitada.buffer_fim = SEGUNDA_10H_LOCAL + timedelta(minutes=5)
    _db.session.commit()
    relogio.avancar(minutes=2, seconds=30)

    viagem = _rodada(aluno, rota_sob_demanda).get_json()["viagem"]
    assert viagem["status"] == "BUFFER_ABERTO"
    assert viagem["segundos_restantes_buffer"] == 150


def test_buffer_vencido_nao_retorna_segundos_negativos(
    _db, aluno, rota_sob_demanda, viagem_solicitada, relogio
):
    viagem_solicitada.status = StatusViagem.BUFFER_ABERTO
    viagem_solicitada.buffer_fim = SEGUNDA_10H_LOCAL - timedelta(seconds=10)
    _db.session.commit()

    viagem = _rodada(aluno, rota_sob_demanda).get_json()["viagem"]
    assert viagem["segundos_restantes_buffer"] == 0


def test_em_andamento_aparece(_db, aluno, rota_sob_demanda, viagem_solicitada, relogio):
    viagem_solicitada.status = StatusViagem.EM_ANDAMENTO
    viagem_solicitada.inicio_real = SEGUNDA_10H_LOCAL
    _db.session.commit()

    viagem = _rodada(aluno, rota_sob_demanda).get_json()["viagem"]
    assert viagem["status"] == "EM_ANDAMENTO"
    assert viagem["inicio_real"] is not None


def test_aluno_sem_solicitacao_ativa_ve_a_rodada_sem_flag(
    _db, aluno, rota_sob_demanda, viagem_solicitada, relogio
):
    viagem_solicitada.solicitacoes[0].status = StatusSolicitacao.CANCELADA
    _db.session.commit()

    body = _rodada(aluno, rota_sob_demanda).get_json()
    assert body["viagem"]["id"] == str(viagem_solicitada.id)
    assert body["minha_solicitacao"] is None


def test_gestor_e_motorista_da_organizacao_podem_consultar(
    gestor, motorista, rota_sob_demanda, viagem_solicitada, relogio
):
    for actor in (gestor, motorista):
        r = _rodada(actor, rota_sob_demanda)
        assert r.status_code == 200, r.get_data(as_text=True)
        assert r.get_json()["minha_solicitacao"] is None


def test_viagem_finalizada_nao_e_rodada_ativa(_db, aluno, rota_sob_demanda, viagem_solicitada):
    viagem_solicitada.status = StatusViagem.FINALIZADA
    _db.session.commit()
    assert _rodada(aluno, rota_sob_demanda).get_json()["viagem"] is None


def test_rota_fixa_retorna_400(aluno, rota):
    assert _rodada(aluno, rota).status_code == 400


def test_outra_organizacao_retorna_403(other_aluno, other_gestor, rota_sob_demanda):
    assert _rodada(other_aluno, rota_sob_demanda).status_code == 403
    assert _rodada(other_gestor, rota_sob_demanda).status_code == 403
