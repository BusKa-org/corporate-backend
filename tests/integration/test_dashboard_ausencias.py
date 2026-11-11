from datetime import UTC, date, datetime

import pytest

from app.models.enum import StatusSolicitacao, StatusViagem
from tests.factories.rota_factory import RotaFactory
from tests.factories.user_factory import AlunoFactory
from tests.factories.viagem_factory import (
    AlunosConfirmadosFactory,
    SolicitacaoViagemFactory,
    ViagemFactory,
)

DIA = date(2026, 3, 10)
URL = "/v1/dashboard/ausencias?inicio=2026-03-10&fim=2026-03-10"


def _viagem(_db, rota, status=StatusViagem.FINALIZADA, data=DIA):
    v = ViagemFactory(rota_id=rota.id, status=status, data=data)
    _db.session.add(v)
    _db.session.flush()
    return v


def _confirmado(_db, viagem, aluno, embarcou):
    _db.session.add(
        AlunosConfirmadosFactory(
            viagem_id=viagem.id, aluno_id=aluno.id, confirmacao=True, embarcou=embarcou
        )
    )


@pytest.fixture()
def alunos(_db, organizacao):
    lista = []
    for nome in ("Ana", "Bruno", "Carla", "Davi"):
        a = AlunoFactory(organizacao_id=organizacao.id, nome=nome, foto_url=f"/foto/{nome}")
        lista.append(a)
    _db.session.add_all(lista)
    _db.session.flush()
    return lista


def test_lista_ausentes_e_desistentes_do_periodo(_db, gestor, rota, alunos, other_organizacao):
    ana, bruno, carla, davi = alunos
    finalizada = _viagem(_db, rota)
    _confirmado(_db, finalizada, ana, embarcou=False)
    _confirmado(_db, finalizada, bruno, embarcou=True)
    # A trip still running has no no-show yet.
    _confirmado(_db, _viagem(_db, rota, status=StatusViagem.EM_ANDAMENTO), davi, embarcou=False)
    # Outside the period.
    _confirmado(_db, _viagem(_db, rota, data=date(2026, 3, 11)), davi, embarcou=False)

    em_rota = _viagem(_db, rota, status=StatusViagem.EM_ANDAMENTO)
    cancelada_em = datetime(2026, 3, 10, 7, 30, tzinfo=UTC)
    _db.session.add(
        SolicitacaoViagemFactory(
            viagem_id=em_rota.id,
            aluno_id=carla.id,
            status=StatusSolicitacao.DESISTENCIA,
            cancelada_em=cancelada_em,
        )
    )
    # Cancelled before the trip left: the seat was given back, not a dropout.
    _db.session.add(
        SolicitacaoViagemFactory(
            viagem_id=em_rota.id, aluno_id=davi.id, status=StatusSolicitacao.CANCELADA
        )
    )

    outra_rota = RotaFactory(
        organizacao_id=other_organizacao.id, motorista_padrao_id=None, veiculo_padrao_id=None
    )
    _db.session.add(outra_rota)
    _db.session.flush()
    _confirmado(_db, _viagem(_db, outra_rota), ana, embarcou=False)
    _db.session.commit()

    resp = gestor.client.get(URL)

    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["total"] == 2
    assert body["items"] == [
        {
            "tipo": "AUSENCIA",
            "aluno_id": str(ana.id),
            "aluno_nome": "Ana",
            "foto_url": "/foto/Ana",
            "viagem_id": str(finalizada.id),
            "rota_nome": rota.nome,
            "data": "2026-03-10",
            "registrado_em": None,
        },
        {
            "tipo": "DESISTENCIA",
            "aluno_id": str(carla.id),
            "aluno_nome": "Carla",
            "foto_url": "/foto/Carla",
            "viagem_id": str(em_rota.id),
            "rota_nome": rota.nome,
            "data": "2026-03-10",
            "registrado_em": cancelada_em.isoformat(),
        },
    ]


def test_pagina_as_ausencias(_db, gestor, rota, alunos):
    viagem = _viagem(_db, rota)
    for aluno in alunos:
        _confirmado(_db, viagem, aluno, embarcou=False)
    _db.session.commit()

    resp = gestor.client.get(URL + "&page=2&per_page=3")

    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["total"] == 4
    assert body["page"] == 2
    assert body["per_page"] == 3
    assert [i["aluno_nome"] for i in body["items"]] == ["Davi"]


def test_ausencias_so_para_gestor(aluno):
    resp = aluno.client.get(URL)

    assert resp.status_code == 403
