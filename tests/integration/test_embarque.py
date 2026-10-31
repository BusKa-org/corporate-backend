"""Embarque por credencial: RF-15, RF-16, RF-17 e RF-18.

A rodada consolidada é o ponto de partida de quase tudo aqui, então ela é
montada uma vez na fixture `rodada`: três alunos com trajetos que se cruzam
(P1→P3 e P2→P4) e um disjunto (P3→P4), o suficiente para que as contagens de
embarque e desembarque do roteiro sejam diferentes em cada ponto.
"""

import io
from datetime import UTC, datetime, timedelta

import pytest
from flask_jwt_extended import create_access_token

from app.models.credencial_embarque import CredencialEmbarque
from app.models.enum import StatusOcorrencia, StatusViagem, TipoOcorrencia
from app.models.ocorrencia import Ocorrencia
from app.models.viagem import AlunosConfirmados, TelemetriaViagem, Viagem, ViagemPonto
from app.services import buffer_service, consentimento_service
from tests.conftest import Actor, AuthenticatedClient, reservar_trajeto
from tests.factories.user_factory import AlunoFactory, MotoristaFactory
from tests.factories.viagem_factory import SolicitacaoViagemFactory, ViagemFactory
from tests.helpers import imagens


def _aluno(client, app, _db, organizacao) -> Actor:
    u = AlunoFactory(organizacao_id=organizacao.id)
    _db.session.add(u)
    _db.session.commit()
    with app.app_context():
        token = create_access_token(identity=str(u.id))
    headers = {"Authorization": f"Bearer {token}"}
    return Actor(user=u, headers=headers, client=AuthenticatedClient(client, headers))


@pytest.fixture()
def aluno2(client, app, _db, organizacao):
    return _aluno(client, app, _db, organizacao)


@pytest.fixture()
def aluno3(client, app, _db, organizacao):
    return _aluno(client, app, _db, organizacao)


def _consolidar(_db, viagem, reservas):
    """Abre o buffer, registra os trajetos e deixa a varredura consolidar."""
    # A fábrica sorteia a capacidade do veículo; aqui ela é fixa, senão um
    # sorteio baixo nega os trajetos que se cruzam.
    viagem.veiculo.capacidade = 17
    viagem.status = StatusViagem.BUFFER_ABERTO
    viagem.buffer_fim = datetime.now(UTC) + timedelta(minutes=5)
    _db.session.commit()

    for aluno_id, origem, destino in reservas:
        reservar_trajeto(_db, viagem, aluno_id, origem.id, destino.id)

    viagem.buffer_fim = datetime.now(UTC) - timedelta(seconds=1)
    _db.session.commit()

    buffer_service.fechar_buffers_expirados()
    _db.session.refresh(viagem)
    return viagem


@pytest.fixture()
def rodada(_db, viagem_buffer_aberto, pontos_circuito, aluno, aluno2, aluno3):
    p1, p2, p3, p4 = pontos_circuito
    return _consolidar(
        _db,
        viagem_buffer_aberto,
        [
            (aluno.user.id, p1, p3),
            (aluno2.user.id, p2, p4),
            (aluno3.user.id, p3, p4),
        ],
    )


def _registro(_db, viagem, actor) -> AlunosConfirmados:
    return _db.session.get(AlunosConfirmados, (viagem.id, actor.user.id))


def _token(_db, viagem, actor) -> str | None:
    """Token da credencial de embarque do aluno na viagem, ou None."""
    credencial = (
        _db.session.query(CredencialEmbarque)
        .filter_by(viagem_id=viagem.id, aluno_id=actor.user.id)
        .first()
    )
    return credencial.token if credencial else None


# ==========================================
# RF-15 — emissão das credenciais
# ==========================================


@pytest.mark.integration
def test_consolidacao_emite_uma_credencial_por_confirmado(_db, rodada, aluno, aluno2, aluno3):
    tokens = [_token(_db, rodada, a) for a in (aluno, aluno2, aluno3)]

    assert all(tokens)
    assert len(set(tokens)) == 3


