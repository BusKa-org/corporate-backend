import csv
import io
import logging
from datetime import date
from decimal import Decimal
from typing import Any

from flask import current_app
from sqlalchemy import Float, Select, Time, and_, case, cast, func, literal, select, union_all
from sqlalchemy.orm import aliased

from app.core.exceptions import NotFoundError
from app.models.base import db
from app.models.enum import StatusSolicitacao, StatusViagem
from app.models.geo import Ponto
from app.models.onibus import Onibus
from app.models.rota import HorarioRota, Rota
from app.models.user import Aluno
from app.models.viagem import (
    AlunosConfirmados,
    SolicitacaoViagem,
    TelemetriaViagem,
    Viagem,
    ViagemPonto,
)
from app.services.user_service import _get_gestor_or_403
from app.services.viagens_service import juntar_rota

logger = logging.getLogger(__name__)


def obter_progresso_viagem(gestor_id: str, viagem_id: str) -> list[dict]:
    """Return the stops the driver has already passed, in chronological order."""

    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem auditar o trajeto de viagens")

    viagem = (
        juntar_rota(db.session.query(Viagem))
        .filter(Viagem.id == viagem_id, Rota.organizacao_id == gestor.organizacao_id)
        .first()
    )

    if not viagem:
        raise NotFoundError("Viagem não encontrada ou não pertence à sua organização")

    pontos_visitados = (
        ViagemPonto.query.filter(
            ViagemPonto.viagem_id == viagem_id, ViagemPonto.chegada_real.isnot(None)
        )
        .order_by(ViagemPonto.chegada_real.asc())
        .all()
    )

    return [
        {
            "ponto_id": str(vp.ponto_id),
            "apelido": vp.ponto.apelido,
            "horario_passagem": vp.chegada_real.isoformat() if vp.chegada_real else None,
        }
        for vp in pontos_visitados
    ]


def relatorio_periodo_gestor(gestor_id: str, data_inicio: str, data_fim: str) -> dict:
    """Build aggregated business intelligence for the Manager's web dashboard."""
    gestor = _get_gestor_or_403(
        gestor_id, "Apenas gestores podem visualizar relatórios operacionais"
    )

    try:
        stats_viagem = (
            juntar_rota(
                db.session.query(
                    func.count(Viagem.id).label("total_viagens"),
                    func.sum(Viagem.km_real).label("km_total_rodado"),
                ).select_from(Viagem)
            )
            .filter(
                Rota.organizacao_id == gestor.organizacao_id,
                Viagem.data >= data_inicio,
                Viagem.data <= data_fim,
                Viagem.status == StatusViagem.FINALIZADA,
            )
            .first()
        )

        stats_alunos = (
            db.session.query(
                func.sum(case((AlunosConfirmados.embarcou.is_(True), 1), else_=0)).label(
                    "total_embarques"
                ),
                func.sum(
                    case(
                        (
                            (AlunosConfirmados.confirmacao.is_(True))
                            & (AlunosConfirmados.embarcou.is_(False)),
                            1,
                        ),
                        else_=0,
                    )
                ).label("total_desperdicio"),
            )
            .select_from(Viagem)
            .outerjoin(HorarioRota, Viagem.horario_rota_id == HorarioRota.id)
            .join(Rota, Rota.id == func.coalesce(Viagem.rota_id, HorarioRota.rota_id))
            .join(AlunosConfirmados, Viagem.id == AlunosConfirmados.viagem_id)
            .filter(
                Rota.organizacao_id == gestor.organizacao_id,
                Viagem.data >= data_inicio,
                Viagem.data <= data_fim,
                Viagem.status == StatusViagem.FINALIZADA,
            )
            .first()
        )
        total_viagens = int(stats_viagem.total_viagens or 0) if stats_viagem else 0
        km = float(stats_viagem.km_total_rodado or 0) if stats_viagem else 0.0

        embarques = int(stats_alunos.total_embarques or 0) if stats_alunos else 0
        desperdicio = int(stats_alunos.total_desperdicio or 0) if stats_alunos else 0

        return {
            "periodo": f"{data_inicio} até {data_fim}",
            "viagens_realizadas": total_viagens,
            "alunos_transportados": embarques,
            "vagas_desperdicadas": desperdicio,
            "km_total_rodado": km,
            "media_alunos_por_km": round(embarques / km, 2) if km > 0 else 0.0,
        }

    except Exception as e:
        logger.error(f"Erro ao gerar relatorio do gestor {gestor_id}: {e}")
        from app.core.exceptions import AppError

        raise AppError("Erro ao processar relatório do período", 500)


