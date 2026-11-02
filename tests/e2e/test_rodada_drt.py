"""The on-demand trip end to end, through the API (RF-09 to RF-19).

Each plan tested its own piece. These tests cover what none of them could alone:
the whole trip across consent, window, buffer, capacity, buffer close and
boarding, always over HTTP and with a real JWT.

The clock is the only thing faked (`relogio` fixture): actually waiting for the
buffer to expire would make the suite slow without proving anything more.
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
    """Fixed capacity: the factory picks a random one, and a low pick would deny the
    crossing routes because the vehicle is full instead of because of a bug.
    """
    onibus.capacidade = CAPACIDADE_VEICULO
    _db.session.commit()
    return onibus


@pytest.fixture()
def passageiros(client, app, _db, organizacao):
    """Students who already accepted the terms; acceptance itself is tested in plan 5."""
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
    """On-demand route with a 4-stop circuit, on a Monday at 10:00 inside the window."""
    return circuito


def _trajeto(origem, destino):
    return {"ponto_origem_id": str(origem.id), "ponto_destino_id": str(destino.id)}


def _qr_do_app(credencial, relogio):
    """What the student app does offline: the TOTP code for the current step."""
    contador = int(relogio.agora.timestamp()) // credencial["passo_segundos"]
    codigo = credencial_embarque_service.gerar_codigo(
        bytes.fromhex(credencial["segredo"]), contador, credencial["digitos"]
    )
    return f"{credencial['credencial_id']}.{codigo}"


def _expirar_buffer(relogio):
    """Move the clock past the buffer end (5 min on the route) and run the job."""
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
    """RF-10 -> RF-17: call the vehicle, open the buffer, declare, board."""
    p1, p2, p3, p4 = pontos_circuito
    ana, bruno, carla, _ = passageiros

    # RF-10: the first request does not dispatch the vehicle, it only notifies the driver.
    r = ana.post(f"/v1/rotas/{operacao.id}/solicitacoes")
    assert r.status_code == 201, r.get_data(as_text=True)
    viagem_id = r.get_json()["viagem_id"]
    assert r.get_json()["viagem"]["status"] == StatusViagem.SOLICITADA.value
    assert Notificacao.query.filter_by(usuario_id=motorista.user.id).count() == 1

    # RF-10 secondary flow 1: the second joins the same trip, without re-notifying.
    r = bruno.post(f"/v1/rotas/{operacao.id}/solicitacoes")
    assert r.status_code == 201
    assert r.get_json()["viagem_id"] == viagem_id
    assert Notificacao.query.filter_by(usuario_id=motorista.user.id).count() == 1

    # RF-11: the driver opens the buffer window.
    r = condutor.post(f"/v1/viagens/{viagem_id}/iniciar-percurso")
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["status"] == StatusViagem.BUFFER_ABERTO.value

    # RF-12: those without push see the trip and the countdown.
    ativa = carla.get(f"/v1/rotas/{operacao.id}/viagem-ativa").get_json()
    assert ativa["viagem"]["id"] == viagem_id
    assert ativa["viagem"]["segundos_restantes_buffer"] > 0

    # RF-13/RF-14: overlapping and disjoint routes, all fit in the vehicle.
    # Carla only got the notice: declaring already puts her on the trip.
    for ator, origem, destino in ((ana, p1, p3), (bruno, p2, p4), (carla, p3, p4)):
        r = ator.post(f"/v1/viagens/{viagem_id}/declaracao", json=_trajeto(origem, destino))
        assert r.status_code == 200, r.get_data(as_text=True)
        assert r.get_json()["status"] == StatusSolicitacao.ATIVA.value

    # RF-15: the buffer expires and those who declared become passengers.
    assert _expirar_buffer(relogio) == 1
    viagem = _db.session.get(Viagem, viagem_id)
    assert viagem.status == StatusViagem.EM_ANDAMENTO

    # Each passenger gets their own credential, and no one sees another's.
    credencial_ana = ana.get(f"/v1/viagens/{viagem_id}/credencial-embarque").get_json()
    assert credencial_ana["segredo"]
    credencial_bruno = bruno.get(f"/v1/viagens/{viagem_id}/credencial-embarque").get_json()
    assert credencial_bruno["segredo"] != credencial_ana["segredo"]

    # Ana has a photo on file: without it, the QR alone would not board her.
    monkeypatch.setitem(app.config, "FOTOS_ALUNO_DIR", str(tmp_path))
    r = ana.put(
        "/v1/alunos/me/foto",
        data={"foto": (io.BytesIO(imagens.png()), "foto.png")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 200, r.get_data(as_text=True)

    # RF-16: the driver's itinerary follows the circuit order.
    roteiro = condutor.get(f"/v1/embarque/viagens/{viagem_id}/roteiro").get_json()
    paradas = {p["ordem"]: p for p in roteiro["pontos"]}
    assert paradas[1]["embarcam"] == 1  # Ana at P1
    assert paradas[2]["embarcam"] == 1  # Bruno at P2
    assert paradas[3]["embarcam"] == 1 and paradas[3]["desembarcam"] == 1  # Carla on, Ana off
    assert paradas[4]["desembarcam"] == 2  # Bruno and Carla

    # RF-17: scanning at the right stop shows Ana with the photo, without boarding her.
    qr_ana = _qr_do_app(credencial_ana, relogio)
    r = condutor.post(f"/v1/embarque/viagens/{viagem_id}/checkin", json={"qr_token": qr_ana})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["ponto_embarque_id"] == str(p1.id)
    assert r.get_json()["sem_foto"] is False

    # The photo matches and the driver confirms: only now is the boarding recorded.
    relogio.avancar(seconds=10)
    r = condutor.post(f"/v1/embarque/viagens/{viagem_id}/confirmacao", json={"qr_token": qr_ana})
    assert r.status_code == 200, r.get_data(as_text=True)

    _db.session.expire_all()
    embarcados = (
        _db.session.query(AlunosConfirmados).filter_by(viagem_id=viagem.id, embarcou=True).count()
    )
    assert embarcados == 1

    # The same credential does not board twice.
    r = condutor.post(
        f"/v1/embarque/viagens/{viagem_id}/confirmacao",
        json={"qr_token": _qr_do_app(credencial_ana, relogio)},
    )
    assert r.status_code == 409
    assert r.get_json()["error"]["code"] == "CREDENCIAL_JA_UTILIZADA"

    # A screenshot of Ana's QR kept by someone stops working within a minute.
    relogio.avancar(seconds=90)
    r = condutor.post(f"/v1/embarque/viagens/{viagem_id}/confirmacao", json={"qr_token": qr_ana})
    assert r.status_code == 409
    assert r.get_json()["error"]["code"] == "CODIGO_EXPIRADO"


@pytest.mark.e2e
def test_buffer_sem_nenhum_trajeto_cancela_a_viagem(
    _db, operacao, van, passageiros, condutor, relogio
):
    """RF-15 secondary flow 1: no one declared a route, the van does not leave."""
    ana = passageiros[0]

    viagem_id = ana.post(f"/v1/rotas/{operacao.id}/solicitacoes").get_json()["viagem_id"]
    condutor.post(f"/v1/viagens/{viagem_id}/iniciar-percurso")

    assert _expirar_buffer(relogio) == 1

    viagem = _db.session.get(Viagem, viagem_id)
    assert viagem.status == StatusViagem.CANCELADA
    assert viagem.inicio_real is None

    # And the loose interest is not left hanging for the next trip.
    ativas = SolicitacaoViagem.query.filter_by(
        viagem_id=viagem.id, status=StatusSolicitacao.ATIVA
    ).count()
    assert ativas == 0


@pytest.mark.e2e
def test_cancelar_no_buffer_devolve_a_vaga_para_quem_tinha_sido_negado(
    _db, operacao, pontos_circuito, onibus, passageiros, condutor
):
    """RF-19 + RF-14: the freed seat can be offered again on the same trip."""
    onibus.capacidade = 1
    _db.session.commit()

    p1, p2, _, _ = pontos_circuito
    ana, bruno, *_ = passageiros

    viagem_id = ana.post(f"/v1/rotas/{operacao.id}/solicitacoes").get_json()["viagem_id"]
    condutor.post(f"/v1/viagens/{viagem_id}/iniciar-percurso")

    trajeto = _trajeto(p1, p2)
    assert ana.post(f"/v1/viagens/{viagem_id}/declaracao", json=trajeto).status_code == 200
    # Only seat taken: Bruno is denied.
    assert bruno.post(f"/v1/viagens/{viagem_id}/declaracao", json=trajeto).status_code == 409

    # Ana drops out during the buffer and the seat exists again.
    r = ana.delete(f"/v1/viagens/{viagem_id}/solicitacao")
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["status"] == StatusSolicitacao.CANCELADA.value

    assert bruno.post(f"/v1/viagens/{viagem_id}/declaracao", json=trajeto).status_code == 200


@pytest.mark.e2e
def test_sem_consentimento_nao_solicita(client, app, _db, operacao, van, organizacao):
    """RF-09: without accepting the terms, the flow does not even start."""
    aluno = AlunoFactory(organizacao_id=organizacao.id)
    _db.session.add(aluno)
    _db.session.commit()

    r = _ator(client, app, aluno).post(f"/v1/rotas/{operacao.id}/solicitacoes")
    assert r.status_code == 403, r.get_data(as_text=True)
    assert _db.session.query(Viagem).count() == 0, "nada pode ser criado sem consentimento"
