"""Electric vehicle battery telemetry ingestion and queries (RF-22).

A *desirable* requirement, conditional on the vehicle having a data interface
(CAN bus / OBD-II). The adapter that talks to the vehicle lives in the client's
deploy repository (`mebuska-deploy`); here there is only the authenticated
endpoint that receives the batches, plus the manager's queries.

Resending a whole batch after a network failure is safe (see `ingerir`).
"""

import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import distinct_on, insert as pg_insert

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
    """Store a batch of samples from one vehicle.

    Idempotent per ``(veiculo_id, timestamp)``: a batch resent after a network
    failure carries exactly the same timestamps, from the onboard reader's clock,
    so the ones already saved are dropped. The key is enough because there is a
    single reader per vehicle emitting serially.

    The database is the guarantee: ``UNIQUE (veiculo_id, timestamp)`` plus
    ``ON CONFLICT DO NOTHING`` on insert. The query-based filter before it only
    saves work in the common case; alone it would not cover two identical batches
    arriving at the same time.
    """
    user = db.session.get(User, user_id)
    if not user:
        raise NotFoundError("Usuário não encontrado")
    if user.role not in (UserRole.MOTORISTA, UserRole.GESTOR):
        raise ForbiddenError("Perfil sem permissão para enviar telemetria")

    veiculo = _veiculo_da_organizacao(user, veiculo_id)

    # Dedupe within the batch itself before looking at the database.
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
        # ON CONFLICT on the natural key closes the window where two identical concurrent
        # batches pass the query above before either saves. `armazenadas` comes from
        # RETURNING, not from the optimistic count.
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
    """(Manager) Latest reading of each vehicle in the organization."""
    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem consultar telemetria")

    return (
        db.session.query(TelemetriaVeiculo)
        .join(Onibus, TelemetriaVeiculo.veiculo_id == Onibus.id)
        .filter(Onibus.organizacao_id == gestor.organizacao_id)
        .ext(distinct_on(TelemetriaVeiculo.veiculo_id))
        .order_by(TelemetriaVeiculo.veiculo_id, TelemetriaVeiculo.timestamp.desc())
        .all()
    )


def serie(
    gestor_id: str,
    veiculo_id: Any | None = None,
    inicio: datetime | None = None,
    fim: datetime | None = None,
) -> list[TelemetriaVeiculo]:
    """(Manager) Time series for the period, inclusive bounds."""
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
    """(Manager) Aggregates the energy indicators per trip.

    Only samples with `viagem_id` count; out-of-service ones belong to no trip.
    One record per trip, so the dashboard (RF-21) can cross consumption with
    occupancy without reprocessing the whole series.
    """
    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem consultar telemetria")

    q = (
        db.session.query(
            TelemetriaVeiculo.viagem_id,
            TelemetriaVeiculo.veiculo_id,
            func.count().label("amostras"),
            func.min(TelemetriaVeiculo.timestamp).label("inicio"),
            func.max(TelemetriaVeiculo.timestamp).label("fim"),
            # `consumo_kwh` is read as a per-sample increment; the odometer is cumulative,
            # so the mileage is the difference between the extremes.
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