def obter_telemetria_viagem(gestor_id: str, viagem_id: str) -> list[dict]:
    """Return a trip's GPS trail (telemetry) in chronological order."""

    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem auditar a telemetria de viagens")

    viagem = (
        juntar_rota(db.session.query(Viagem))
        .filter(Viagem.id == viagem_id, Rota.organizacao_id == gestor.organizacao_id)
        .first()
    )

    if not viagem:
        raise NotFoundError("Viagem não encontrada ou não pertence à sua organização")

    rastros = (
        TelemetriaViagem.query.filter_by(viagem_id=viagem_id)
        .order_by(TelemetriaViagem.timestamp.asc())
        .all()
    )

    return [
        {
            "latitude": float(r.latitude),
            "longitude": float(r.longitude),
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
        }
        for r in rastros
    ]


# RF-21: aggregated, anonymized indicators for the period.
#
# Decisions that apply to all indicators below:
#
# * Route scope. A trip reaches the circuit two ways: the on-demand round points
#   straight to `rota_id`, the inherited scheduled trip via `horario_rota_id`.
#   The dashboard covers both: the current operation is DRT, but the same base
#   still holds scheduled trips, and a report ignoring them would under-report.
# * Period. `Viagem.data` is a `DATE`; both bounds are inclusive, compared as
#   calendar dates, with no time zone involved.
# * Anonymization (RF-20). Nothing here touches `Aluno`/`User`: `alunos_confirmados`
#   rows of deleted accounts still count, and no query joins back to identity.
#   The only named entities in the responses are boarding stops.

# Only trips that actually ran count for occupancy and IPK. A CANCELADA trip is
# not operation: counting it would sink average occupancy and suggest an oversized fleet.
_STATUS_OPERADAS = (StatusViagem.EM_ANDAMENTO, StatusViagem.FINALIZADA)


def _viagens_periodo(organizacao_id: Any, inicio: date, fim: date, operadas: bool = False) -> Any:
    """Subquery with the organization's trips in the period (inclusive bounds)."""
    q: Select = (
        select(
            Viagem.id.label("id"),
            Viagem.status.label("status"),
            Viagem.km_real.label("km_real"),
            Viagem.veiculo_id.label("veiculo_id"),
        )
        .select_from(Viagem)
        .outerjoin(HorarioRota, Viagem.horario_rota_id == HorarioRota.id)
        .join(Rota, Rota.id == func.coalesce(Viagem.rota_id, HorarioRota.rota_id))
        .where(
            Rota.organizacao_id == organizacao_id,
            Viagem.data >= inicio,
            Viagem.data <= fim,
        )
    )
    if operadas:
        q = q.where(Viagem.status.in_(_STATUS_OPERADAS))
    return q.subquery()


def _embarques_por_viagem() -> Any:
    """Subquery: how many students actually boarded each trip."""
    return (
        select(
            AlunosConfirmados.viagem_id.label("viagem_id"),
            func.count().label("passageiros"),
        )
        .where(AlunosConfirmados.embarcou.is_(True))
        .group_by(AlunosConfirmados.viagem_id)
        .subquery()
    )


def _num(valor: Any) -> float | None:
    """Convert Postgres Numeric/Decimal to float, keeping nulls."""
    if valor is None:
        return None
    return float(valor) if isinstance(valor, (Decimal, int, float)) else None


