"""Rodada sob demanda sob concorrência: solicitação, cancelamento, buffer e declaração.

Cada teste solta duas ou mais requisições no mesmo instante, em conexões
separadas, e confere a regra que um teste sequencial não consegue provar.
"""

import threading
from datetime import UTC, datetime, time, timedelta

import pytest

from app.models.enum import DiaDaSemana, StatusSolicitacao, StatusViagem, TipoViagem
from app.models.viagem import AlunosConfirmados, SolicitacaoViagem, Viagem
from app.services import buffer_service
from app.utils import tempo
from tests.factories.onibus_factory import JanelaDisponibilidadeFactory, OnibusFactory
from tests.factories.rota_factory import RotaFactory
from tests.factories.user_factory import MotoristaFactory
from tests.factories.viagem_factory import SolicitacaoViagemFactory
from tests.integration.concurrency.conftest import ao_mesmo_tempo, status_de

pytestmark = [pytest.mark.integration, pytest.mark.concurrency]


def _solicitar(app, actor, rota_id):
    return lambda: app.test_client().post(
        f"/v1/rotas/{rota_id}/solicitacoes", headers=actor.headers
    )


def _cancelar(app, actor, viagem_id):
    return lambda: app.test_client().delete(
        f"/v1/viagens/{viagem_id}/solicitacao", headers=actor.headers
    )


def _iniciar_percurso(app, motorista, viagem_id):
    return lambda: app.test_client().post(
        f"/v1/viagens/{viagem_id}/iniciar-percurso", headers=motorista.headers
    )


def _ativas(_db, viagem_id) -> int:
    return (
        _db.session.query(SolicitacaoViagem)
        .filter_by(viagem_id=viagem_id, status=StatusSolicitacao.ATIVA)
        .count()
    )


# ---------- solicitação (RF-10) ----------


def test_primeiras_solicitacoes_simultaneas_criam_uma_viagem_so(
    app, _db, rota_sob_demanda, janela, relogio, novo_aluno
):
    alunos = []
    for _ in range(5):
        alunos.append(novo_aluno())

    tarefas = []
    for aluno in alunos:
        tarefas.append(_solicitar(app, aluno, rota_sob_demanda.id))
    respostas = ao_mesmo_tempo(app, tarefas)

    assert status_de(respostas) == [201, 201, 201, 201, 201]
    _db.session.expire_all()
    viagens = _db.session.query(Viagem).filter_by(rota_id=rota_sob_demanda.id).all()
    assert len(viagens) == 1
    assert _ativas(_db, viagens[0].id) == 5


def test_mesmo_aluno_solicitando_duas_vezes_ao_mesmo_tempo(
    app, _db, aluno, rota_sob_demanda, janela, relogio
):
    respostas = ao_mesmo_tempo(
        app,
        [_solicitar(app, aluno, rota_sob_demanda.id), _solicitar(app, aluno, rota_sob_demanda.id)],
    )

    assert status_de(respostas) == [201, 409]
    _db.session.expire_all()
    assert (
        _db.session.query(SolicitacaoViagem)
        .filter_by(aluno_id=aluno.user.id, status=StatusSolicitacao.ATIVA)
        .count()
        == 1
    )


@pytest.fixture()
def rota_de_outro_veiculo(_db, organizacao):
    """Outra rota sob demanda, com veículo e motorista próprios e janela aberta na segunda."""
    onibus = OnibusFactory(organizacao_id=organizacao.id)
    motorista = MotoristaFactory(organizacao_id=organizacao.id)
    _db.session.add_all([onibus, motorista])
    _db.session.flush()
    _db.session.add(
        JanelaDisponibilidadeFactory(
            onibus_id=onibus.id,
            motorista_id=motorista.id,
            dia=DiaDaSemana.SEG,
            hora_inicio=time(8, 0),
            hora_fim=time(12, 0),
        )
    )
    rota = RotaFactory(
        organizacao_id=organizacao.id,
        tipo=TipoViagem.SOB_DEMANDA,
        buffer_minutos=5,
        prazo_inicio_minutos=10,
        motorista_padrao_id=None,
        veiculo_padrao_id=onibus.id,
    )
    _db.session.add(rota)
    _db.session.commit()
    return rota


