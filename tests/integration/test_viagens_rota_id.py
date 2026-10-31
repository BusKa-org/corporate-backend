"""Código existente com viagens sob demanda (rota_id, sem horario_rota)."""

from datetime import date, datetime, timedelta

from app.models.enum import StatusSolicitacao, StatusViagem
from app.models.notificacao import Notificacao
from app.models.rota import RotaAluno
from app.models.viagem import SolicitacaoViagem
from app.services import viagens_service
from app.tasks.notificacao_tasks import verificar_viagens_10min, verificar_viagens_24h
from tests.factories.viagem_factory import ViagemFactory


def _viagem_sob_demanda(_db, rota, motorista, status, data=None):
    v = ViagemFactory(
        rota_id=rota.id,
        horario_rota_id=None,
        data=data or date.today(),
        status=status,
        motorista_id=motorista.user.id,
        veiculo_id=rota.veiculo_padrao_id,
    )
    _db.session.add(v)
    _db.session.commit()
    return v


def test_gerar_viagem_fixa_grava_rota_id(gestor, rota, dia_operacao):
    viagem = viagens_service.gerar_viagem(
        str(gestor.user.id), {"rota_id": rota.id, "data": date(2026, 11, 2)}
    )
    assert viagem.rota_id == rota.id
    assert viagem.horario_rota_id == dia_operacao.horario_rota_id


def test_gerar_viagem_sob_demanda_e_rejeitada(gestor, rota_sob_demanda):
    r = gestor.client.post(
        "/v1/viagens/", json={"rota_id": str(rota_sob_demanda.id), "data": "2026-11-02"}
    )
    assert r.status_code == 400, r.get_data(as_text=True)
    assert "solicitações dos alunos" in r.get_json()["error"]["message"]


def test_listagem_do_gestor_inclui_viagem_sob_demanda(gestor, viagem_solicitada, _db):
    viagem_solicitada.buffer_fim = datetime(2026, 11, 2, 13, 5)
    _db.session.commit()

    r = gestor.client.get("/v1/viagens/")
    assert r.status_code == 200, r.get_data(as_text=True)
    items = r.get_json()["items"]
    assert len(items) == 1
    item = items[0]
    assert item["rota_id"] == str(viagem_solicitada.rota_id)
    assert item["rota_nome"] == viagem_solicitada.rota.nome
    assert item["status"] == "SOLICITADA"
    assert item["horario_inicio"] is None
    assert item["tipo"] is None
    assert item["buffer_fim"] is not None

    r = gestor.client.get(f"/v1/viagens/?rota_id={viagem_solicitada.rota_id}&status=SOLICITADA")
    assert len(r.get_json()["items"]) == 1


def test_agenda_do_aluno_com_viagem_sob_demanda(
    aluno, rota_sob_demanda, motorista, _db, horario_rota
):
    _db.session.add(RotaAluno(rota_id=rota_sob_demanda.id, aluno_id=aluno.user.id))
    _db.session.add(RotaAluno(rota_id=horario_rota.rota_id, aluno_id=aluno.user.id))
    fixa = ViagemFactory(
        rota_id=horario_rota.rota_id,
        horario_rota_id=horario_rota.id,
        data=date.today(),
        status=StatusViagem.AGENDADA,
    )
    _db.session.add(fixa)
    _db.session.commit()
    sob_demanda = _viagem_sob_demanda(_db, rota_sob_demanda, motorista, StatusViagem.EM_ANDAMENTO)

    r = aluno.client.get("/v1/viagens/aluno/agenda")
    assert r.status_code == 200, r.get_data(as_text=True)
    items = r.get_json()["items"]
    assert [i["viagem_id"] for i in items] == [str(fixa.id), str(sob_demanda.id)]
    assert items[1]["horario_saida"] is None
    assert items[1]["rota_id"] == str(rota_sob_demanda.id)


