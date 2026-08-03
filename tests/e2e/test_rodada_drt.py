"""A rodada sob demanda de ponta a ponta, pela API — RF-09 a RF-19.

Cada plano testou o seu pedaço. Estes testes cobrem o que nenhum deles podia
cobrir sozinho: a rodada inteira atravessando consentimento, janela, buffer,
capacidade, consolidação e embarque, sempre por HTTP e com JWT de verdade.

O relógio é a única coisa manipulada — esperar o buffer expirar de verdade
tornaria a suíte lenta sem provar nada a mais.
"""

from datetime import UTC, datetime, timedelta

import pytest
from flask_jwt_extended import create_access_token

from app.models.enum import StatusSolicitacao, StatusViagem
from app.models.viagem import AlunosConfirmados, Viagem
from app.tasks.viagem_tasks import consolidar_buffers_expirados
from tests.conftest import AuthenticatedClient
from tests.factories.user_factory import AlunoFactory

pytestmark = pytest.mark.e2e

CAPACIDADE_VEICULO = 17


def _ator(client, app, usuario):
    with app.app_context():
        token = create_access_token(identity=str(usuario.id))
    return AuthenticatedClient(client, {"Authorization": f"Bearer {token}"})


@pytest.fixture()
def van(_db, onibus):
    """Capacidade fixa: a fábrica sorteia, e um sorteio baixo negaria os
    trajetos que se cruzam por lotação em vez de por defeito."""
    onibus.capacidade = CAPACIDADE_VEICULO
    _db.session.commit()
    return onibus


@pytest.fixture()
def passageiros(client, app, _db, organizacao):
    """Alunos já com o termo aceito — o aceite em si é testado no plano 5."""
    turma = [AlunoFactory(organizacao_id=organizacao.id) for _ in range(4)]
    _db.session.add_all(turma)
    _db.session.commit()

    atores = []
    for aluno in turma:
        ator = _ator(client, app, aluno)
        assert ator.post("/v1/consentimento").status_code == 201
        atores.append(ator)
    return atores


@pytest.fixture()
def condutor(client, app, motorista):
    return _ator(client, app, motorista.user)


def _expirar_buffer(_db, viagem_id):
    """Empurra o fim do buffer para trás e roda a consolidação."""
    viagem = _db.session.get(Viagem, viagem_id)
    viagem.buffer_expira_em = datetime.now(UTC) - timedelta(seconds=1)
    _db.session.commit()
    return consolidar_buffers_expirados()


@pytest.mark.e2e
def test_rodada_completa_da_solicitacao_ao_embarque(
    app, _db, janela_hoje, pontos_circuito, van, passageiros, condutor
):
    """RF-10 -> RF-17: chamar o veículo, abrir o buffer, declarar, embarcar."""
    p1, p2, p3, p4 = pontos_circuito
    ana, bruno, carla, _ = passageiros

    # RF-10 — a primeira solicitação não despacha o veículo, só avisa o motorista.
    r = ana.post("/v1/viagens/solicitar")
    assert r.status_code == 201, r.get_data(as_text=True)
    rodada = r.get_json()
    viagem_id = rodada["viagem_id"]
    assert rodada["status"] == StatusViagem.SOLICITADA.value
    assert rodada["motorista_notificado"] is True

    # RF-10 fluxo secundário 1 — o segundo entra na mesma rodada, sem re-notificar.
    r = bruno.post("/v1/viagens/solicitar")
    assert r.status_code == 201
    assert r.get_json()["viagem_id"] == viagem_id
    assert r.get_json()["motorista_notificado"] is False

    # RF-11 — o motorista abre a janela de buffer.
    r = condutor.post(f"/v1/viagens/{viagem_id}/iniciar-percurso")
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["status"] == StatusViagem.BUFFER_ABERTO.value

    # RF-12 — quem está sem push enxerga a rodada e a contagem regressiva.
    ativa = carla.get("/v1/viagens/rodada-ativa").get_json()
    assert ativa["em_operacao"] is True
    assert ativa["rodada"]["viagem_id"] == viagem_id

    # RF-13/RF-14 — trajetos sobrepostos e disjuntos, todos cabem no veículo.
    for ator, origem, destino in (
        (ana, p1, p3),
        (bruno, p2, p4),
        (carla, p3, p4),
    ):
        r = ator.post(
            f"/v1/viagens/{viagem_id}/declaracao",
            json={"ponto_origem_id": str(origem.id), "ponto_destino_id": str(destino.id)},
        )
        assert r.status_code == 201, r.get_data(as_text=True)
        assert r.get_json()["status"] == StatusSolicitacao.CONFIRMADO.value

    # RF-15 — o buffer vence e a rodada é consolidada.
    assert _expirar_buffer(_db, viagem_id) == 1
    viagem = _db.session.get(Viagem, viagem_id)
    assert viagem.status == StatusViagem.EM_ROTA

    # Cada confirmado recebe a sua credencial, e ninguém vê a do outro.
    credencial = ana.get(f"/v1/embarque/viagens/{viagem_id}/credencial").get_json()
    assert credencial["qr_token"]
    token_bruno = bruno.get(f"/v1/embarque/viagens/{viagem_id}/credencial").get_json()["qr_token"]
    assert token_bruno != credencial["qr_token"]

    # RF-16 — o roteiro do motorista sai na ordem do circuito.
    roteiro = condutor.get(f"/v1/embarque/viagens/{viagem_id}/roteiro").get_json()
    paradas = {p["ordem"]: p for p in roteiro["pontos"]}
    assert paradas[1]["embarcam"] == 1  # Ana em P1
    assert paradas[2]["embarcam"] == 1  # Bruno em P2
    assert paradas[3]["embarcam"] == 1 and paradas[3]["desembarcam"] == 1  # Carla sobe, Ana desce
    assert paradas[4]["desembarcam"] == 2  # Bruno e Carla

    # RF-17 — o motorista valida a credencial no ponto correto.
    r = condutor.post(
        f"/v1/embarque/viagens/{viagem_id}/validacao",
        json={"qr_token": credencial["qr_token"]},
    )
    assert r.status_code == 200, r.get_data(as_text=True)

    _db.session.expire_all()
    embarcados = (
        _db.session.query(AlunosConfirmados).filter_by(viagem_id=viagem.id, embarcou=True).count()
    )
    assert embarcados == 1

    # A mesma credencial não embarca duas vezes.
    r = condutor.post(
        f"/v1/embarque/viagens/{viagem_id}/validacao",
        json={"qr_token": credencial["qr_token"]},
    )
    assert r.status_code == 409