@pytest.mark.integration
def test_consolidacao_materializa_o_roteiro(_db, rodada, pontos_circuito):
    pontos = (
        _db.session.query(ViagemPonto)
        .filter_by(viagem_id=rodada.id)
        .order_by(ViagemPonto.ordem)
        .all()
    )
    assert [vp.ponto_id for vp in pontos] == [p.id for p in pontos_circuito]
    assert not any(vp.visitado for vp in pontos)


@pytest.mark.integration
def test_interessado_que_nao_declarou_trajeto_nao_recebe_credencial(
    _db, viagem_buffer_aberto, pontos_circuito, aluno, aluno2
):
    p1, _, p3, _ = pontos_circuito
    _db.session.add(
        SolicitacaoViagemFactory(viagem_id=viagem_buffer_aberto.id, aluno_id=aluno2.user.id)
    )
    _db.session.commit()

    _consolidar(_db, viagem_buffer_aberto, [(aluno.user.id, p1, p3)])

    assert _token(_db, viagem_buffer_aberto, aluno)
    assert _token(_db, viagem_buffer_aberto, aluno2) is None


@pytest.mark.integration
def test_aluno_busca_a_propria_credencial(_db, rodada, aluno, pontos_circuito):
    r = aluno.client.get(f"/v1/viagens/{rodada.id}/credencial-embarque")

    assert r.status_code == 200, r.get_data(as_text=True)
    corpo = r.get_json()
    assert corpo["token"] == _token(_db, rodada, aluno)
    assert corpo["ponto_embarque_id"] == str(pontos_circuito[0].id)


@pytest.mark.integration
def test_aluno_de_fora_da_rodada_nao_alcanca_credencial_alguma(
    _db, viagem_buffer_aberto, pontos_circuito, aluno, aluno2
):
    """A busca é sempre pela identidade do JWT: não há como pedir a do outro."""
    p1, _, p3, _ = pontos_circuito
    _consolidar(_db, viagem_buffer_aberto, [(aluno.user.id, p1, p3)])
    consentimento_service.aceitar(str(aluno2.user.id), consentimento_service.VERSAO_TERMO_VIGENTE)

    r = aluno2.client.get(f"/v1/viagens/{viagem_buffer_aberto.id}/credencial-embarque")
    assert r.status_code == 404


# ==========================================
# RF-16 — roteiro do motorista
# ==========================================


@pytest.mark.integration
def test_roteiro_conta_embarques_e_desembarques_por_ponto(rodada, motorista):
    r = motorista.client.get(f"/v1/embarque/viagens/{rodada.id}/roteiro")

    assert r.status_code == 200, r.get_data(as_text=True)
    corpo = r.get_json()
    contagens = [(p["embarcam"], p["desembarcam"]) for p in corpo["pontos"]]

    # P1: sobe o aluno 1. P2: sobe o 2. P3: desce o 1 e sobe o 3. P4: descem 2.
    assert contagens == [(1, 0), (1, 0), (1, 1), (0, 2)]
    assert corpo["pontos"][0]["instrucao"].startswith("Aproximando-se de ")
    assert corpo["pontos"][0]["instrucao"].endswith("embarcam 1, desembarcam 0")
    assert corpo["ponto_atual_id"] == corpo["pontos"][0]["ponto_id"]


@pytest.mark.integration
def test_roteiro_traz_a_matriz_de_permissoes_do_ponto(_db, rodada, motorista, aluno):
    corpo = motorista.client.get(f"/v1/embarque/viagens/{rodada.id}/roteiro").get_json()

    passageiros = corpo["pontos"][0]["passageiros"]
    assert [p["aluno_id"] for p in passageiros] == [str(aluno.user.id)]
    assert passageiros[0]["qr_token"] == _token(_db, rodada, aluno)