def test_dashboard_funciona_com_viagem_sob_demanda(gestor, rota_sob_demanda, motorista, _db):
    v = _viagem_sob_demanda(_db, rota_sob_demanda, motorista, StatusViagem.FINALIZADA)
    v.km_real = 12.5
    _db.session.commit()
    hoje = date.today().isoformat()

    r = gestor.client.get(f"/v1/dashboard/relatorios/periodo?data_inicio={hoje}&data_fim={hoje}")
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["viagens_realizadas"] == 1
    assert r.get_json()["km_total_rodado"] == 12.5

    assert gestor.client.get(f"/v1/dashboard/viagens/{v.id}/progresso").status_code == 200
    assert gestor.client.get(f"/v1/dashboard/viagens/{v.id}/trajeto-real").status_code == 200


def test_lembretes_ignoram_viagem_sob_demanda(app, _db, aluno, rota_sob_demanda, motorista):
    _db.session.add(RotaAluno(rota_id=rota_sob_demanda.id, aluno_id=aluno.user.id))
    _db.session.commit()
    # Never AGENDADA in practice; forced here to prove the jobs skip them anyway.
    amanha = _viagem_sob_demanda(
        _db, rota_sob_demanda, motorista, StatusViagem.AGENDADA, date.today() + timedelta(days=1)
    )
    hoje = _viagem_sob_demanda(_db, rota_sob_demanda, motorista, StatusViagem.AGENDADA)

    verificar_viagens_24h(app)
    verificar_viagens_10min(app)

    _db.session.refresh(amanha)
    _db.session.refresh(hoje)
    assert amanha.aviso_24h_enviado is False
    assert hoje.aviso_10min_enviado is False
    assert Notificacao.query.count() == 0


def test_confirmar_presenca_em_viagem_sob_demanda_e_rejeitada(aluno, viagem_solicitada):
    r = aluno.client.put(
        f"/v1/viagens/{viagem_solicitada.id}/confirmacao", json={"confirmacao": False}
    )
    assert r.status_code == 400, r.get_data(as_text=True)
    assert "solicitacoes" in r.get_json()["error"]["message"]


def test_cancelar_viagem_sob_demanda_notifica_e_cancela_solicitacao(
    gestor, aluno, viagem_solicitada, _db
):
    r = gestor.client.put(f"/v1/viagens/{viagem_solicitada.id}/cancelar")
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["alunos_notificados"] == 1

    solicitacao = SolicitacaoViagem.query.filter_by(viagem_id=viagem_solicitada.id).one()
    assert solicitacao.status == StatusSolicitacao.CANCELADA
    assert solicitacao.cancelada_em is not None
    assert Notificacao.query.filter_by(usuario_id=aluno.user.id).count() == 1


def test_finalizar_viagem_sob_demanda_grava_fim_real(motorista, rota_sob_demanda, _db):
    v = _viagem_sob_demanda(_db, rota_sob_demanda, motorista, StatusViagem.EM_ANDAMENTO)

    r = motorista.client.put(f"/v1/viagens/{v.id}/acao", json={"acao": "FINALIZAR"})
    assert r.status_code == 200, r.get_data(as_text=True)
    _db.session.refresh(v)
    assert v.status == StatusViagem.FINALIZADA
    assert v.fim_real is not None


def test_post_viagem_fixa_responde_201_com_a_viagem(gestor, rota, dia_operacao):
    r = gestor.client.post("/v1/viagens/", json={"rota_id": str(rota.id), "data": "2026-11-02"})
    assert r.status_code == 201, r.get_data(as_text=True)
    body = r.get_json()
    assert body["rota_id"] == str(rota.id)
    assert body["status"] == "AGENDADA"


def test_gestor_de_outra_organizacao_nao_cancela_viagem(other_gestor, viagem_solicitada, _db):
    r = other_gestor.client.put(f"/v1/viagens/{viagem_solicitada.id}/cancelar")
    assert r.status_code == 403, r.get_data(as_text=True)
    _db.session.refresh(viagem_solicitada)
    assert viagem_solicitada.status == StatusViagem.SOLICITADA