def _viagens_por_status(viagens: Any) -> list[dict]:
    linhas = db.session.execute(
        select(viagens.c.status, func.count().label("total"))
        .group_by(viagens.c.status)
        .order_by(viagens.c.status)
    ).all()
    return [{"status": s.value, "total": total} for s, total in linhas]


def _negacoes_por_ponto(viagens: Any) -> list[dict]:
    """Bottlenecks: where demand exceeded capacity (RF-14).

    Denials without a declared boarding stop are left out: they cannot be assigned
    to a stop, and by construction they should not exist, since denial only happens
    after origin/destination is declared (RF-13).
    """
    total = func.count().label("negacoes")
    linhas = db.session.execute(
        select(SolicitacaoViagem.ponto_embarque_id, Ponto.apelido, total)
        .select_from(SolicitacaoViagem)
        .join(viagens, viagens.c.id == SolicitacaoViagem.viagem_id)
        .join(Ponto, Ponto.id == SolicitacaoViagem.ponto_embarque_id)
        .where(SolicitacaoViagem.status == StatusSolicitacao.NEGADA)
        .group_by(SolicitacaoViagem.ponto_embarque_id, Ponto.apelido)
        .order_by(total.desc(), Ponto.apelido)
    ).all()
    return [
        {"ponto_id": str(ponto_id), "apelido": apelido, "negacoes": negacoes}
        for ponto_id, apelido, negacoes in linhas
    ]


def _tempo_medio_por_trecho(viagens: Any) -> list[dict]:
    """Average time between consecutive circuit stops.

    Legs come from the (ordem, ordem+1) pair of `viagem_ponto`, which has the same
    ordering as `rota_ponto`. Only legs where both stops have an actual arrival count.
    """
    origem = aliased(ViagemPonto)
    destino = aliased(ViagemPonto)
    p_origem = aliased(Ponto)
    p_destino = aliased(Ponto)

    segundos = func.extract("epoch", destino.chegada_real - origem.chegada_real)
    linhas = db.session.execute(
        select(
            origem.ponto_id,
            p_origem.apelido,
            destino.ponto_id,
            p_destino.apelido,
            func.avg(segundos).label("segundos"),
            func.count().label("amostras"),
            func.min(origem.ordem).label("ordem"),
        )
        .select_from(origem)
        .join(viagens, viagens.c.id == origem.viagem_id)
        .join(
            destino,
            and_(destino.viagem_id == origem.viagem_id, destino.ordem == origem.ordem + 1),
        )
        .join(p_origem, p_origem.id == origem.ponto_id)
        .join(p_destino, p_destino.id == destino.ponto_id)
        .where(origem.chegada_real.isnot(None), destino.chegada_real.isnot(None))
        .group_by(origem.ponto_id, p_origem.apelido, destino.ponto_id, p_destino.apelido)
        .order_by(func.min(origem.ordem))
    ).all()

    return [
        {
            "ponto_origem_id": str(linha[0]),
            "ponto_origem": linha[1],
            "ponto_destino_id": str(linha[2]),
            "ponto_destino": linha[3],
            "minutos_medio": round(float(linha[4]) / 60, 2),
            "amostras": linha[5],
            "ordem": linha[6],
        }
        for linha in linhas
    ]