@pytest.mark.integration
def test_roteiro_ignora_quem_desistiu(_db, rodada, motorista, aluno):
    registro = _registro(_db, rodada, aluno)
    registro.confirmacao = False
    _db.session.commit()

    corpo = motorista.client.get(f"/v1/embarque/viagens/{rodada.id}/roteiro").get_json()
    assert corpo["pontos"][0]["embarcam"] == 0


@pytest.mark.integration
def test_roteiro_e_do_motorista_da_viagem(rodada, other_motorista, aluno):
    assert (
        other_motorista.client.get(f"/v1/embarque/viagens/{rodada.id}/roteiro").status_code == 403
    )
    assert aluno.client.get(f"/v1/embarque/viagens/{rodada.id}/roteiro").status_code == 403


@pytest.mark.integration
def test_avancar_marca_a_parada_e_muda_a_instrucao(_db, rodada, motorista, pontos_circuito):
    r = motorista.client.post(f"/v1/embarque/viagens/{rodada.id}/roteiro/avancar", json={})

    assert r.status_code == 200, r.get_data(as_text=True)
    corpo = r.get_json()
    assert corpo["pontos"][0]["visitado"] is True
    assert corpo["pontos"][0]["chegada_real"]
    assert corpo["ponto_atual_id"] == str(pontos_circuito[1].id)
    assert corpo["instrucao_atual"] == corpo["pontos"][1]["instrucao"]


@pytest.mark.integration
def test_avancar_alem_do_ultimo_ponto_e_recusado(rodada, motorista, pontos_circuito):
    for _ in pontos_circuito:
        motorista.client.post(f"/v1/embarque/viagens/{rodada.id}/roteiro/avancar", json={})

    r = motorista.client.post(f"/v1/embarque/viagens/{rodada.id}/roteiro/avancar", json={})
    assert r.status_code == 400


# ==========================================
# RF-17 — validação do embarque
# ==========================================


def _validar(motorista, viagem, token):
    return motorista.client.post(
        f"/v1/embarque/viagens/{viagem.id}/validacao", json={"qr_token": token}
    )


def _confirmar(motorista, viagem, token):
    return motorista.client.post(
        f"/v1/embarque/viagens/{viagem.id}/confirmacao", json={"qr_token": token}
    )


def _recusar(motorista, viagem, token, motivo="FOTO_NAO_CONFERE", observacao=None):
    corpo = {"qr_token": token, "motivo": motivo}
    if observacao:
        corpo["observacao"] = observacao
    return motorista.client.post(f"/v1/embarque/viagens/{viagem.id}/recusa", json=corpo)


def _com_foto(_db, actor) -> str:
    foto_url = f"/v1/alunos/{actor.user.id}/foto"
    actor.user.foto_url = foto_url
    _db.session.commit()
    return foto_url


def _credencial(_db, viagem, actor) -> CredencialEmbarque:
    return (
        _db.session.query(CredencialEmbarque)
        .filter_by(viagem_id=viagem.id, aluno_id=actor.user.id)
        .one()
    )


def _ocorrencias(_db, viagem) -> list[Ocorrencia]:
    _db.session.expire_all()
    return _db.session.query(Ocorrencia).filter_by(viagem_id=viagem.id).all()


@pytest.mark.integration
def test_leitura_devolve_passageiro_e_foto_sem_embarcar(
    _db, rodada, motorista, aluno, pontos_circuito
):
    foto_url = _com_foto(_db, aluno)

    r = _validar(motorista, rodada, _token(_db, rodada, aluno))

    assert r.status_code == 200, r.get_data(as_text=True)
    corpo = r.get_json()
    assert corpo["aluno_id"] == str(aluno.user.id)
    assert corpo["nome"] == aluno.user.nome
    assert corpo["foto_url"] == foto_url
    assert corpo["sem_foto"] is False
    assert corpo["ponto_embarque_id"] == str(pontos_circuito[0].id)
    assert corpo["ponto_destino_id"] == str(pontos_circuito[2].id)

    _db.session.expire_all()
    assert _registro(_db, rodada, aluno).embarcou is False
    assert _credencial(_db, rodada, aluno).usado is False
    assert _ocorrencias(_db, rodada) == []


