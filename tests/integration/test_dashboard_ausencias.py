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
            # No fim_real on this trip: falls back to its last update.
            "registrado_em": finalizada.updated_at.isoformat(),
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


def _desistencia(_db, viagem, aluno, cancelada_em=None):
    _db.session.add(
        SolicitacaoViagemFactory(
            viagem_id=viagem.id,
            aluno_id=aluno.id,
            status=StatusSolicitacao.DESISTENCIA,
            cancelada_em=cancelada_em or datetime(2026, 3, 10, 7, 30, tzinfo=UTC),
        )
    )


def test_ausencia_usa_o_fim_real_da_viagem(_db, gestor, rota, alunos):
    fim_real = datetime(2026, 3, 10, 9, 0, tzinfo=UTC)
    viagem = _viagem(_db, rota)
    viagem.fim_real = fim_real
    _confirmado(_db, viagem, alunos[0], embarcou=False)
    _db.session.commit()

    body = gestor.client.get(URL).get_json()

    assert body["items"][0]["registrado_em"] == fim_real.isoformat()


def test_viagem_de_rota_fixa_aparece_como_ausencia(_db, gestor, horario_rota, alunos):
    # Fixed trips only carry horario_rota_id; the route comes through the schedule.
    viagem = ViagemFactory(
        horario_rota_id=horario_rota.id, status=StatusViagem.FINALIZADA, data=DIA
    )
    _db.session.add(viagem)
    _db.session.flush()
    _confirmado(_db, viagem, alunos[0], embarcou=False)
    _db.session.commit()

    body = gestor.client.get(URL).get_json()

    assert body["total"] == 1
    assert body["items"][0]["tipo"] == "AUSENCIA"
    assert body["items"][0]["viagem_id"] == str(viagem.id)


def test_desistencia_ignora_viagem_cancelada(_db, gestor, rota, alunos):
    _desistencia(_db, _viagem(_db, rota, status=StatusViagem.CANCELADA), alunos[0])
    _db.session.commit()

    body = gestor.client.get(URL).get_json()

    assert body["total"] == 0
    assert body["items"] == []


def test_desistencia_ignora_quem_embarcou(_db, gestor, rota, alunos):
    ana, bruno = alunos[0], alunos[1]
    viagem = _viagem(_db, rota, status=StatusViagem.EM_ANDAMENTO)
    _confirmado(_db, viagem, ana, embarcou=True)
    _desistencia(_db, viagem, ana)
    _desistencia(_db, viagem, bruno)
    _db.session.commit()

    body = gestor.client.get(URL).get_json()

    assert [i["aluno_nome"] for i in body["items"]] == ["Bruno"]


def test_paginas_nao_repetem_nem_perdem_empates(_db, gestor, rota, organizacao):
    # Same date and same name everywhere: only the tie-breakers order these rows.
    viagens = [_viagem(_db, rota), _viagem(_db, rota)]
    for _ in range(3):
        xara = AlunoFactory(organizacao_id=organizacao.id, nome="Igual")
        _db.session.add(xara)
        _db.session.flush()
        for viagem in viagens:
            _confirmado(_db, viagem, xara, embarcou=False)
    _db.session.commit()

    tudo = gestor.client.get(URL + "&per_page=100").get_json()["items"]
    paginado = []
    for page in range(1, 7):
        body = gestor.client.get(URL + f"&page={page}&per_page=1").get_json()
        assert body["total"] == 6
        paginado.extend(body["items"])

    assert paginado == tudo
    chaves = set()
    for item in paginado:
        chaves.add((item["viagem_id"], item["aluno_id"]))
    assert len(chaves) == 6


def test_pagina_alem_do_fim_mantem_o_total(_db, gestor, rota, alunos):
    _confirmado(_db, _viagem(_db, rota), alunos[0], embarcou=False)
    _db.session.commit()

    body = gestor.client.get(URL + "&page=5").get_json()

    assert body["items"] == []
    assert body["total"] == 1


@pytest.mark.parametrize(
    "query",
    [
        "inicio=2026-03-11&fim=2026-03-10",
        "fim=2026-03-10",
        "inicio=2026-03-10",
        "",
        "inicio=2026-03-10&fim=2026-03-10&per_page=101",
        "inicio=2026-03-10&fim=2026-03-10&per_page=0",
        "inicio=2026-03-10&fim=2026-03-10&page=0",
    ],
)
def test_valida_os_filtros(gestor, query):
    resp = gestor.client.get(f"/v1/dashboard/ausencias?{query}")

    assert resp.status_code == 400, resp.get_json()


def test_ausencias_so_para_gestor(aluno):
    resp = aluno.client.get(URL)

    assert resp.status_code == 403