def _ocupacao_e_ipk(operadas: Any) -> tuple[dict, dict]:
    """Average occupancy against `Onibus.capacidade`, and IPK (passengers per km).

    `km_real` is nullable and still empty on most trips. Trips without mileage are
    excluded from IPK (numerator and denominator) and counted separately in
    `viagens_sem_km`. Treating null as zero would skew IPK and lead to the wrong
    fleet decision. With no trip having km, IPK is `null`, not `0`.
    """
    emb = _embarques_por_viagem()
    passageiros = func.coalesce(emb.c.passageiros, 0)
    capacidade = Onibus.capacidade
    com_km = and_(operadas.c.km_real.isnot(None), operadas.c.km_real > 0)
    # A trip with no vehicle assigned (or zero capacity) is left out of occupancy:
    # there is no denominator. The `case` still keeps it in IPK.
    com_capacidade = and_(capacidade.isnot(None), capacidade > 0)

    linha = db.session.execute(
        select(
            func.count().label("viagens"),
            func.sum(case((com_capacidade, 1), else_=0)).label("viagens_com_capacidade"),
            func.avg(case((com_capacidade, passageiros))).label("passageiros_medios"),
            func.avg(case((com_capacidade, capacidade))).label("capacidade_media"),
            func.avg(
                case((com_capacidade, cast(passageiros, Float) / cast(capacidade, Float)))
            ).label("taxa"),
            func.sum(case((com_km, passageiros), else_=0)).label("passageiros_km"),
            func.sum(case((com_km, operadas.c.km_real), else_=0)).label("km"),
            func.sum(case((com_km, 1), else_=0)).label("viagens_com_km"),
            func.sum(case((com_km, 0), else_=1)).label("viagens_sem_km"),
        )
        .select_from(operadas)
        .outerjoin(emb, emb.c.viagem_id == operadas.c.id)
        .outerjoin(Onibus, Onibus.id == operadas.c.veiculo_id)
    ).one()

    taxa = _num(linha.taxa)
    ocupacao = {
        "viagens_consideradas": int(linha.viagens_com_capacidade or 0),
        "passageiros_media": (
            round(_num(linha.passageiros_medios) or 0.0, 2)
            if linha.passageiros_medios is not None
            else None
        ),
        "capacidade_media": (
            round(_num(linha.capacidade_media) or 0.0, 2)
            if linha.capacidade_media is not None
            else None
        ),
        "taxa_ocupacao": round(taxa, 4) if taxa is not None else None,
    }

    km = _num(linha.km) or 0.0
    viagens_com_km = int(linha.viagens_com_km or 0)
    passageiros_km = int(linha.passageiros_km or 0)
    ipk = {
        "passageiros": passageiros_km,
        "km": round(km, 2),
        "ipk": round(passageiros_km / km, 4) if km > 0 else None,
        "viagens_consideradas": viagens_com_km,
        "viagens_sem_km": int(linha.viagens_sem_km or 0),
    }
    return ocupacao, ipk


def _periodo_sugerido(organizacao_id: Any) -> dict | None:
    """Range in which the organization actually has trips, to suggest to the manager."""
    linha = db.session.execute(
        select(func.min(Viagem.data), func.max(Viagem.data))
        .select_from(Viagem)
        .outerjoin(HorarioRota, Viagem.horario_rota_id == HorarioRota.id)
        .join(Rota, Rota.id == func.coalesce(Viagem.rota_id, HorarioRota.rota_id))
        .where(Rota.organizacao_id == organizacao_id)
    ).one()
    if not linha[0]:
        return None
    return {"inicio": linha[0].isoformat(), "fim": linha[1].isoformat()}


def indicadores_periodo(gestor_id: str, inicio: date, fim: date) -> dict:
    """RF-21: the manager's aggregated dashboard for the selected period.

    Everything is computed in the database; no trip or student row reaches Python.
    The response has no name, e-mail, CPF or user id.
    """
    gestor = _get_gestor_or_403(
        gestor_id, "Apenas gestores podem visualizar indicadores operacionais"
    )
    organizacao_id = gestor.organizacao_id

    viagens = _viagens_periodo(organizacao_id, inicio, fim)
    operadas = _viagens_periodo(organizacao_id, inicio, fim, operadas=True)

    por_status = _viagens_por_status(viagens)
    total_viagens = sum(item["total"] for item in por_status)

    if total_viagens == 0:
        sugestao = _periodo_sugerido(organizacao_id)
        mensagem = (
            "Nenhuma viagem registrada entre "
            f"{inicio.isoformat()} e {fim.isoformat()}. "
            + (
                f"Há dados entre {sugestao['inicio']} e {sugestao['fim']} — "
                "tente esse intervalo."
                if sugestao
                else "Ainda não há viagens registradas para esta organização."
            )
        )
    else:
        sugestao = None
        mensagem = None

    ocupacao, ipk = _ocupacao_e_ipk(operadas)

    return {
        "periodo": {"inicio": inicio.isoformat(), "fim": fim.isoformat()},
        "sem_dados": total_viagens == 0,
        "mensagem": mensagem,
        "periodo_sugerido": sugestao,
        "total_viagens": total_viagens,
        "viagens_por_status": por_status,
        "negacoes_por_ponto": _negacoes_por_ponto(viagens),
        "tempo_medio_por_trecho": _tempo_medio_por_trecho(viagens),
        "ocupacao": ocupacao,
        "ipk": ipk,
    }