@pytest.mark.integration
def test_confirmacao_registra_o_embarque_e_consome_a_credencial(_db, rodada, motorista, aluno):
    _com_foto(_db, aluno)
    token = _token(_db, rodada, aluno)
    assert _validar(motorista, rodada, token).status_code == 200

    r = _confirmar(motorista, rodada, token)

    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["manual"] is False
    assert r.get_json()["sem_foto"] is False
    _db.session.expire_all()
    registro = _registro(_db, rodada, aluno)
    assert registro.embarcou is True
    assert registro.embarcado_em is not None
    assert _credencial(_db, rodada, aluno).usado is True
    assert _ocorrencias(_db, rodada) == []

    segunda = _confirmar(motorista, rodada, token)
    assert segunda.status_code == 409
    assert segunda.get_json()["error"]["code"] == "CREDENCIAL_JA_UTILIZADA"


@pytest.mark.integration
def test_recusa_abre_ocorrencia_e_deixa_a_credencial_para_o_manual(_db, rodada, motorista, aluno):
    _com_foto(_db, aluno)
    token = _token(_db, rodada, aluno)

    r = _recusar(motorista, rodada, token, observacao="pessoa diferente da foto")

    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["motivo"] == "FOTO_NAO_CONFERE"
    ocorrencias = _ocorrencias(_db, rodada)
    assert len(ocorrencias) == 1
    assert str(ocorrencias[0].id) == r.get_json()["ocorrencia_id"]
    assert ocorrencias[0].status == StatusOcorrencia.ABERTA
    assert "FOTO_NAO_CONFERE" in ocorrencias[0].descricao
    assert "pessoa diferente da foto" in ocorrencias[0].descricao
    assert _registro(_db, rodada, aluno).embarcou is False
    assert _credencial(_db, rodada, aluno).usado is False

    # O passageiro real aparece e embarca pelo fallback manual.
    manual = motorista.client.post(
        f"/v1/embarque/viagens/{rodada.id}/manual", json={"aluno_id": str(aluno.user.id)}
    )
    assert manual.status_code == 200, manual.get_data(as_text=True)
    assert _registro(_db, rodada, aluno).embarcou is True


@pytest.mark.integration
def test_recusa_com_motivo_desconhecido_e_invalida(_db, rodada, motorista, aluno):
    r = _recusar(motorista, rodada, _token(_db, rodada, aluno), motivo="CARA_FEIA")
    assert r.status_code == 400


@pytest.mark.integration
def test_aluno_sem_foto_embarca_com_aviso_e_ocorrencia(_db, rodada, motorista, aluno):
    token = _token(_db, rodada, aluno)

    leitura = _validar(motorista, rodada, token).get_json()
    assert leitura["sem_foto"] is True
    assert leitura["foto_url"] is None

    r = _confirmar(motorista, rodada, token)

    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["sem_foto"] is True
    assert _registro(_db, rodada, aluno).embarcou is True
    ocorrencias = _ocorrencias(_db, rodada)
    assert len(ocorrencias) == 1
    assert ocorrencias[0].status == StatusOcorrencia.ABERTA
    assert "sem foto" in ocorrencias[0].descricao


@pytest.mark.integration
@pytest.mark.parametrize("passo", ["validacao", "confirmacao", "recusa"])
def test_credencial_desconhecida(rodada, motorista, passo):
    r = motorista.client.post(
        f"/v1/embarque/viagens/{rodada.id}/{passo}",
        json={"qr_token": "token-que-nunca-foi-emitido", "motivo": "FOTO_NAO_CONFERE"},
    )

    assert r.status_code == 404
    assert r.get_json()["error"]["code"] == "CREDENCIAL_DESCONHECIDA"


