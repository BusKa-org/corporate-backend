"""A rodada sob demanda substitui a inscrição permanente na rota (RotaAluno).

O que se garante aqui: nos pontos que serviam aos dois fluxos, a rodada sob
demanda usa a lista da própria rodada, e o fluxo programado herdado continua
usando o roster — sem que um contamine o outro.
"""

import pytest

from app.models.enum import StatusSolicitacao, StatusViagem
from app.models.viagem import AlunosConfirmados
from app.schemas.viagem_schema import ViagemResponseSchema
from app.services import consentimento_service, viagens_service


@pytest.mark.integration
def test_confirmacao_de_presenca_nao_serve_para_rodada_sob_demanda(aluno, viagem_ociosa, ponto):
    """A rodada exige declaração de origem e destino, que passa pela validação
    de capacidade — confirmar presença furaria essa validação."""
    r = aluno.client.put(
        f"/v1/viagens/{viagem_ociosa.id}/confirmacao",
        json={"confirmacao": True, "ponto_embarque_id": str(ponto.id)},
    )
    assert r.status_code == 400
    assert "declaracao" in (r.get_json() or {})["error"]["message"]


@pytest.mark.integration
def test_total_de_alunos_da_rodada_conta_participantes_nao_inscritos(
    _db, viagem_ociosa, aluno, circuito, rota_aluno
):
    """`rota_aluno` inscreve o aluno na rota *herdada*; a rodada não olha para
    isso — ela conta quem entrou na rodada."""
    payload = ViagemResponseSchema().dump(viagem_ociosa)
    assert payload["total_alunos"] == 0

    _db.session.add(
        AlunosConfirmados(
            viagem_id=viagem_ociosa.id,
            aluno_id=aluno.user.id,
            confirmacao=False,
            status=StatusSolicitacao.INTERESSADO,
        )
    )
    _db.session.commit()
    _db.session.refresh(viagem_ociosa)

    assert ViagemResponseSchema().dump(viagem_ociosa)["total_alunos"] == 1


@pytest.mark.integration
def test_desistente_sai_da_contagem_da_rodada(_db, viagem_ociosa, aluno):
    registro = AlunosConfirmados(
        viagem_id=viagem_ociosa.id,
        aluno_id=aluno.user.id,
        confirmacao=False,
        status=StatusSolicitacao.CANCELADO,
    )
    _db.session.add(registro)
    _db.session.commit()
    _db.session.refresh(viagem_ociosa)

    assert ViagemResponseSchema().dump(viagem_ociosa)["total_alunos"] == 0


@pytest.mark.integration
def test_viagem_programada_ainda_conta_pelo_roster(
    _db, viagem_futura_agendada_com_motorista, rota_aluno
):
    """O fluxo herdado continua contando os inscritos na rota."""
    payload = ViagemResponseSchema().dump(viagem_futura_agendada_com_motorista)
    assert payload["total_alunos"] == 1


@pytest.mark.integration
def test_gerar_viagem_programada_nao_copia_mais_o_roster(
    _db, gestor, rota, dia_operacao, rota_ponto, rota_aluno
):
    """A viagem nasce só com os pontos: passageiro entra por confirmação
    (fluxo herdado) ou por declaração de trajeto (rodada)."""
    from datetime import date, timedelta

    proxima_segunda = date.today()
    while proxima_segunda.weekday() != 0:
        proxima_segunda += timedelta(days=1)

    viagem = viagens_service.gerar_viagem(
        str(gestor.user.id), {"rota_id": str(rota.id), "data": proxima_segunda}
    )
    _db.session.refresh(viagem)

    assert viagem.status == StatusViagem.AGENDADA
    assert viagem.alunos_confirmados == []
    assert len(viagem.pontos_visitados) == 1


@pytest.mark.integration
def test_aviso_por_viagem_alcanca_o_interessado_da_rodada(_db, viagem_ociosa, aluno, gestor):
    """Numa rodada, quem só demonstrou interesse ainda não tem `confirmacao`,
    mas precisa receber o comunicado do gestor."""
    consentimento_service.registrar_aceite(str(aluno.user.id))
    _db.session.add(
        AlunosConfirmados(
            viagem_id=viagem_ociosa.id,
            aluno_id=aluno.user.id,
            confirmacao=False,
            status=StatusSolicitacao.INTERESSADO,
        )
    )
    _db.session.commit()

    r = gestor.client.post(
        "/v1/notificacoes/",
        json={
            "titulo": "Aviso da rodada",
            "mensagem": "O veículo está a caminho.",
            "viagem_id": str(viagem_ociosa.id),
        },
    )
    assert r.status_code == 201, r.get_data(as_text=True)

    caixa = aluno.client.get("/v1/notificacoes/").get_json() or []
    assert any(n["titulo"] == "Aviso da rodada" for n in caixa)
