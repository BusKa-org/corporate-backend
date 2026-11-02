"""RF-21: aggregated indicators of the manager dashboard.

The scenario below uses fixed values so each indicator has a hand-computed
result, not just a 200.
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from marshmallow import ValidationError as MarshmallowValidationError

from app.core.exceptions import ForbiddenError
from app.models.enum import StatusSolicitacao, StatusViagem
from app.models.onibus import Onibus
from app.models.viagem import AlunosConfirmados, SolicitacaoViagem, Viagem, ViagemPonto
from app.services.dashboard_service import exportar_indicadores_csv, indicadores_periodo
from tests.factories.geo_factory import PontoFactory
from tests.factories.organizacao_factory import OrganizacaoFactory
from tests.factories.rota_factory import HorarioRotaFactory, RotaFactory, RotaPontoFactory
from tests.factories.user_factory import AlunoFactory

INICIO = date(2026, 3, 10)
MEIO = date(2026, 3, 11)
FIM = date(2026, 3, 12)
CAPACIDADE = 20


def _onibus(_db, organizacao_id, placa):
    o = Onibus(organizacao_id=organizacao_id, placa=placa, modelo="X", capacidade=CAPACIDADE)
    _db.session.add(o)
    return o


def _viagem(_db, **kwargs):
    v = Viagem(**kwargs)
    _db.session.add(v)
    return v


def _negada(_db, viagem, aluno, ponto_embarque):
    linha = SolicitacaoViagem(
        viagem_id=viagem.id,
        aluno_id=aluno.id,
        status=StatusSolicitacao.NEGADA,
        ponto_embarque_id=ponto_embarque.id,
    )
    _db.session.add(linha)
    return linha


def _embarcado(_db, viagem, aluno, ponto_embarque):
    linha = AlunosConfirmados(
        viagem_id=viagem.id,
        aluno_id=aluno.id,
        confirmacao=True,
        ponto_embarque_id=ponto_embarque.id,
        embarcou=True,
        embarcado_em=datetime(2026, 3, 10, 7, 5, tzinfo=UTC),
    )
    _db.session.add(linha)
    return linha


@pytest.fixture()
def cenario(_db, organizacao, gestor, motorista):
    """Three trips in the period (two at the bounds), two outside, one from another
    organization, plus an inherited scheduled trip to prove both route paths make
    it into the report.
    """
    pontos = [PontoFactory(organizacao_id=organizacao.id, apelido=f"P{i}") for i in range(1, 5)]
    _db.session.add_all(pontos)
    onibus = _onibus(_db, organizacao.id, "AAA0A01")
    _db.session.flush()

    rota = RotaFactory(
        organizacao_id=organizacao.id,
        motorista_padrao_id=motorista.user.id,
        veiculo_padrao_id=onibus.id,
    )
    _db.session.add(rota)
    _db.session.flush()
    for ordem, p in enumerate(pontos, start=1):
        _db.session.add(RotaPontoFactory(rota_id=rota.id, ponto_id=p.id, ordem=ordem))

    horario = HorarioRotaFactory(rota_id=rota.id)
    _db.session.add(horario)
    _db.session.flush()

    alunos = [AlunoFactory(organizacao_id=organizacao.id) for _ in range(6)]
    _db.session.add_all(alunos)
    _db.session.flush()

    comum = {"rota_id": rota.id, "veiculo_id": onibus.id, "motorista_id": motorista.user.id}

    # Lower bound: 3 boardings, 10 km, 3 denials.
    v1 = _viagem(_db, data=INICIO, status=StatusViagem.FINALIZADA, km_real=10, **comum)
    # Upper bound: 2 boardings, no km recorded, 1 denial.
    v2 = _viagem(_db, data=FIM, status=StatusViagem.FINALIZADA, km_real=None, **comum)
    # Cancelled round: counts in "trips by status" and in denials, but not in
    # occupancy or IPK.
    v3 = _viagem(_db, data=MEIO, status=StatusViagem.CANCELADA, km_real=None, **comum)
    # Inherited scheduled trip: comes via horario_rota_id, without rota_id.
    v6 = _viagem(
        _db,
        data=MEIO,
        status=StatusViagem.FINALIZADA,
        km_real=5,
        horario_rota_id=horario.id,
        veiculo_id=onibus.id,
        motorista_id=motorista.user.id,
    )
    # Outside the period, on both sides.
    v4 = _viagem(
        _db, data=INICIO - timedelta(days=1), status=StatusViagem.FINALIZADA, km_real=100, **comum
    )
    v5 = _viagem(
        _db, data=FIM + timedelta(days=1), status=StatusViagem.FINALIZADA, km_real=100, **comum
    )
    _db.session.flush()

    for aluno in alunos[:3]:
        _embarcado(_db, v1, aluno, pontos[0])
    _negada(_db, v1, alunos[3], pontos[0])
    _negada(_db, v1, alunos[4], pontos[0])
    _negada(_db, v1, alunos[5], pontos[1])

    for aluno in alunos[:2]:
        _embarcado(_db, v2, aluno, pontos[0])
    _negada(_db, v2, alunos[3], pontos[0])

    _negada(_db, v3, alunos[0], pontos[0])
    _embarcado(_db, v6, alunos[0], pontos[0])

    for fora in (v4, v5):
        _embarcado(_db, fora, alunos[0], pontos[0])
        _negada(_db, fora, alunos[1], pontos[1])

    # Legs: v1 does P1->P2 in 10 min and P2->P3 in 15 min; v2 does P1->P2 in
    # 20 min and records no arrival at P3. Average P1->P2 = 15 min.
    base = datetime(2026, 3, 10, 7, 0, tzinfo=UTC)
    marcos = {
        v1.id: [base, base + timedelta(minutes=10), base + timedelta(minutes=25), None],
        v2.id: [base, base + timedelta(minutes=20), None, None],
    }
    for viagem_id, chegadas in marcos.items():
        for ordem, (p, chegada) in enumerate(zip(pontos, chegadas, strict=True), start=1):
            _db.session.add(
                ViagemPonto(viagem_id=viagem_id, ponto_id=p.id, ordem=ordem, chegada_real=chegada)
            )

    # Another organization: none of this may show up in the manager's report above.
    outra = OrganizacaoFactory()
    _db.session.add(outra)
    _db.session.flush()
    ponto_outro = PontoFactory(organizacao_id=outra.id, apelido="P_OUTRA")
    onibus_outro = _onibus(_db, outra.id, "BBB0B02")
    _db.session.add(ponto_outro)
    _db.session.flush()
    rota_outra = RotaFactory(
        organizacao_id=outra.id, motorista_padrao_id=None, veiculo_padrao_id=onibus_outro.id
    )
    _db.session.add(rota_outra)
    _db.session.flush()
    v7 = _viagem(
        _db,
        data=MEIO,
        status=StatusViagem.FINALIZADA,
        km_real=50,
        rota_id=rota_outra.id,
        veiculo_id=onibus_outro.id,
    )
    alunos_outros = [AlunoFactory(organizacao_id=outra.id) for _ in range(2)]
    _db.session.add_all(alunos_outros)
    _db.session.flush()
    _negada(_db, v7, alunos_outros[0], ponto_outro)
    _embarcado(_db, v7, alunos_outros[1], ponto_outro)

    _db.session.commit()
    return {"pontos": pontos, "alunos": alunos, "outra_organizacao": outra}


def test_indicadores_do_periodo_batem_com_o_calculo_manual(app, cenario, gestor):
    with app.app_context():
        dados = indicadores_periodo(str(gestor.user.id), INICIO, FIM)

    assert dados["sem_dados"] is False
    assert dados["periodo"] == {"inicio": "2026-03-10", "fim": "2026-03-12"}

    # 1. Trips by period: v1, v2, v3 and the scheduled v6. v4/v5 are outside the
    # bounds (one day before and one day after) and v7 is from another organization.
    assert dados["total_viagens"] == 4
    assert {i["status"]: i["total"] for i in dados["viagens_por_status"]} == {
        "FINALIZADA": 3,
        "CANCELADA": 1,
    }

    # 2. Denials per stop: P1 gets 2 (v1) + 1 (v2) + 1 (v3), P2 gets 1.
    assert dados["negacoes_por_ponto"] == [
        {"ponto_id": str(cenario["pontos"][0].id), "apelido": "P1", "negacoes": 4},
        {"ponto_id": str(cenario["pontos"][1].id), "apelido": "P2", "negacoes": 1},
    ]

    # 3. Average time per leg: (10 + 20) / 2 and 15 min.
    trechos = dados["tempo_medio_por_trecho"]
    assert [
        (t["ponto_origem"], t["ponto_destino"], t["minutos_medio"], t["amostras"]) for t in trechos
    ] == [
        ("P1", "P2", 15.0, 2),
        ("P2", "P3", 15.0, 1),
    ]

    # 4. Occupancy: operated trips v1 (3), v2 (2) and v6 (1) over capacity 20.
    assert dados["ocupacao"] == {
        "viagens_consideradas": 3,
        "passageiros_media": 2.0,
        "capacidade_media": 20.0,
        "taxa_ocupacao": round((3 / 20 + 2 / 20 + 1 / 20) / 3, 4),
    }

    # 5. IPK: only v1 (10 km, 3 pax) and v6 (5 km, 1 pax); v2 has no km_real.
    assert dados["ipk"] == {
        "passageiros": 4,
        "km": 15.0,
        "ipk": round(4 / 15, 4),
        "viagens_consideradas": 2,
        "viagens_sem_km": 1,
    }


def test_limites_do_periodo_sao_inclusivos_nas_duas_pontas(app, cenario, gestor):
    """Shrinking the range by one day on each side must drop exactly the trips at the bounds."""
    with app.app_context():
        so_inicio = indicadores_periodo(str(gestor.user.id), INICIO, INICIO)
        so_fim = indicadores_periodo(str(gestor.user.id), FIM, FIM)
        miolo = indicadores_periodo(str(gestor.user.id), MEIO, MEIO)

    assert so_inicio["total_viagens"] == 1
    assert so_inicio["ipk"]["km"] == 10.0
    assert so_fim["total_viagens"] == 1
    assert so_fim["ipk"]["viagens_sem_km"] == 1
    assert miolo["total_viagens"] == 2


def test_km_real_nulo_nao_explode_e_nao_vira_zero(app, cenario, gestor):
    """On a day when no operated trip has km, IPK is null, not zero."""
    with app.app_context():
        dados = indicadores_periodo(str(gestor.user.id), FIM, FIM)

    assert dados["ipk"]["ipk"] is None
    assert dados["ipk"]["km"] == 0.0
    assert dados["ipk"]["viagens_sem_km"] == 1


def test_periodo_sem_dados_responde_com_mensagem_e_sugestao(app, cenario, gestor):
    vazio_inicio = date(2020, 1, 1)
    with app.app_context():
        dados = indicadores_periodo(str(gestor.user.id), vazio_inicio, date(2020, 1, 31))

    assert dados["sem_dados"] is True
    assert "Nenhuma viagem registrada" in dados["mensagem"]
    assert dados["periodo_sugerido"] == {"inicio": "2026-03-09", "fim": "2026-03-13"}
    assert dados["total_viagens"] == 0
    assert dados["negacoes_por_ponto"] == []
    assert dados["ocupacao"]["taxa_ocupacao"] is None
    assert dados["ipk"]["ipk"] is None


def test_organizacao_sem_viagem_alguma_recebe_mensagem_sem_sugestao(app, _db, other_gestor):
    with app.app_context():
        dados = indicadores_periodo(str(other_gestor.user.id), INICIO, FIM)

    assert dados["sem_dados"] is True
    assert dados["periodo_sugerido"] is None
    assert "Ainda não há viagens" in dados["mensagem"]


def test_gestor_nao_ve_dados_de_outra_organizacao(app, cenario, gestor, other_gestor):
    with app.app_context():
        meus = indicadores_periodo(str(gestor.user.id), INICIO, FIM)
        alheios = indicadores_periodo(str(other_gestor.user.id), INICIO, FIM)

    assert alheios["total_viagens"] == 0
    assert alheios["negacoes_por_ponto"] == []
    # The third organization's trip (50 km, 1 boarding) did not leak in here.
    assert meus["ipk"]["km"] == 15.0
    assert all(i["apelido"] != "P_OUTRA" for i in meus["negacoes_por_ponto"])


def test_apenas_gestores_acessam_os_indicadores(app, _db, motorista):
    with app.app_context(), pytest.raises(ForbiddenError):
        indicadores_periodo(str(motorista.user.id), INICIO, FIM)


def test_resposta_nao_contem_dado_pessoal(app, cenario, gestor):
    with app.app_context():
        dados = indicadores_periodo(str(gestor.user.id), INICIO, FIM)
        csv_texto = exportar_indicadores_csv(str(gestor.user.id), INICIO, FIM)

    proibidos = []
    for aluno in cenario["alunos"]:
        proibidos += [aluno.nome, aluno.email, aluno.cpf, str(aluno.id)]

    for texto in (repr(dados), csv_texto):
        for termo in proibidos:
            assert termo not in texto


def test_exportacao_csv_traz_os_blocos_do_relatorio(app, cenario, gestor):
    import csv
    import io

    with app.app_context():
        texto = exportar_indicadores_csv(str(gestor.user.id), INICIO, FIM)

    linhas = list(csv.reader(io.StringIO(texto)))
    assert ["periodo_inicio", "2026-03-10"] in linhas
    assert ["periodo_fim", "2026-03-12"] in linhas
    assert ["total_viagens", "4"] in linhas
    assert ["negacoes_por_ponto"] in linhas
    assert [str(cenario["pontos"][0].id), "P1", "4"] in linhas
    assert ["FINALIZADA", "3"] in linhas
    assert ["ipk", str(round(4 / 15, 4))] in linhas
    assert ["viagens_sem_km", "1"] in linhas


def test_endpoints_http_do_painel(app, cenario, gestor):
    resposta = gestor.client.get("/v1/dashboard/indicadores?inicio=2026-03-10&fim=2026-03-12")
    assert resposta.status_code == 200
    corpo = resposta.get_json()
    assert corpo["total_viagens"] == 4
    assert corpo["ipk"]["ipk"] == round(4 / 15, 4)

    export = gestor.client.get(
        "/v1/dashboard/indicadores/exportar?inicio=2026-03-10&fim=2026-03-12"
    )
    assert export.status_code == 200
    assert export.mimetype == "text/csv"
    assert "attachment" in export.headers["Content-Disposition"]
    assert "negacoes_por_ponto" in export.get_data(as_text=True)


def test_periodo_invertido_e_recusado(app, gestor):
    resposta = gestor.client.get("/v1/dashboard/indicadores?inicio=2026-03-12&fim=2026-03-10")
    assert resposta.status_code == 400

    from app.schemas.dashboard_schema import PeriodoRelatorioQuerySchema

    with pytest.raises(MarshmallowValidationError):
        PeriodoRelatorioQuerySchema().load({"inicio": "2026-03-12", "fim": "2026-03-10"})
