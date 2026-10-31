"""A viagem sob demanda de ponta a ponta, pela API — RF-09 a RF-19.

Cada plano testou o seu pedaço. Estes testes cobrem o que nenhum deles podia
cobrir sozinho: a viagem inteira atravessando consentimento, janela, buffer,
capacidade, fechamento do buffer e embarque, sempre por HTTP e com JWT de verdade.

O relógio é a única coisa manipulada (fixture `relogio`): esperar o buffer
expirar de verdade tornaria a suíte lenta sem provar nada a mais.
"""

import io

import pytest
from flask_jwt_extended import create_access_token

from app.models.enum import StatusSolicitacao, StatusViagem
from app.models.notificacao import Notificacao
from app.models.viagem import AlunosConfirmados, SolicitacaoViagem, Viagem
from app.services import buffer_service, credencial_embarque_service
from tests.conftest import AuthenticatedClient
from tests.factories.user_factory import AlunoFactory
from tests.helpers import imagens

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
        assert ator.post("/v1/consentimento", json={"versao": "1.0"}).status_code == 200
        atores.append(ator)
    return atores


@pytest.fixture()
def condutor(client, app, motorista):
    return _ator(client, app, motorista.user)


@pytest.fixture()
def operacao(circuito, janela, relogio):
    """Rota sob demanda com circuito de 4 pontos, numa segunda às 10h dentro da janela."""
    return circuito


def _trajeto(origem, destino):
    return {"ponto_origem_id": str(origem.id), "ponto_destino_id": str(destino.id)}


def _qr_do_app(credencial, relogio):
    """O que o app do aluno faz sem rede: o código TOTP do passo corrente."""
    contador = int(relogio.agora.timestamp()) // credencial["passo_segundos"]
    codigo = credencial_embarque_service.gerar_codigo(
        bytes.fromhex(credencial["segredo"]), contador, credencial["digitos"]
    )
    return f"{credencial['credencial_id']}.{codigo}"


def _expirar_buffer(relogio):
    """Passa o relógio do fim do buffer (5 min na rota) e roda o job."""
    relogio.avancar(minutes=6)
    return buffer_service.fechar_buffers_expirados()


