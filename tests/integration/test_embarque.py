"""Embarque por credencial: RF-15, RF-16, RF-17 e RF-18.

A rodada consolidada é o ponto de partida de quase tudo aqui, então ela é
montada uma vez na fixture `rodada`: três alunos com trajetos que se cruzam
(P1→P3 e P2→P4) e um disjunto (P3→P4), o suficiente para que as contagens de
embarque e desembarque do roteiro sejam diferentes em cada ponto.
"""

from datetime import UTC, datetime, timedelta

import pytest
from flask_jwt_extended import create_access_token

from app.models.enum import StatusSolicitacao, StatusViagem, TipoOcorrencia
from app.models.ocorrencia import Ocorrencia
from app.models.viagem import AlunosConfirmados, TelemetriaViagem, Viagem, ViagemPonto
from app.services import capacidade_service
from app.tasks.viagem_tasks import consolidar_buffers_expirados
from tests.conftest import Actor, AuthenticatedClient
from tests.factories.user_factory import AlunoFactory
from tests.factories.viagem_factory import ViagemFactory


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
    # A fábrica sorteia a capacidade do veículo; aqui vale a da van real do
    # PaqTcPB, senão um sorteio baixo nega os trajetos que se cruzam.
    viagem.veiculo.capacidade = 17
    viagem.status = StatusViagem.BUFFER_ABERTO
    viagem.buffer_expira_em = datetime.now(UTC) + timedelta(minutes=5)
    _db.session.commit()

    for aluno_id, origem, destino in reservas:
        capacidade_service.validar_e_reservar(viagem.id, aluno_id, origem.id, destino.id)

    viagem.buffer_expira_em = datetime.now(UTC) - timedelta(seconds=1)
    _db.session.commit()

    consolidar_buffers_expirados()
    _db.session.refresh(viagem)
    return viagem


@pytest.fixture()
def rodada(_db, viagem_ociosa, pontos_circuito, aluno, aluno2, aluno3):
    p1, p2, p3, p4 = pontos_circuito
    return _consolidar(
        _db,
        viagem_ociosa,
        [
            (aluno.user.id, p1, p3),
            (aluno2.user.id, p2, p4),
            (aluno3.user.id, p3, p4),
        ],
    )


def _registro(_db, viagem, actor) -> AlunosConfirmados:
    return _db.session.get(AlunosConfirmados, (viagem.id, actor.user.id))


# ==========================================
# RF-15 — emissão das credenciais
# ==========================================


@pytest.mark.integration
def test_consolidacao_emite_uma_credencial_por_confirmado(_db, rodada, aluno, aluno2, aluno3):
    tokens = [_registro(_db, rodada, a).qr_token for a in (aluno, aluno2, aluno3)]

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
    _db, viagem_ociosa, pontos_circuito, aluno, aluno2
):
    p1, _, p3, _ = pontos_circuito
    _db.session.add(
        AlunosConfirmados(
            viagem_id=viagem_ociosa.id,
            aluno_id=aluno2.user.id,
            confirmacao=False,
            status=StatusSolicitacao.INTERESSADO,
        )
    )
    _db.session.commit()

    _consolidar(_db, viagem_ociosa, [(aluno.user.id, p1, p3)])

    assert _registro(_db, viagem_ociosa, aluno).qr_token
    assert _registro(_db, viagem_ociosa, aluno2).qr_token is None


@pytest.mark.integration
def test_aluno_busca_a_propria_credencial(rodada, aluno, pontos_circuito):
    r = aluno.client.get(f"/v1/embarque/viagens/{rodada.id}/credencial")

    assert r.status_code == 200, r.get_data(as_text=True)
    corpo = r.get_json()
    assert corpo["aluno_id"] == str(aluno.user.id)
    assert corpo["qr_token"]
    assert corpo["ponto_embarque_id"] == str(pontos_circuito[0].id)


@pytest.mark.integration
def test_aluno_de_fora_da_rodada_nao_alcanca_credencial_alguma(
    _db, viagem_ociosa, pontos_circuito, aluno, aluno2
):
    """A busca é sempre pela identidade do JWT: não há como pedir a do outro."""
    p1, _, p3, _ = pontos_circuito
    _consolidar(_db, viagem_ociosa, [(aluno.user.id, p1, p3)])

    r = aluno2.client.get(f"/v1/embarque/viagens/{viagem_ociosa.id}/credencial")
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
    assert passageiros[0]["qr_token"] == _registro(_db, rodada, aluno).qr_token


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


