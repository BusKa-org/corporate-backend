"""RF-22 — ingestão e consulta da telemetria da bateria do veículo elétrico.

Requisito *desejável* e condicionado à existência de interface de dados no
veículo (CAN bus / OBD-II). O adaptador que fala com o veículo mora no
repositório de deploy do cliente (`mebuska-deploy`); aqui existe apenas o
endpoint autenticado que recebe os lotes e as consultas do gestor.

Cliente embarcado: acumula as leituras localmente e faz
``POST /v1/telemetria/ingestao`` com ``{"veiculo_id": ..., "amostras": [...]}``
usando o mesmo JWT dos demais endpoints. Reenviar o lote inteiro após falha de
rede é seguro (ver `ingerir`).
"""

import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.base import db
from app.models.enum import UserRole
from app.models.onibus import Onibus
from app.models.telemetria import TelemetriaVeiculo
from app.models.user import User
from app.models.viagem import Viagem
from app.services.user_service import _get_gestor_or_403

logger = logging.getLogger(__name__)


def _veiculo_da_organizacao(user: User, veiculo_id: Any) -> Onibus:
    veiculo = db.session.get(Onibus, veiculo_id)
    if not veiculo or veiculo.organizacao_id != user.organizacao_id:
        raise NotFoundError("Veículo não encontrado")
    return veiculo


def ingerir(user_id: str, veiculo_id: Any, amostras: list[dict[str, Any]]) -> dict[str, int]:
    """Armazena um lote de amostras de um veículo.

    Idempotente por ``(veiculo_id, timestamp)``: o lote reenviado após uma falha
    de rede traz exatamente os mesmos carimbos de tempo, gerados pelo relógio do
    leitor embarcado, então basta descartar os que já estão gravados. A chave é
    suficiente porque há um único leitor por veículo emitindo em série — dois
    valores distintos para o mesmo instante e o mesmo veículo não existem.

    A garantia é do banco: ``UNIQUE (veiculo_id, timestamp)`` mais um
    ``ON CONFLICT DO NOTHING`` na gravação. A filtragem por consulta que vem
    antes é só para evitar trabalho no caso comum — sozinha ela não cobriria
    dois lotes idênticos chegando ao mesmo tempo.
    """
    user = db.session.get(User, user_id)
    if not user:
        raise NotFoundError("Usuário não encontrado")
    if user.role not in (UserRole.MOTORISTA, UserRole.GESTOR):
        raise ForbiddenError("Perfil sem permissão para enviar telemetria")

    veiculo = _veiculo_da_organizacao(user, veiculo_id)

    # Dedup dentro do próprio lote antes de olhar o banco.
    por_timestamp: dict[datetime, dict[str, Any]] = {}
    for amostra in amostras:
        por_timestamp[amostra["timestamp"]] = amostra

    ja_gravados = {
        ts
        for (ts,) in db.session.query(TelemetriaVeiculo.timestamp).filter(
            TelemetriaVeiculo.veiculo_id == veiculo.id,
            TelemetriaVeiculo.timestamp.in_(list(por_timestamp)),
        )
    }

    novos = [a for ts, a in por_timestamp.items() if ts not in ja_gravados]

    viagens_validas: set[Any] = set()
    for amostra in novos:
        viagem_id = amostra.get("viagem_id")
        if viagem_id and viagem_id not in viagens_validas:
            if not db.session.get(Viagem, viagem_id):
                raise NotFoundError("Viagem não encontrada")
            viagens_validas.add(viagem_id)

    if not novos:
        return {"recebidas": len(amostras), "armazenadas": 0, "duplicadas": len(amostras)}

    try:
        # ON CONFLICT sobre a chave natural: a filtragem acima já evita o
        # trabalho no caso comum, e isto fecha a janela em que dois lotes
        # idênticos concorrentes passam pela consulta antes de qualquer um
        # gravar. `armazenadas` vem do RETURNING, não da contagem otimista.
        inseridos = db.session.execute(
            pg_insert(TelemetriaVeiculo)
            .values(
                [
                    {
                        "id": uuid.uuid4(),
                        "veiculo_id": veiculo.id,
                        "viagem_id": a.get("viagem_id"),
                        "timestamp": a["timestamp"],
                        "nivel_bateria": a.get("nivel_bateria"),
                        "consumo_kwh": a.get("consumo_kwh"),
                        "autonomia_km": a.get("autonomia_km"),
                        "odometro_km": a.get("odometro_km"),
                        "saude_bateria": a.get("saude_bateria"),
                    }
                    for a in novos
                ]
            )
            .on_conflict_do_nothing(constraint="uq_telemetria_veiculo_timestamp")
            .returning(TelemetriaVeiculo.id)
        ).all()
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao ingerir telemetria do veículo {veiculo.id}: {e}")
        raise

    armazenadas = len(inseridos)
    return {
        "recebidas": len(amostras),
        "armazenadas": armazenadas,
        "duplicadas": len(amostras) - armazenadas,
    }