@pytest.mark.e2e
def test_rodada_sem_nenhuma_confirmacao_volta_a_ociosa(
    app, _db, janela_hoje, van, passageiros, condutor
):
    """RF-15 fluxo secundário 1: ninguém declarou trajeto, a van não sai."""
    ana = passageiros[0]

    viagem_id = ana.post("/v1/viagens/solicitar").get_json()["viagem_id"]
    condutor.post(f"/v1/viagens/{viagem_id}/iniciar-percurso")

    # Ninguém declarou origem/destino durante o buffer.
    assert _expirar_buffer(_db, viagem_id) == 1

    viagem = _db.session.get(Viagem, viagem_id)
    assert viagem.status == StatusViagem.OCIOSA
    assert viagem.buffer_expira_em is None

    # E o interesse solto não fica pendurado para a próxima rodada.
    interessados = (
        _db.session.query(AlunosConfirmados)
        .filter_by(viagem_id=viagem.id, status=StatusSolicitacao.INTERESSADO)
        .count()
    )
    assert interessados == 0


@pytest.mark.e2e
def test_cancelar_no_buffer_devolve_a_vaga_para_quem_tinha_sido_negado(
    app, _db, janela_hoje, pontos_circuito, onibus, passageiros, condutor
):
    """RF-19 + RF-14: a vaga liberada volta a ser oferecível na mesma rodada."""
    onibus.capacidade = 1
    _db.session.commit()

    p1, p2, _, _ = pontos_circuito
    ana, bruno, *_ = passageiros

    viagem_id = ana.post("/v1/viagens/solicitar").get_json()["viagem_id"]
    condutor.post(f"/v1/viagens/{viagem_id}/iniciar-percurso")

    trajeto = {"ponto_origem_id": str(p1.id), "ponto_destino_id": str(p2.id)}

    assert ana.post(f"/v1/viagens/{viagem_id}/declaracao", json=trajeto).status_code == 201
    # Único assento ocupado: o Bruno é recusado.
    assert bruno.post(f"/v1/viagens/{viagem_id}/declaracao", json=trajeto).status_code == 409

    # Ana desiste durante o buffer e a vaga volta a existir.
    r = ana.delete(f"/v1/viagens/{viagem_id}/declaracao")
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["vaga_liberada"] is True

    assert bruno.post(f"/v1/viagens/{viagem_id}/declaracao", json=trajeto).status_code == 201


@pytest.mark.e2e
def test_sem_consentimento_nao_solicita(client, app, _db, janela_hoje, van, organizacao):
    """RF-09: sem aceite do termo, o fluxo nem começa."""
    aluno = AlunoFactory(organizacao_id=organizacao.id)
    _db.session.add(aluno)
    _db.session.commit()

    r = _ator(client, app, aluno).post("/v1/viagens/solicitar")
    assert r.status_code == 403, r.get_data(as_text=True)
    assert _db.session.query(Viagem).count() == 0, "nada pode ser criado sem consentimento"