def exportar_indicadores_csv(gestor_id: str, inicio: date, fim: date) -> str:
    """Export the period report as CSV (RF-21, step 4 of the main flow).

    CSV via the standard library: the report is tabular, the target is a
    spreadsheet, and PDF or XLSX would add only a dependency. Each indicator
    becomes a block with its own header, which Excel, LibreOffice and pandas read as is.
    """
    dados = indicadores_periodo(gestor_id, inicio, fim)

    buffer = io.StringIO()
    escritor = csv.writer(buffer)
    escritor.writerow(["relatorio", "MeBusKa - indicadores operacionais (RF-21)"])
    escritor.writerow(["periodo_inicio", dados["periodo"]["inicio"]])
    escritor.writerow(["periodo_fim", dados["periodo"]["fim"]])
    escritor.writerow(["total_viagens", dados["total_viagens"]])
    if dados["mensagem"]:
        escritor.writerow(["mensagem", dados["mensagem"]])

    blocos: list[tuple[str, list[str], list[list]]] = [
        (
            "viagens_por_status",
            ["status", "total"],
            [[i["status"], i["total"]] for i in dados["viagens_por_status"]],
        ),
        (
            "negacoes_por_ponto",
            ["ponto_id", "ponto", "negacoes"],
            [[i["ponto_id"], i["apelido"], i["negacoes"]] for i in dados["negacoes_por_ponto"]],
        ),
        (
            "tempo_medio_por_trecho",
            ["ordem", "ponto_origem", "ponto_destino", "minutos_medio", "amostras"],
            [
                [
                    i["ordem"],
                    i["ponto_origem"],
                    i["ponto_destino"],
                    i["minutos_medio"],
                    i["amostras"],
                ]
                for i in dados["tempo_medio_por_trecho"]
            ],
        ),
        (
            "ocupacao",
            ["metrica", "valor"],
            [[chave, valor] for chave, valor in dados["ocupacao"].items()],
        ),
        (
            "ipk",
            ["metrica", "valor"],
            [[chave, valor] for chave, valor in dados["ipk"].items()],
        ),
    ]

    for nome, cabecalho, linhas in blocos:
        escritor.writerow([])
        escritor.writerow([nome])
        escritor.writerow(cabecalho)
        escritor.writerows(linhas)

    return buffer.getvalue()