@pytest.mark.integration
def test_credencial_de_outra_viagem(
    _db, rodada, motorista, onibus, circuito, pontos_circuito, aluno2
):
    p2, p4 = pontos_circuito[1], pontos_circuito[3]
    outra = ViagemFactory(
        data=rodada.data,
        rota_id=circuito.id,
        motorista_id=motorista.user.id,
        veiculo_id=onibus.id,
        status=StatusViagem.SOLICITADA,
    )
    _db.session.add(outra)
    _db.session.commit()

    # aluno2 já está na `rodada`; aqui ele ganha uma credencial da outra viagem.
    _consolidar(_db, outra, [(aluno2.user.id, p2, p4)])
    token_da_outra = _token(_db, outra, aluno2)

    for r in (
        _validar(motorista, rodada, token_da_outra),
        _confirmar(motorista, rodada, token_da_outra),
        _recusar(motorista, rodada, token_da_outra),
    ):
        assert r.status_code == 409
        assert r.get_json()["error"]["code"] == "CREDENCIAL_DE_OUTRA_VIAGEM"


@pytest.mark.integration
def test_credencial_de_outro_ponto(_db, rodada, motorista, aluno2):
    """O veículo está em P1 e a credencial do aluno 2 é de P2."""
    token = _token(_db, rodada, aluno2)

    for r in (
        _validar(motorista, rodada, token),
        _confirmar(motorista, rodada, token),
        _recusar(motorista, rodada, token),
    ):
        assert r.status_code == 409
        assert r.get_json()["error"]["code"] == "CREDENCIAL_DE_OUTRO_PONTO"
    assert _registro(_db, rodada, aluno2).embarcou is False
    assert _ocorrencias(_db, rodada) == []


@pytest.mark.integration
def test_credencial_expirada(_db, rodada, motorista, aluno):
    credencial = _credencial(_db, rodada, aluno)
    credencial.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    _db.session.commit()

    for r in (
        _validar(motorista, rodada, credencial.token),
        _confirmar(motorista, rodada, credencial.token),
        _recusar(motorista, rodada, credencial.token),
    ):
        assert r.status_code == 409
        assert r.get_json()["error"]["code"] == "CREDENCIAL_EXPIRADA"


@pytest.mark.integration
def test_credencial_ja_utilizada(_db, rodada, motorista, aluno):
    token = _token(_db, rodada, aluno)
    assert _confirmar(motorista, rodada, token).status_code == 200

    for r in (_validar(motorista, rodada, token), _recusar(motorista, rodada, token)):
        assert r.status_code == 409
        assert r.get_json()["error"]["code"] == "CREDENCIAL_JA_UTILIZADA"


@pytest.mark.integration
def test_outro_motorista_nao_le_confirma_nem_recusa(_db, rodada, other_motorista, aluno):
    token = _token(_db, rodada, aluno)

    for r in (
        _validar(other_motorista, rodada, token),
        _confirmar(other_motorista, rodada, token),
        _recusar(other_motorista, rodada, token),
    ):
        assert r.status_code == 403
    assert _registro(_db, rodada, aluno).embarcou is False
    assert _ocorrencias(_db, rodada) == []


@pytest.mark.integration
def test_fallback_manual_registra_embarque_e_deixa_rastro(_db, rodada, motorista, aluno):
    _com_foto(_db, aluno)
    r = motorista.client.post(
        f"/v1/embarque/viagens/{rodada.id}/manual", json={"aluno_id": str(aluno.user.id)}
    )

    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["manual"] is True
    assert _registro(_db, rodada, aluno).embarcou is True

    ocorrencias = _ocorrencias(_db, rodada)
    assert len(ocorrencias) == 1
    assert ocorrencias[0].tipo == TipoOcorrencia.OUTRO
    assert "manual" in ocorrencias[0].descricao.lower()
    assert "foto da lista do ponto" in ocorrencias[0].descricao