def test_mesmo_aluno_em_duas_rotas_ao_mesmo_tempo_fica_com_uma_solicitacao(
    app, _db, aluno, rota_sob_demanda, janela, rota_de_outro_veiculo, relogio
):
    """O lock do veículo não basta aqui: as duas rotas usam veículos diferentes."""
    respostas = ao_mesmo_tempo(
        app,
        [
            _solicitar(app, aluno, rota_sob_demanda.id),
            _solicitar(app, aluno, rota_de_outro_veiculo.id),
        ],
    )

    assert status_de(respostas) == [201, 409]
    _db.session.expire_all()
    assert (
        _db.session.query(SolicitacaoViagem)
        .filter_by(aluno_id=aluno.user.id, status=StatusSolicitacao.ATIVA)
        .count()
        == 1
    )


# ---------- cancelamento (RF-19) ----------


def test_cancelar_a_ultima_solicitacao_enquanto_outro_aluno_entra(
    app, _db, aluno, viagem_solicitada, rota_sob_demanda, janela, relogio, novo_aluno
):
    """Quem entra no mesmo instante não pode ficar preso numa viagem cancelada."""
    outro = novo_aluno()

    respostas = ao_mesmo_tempo(
        app,
        [
            _cancelar(app, aluno, viagem_solicitada.id),
            _solicitar(app, outro, rota_sob_demanda.id),
        ],
    )

    assert status_de(respostas) == [200, 201]
    _db.session.expire_all()
    solicitacao = (
        _db.session.query(SolicitacaoViagem)
        .filter_by(aluno_id=outro.user.id, status=StatusSolicitacao.ATIVA)
        .one()
    )
    assert solicitacao.viagem.status == StatusViagem.SOLICITADA


def test_cancelar_enquanto_o_motorista_inicia_o_percurso(
    app, _db, aluno, motorista, viagem_solicitada, relogio
):
    """Uma das duas ações vence inteira; o buffer aberto nunca vira viagem cancelada."""
    cancelamento, inicio = ao_mesmo_tempo(
        app,
        [
            _cancelar(app, aluno, viagem_solicitada.id),
            _iniciar_percurso(app, motorista, viagem_solicitada.id),
        ],
    )

    assert cancelamento.status_code == 200
    _db.session.expire_all()
    viagem = _db.session.get(Viagem, viagem_solicitada.id)
    if inicio.status_code == 200:
        assert viagem.status == StatusViagem.BUFFER_ABERTO
    else:
        assert inicio.status_code == 409
        assert viagem.status == StatusViagem.CANCELADA


def test_aluno_entra_enquanto_o_motorista_inicia_o_percurso(
    app, _db, motorista, viagem_solicitada, rota_sob_demanda, janela, relogio, novo_aluno
):
    """As duas ações cabem juntas: o aluno entra na rodada, com ou sem buffer aberto."""
    outro = novo_aluno()

    respostas = ao_mesmo_tempo(
        app,
        [
            _solicitar(app, outro, rota_sob_demanda.id),
            _iniciar_percurso(app, motorista, viagem_solicitada.id),
        ],
    )

    assert status_de(respostas) == [200, 201]
    _db.session.expire_all()
    assert _ativas(_db, viagem_solicitada.id) == 2
    assert _db.session.get(Viagem, viagem_solicitada.id).status == StatusViagem.BUFFER_ABERTO


# ---------- buffer (RF-11, RF-15) ----------


def test_dois_toques_em_iniciar_percurso_abrem_o_buffer_uma_vez(
    app, _db, motorista, viagem_solicitada, relogio
):
    respostas = ao_mesmo_tempo(
        app,
        [
            _iniciar_percurso(app, motorista, viagem_solicitada.id),
            _iniciar_percurso(app, motorista, viagem_solicitada.id),
        ],
    )

    assert status_de(respostas) == [200, 409]
    _db.session.expire_all()
    assert _db.session.get(Viagem, viagem_solicitada.id).status == StatusViagem.BUFFER_ABERTO


@pytest.fixture()
def relogio_por_thread(monkeypatch):
    """Cada thread lê o próprio relógio: um dentro do buffer, outro já depois do fim."""
    local = threading.local()
    monkeypatch.setattr(tempo, "agora_utc", lambda: local.agora)
    return local


@pytest.fixture()
def buffer_no_fim(_db, viagem_buffer_aberto, pontos_circuito, aluno, onibus):
    onibus.capacidade = 10
    viagem_buffer_aberto.buffer_fim = datetime.now(UTC) + timedelta(seconds=1)
    _db.session.add(
        SolicitacaoViagemFactory(viagem_id=viagem_buffer_aberto.id, aluno_id=aluno.user.id)
    )
    _db.session.commit()
    return viagem_buffer_aberto