def listar_ausencias(gestor_id: str, inicio: date, fim: date, page: int, per_page: int) -> dict:
    """Students who missed a trip they were confirmed on, or dropped out after it left.

    Derived, not stored: a no-show is an `alunos_confirmados` row still confirmed
    but not boarded on a finished trip. A dropout is `alunos_confirmados.desistencia_em`
    on a fixed trip, or a DESISTENCIA request (RF-19) on an on-demand one; both clear
    `confirmacao`, so nobody is listed twice.
    Unlike the RF-21 indicators this list names students, so it is manager only.

    `registrado_em` never moves after the fact: the trip's end for a no-show and the
    dropout time for a dropout (`desistencia_em`, or the request's `cancelada_em`, never
    its `created_at`), falling back to the scheduled departure in local time
    (the trip date at 00:00 for on-demand trips), which is never null.
    """
    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem visualizar ausências")
    organizacao_id = gestor.organizacao_id

    partida_prevista = func.timezone(
        current_app.config["TIMEZONE"],
        Viagem.data + func.coalesce(HorarioRota.horario_saida, cast("00:00", Time)),
    )

    def ausencias_do_periodo(tipo: str, aluno_id, registrado_em) -> Select:
        """Shared columns, route join and org/period filters of every UNION branch."""
        return juntar_rota(
            select(
                literal(tipo).label("tipo"),
                aluno_id.label("aluno_id"),
                Viagem.id.label("viagem_id"),
                Viagem.data.label("data"),
                Rota.nome.label("rota_nome"),
                func.coalesce(registrado_em, partida_prevista).label("registrado_em"),
            ).select_from(Viagem)
        ).where(
            Rota.organizacao_id == organizacao_id,
            Viagem.data >= inicio,
            Viagem.data <= fim,
            Viagem.status != StatusViagem.CANCELADA,
        )

    nao_embarcou = (
        ausencias_do_periodo("AUSENCIA", AlunosConfirmados.aluno_id, Viagem.fim_real)
        .join(AlunosConfirmados, AlunosConfirmados.viagem_id == Viagem.id)
        .where(
            Viagem.status == StatusViagem.FINALIZADA,
            AlunosConfirmados.confirmacao.is_(True),
            AlunosConfirmados.embarcou.is_(False),
        )
    )

    desistiu_fixa = (
        ausencias_do_periodo(
            "DESISTENCIA", AlunosConfirmados.aluno_id, AlunosConfirmados.desistencia_em
        )
        .join(AlunosConfirmados, AlunosConfirmados.viagem_id == Viagem.id)
        .where(
            AlunosConfirmados.desistencia_em.is_not(None),
            AlunosConfirmados.embarcou.is_(False),
        )
    )

    # One row per (trip, student) even if old data holds several DESISTENCIA requests.
    desistencias = (
        select(
            SolicitacaoViagem.viagem_id,
            SolicitacaoViagem.aluno_id,
            func.max(SolicitacaoViagem.cancelada_em).label("registrado_em"),
        )
        .where(SolicitacaoViagem.status == StatusSolicitacao.DESISTENCIA)
        .group_by(SolicitacaoViagem.viagem_id, SolicitacaoViagem.aluno_id)
        .subquery()
    )
    desistiu_sob_demanda = (
        ausencias_do_periodo("DESISTENCIA", desistencias.c.aluno_id, desistencias.c.registrado_em)
        .join(desistencias, desistencias.c.viagem_id == Viagem.id)
        .outerjoin(
            AlunosConfirmados,
            and_(
                AlunosConfirmados.viagem_id == Viagem.id,
                AlunosConfirmados.aluno_id == desistencias.c.aluno_id,
            ),
        )
        # Rows from before the cancel flow refused dropping out after boarding.
        .where(AlunosConfirmados.embarcou.is_not(True))
    )

    ausencias = union_all(nao_embarcou, desistiu_fixa, desistiu_sob_demanda).subquery()

    total = db.session.execute(
        select(func.count())
        .select_from(ausencias)
        .join(Aluno, Aluno.usuario_id == ausencias.c.aluno_id)
    ).scalar_one()

    linhas = db.session.execute(
        select(ausencias, Aluno.nome, Aluno.foto_url)
        .join(Aluno, Aluno.usuario_id == ausencias.c.aluno_id)
        .order_by(
            ausencias.c.data.desc(),
            Aluno.nome,
            ausencias.c.viagem_id,
            ausencias.c.aluno_id,
            ausencias.c.tipo,
        )
        .limit(per_page)
        .offset((page - 1) * per_page)
    ).all()

    items: list[dict] = []
    for linha in linhas:
        items.append(
            {
                "tipo": linha.tipo,
                "aluno_id": str(linha.aluno_id),
                "aluno_nome": linha.nome,
                "foto_url": linha.foto_url,
                "viagem_id": str(linha.viagem_id),
                "rota_nome": linha.rota_nome,
                "data": linha.data.isoformat(),
                "registrado_em": linha.registrado_em.isoformat(),
            }
        )

    return {"items": items, "total": total, "page": page, "per_page": per_page}