@pytest.mark.integration
def test_credencial_valida_registra_o_embarque(_db, rodada, motorista, aluno):
    r = _validar(motorista, rodada, _registro(_db, rodada, aluno).qr_token)

    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["manual"] is False

    registro = _registro(_db, rodada, aluno)
    assert registro.embarcou is True
    assert registro.embarcado_em is not None


@pytest.mark.integration
def test_credencial_desconhecida(rodada, motorista):
    r = _validar(motorista, rodada, "token-que-nunca-foi-emitido")

    assert r.status_code == 404
    assert r.get_json()["error"]["code"] == "CREDENCIAL_DESCONHECIDA"


@pytest.mark.integration
def test_credencial_de_outra_viagem(
    _db, rodada, motorista, onibus, circuito, janela_hoje, pontos_circuito, aluno2
):
    p2, p4 = pontos_circuito[1], pontos_circuito[3]
    outra = ViagemFactory(
        data=rodada.data,
        rota_id=circuito.id,
        janela_id=janela_hoje.id,
        motorista_id=motorista.user.id,
        veiculo_id=onibus.id,
        status=StatusViagem.OCIOSA,
    )
    _db.session.add(outra)
    _db.session.commit()

    # aluno2 já está na `rodada`; aqui ele ganha uma credencial da outra viagem.
    _consolidar(_db, outra, [(aluno2.user.id, p2, p4)])
    token_da_outra = _db.session.get(AlunosConfirmados, (outra.id, aluno2.user.id)).qr_token

    r = _validar(motorista, rodada, token_da_outra)

    assert r.status_code == 409
    assert r.get_json()["error"]["code"] == "CREDENCIAL_DE_OUTRA_VIAGEM"


@pytest.mark.integration
def test_credencial_de_outro_ponto(_db, rodada, motorista, aluno2):
    """O veículo está em P1 e a credencial do aluno 2 é de P2."""
    r = _validar(motorista, rodada, _registro(_db, rodada, aluno2).qr_token)

    assert r.status_code == 409
    assert r.get_json()["error"]["code"] == "CREDENCIAL_DE_OUTRO_PONTO"
    assert _registro(_db, rodada, aluno2).embarcou is False


@pytest.mark.integration
def test_credencial_ja_utilizada(_db, rodada, motorista, aluno):
    token = _registro(_db, rodada, aluno).qr_token
    assert _validar(motorista, rodada, token).status_code == 200

    r = _validar(motorista, rodada, token)
    assert r.status_code == 409
    assert r.get_json()["error"]["code"] == "CREDENCIAL_JA_UTILIZADA"


@pytest.mark.integration
def test_fallback_manual_registra_embarque_e_deixa_rastro(_db, rodada, motorista, aluno):
    r = motorista.client.post(
        f"/v1/embarque/viagens/{rodada.id}/manual", json={"aluno_id": str(aluno.user.id)}
    )

    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["manual"] is True
    assert _registro(_db, rodada, aluno).embarcou is True

    ocorrencias = _db.session.query(Ocorrencia).filter_by(viagem_id=rodada.id).all()
    assert len(ocorrencias) == 1
    assert ocorrencias[0].tipo == TipoOcorrencia.OUTRO
    assert "manual" in ocorrencias[0].descricao.lower()


@pytest.mark.integration
def test_fallback_manual_recusa_aluno_de_outro_ponto(_db, rodada, motorista, aluno2):
    r = motorista.client.post(
        f"/v1/embarque/viagens/{rodada.id}/manual", json={"aluno_id": str(aluno2.user.id)}
    )

    assert r.status_code == 409
    assert r.get_json()["error"]["code"] == "CREDENCIAL_DE_OUTRO_PONTO"


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
            "qr_token": _registro(_db, rodada, aluno).qr_token,
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
    # O fallback manual reenviado não duplica a ocorrência de auditoria.
    assert _db.session.query(Ocorrencia).filter_by(viagem_id=rodada.id).count() == 1


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
                "qr_token": _registro(_db, rodada, aluno).qr_token,
                "ponto_id": str(pontos_circuito[0].id),
            }
        ],
    ).get_json()

    assert corpo["aplicados"] == 1
    assert _registro(_db, rodada, aluno).embarcou is True