@pytest.mark.e2e
def test_rodada_completa_da_solicitacao_ao_embarque(
    app,
    _db,
    operacao,
    pontos_circuito,
    van,
    passageiros,
    condutor,
    motorista,
    relogio,
    tmp_path,
    monkeypatch,
):
    """RF-10 -> RF-17: chamar o veículo, abrir o buffer, declarar, embarcar."""
    p1, p2, p3, p4 = pontos_circuito
    ana, bruno, carla, _ = passageiros

    # RF-10 — a primeira solicitação não despacha o veículo, só avisa o motorista.
    r = ana.post(f"/v1/rotas/{operacao.id}/solicitacoes")
    assert r.status_code == 201, r.get_data(as_text=True)
    viagem_id = r.get_json()["viagem_id"]
    assert r.get_json()["viagem"]["status"] == StatusViagem.SOLICITADA.value
    assert Notificacao.query.filter_by(usuario_id=motorista.user.id).count() == 1

    # RF-10 fluxo secundário 1 — o segundo entra na mesma viagem, sem re-notificar.
    r = bruno.post(f"/v1/rotas/{operacao.id}/solicitacoes")
    assert r.status_code == 201
    assert r.get_json()["viagem_id"] == viagem_id
    assert Notificacao.query.filter_by(usuario_id=motorista.user.id).count() == 1

    # RF-11 — o motorista abre a janela de buffer.
    r = condutor.post(f"/v1/viagens/{viagem_id}/iniciar-percurso")
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["status"] == StatusViagem.BUFFER_ABERTO.value

    # RF-12 — quem está sem push enxerga a viagem e a contagem regressiva.
    ativa = carla.get(f"/v1/rotas/{operacao.id}/viagem-ativa").get_json()
    assert ativa["viagem"]["id"] == viagem_id
    assert ativa["viagem"]["segundos_restantes_buffer"] > 0

    # RF-13/RF-14 — trajetos sobrepostos e disjuntos, todos cabem no veículo.
    # A Carla só recebeu o aviso: declarar já a coloca na viagem.
    for ator, origem, destino in ((ana, p1, p3), (bruno, p2, p4), (carla, p3, p4)):
        r = ator.post(f"/v1/viagens/{viagem_id}/declaracao", json=_trajeto(origem, destino))
        assert r.status_code == 200, r.get_data(as_text=True)
        assert r.get_json()["status"] == StatusSolicitacao.ATIVA.value

    # RF-15 — o buffer vence e quem declarou vira passageiro.
    assert _expirar_buffer(relogio) == 1
    viagem = _db.session.get(Viagem, viagem_id)
    assert viagem.status == StatusViagem.EM_ANDAMENTO

    # Cada passageiro recebe a sua credencial, e ninguém vê a do outro.
    credencial_ana = ana.get(f"/v1/viagens/{viagem_id}/credencial-embarque").get_json()
    assert credencial_ana["segredo"]
    credencial_bruno = bruno.get(f"/v1/viagens/{viagem_id}/credencial-embarque").get_json()
    assert credencial_bruno["segredo"] != credencial_ana["segredo"]

    # A Ana tem foto cadastrada: sem ela, o QR sozinho não a embarcaria.
    monkeypatch.setitem(app.config, "FOTOS_ALUNO_DIR", str(tmp_path))
    r = ana.put(
        "/v1/alunos/me/foto",
        data={"foto": (io.BytesIO(imagens.png()), "foto.png")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 200, r.get_data(as_text=True)

    # RF-16 — o roteiro do motorista sai na ordem do circuito.
    roteiro = condutor.get(f"/v1/embarque/viagens/{viagem_id}/roteiro").get_json()
    paradas = {p["ordem"]: p for p in roteiro["pontos"]}
    assert paradas[1]["embarcam"] == 1  # Ana em P1
    assert paradas[2]["embarcam"] == 1  # Bruno em P2
    assert paradas[3]["embarcam"] == 1 and paradas[3]["desembarcam"] == 1  # Carla sobe, Ana desce
    assert paradas[4]["desembarcam"] == 2  # Bruno e Carla

    # RF-17 — a leitura no ponto correto mostra a Ana com a foto, sem embarcá-la.
    qr_ana = _qr_do_app(credencial_ana, relogio)
    r = condutor.post(f"/v1/embarque/viagens/{viagem_id}/checkin", json={"qr_token": qr_ana})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["ponto_embarque_id"] == str(p1.id)
    assert r.get_json()["sem_foto"] is False

    # A foto confere e o motorista confirma: só agora o embarque é registrado.
    relogio.avancar(seconds=10)
    r = condutor.post(f"/v1/embarque/viagens/{viagem_id}/confirmacao", json={"qr_token": qr_ana})
    assert r.status_code == 200, r.get_data(as_text=True)

    _db.session.expire_all()
    embarcados = (
        _db.session.query(AlunosConfirmados).filter_by(viagem_id=viagem.id, embarcou=True).count()
    )
    assert embarcados == 1

    # A mesma credencial não embarca duas vezes.
    r = condutor.post(
        f"/v1/embarque/viagens/{viagem_id}/confirmacao",
        json={"qr_token": _qr_do_app(credencial_ana, relogio)},
    )
    assert r.status_code == 409
    assert r.get_json()["error"]["code"] == "CREDENCIAL_JA_UTILIZADA"

    # Um print do QR da Ana guardado por alguém para de valer em um minuto.
    relogio.avancar(seconds=90)
    r = condutor.post(f"/v1/embarque/viagens/{viagem_id}/confirmacao", json={"qr_token": qr_ana})
    assert r.status_code == 409
    assert r.get_json()["error"]["code"] == "CODIGO_EXPIRADO"


@pytest.mark.e2e
def test_buffer_sem_nenhum_trajeto_cancela_a_viagem(
    _db, operacao, van, passageiros, condutor, relogio
):
    """RF-15 fluxo secundário 1: ninguém declarou trajeto, a van não sai."""
    ana = passageiros[0]

    viagem_id = ana.post(f"/v1/rotas/{operacao.id}/solicitacoes").get_json()["viagem_id"]
    condutor.post(f"/v1/viagens/{viagem_id}/iniciar-percurso")

    assert _expirar_buffer(relogio) == 1

    viagem = _db.session.get(Viagem, viagem_id)
    assert viagem.status == StatusViagem.CANCELADA
    assert viagem.inicio_real is None

    # E o interesse solto não fica pendurado para a próxima viagem.
    ativas = SolicitacaoViagem.query.filter_by(
        viagem_id=viagem.id, status=StatusSolicitacao.ATIVA
    ).count()
    assert ativas == 0


@pytest.mark.e2e
def test_cancelar_no_buffer_devolve_a_vaga_para_quem_tinha_sido_negado(
    _db, operacao, pontos_circuito, onibus, passageiros, condutor
):
    """RF-19 + RF-14: a vaga liberada volta a ser oferecível na mesma viagem."""
    onibus.capacidade = 1
    _db.session.commit()

    p1, p2, _, _ = pontos_circuito
    ana, bruno, *_ = passageiros

    viagem_id = ana.post(f"/v1/rotas/{operacao.id}/solicitacoes").get_json()["viagem_id"]
    condutor.post(f"/v1/viagens/{viagem_id}/iniciar-percurso")

    trajeto = _trajeto(p1, p2)
    assert ana.post(f"/v1/viagens/{viagem_id}/declaracao", json=trajeto).status_code == 200
    # Único assento ocupado: o Bruno é recusado.
    assert bruno.post(f"/v1/viagens/{viagem_id}/declaracao", json=trajeto).status_code == 409

    # Ana desiste durante o buffer e a vaga volta a existir.
    r = ana.delete(f"/v1/viagens/{viagem_id}/solicitacao")
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["status"] == StatusSolicitacao.CANCELADA.value

    assert bruno.post(f"/v1/viagens/{viagem_id}/declaracao", json=trajeto).status_code == 200


@pytest.mark.e2e
def test_sem_consentimento_nao_solicita(client, app, _db, operacao, van, organizacao):
    """RF-09: sem aceite do termo, o fluxo nem começa."""
    aluno = AlunoFactory(organizacao_id=organizacao.id)
    _db.session.add(aluno)
    _db.session.commit()

    r = _ator(client, app, aluno).post(f"/v1/rotas/{operacao.id}/solicitacoes")
    assert r.status_code == 403, r.get_data(as_text=True)
    assert _db.session.query(Viagem).count() == 0, "nada pode ser criado sem consentimento"