@pytest.mark.integration
def test_fallback_manual_recusa_aluno_de_outro_ponto(_db, rodada, motorista, aluno2):
    r = motorista.client.post(
        f"/v1/embarque/viagens/{rodada.id}/manual", json={"aluno_id": str(aluno2.user.id)}
    )

    assert r.status_code == 409
    assert r.get_json()["error"]["code"] == "CREDENCIAL_DE_OUTRO_PONTO"


@pytest.mark.integration
def test_roteiro_traz_a_foto_de_cada_passageiro(_db, rodada, motorista, aluno, aluno2):
    foto_url = _com_foto(_db, aluno)

    corpo = motorista.client.get(f"/v1/embarque/viagens/{rodada.id}/roteiro").get_json()

    com_foto = corpo["pontos"][0]["passageiros"][0]
    assert (com_foto["nome"], com_foto["foto_url"], com_foto["sem_foto"]) == (
        aluno.user.nome,
        foto_url,
        False,
    )
    sem_foto = corpo["pontos"][1]["passageiros"][0]
    assert sem_foto["aluno_id"] == str(aluno2.user.id)
    assert (sem_foto["foto_url"], sem_foto["sem_foto"]) == (None, True)


@pytest.mark.integration
def test_motorista_ve_a_foto_do_passageiro_do_roteiro_e_o_de_outra_viagem_nao(
    client, app, _db, rodada, motorista, aluno, organizacao, tmp_path, monkeypatch
):
    """RF-18: com a viagem em rota, o app baixa as fotos do roteiro antes de perder a rede."""
    monkeypatch.setitem(app.config, "FOTOS_ALUNO_DIR", str(tmp_path))
    enviada = aluno.client.put(
        "/v1/alunos/me/foto",
        data={"foto": (io.BytesIO(imagens.png()), "foto.png")},
        content_type="multipart/form-data",
    )
    assert enviada.status_code == 200, enviada.get_data(as_text=True)

    corpo = motorista.client.get(f"/v1/embarque/viagens/{rodada.id}/roteiro").get_json()
    foto_url = corpo["pontos"][0]["passageiros"][0]["foto_url"]
    assert motorista.client.get(foto_url).status_code == 200

    outro = MotoristaFactory(organizacao_id=organizacao.id)
    _db.session.add(outro)
    _db.session.commit()
    with app.app_context():
        headers = {"Authorization": f"Bearer {create_access_token(identity=str(outro.id))}"}
    assert client.get(foto_url, headers=headers).status_code == 403


# ==========================================
# RF-18 — sincronização em lote
# ==========================================


def _lote(_db, rodada, aluno, aluno2, pontos_circuito):
    p1, p2 = pontos_circuito[0], pontos_circuito[1]
    base = datetime.now(UTC) - timedelta(minutes=10)
    return [
        {
            "evento_id": "ev-embarque-1",
            "tipo": "EMBARQUE",
            "ocorrido_em": base.isoformat(),
            "qr_token": _token(_db, rodada, aluno),
            "ponto_id": str(p1.id),
        },
        {
            "evento_id": "ev-chegada-1",
            "tipo": "CHEGADA_PONTO",
            "ocorrido_em": (base + timedelta(minutes=1)).isoformat(),
            "ponto_id": str(p1.id),
        },
        {
            "evento_id": "ev-posicao-1",
            "tipo": "POSICAO",
            "ocorrido_em": (base + timedelta(minutes=2)).isoformat(),
            "latitude": "-7.21",
            "longitude": "-35.88",
        },
        {
            "evento_id": "ev-manual-1",
            "tipo": "EMBARQUE_MANUAL",
            "ocorrido_em": (base + timedelta(minutes=3)).isoformat(),
            "aluno_id": str(aluno2.user.id),
            "ponto_id": str(p2.id),
        },
    ]


def _sincronizar(motorista, rodada, eventos):
    return motorista.client.post(
        f"/v1/embarque/viagens/{rodada.id}/sincronizacao", json={"eventos": eventos}
    )