def ultimo_por_veiculo(gestor_id: str) -> list[TelemetriaVeiculo]:
    """(Gestor) Leitura mais recente de cada veículo da organização."""
    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem consultar telemetria")

    return (
        db.session.query(TelemetriaVeiculo)
        .join(Onibus, TelemetriaVeiculo.veiculo_id == Onibus.id)
        .filter(Onibus.organizacao_id == gestor.organizacao_id)
        .distinct(TelemetriaVeiculo.veiculo_id)
        .order_by(TelemetriaVeiculo.veiculo_id, TelemetriaVeiculo.timestamp.desc())
        .all()
    )


def serie(
    gestor_id: str,
    veiculo_id: Any | None = None,
    inicio: datetime | None = None,
    fim: datetime | None = None,
) -> list[TelemetriaVeiculo]:
    """(Gestor) Série temporal do período, limites inclusivos."""
    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem consultar telemetria")

    q = (
        db.session.query(TelemetriaVeiculo)
        .join(Onibus, TelemetriaVeiculo.veiculo_id == Onibus.id)
        .filter(Onibus.organizacao_id == gestor.organizacao_id)
    )
    if veiculo_id:
        q = q.filter(TelemetriaVeiculo.veiculo_id == veiculo_id)
    if inicio:
        q = q.filter(TelemetriaVeiculo.timestamp >= inicio)
    if fim:
        q = q.filter(TelemetriaVeiculo.timestamp <= fim)

    return q.order_by(TelemetriaVeiculo.timestamp).all()


def consumo_por_viagem(
    gestor_id: str, inicio: datetime | None = None, fim: datetime | None = None
) -> list[dict[str, Any]]:
    """(Gestor) Agrega os indicadores energéticos por viagem.

    Só entram amostras com `viagem_id` — as de fora de operação não pertencem a
    viagem alguma. Sai um registro por viagem para que o dashboard (RF-21)
    consiga cruzar consumo com ocupação sem reprocessar a série inteira.
    """
    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem consultar telemetria")

    q = (
        db.session.query(
            TelemetriaVeiculo.viagem_id,
            TelemetriaVeiculo.veiculo_id,
            func.count().label("amostras"),
            func.min(TelemetriaVeiculo.timestamp).label("inicio"),
            func.max(TelemetriaVeiculo.timestamp).label("fim"),
            # `consumo_kwh` é lido como incremento por amostra; o odômetro é
            # cumulativo, então a quilometragem é a diferença entre extremos.
            func.sum(TelemetriaVeiculo.consumo_kwh).label("consumo_kwh"),
            (
                func.max(TelemetriaVeiculo.odometro_km) - func.min(TelemetriaVeiculo.odometro_km)
            ).label("km"),
            func.max(TelemetriaVeiculo.nivel_bateria).label("bateria_max"),
            func.min(TelemetriaVeiculo.nivel_bateria).label("bateria_min"),
        )
        .join(Onibus, TelemetriaVeiculo.veiculo_id == Onibus.id)
        .filter(
            Onibus.organizacao_id == gestor.organizacao_id,
            TelemetriaVeiculo.viagem_id.isnot(None),
        )
    )
    if inicio:
        q = q.filter(TelemetriaVeiculo.timestamp >= inicio)
    if fim:
        q = q.filter(TelemetriaVeiculo.timestamp <= fim)

    linhas = q.group_by(TelemetriaVeiculo.viagem_id, TelemetriaVeiculo.veiculo_id).all()
    return [linha._asdict() for linha in linhas]