def test_declaracao_no_ultimo_instante_entra_na_rodada_fechada_pelo_job(
    app, _db, aluno, buffer_no_fim, pontos_circuito, relogio_por_thread
):
    """O job que fecha o buffer espera a declaração em curso; quem recebeu 200 embarca."""
    p1, p2, _, _ = pontos_circuito
    fim = buffer_no_fim.buffer_fim

    def declarar():
        relogio_por_thread.agora = fim - timedelta(milliseconds=1)
        return app.test_client().post(
            f"/v1/viagens/{buffer_no_fim.id}/declaracao",
            json={"ponto_origem_id": str(p1.id), "ponto_destino_id": str(p2.id)},
            headers=aluno.headers,
        )

    def fechar():
        relogio_por_thread.agora = fim + timedelta(seconds=1)
        return buffer_service.fechar_buffers_expirados()

    declaracao, _ = ao_mesmo_tempo(app, [declarar, fechar])

    _db.session.expire_all()
    viagem = _db.session.get(Viagem, buffer_no_fim.id)
    passageiro = _db.session.get(AlunosConfirmados, (viagem.id, aluno.user.id))
    if declaracao.status_code == 200:
        # O job já tinha travado a viagem? Então ele rodou depois e viu a declaração.
        assert viagem.status == StatusViagem.EM_ANDAMENTO
        assert passageiro is not None and passageiro.confirmacao is True
    else:
        # O job fechou antes: a declaração chegou com a viagem já fora do buffer.
        assert declaracao.status_code == 400
        assert passageiro is None


def test_cancelar_enquanto_o_job_fecha_o_buffer(
    app, _db, aluno, novo_aluno, viagem_buffer_aberto, pontos_circuito, onibus
):
    """Quem cancelou não pode virar passageiro confirmado com credencial."""
    from tests.conftest import reservar_trajeto

    p1, p2, _, _ = pontos_circuito
    onibus.capacidade = 10
    _db.session.commit()
    outro = novo_aluno()
    reservar_trajeto(_db, viagem_buffer_aberto, aluno.user.id, p1.id, p2.id)
    reservar_trajeto(_db, viagem_buffer_aberto, outro.user.id, p1.id, p2.id)
    viagem_buffer_aberto.buffer_fim = datetime.now(UTC) - timedelta(seconds=1)
    _db.session.commit()

    cancelamento, _ = ao_mesmo_tempo(
        app,
        [_cancelar(app, aluno, viagem_buffer_aberto.id), buffer_service.fechar_buffers_expirados],
    )

    assert cancelamento.status_code == 200
    _db.session.expire_all()
    solicitacao = (
        _db.session.query(SolicitacaoViagem)
        .filter_by(viagem_id=viagem_buffer_aberto.id, aluno_id=aluno.user.id)
        .one()
    )
    passageiro = _db.session.get(AlunosConfirmados, (viagem_buffer_aberto.id, aluno.user.id))
    if solicitacao.status == StatusSolicitacao.CANCELADA:
        # Cancelou antes do fechamento: nem entrou na lista.
        assert passageiro is None
    else:
        # O job fechou antes: o cancelamento virou desistência e saiu da lista.
        assert solicitacao.status == StatusSolicitacao.DESISTENCIA
        assert passageiro.confirmacao is False


# ---------- declaração (RF-13/RF-14) ----------


def test_declaracoes_simultaneas_respeitam_a_capacidade_do_trecho(
    app, _db, viagem_buffer_aberto, pontos_circuito, onibus, novo_aluno
):
    p1, p2, _, _ = pontos_circuito
    onibus.capacidade = 2
    _db.session.commit()

    tarefas = []
    for _ in range(6):
        aluno = novo_aluno()
        _db.session.add(
            SolicitacaoViagemFactory(viagem_id=viagem_buffer_aberto.id, aluno_id=aluno.user.id)
        )
        _db.session.commit()
        tarefas.append(
            lambda headers=aluno.headers: app.test_client().post(
                f"/v1/viagens/{viagem_buffer_aberto.id}/declaracao",
                json={"ponto_origem_id": str(p1.id), "ponto_destino_id": str(p2.id)},
                headers=headers,
            )
        )
    respostas = ao_mesmo_tempo(app, tarefas)

    assert status_de(respostas) == [200, 200, 409, 409, 409, 409]
    _db.session.expire_all()
    assert _ativas(_db, viagem_buffer_aberto.id) == 2
