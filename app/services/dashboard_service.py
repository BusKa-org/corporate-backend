import csv
import io
import logging
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Float, Select, and_, case, cast, func, select
from sqlalchemy.orm import aliased

from app.core.exceptions import NotFoundError
from app.models.base import db
from app.models.enum import StatusSolicitacao, StatusViagem
from app.models.geo import Ponto
from app.models.onibus import Onibus
from app.models.rota import HorarioRota, Rota
from app.models.viagem import AlunosConfirmados, TelemetriaViagem, Viagem, ViagemPonto
from app.services.user_service import _get_gestor_or_403

logger = logging.getLogger(__name__)


def obter_progresso_viagem(gestor_id: str, viagem_id: str) -> list[dict]:
    """Retorna os pontos pelos quais o motorista já passou, em ordem cronológica."""

    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem auditar o trajeto de viagens")

    viagem = (
        db.session.query(Viagem)
        .join(HorarioRota)
        .join(Rota)
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
    """Gera inteligência de negócio agregada para o painel web do Gestor."""
    gestor = _get_gestor_or_403(
        gestor_id, "Apenas gestores podem visualizar relatórios operacionais"
    )

    try:
        stats_viagem = (
            db.session.query(
                func.count(Viagem.id).label("total_viagens"),
                func.sum(Viagem.km_real).label("km_total_rodado"),
            )
            .join(HorarioRota, Viagem.horario_rota_id == HorarioRota.id)
            .join(Rota, HorarioRota.rota_id == Rota.id)
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
            .join(HorarioRota, Viagem.horario_rota_id == HorarioRota.id)
            .join(Rota, HorarioRota.rota_id == Rota.id)
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
    """Retorna o rastro de GPS (telemetria) de uma viagem em ordem cronológica."""

    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem auditar a telemetria de viagens")

    viagem = (
        db.session.query(Viagem)
        .join(HorarioRota)
        .join(Rota)
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


# ==========================================
# RF-21 — indicadores agregados e anonimizados do período
# ==========================================
#
# Decisões que valem para todos os indicadores abaixo:
#
# * **Escopo de rota.** Uma viagem chega ao circuito por dois caminhos: a
#   rodada sob demanda aponta direto para `rota_id`, a viagem programada
#   herdada chega por `horario_rota_id`. O painel cobre os dois — o gestor do
#   A operação corrente é DRT, mas a mesma base ainda guarda viagens programadas e um
#   relatório que as ignorasse subnotificaria o período sem avisar.
# * **Período.** `Viagem.data` é um `DATE`; os dois limites são inclusivos e a
#   comparação é de data civil, sem fuso envolvido.
# * **Anonimização (RF-20).** Nada aqui toca `Aluno`/`User`: as linhas de
#   `alunos_confirmados` de contas excluídas continuam contando, e nenhuma
#   consulta junta de volta com identidade. As únicas entidades nomeadas nas
#   respostas são pontos de embarque.

# Só viagens que de fato rodaram entram em ocupação e IPK. Uma rodada OCIOSA
# ou CANCELADA não é operação: contá-la afundaria a ocupação média e sugeriria
# uma frota superdimensionada.
_STATUS_OPERADAS = (StatusViagem.EM_ROTA, StatusViagem.EM_ANDAMENTO, StatusViagem.FINALIZADA)


def _viagens_periodo(organizacao_id: Any, inicio: date, fim: date, operadas: bool = False) -> Any:
    """Subconsulta com as viagens da organização no período (limites inclusivos)."""
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
    """Subconsulta: quantos alunos efetivamente embarcaram em cada viagem."""
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
    """Converte Numeric/Decimal do Postgres em float, preservando o nulo."""
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
    """Estrangulamentos: onde a demanda passou da capacidade (RF-14).

    Negações sem ponto de embarque declarado ficam de fora — não há como
    atribuí-las a um ponto, e por construção não deveriam existir, já que a
    recusa só acontece depois da declaração de origem/destino (RF-13).
    """
    total = func.count().label("negacoes")
    linhas = db.session.execute(
        select(AlunosConfirmados.ponto_embarque_id, Ponto.apelido, total)
        .select_from(AlunosConfirmados)
        .join(viagens, viagens.c.id == AlunosConfirmados.viagem_id)
        .join(Ponto, Ponto.id == AlunosConfirmados.ponto_embarque_id)
        .where(AlunosConfirmados.status == StatusSolicitacao.NEGADO)
        .group_by(AlunosConfirmados.ponto_embarque_id, Ponto.apelido)
        .order_by(total.desc(), Ponto.apelido)
    ).all()
    return [
        {"ponto_id": str(ponto_id), "apelido": apelido, "negacoes": negacoes}
        for ponto_id, apelido, negacoes in linhas
    ]


def _tempo_medio_por_trecho(viagens: Any) -> list[dict]:
    """Tempo médio entre pontos consecutivos do circuito.

    Os trechos saem do par (ordem, ordem+1) de `viagem_ponto`, que é a mesma
    ordenação de `rota_ponto`. Só entram trechos em que os dois pontos têm
    chegada real registrada.
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
    """Ocupação média contra `Onibus.capacidade` e IPK (passageiros por km).

    `km_real` é anulável e continua vazio na maioria das viagens. As viagens
    sem quilometragem são **excluídas** do IPK — numerador e denominador — e
    contadas à parte em `viagens_sem_km`. Tratar o nulo como zero inflaria o
    denominador com zeros ou o numerador com passageiros sem km, e um IPK
    subestimado leva a decisão de frota errada. Sem nenhuma viagem com km, o
    IPK vem `null`, não `0`.
    """
    emb = _embarques_por_viagem()
    passageiros = func.coalesce(emb.c.passageiros, 0)
    capacidade = Onibus.capacidade
    com_km = and_(operadas.c.km_real.isnot(None), operadas.c.km_real > 0)
    # Viagem sem veículo atribuído (ou com capacidade zerada) não entra na
    # ocupação: não há denominador. O `case` a mantém no IPK mesmo assim.
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
    """Intervalo em que a organização de fato tem viagens, para sugerir ao gestor."""
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
    """RF-21 — painel agregado do gestor para o período selecionado.

    Tudo é calculado no banco; nenhuma linha de viagem ou de aluno sobe para o
    Python. A resposta não contém nome, e-mail, CPF nem id de usuário.
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
    """Exporta o relatório do período em CSV (RF-21, passo 4 do fluxo principal).

    CSV pela biblioteca padrão: o relatório é tabular, o destino é planilha, e
    nem PDF nem XLSX acrescentam informação — só uma dependência. Cada
    indicador vira um bloco com seu próprio cabeçalho, formato que Excel,
    LibreOffice e pandas leem sem tratamento.
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