@pytest.mark.integration
def test_lote_misto_e_aplicado(_db, rodada, motorista, aluno, aluno2, pontos_circuito):
    eventos = _lote(_db, rodada, aluno, aluno2, pontos_circuito)

    r = _sincronizar(motorista, rodada, eventos)

    assert r.status_code == 200, r.get_data(as_text=True)
    corpo = r.get_json()
    assert corpo["aplicados"] == 4
    assert [x["situacao"] for x in corpo["resultados"]] == ["aplicado"] * 4

    assert _registro(_db, rodada, aluno).embarcou is True
    assert _registro(_db, rodada, aluno2).embarcou is True
    assert _db.session.get(ViagemPonto, (rodada.id, pontos_circuito[0].id)).visitado is True
    assert _db.session.query(TelemetriaViagem).filter_by(viagem_id=rodada.id).count() == 1


@pytest.mark.integration
def test_lote_reenviado_nao_muda_nada(_db, rodada, motorista, aluno, aluno2, pontos_circuito):
    eventos = _lote(_db, rodada, aluno, aluno2, pontos_circuito)
    _sincronizar(motorista, rodada, eventos)

    embarcado_em = _registro(_db, rodada, aluno).embarcado_em
    chegada = _db.session.get(ViagemPonto, (rodada.id, pontos_circuito[0].id)).chegada_real

    r = _sincronizar(motorista, rodada, eventos)

    corpo = r.get_json()
    assert corpo["aplicados"] == 0
    assert corpo["ja_aplicados"] == 4

    _db.session.expire_all()
    assert _registro(_db, rodada, aluno).embarcado_em == embarcado_em
    assert _db.session.get(ViagemPonto, (rodada.id, pontos_circuito[0].id)).chegada_real == chegada
    assert _db.session.query(TelemetriaViagem).filter_by(viagem_id=rodada.id).count() == 1
    # Reenviados, o embarque sem foto e o fallback manual não duplicam a auditoria.
    assert _db.session.query(Ocorrencia).filter_by(viagem_id=rodada.id).count() == 2


@pytest.mark.integration
def test_evento_invalido_nao_derruba_o_resto_do_lote(
    _db, rodada, motorista, aluno, aluno2, pontos_circuito
):
    eventos = _lote(_db, rodada, aluno, aluno2, pontos_circuito)
    eventos.insert(
        1,
        {
            "evento_id": "ev-invalido",
            "tipo": "EMBARQUE",
            "ocorrido_em": datetime.now(UTC).isoformat(),
            "qr_token": "credencial-inexistente",
        },
    )

    corpo = _sincronizar(motorista, rodada, eventos).get_json()

    assert corpo["aplicados"] == 4
    assert corpo["recusados"] == 1
    recusado = next(x for x in corpo["resultados"] if x["situacao"] == "recusado")
    assert recusado["evento_id"] == "ev-invalido"
    assert recusado["codigo"] == "CREDENCIAL_DESCONHECIDA"
    assert _registro(_db, rodada, aluno).embarcou is True


@pytest.mark.integration
def test_posicao_atrasada_nao_sobrescreve_a_mais_recente(_db, rodada, motorista):
    agora = datetime.now(UTC)
    eventos = [
        {
            "evento_id": "ev-nova",
            "tipo": "POSICAO",
            "ocorrido_em": agora.isoformat(),
            "latitude": "-7.10",
            "longitude": "-35.10",
        },
        {
            "evento_id": "ev-antiga",
            "tipo": "POSICAO",
            "ocorrido_em": (agora - timedelta(minutes=30)).isoformat(),
            "latitude": "-7.99",
            "longitude": "-35.99",
        },
    ]

    assert _sincronizar(motorista, rodada, eventos).get_json()["aplicados"] == 2

    _db.session.expire_all()
    viagem = _db.session.get(Viagem, rodada.id)
    assert float(viagem.motorista_lat) == pytest.approx(-7.10)
    # As duas posições ficam na trilha; só a corrente respeita o carimbo.
    assert _db.session.query(TelemetriaViagem).filter_by(viagem_id=rodada.id).count() == 2


@pytest.mark.integration
def test_sincronizacao_aceita_viagem_ja_finalizada(_db, rodada, motorista, aluno, pontos_circuito):
    """A fila pode chegar depois que o motorista encerrou o percurso."""
    rodada.status = StatusViagem.FINALIZADA
    _db.session.commit()

    corpo = _sincronizar(
        motorista,
        rodada,
        [
            {
                "evento_id": "ev-tardio",
                "tipo": "EMBARQUE",
                "ocorrido_em": datetime.now(UTC).isoformat(),
                "qr_token": _token(_db, rodada, aluno),
                "ponto_id": str(pontos_circuito[0].id),
            }
        ],
    ).get_json()

    assert corpo["aplicados"] == 1
    assert _registro(_db, rodada, aluno).embarcou is True


def _recusa_offline(_db, rodada, aluno, pontos_circuito, evento_id="ev-recusa-1"):
    return {
        "evento_id": evento_id,
        "tipo": "RECUSA",
        "ocorrido_em": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
        "qr_token": _token(_db, rodada, aluno),
        "ponto_id": str(pontos_circuito[0].id),
        "motivo": "FOTO_NAO_CONFERE",
        "observacao": "outra pessoa",
    }


@pytest.mark.integration
def test_recusa_offline_abre_ocorrencia_uma_vez_so(_db, rodada, motorista, aluno, pontos_circuito):
    eventos = [_recusa_offline(_db, rodada, aluno, pontos_circuito)]

    primeiro = _sincronizar(motorista, rodada, eventos).get_json()
    reenvio = _sincronizar(motorista, rodada, eventos).get_json()

    assert primeiro["aplicados"] == 1
    assert reenvio["ja_aplicados"] == 1
    ocorrencias = _ocorrencias(_db, rodada)
    assert len(ocorrencias) == 1
    assert ocorrencias[0].status == StatusOcorrencia.ABERTA
    assert "outra pessoa" in ocorrencias[0].descricao
    assert _registro(_db, rodada, aluno).embarcou is False
    assert _credencial(_db, rodada, aluno).usado is False


@pytest.mark.integration
def test_recusa_e_embarque_manual_offline_no_mesmo_lote(
    _db, rodada, motorista, aluno, pontos_circuito
):
    """Foto não confere, depois o passageiro real embarca pelo manual, tudo sem rede."""
    _com_foto(_db, aluno)
    recusa = _recusa_offline(_db, rodada, aluno, pontos_circuito)
    manual = {
        "evento_id": "ev-manual-depois-da-recusa",
        "tipo": "EMBARQUE_MANUAL",
        "ocorrido_em": datetime.now(UTC).isoformat(),
        "aluno_id": str(aluno.user.id),
        "ponto_id": str(pontos_circuito[0].id),
    }

    corpo = _sincronizar(motorista, rodada, [manual, recusa]).get_json()
    reenvio = _sincronizar(motorista, rodada, [manual, recusa]).get_json()

    # Fora de ordem: a recusa chega depois do embarque e ainda assim é registrada.
    assert corpo["aplicados"] == 2, corpo
    assert reenvio["ja_aplicados"] == 2
    assert _registro(_db, rodada, aluno).embarcou is True
    assert len(_ocorrencias(_db, rodada)) == 2


@pytest.mark.integration
def test_recusa_offline_sem_motivo_e_recusada(_db, rodada, motorista, aluno, pontos_circuito):
    evento = _recusa_offline(_db, rodada, aluno, pontos_circuito)
    del evento["motivo"]

    corpo = _sincronizar(motorista, rodada, [evento]).get_json()

    assert corpo["recusados"] == 1
    assert _ocorrencias(_db, rodada) == []
