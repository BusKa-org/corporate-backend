"""Routes (Rota) service - route management, schedules."""

import logging
from typing import Any

from flask import current_app
from sqlalchemy import and_, or_, select

from app.core.exceptions import (
    AppError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.models.base import db
from app.models.enum import DiaDaSemana, SentidoViagem, StatusViagem, TipoViagem, UserRole
from app.models.geo import Ponto
from app.models.rota import DiasOperacao, HorarioRota, Rota, RotaAluno, RotaPonto
from app.models.user import User
from app.models.viagem import Viagem
from app.utils import audit_logger, tempo, validate_uuid

logger = logging.getLogger(__name__)

PARAMETROS_SOB_DEMANDA = ("buffer_minutos", "prazo_inicio_minutos")

# RF-04, secondary flow 1: while a trip using the stop is active, the change waits.
STATUS_VIAGEM_ATIVA = (
    StatusViagem.SOLICITADA,
    StatusViagem.BUFFER_ABERTO,
    StatusViagem.EM_ANDAMENTO,
)


def _existe_viagem_ativa(rota_ids: list) -> bool:
    """Active trip on any of the routes, both the on-demand round (`Viagem.rota_id`)
    and the scheduled trip (via the timetable).
    """
    if not rota_ids:
        return False

    return (
        db.session.query(Viagem.id)
        .outerjoin(HorarioRota, Viagem.horario_rota_id == HorarioRota.id)
        .filter(
            Viagem.status.in_(STATUS_VIAGEM_ATIVA),
            or_(Viagem.rota_id.in_(rota_ids), HorarioRota.rota_id.in_(rota_ids)),
        )
        .first()
        is not None
    )


def garantir_rota_sem_viagem_ativa(rota_id: str) -> None:
    """RF-04: blocks changing the stop sequence of a circuit in use."""
    if _existe_viagem_ativa([rota_id]):
        raise ConflictError(
            "Há viagens ativas usando esta rota; aguarde a finalização para alterar os pontos"
        )


def garantir_ponto_sem_viagem_ativa(ponto_id: str) -> None:
    """RF-04: blocks editing or removing a stop used by an active trip."""
    rota_ids = [
        row[0] for row in db.session.query(RotaPonto.rota_id).filter_by(ponto_id=ponto_id).all()
    ]
    if _existe_viagem_ativa(rota_ids):
        raise ConflictError(
            "Há viagens ativas usando este ponto; aguarde a finalização para alterá-lo"
        )


def _renumerar_pontos(rota_id: str) -> None:
    """Keeps `RotaPonto.ordem` as 1..n with no gaps after add/remove."""
    pontos = RotaPonto.query.filter_by(rota_id=rota_id).order_by(RotaPonto.ordem).all()
    for posicao, rp in enumerate(pontos, start=1):
        rp.ordem = posicao


def _get_rota_do_gestor(
    user_id: str,
    rota_id: str,
    mensagem_permissao: str = "Permissão negada",
    papeis: tuple[UserRole, ...] = (UserRole.GESTOR,),
) -> Rota:
    """Route the user may manage: allowed role and same organization.

    Raises: ValidationError, ForbiddenError, NotFoundError
    """
    validate_uuid(rota_id, "Rota ID")

    user = db.session.get(User, user_id)
    if not user or user.role not in papeis:
        raise ForbiddenError(mensagem_permissao)

    rota = db.session.get(Rota, rota_id)
    if not rota or not rota.ativa:
        raise NotFoundError("Rota não encontrada")

    if rota.organizacao_id != user.organizacao_id:
        raise ForbiddenError("Acesso negado")
    return rota


def list_all_rotas(user_id: str) -> list[Rota]:
    """List all routes for the user's organizacao. Raises NotFoundError if the user is not found."""
    validate_uuid(user_id, "User ID")
    user = db.session.get(User, user_id)
    if not user:
        raise NotFoundError("Usuário não encontrado")

    logger.debug(f"User {user_id} listing routes for organizacao {user.organizacao_id}")
    return Rota.query.filter_by(organizacao_id=user.organizacao_id, ativa=True).all()


def list_my_rotas(user_id: str) -> list[Rota]:
    """List routes linked to the logged-in user."""
    user = db.session.get(User, user_id)
    if not user:
        raise NotFoundError("Usuário não encontrado")

    match user.role:
        case UserRole.ALUNO:
            inscricoes = RotaAluno.query.filter_by(aluno_id=user.id).all()
            rota_ids = [i.rota_id for i in inscricoes]
            return Rota.query.filter(Rota.id.in_(rota_ids), Rota.ativa.is_(True)).all()
        case UserRole.MOTORISTA:
            return Rota.query.filter_by(motorista_padrao_id=user.id, ativa=True).all()
        case UserRole.GESTOR:
            return Rota.query.filter_by(organizacao_id=user.organizacao_id, ativa=True).all()
        case _:
            return []


def create_rota(gestor_id: str, data: dict[str, Any]) -> Rota:
    """
    Create a new route with optional points and schedules.

    Raises: ForbiddenError, ValidationError, AppError
    """
    user = db.session.get(User, gestor_id)
    if not user or user.role not in (UserRole.GESTOR, UserRole.MOTORISTA):
        raise ForbiddenError("Permissão negada")

    nome = data.get("nome")
    if not nome:
        raise ValidationError("Nome da rota é obrigatório")

    tipo = data.get("tipo", TipoViagem.FIXA)
    parametros = {}
    if tipo == TipoViagem.SOB_DEMANDA:
        if data.get("horarios"):
            raise ValidationError("Rotas sob demanda não possuem grade de horários")
        buffer_minutos = data.get("buffer_minutos")
        prazo_inicio_minutos = data.get("prazo_inicio_minutos")
        parametros = {
            "buffer_minutos": buffer_minutos,
            "prazo_inicio_minutos": prazo_inicio_minutos,
        }
        if buffer_minutos is None:
            parametros["buffer_minutos"] = current_app.config["ROTA_BUFFER_MINUTOS_PADRAO"]
        if prazo_inicio_minutos is None:
            parametros["prazo_inicio_minutos"] = current_app.config[
                "ROTA_PRAZO_INICIO_MINUTOS_PADRAO"
            ]
    elif any(data.get(k) is not None for k in PARAMETROS_SOB_DEMANDA):
        raise ValidationError("Parâmetros de buffer só se aplicam a rotas sob demanda")

    try:
        # If a driver creates a route, automatically assign themselves as the default driver
        motorista_id = data.get("motorista_padrao_id")
        if not motorista_id and user.role == UserRole.MOTORISTA:
            motorista_id = user.id

        rota = Rota(
            nome=nome,
            tipo=tipo,
            **parametros,
            motorista_padrao_id=motorista_id,
            veiculo_padrao_id=data.get("veiculo_padrao_id"),
            organizacao_id=user.organizacao_id,
        )

        db.session.add(rota)
        db.session.flush()

        if "pontos" in data:
            for p_data in data["pontos"]:
                ponto_id = p_data.get("ponto_id")
                ordem = p_data.get("ordem", 0)

                if ponto_id:
                    # Link an existing ponto by ID
                    existing_ponto = db.session.get(Ponto, ponto_id)
                    if not existing_ponto:
                        logger.warning(f"Ponto {ponto_id} not found, skipping")
                        continue
                    rota_ponto = RotaPonto(rota_id=rota.id, ponto_id=ponto_id, ordem=ordem)
                    db.session.add(rota_ponto)
                elif "latitude" in p_data and "longitude" in p_data:
                    # Create a brand-new ponto from coordinates
                    novo_ponto = Ponto(
                        organizacao_id=user.organizacao_id,
                        latitude=p_data["latitude"],
                        longitude=p_data["longitude"],
                        apelido=p_data.get("apelido", f"Ponto {ordem}"),
                    )
                    db.session.add(novo_ponto)
                    db.session.flush()

                    rota_ponto = RotaPonto(rota_id=rota.id, ponto_id=novo_ponto.id, ordem=ordem)
                    db.session.add(rota_ponto)

        # No travar_rota here: the new route is invisible to other transactions until commit.
        for h_data in data.get("horarios", []):
            _garantir_horario_nao_duplicado(
                rota.id, h_data["horario_saida"], h_data["sentido"], h_data["dias"]
            )
            _criar_horario(rota.id, h_data)

        db.session.commit()

        return rota

    except AppError:
        db.session.rollback()
        raise
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating route: {e}")
        raise AppError("Erro interno ao criar rota", 500)


def add_ponto(gestor_id: str, rota_id: str, data: dict[str, Any]) -> None:
    """
    Add points to a route.

    Raises: ForbiddenError, NotFoundError, ValidationError, AppError
    """
    rota = _get_rota_do_gestor(gestor_id, rota_id, papeis=(UserRole.GESTOR, UserRole.MOTORISTA))

    pontos = data.get("pontos", [])
    if not pontos or not isinstance(pontos, list):
        raise ValidationError("A rota deve conter pelo menos um ponto válido")

    garantir_rota_sem_viagem_ativa(rota.id)

    try:
        # Clear existing route points (replacing with new set)
        RotaPonto.query.filter_by(rota_id=rota.id).delete()
        db.session.flush()

        # The order sent is a preference: what persists is the gap-free 1..n sequence
        # RF-14 uses to number the segments.
        for ordem, p in enumerate(sorted(pontos, key=lambda x: x.get("ordem", 0)), start=1):
            ponto_id = p.get("ponto_id")

            if ponto_id:
                existing_ponto = db.session.get(Ponto, ponto_id)
                if not existing_ponto:
                    logger.warning(f"Point {ponto_id} not found, skipping")
                    continue
                if existing_ponto.organizacao_id != rota.organizacao_id:
                    logger.warning(f"Point {ponto_id} belongs to different organizacao, skipping")
                    continue

                novo_rota_ponto = RotaPonto(rota_id=rota.id, ponto_id=ponto_id, ordem=ordem)
                db.session.add(novo_rota_ponto)

            else:
                nome_p = p.get("nome")
                lat = p.get("latitude")
                lon = p.get("longitude")

                if not nome_p or lat is None or lon is None:
                    continue

                ponto = Ponto(
                    organizacao_id=rota.organizacao_id,
                    apelido=nome_p,
                    latitude=lat,
                    longitude=lon,
                )
                db.session.add(ponto)
                db.session.flush()

                novo_rota_ponto = RotaPonto(rota_id=rota.id, ponto_id=ponto.id, ordem=ordem)
                db.session.add(novo_rota_ponto)

        # Close the gaps left by the stops skipped above.
        _renumerar_pontos(rota.id)

        db.session.commit()

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error adding points to route: {e}")
        raise AppError("Erro interno ao adicionar pontos", 500)


def remover_ponto(gestor_id: str, rota_id: str, ponto_id: str) -> None:
    """RF-04: removes a stop from the circuit and renumbers the remaining sequence.

    Raises: ForbiddenError, NotFoundError, ConflictError
    """
    rota = _get_rota_do_gestor(
        gestor_id, rota_id, "Apenas gestores gerenciam os pontos do circuito"
    )

    rota_ponto = db.session.get(RotaPonto, (rota.id, ponto_id))
    if not rota_ponto:
        raise NotFoundError("Ponto não encontrado nesta rota")

    garantir_rota_sem_viagem_ativa(rota.id)

    db.session.delete(rota_ponto)
    db.session.flush()
    _renumerar_pontos(rota.id)
    db.session.commit()

    audit_logger.log_user_action(
        action="remover_ponto",
        user_id=gestor_id,
        resource_type="rota",
        resource_id=str(rota_id),
        details={"ponto_id": str(ponto_id)},
    )


def _get_rota_fixa_do_gestor(gestor_id: str, rota_id: str) -> Rota:
    """Raises: ValidationError, ForbiddenError, NotFoundError"""
    rota = _get_rota_do_gestor(gestor_id, rota_id, "Apenas gestores gerenciam horários")
    if rota.tipo == TipoViagem.SOB_DEMANDA:
        raise ValidationError("Rotas sob demanda não possuem grade de horários")
    return rota


def travar_rota(rota_id: Any) -> None:
    """Lock order for schedule edits and trip generation: this Rota row first, held
    until commit. NO KEY UPDATE, so inserts referencing the route are not blocked.
    """
    db.session.execute(select(Rota.id).where(Rota.id == rota_id).with_for_update(key_share=True))


def _garantir_horario_nao_duplicado(
    rota_id: Any, horario_saida: Any, sentido: str, dias: list[str], ignorar_horario_id: Any = None
) -> None:
    """Rejects an active schedule with the same direction and time on any of the weekdays."""
    dias_enum: list[DiaDaSemana] = []
    for dia_str in dias:
        dias_enum.append(DiaDaSemana(dia_str))

    query = (
        db.session.query(DiasOperacao.dia)
        .join(HorarioRota, DiasOperacao.horario_rota_id == HorarioRota.id)
        .filter(
            HorarioRota.rota_id == rota_id,
            HorarioRota.ativo.is_(True),
            HorarioRota.sentido == SentidoViagem(sentido),
            HorarioRota.horario_saida == horario_saida,
            DiasOperacao.dia.in_(dias_enum),
        )
    )
    if ignorar_horario_id is not None:
        query = query.filter(HorarioRota.id != ignorar_horario_id)

    conflito = query.first()
    if conflito:
        raise ConflictError(
            f"Já existe um horário {sentido} às {horario_saida.strftime('%H:%M')} "
            f"nesta rota em {conflito[0].value}"
        )


def _preencher_dias(horario: HorarioRota, dias: list[str]) -> None:
    for dia_str in dias:
        horario.dias.append(DiasOperacao(dia=DiaDaSemana(dia_str)))


def _criar_horario(rota_id: Any, data: dict[str, Any]) -> HorarioRota:
    novo_horario = HorarioRota(
        rota_id=rota_id,
        horario_saida=data.get("horario_saida"),
        sentido=SentidoViagem(data.get("sentido")),
    )
    _preencher_dias(novo_horario, data["dias"])
    db.session.add(novo_horario)
    return novo_horario


def add_horario(gestor_id: str, rota_id: str, data: dict[str, Any]) -> HorarioRota:
    """
    Add a schedule to a route.

    Raises: ForbiddenError, NotFoundError, ValidationError, ConflictError, AppError
    """
    rota = _get_rota_fixa_do_gestor(gestor_id, rota_id)

    travar_rota(rota.id)
    _garantir_horario_nao_duplicado(rota.id, data["horario_saida"], data["sentido"], data["dias"])

    try:
        novo_horario = _criar_horario(rota.id, data)
        db.session.commit()
        return novo_horario

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error adding schedule: {e}")
        raise AppError("Erro interno ao adicionar horário", 500)


def _get_horario_do_gestor(gestor_id: str, rota_id: str, horario_id: str) -> HorarioRota:
    """Active schedule of the route. Locks the route first, so no trip is generated
    for it between the pending-trip check and the write.

    Raises: ValidationError, ForbiddenError, NotFoundError
    """
    validate_uuid(horario_id, "Horário ID")
    rota = _get_rota_fixa_do_gestor(gestor_id, rota_id)
    travar_rota(rota.id)

    horario = (
        db.session.query(HorarioRota)
        .filter(
            HorarioRota.id == horario_id,
            HorarioRota.rota_id == rota.id,
            HorarioRota.ativo.is_(True),
        )
        .first()
    )
    if not horario:
        raise NotFoundError("Horário não encontrado nesta rota")
    return horario


def _filtro_viagem_pendente() -> Any:
    """Past AGENDADA trips never leave that status on their own, so only upcoming
    ones are pending; a started trip always is.
    """
    hoje = tempo.agora_local().date()
    return or_(
        Viagem.status.in_(STATUS_VIAGEM_ATIVA),
        and_(Viagem.status == StatusViagem.AGENDADA, Viagem.data >= hoje),
    )


def _garantir_horario_sem_viagem_pendente(horario: HorarioRota, acao: str) -> None:
    """Pending trips would move with the schedule."""
    pendente = (
        db.session.query(Viagem.id)
        .filter(Viagem.horario_rota_id == horario.id, _filtro_viagem_pendente())
        .first()
    )
    if pendente:
        raise ConflictError(
            f"Há viagens agendadas ou em andamento neste horário; "
            f"cancele-as ou aguarde a finalização para {acao}"
        )


def _horario_tem_viagens(horario: HorarioRota) -> bool:
    return (
        db.session.query(Viagem.id).filter(Viagem.horario_rota_id == horario.id).first() is not None
    )


def update_horario(
    gestor_id: str, rota_id: str, horario_id: str, data: dict[str, Any]
) -> HorarioRota:
    """RF-05: replaces time, direction and weekdays of a fixed route's schedule.

    A schedule with trips is retired and replaced by a new one (new id), so the
    trips keep the time and direction they ran with.

    Raises: ForbiddenError, NotFoundError, ValidationError, ConflictError, AppError
    """
    horario = _get_horario_do_gestor(gestor_id, rota_id, horario_id)
    dias_list = data["dias"]

    _garantir_horario_sem_viagem_pendente(horario, "alterá-lo")
    _garantir_horario_nao_duplicado(
        horario.rota_id, data["horario_saida"], data["sentido"], dias_list, horario.id
    )

    try:
        if _horario_tem_viagens(horario):
            horario.ativo = False
            horario = _criar_horario(horario.rota_id, data)
        else:
            horario.horario_saida = data.get("horario_saida")
            horario.sentido = SentidoViagem(data.get("sentido"))
            horario.dias.clear()
            db.session.flush()
            _preencher_dias(horario, dias_list)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating schedule {horario_id}: {e}")
        raise AppError("Erro interno ao atualizar horário", 500)

    audit_logger.log_user_action(
        action="update_horario",
        user_id=gestor_id,
        resource_type="rota",
        resource_id=str(rota_id),
        details={"horario_id": str(horario_id), "novo_horario_id": str(horario.id)},
    )
    return horario


def delete_horario(gestor_id: str, rota_id: str, horario_id: str) -> None:
    """RF-05: removes a schedule from a fixed route; one with trips is only
    retired, so those trips keep their time and direction.

    Raises: ForbiddenError, NotFoundError, ConflictError, AppError
    """
    horario = _get_horario_do_gestor(gestor_id, rota_id, horario_id)
    _garantir_horario_sem_viagem_pendente(horario, "removê-lo")

    try:
        if _horario_tem_viagens(horario):
            horario.ativo = False
        else:
            db.session.delete(horario)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting schedule {horario_id}: {e}")
        raise AppError("Erro interno ao remover horário", 500)

    audit_logger.log_user_action(
        action="delete_horario",
        user_id=gestor_id,
        resource_type="rota",
        resource_id=str(rota_id),
        details={"horario_id": str(horario_id)},
    )


def get_horarios(user_id: str, rota_id: str) -> list:
    """
    Get schedules for a route.

    Raises: NotFoundError, ForbiddenError
    """
    user = db.session.get(User, user_id)
    if not user:
        raise NotFoundError("Usuário não encontrado")

    rota = db.session.get(Rota, rota_id)
    if not rota or not rota.ativa:
        raise NotFoundError("Rota não encontrada")

    if (
        user.role in (UserRole.GESTOR, UserRole.MOTORISTA)
        and rota.organizacao_id != user.organizacao_id
    ):
        raise ForbiddenError("Acesso negado")

    return rota.grade_horarios_ativos


def get_by_id(user_id: str, rota_id: str) -> Rota:
    """
    Get route by ID.

    Raises: NotFoundError, ForbiddenError
    """
    user = db.session.get(User, user_id)
    if not user:
        raise NotFoundError("Usuário não encontrado")

    rota = db.session.get(Rota, rota_id)
    if not rota or not rota.ativa:
        raise NotFoundError("Rota não encontrada")

    if (
        user.role in (UserRole.GESTOR, UserRole.MOTORISTA)
        and rota.organizacao_id != user.organizacao_id
    ):
        raise ForbiddenError("Acesso negado")

    return rota


def update_rota(user_id: str, rota_id: str, data: dict[str, Any]) -> Rota:
    """Update route name, driver, or vehicle.

    Raises: ForbiddenError, NotFoundError, AppError
    """
    validate_uuid(user_id, "User ID")
    validate_uuid(rota_id, "Rota ID")

    user = db.session.get(User, user_id)
    if not user or user.role != UserRole.GESTOR:
        logger.warning(f"Non-gestor {user_id} attempted to update route {rota_id}")
        raise ForbiddenError("Permissão negada")

    rota = db.session.get(Rota, rota_id)
    if not rota or not rota.ativa:
        raise NotFoundError("Rota não encontrada")

    if rota.organizacao_id != user.organizacao_id:
        audit_logger.log_security_event(
            event_type="unauthorized_route_update",
            severity="high",
            user_id=user_id,
            details={
                "rota_id": rota_id,
                "user_organizacao": user.organizacao_id,
                "rota_organizacao": rota.organizacao_id,
            },
        )
        logger.warning(
            f"Cross-tenant route update attempt: user {user_id} tried to update "
            f"route {rota_id} from different organizacao"
        )
        raise ForbiddenError("Acesso negado")

    if "tipo" in data and data["tipo"] != rota.tipo:
        raise ValidationError("O tipo da rota não pode ser alterado; crie uma nova rota")

    if rota.tipo != TipoViagem.SOB_DEMANDA and any(k in data for k in PARAMETROS_SOB_DEMANDA):
        raise ValidationError("Parâmetros de buffer só se aplicam a rotas sob demanda")

    updated_fields: list[str] = []

    try:
        if "nome" in data:
            rota.nome = data.get("nome")
            updated_fields.append("nome")

        if "motorista_padrao_id" in data:
            rota.motorista_padrao_id = data.get("motorista_padrao_id")
            updated_fields.append("motorista_padrao_id")

        if "veiculo_padrao_id" in data:
            rota.veiculo_padrao_id = data.get("veiculo_padrao_id")
            updated_fields.append("veiculo_padrao_id")

        for campo in PARAMETROS_SOB_DEMANDA:
            if campo in data:
                setattr(rota, campo, data[campo])
                updated_fields.append(campo)

        db.session.commit()

        audit_logger.log_user_action(
            action="update",
            user_id=user_id,
            resource_type="rota",
            resource_id=rota_id,
            details={"updated_fields": updated_fields},
        )
        logger.info(f"Route {rota_id} updated by {user_id}: {', '.join(updated_fields)}")

        return rota

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating route {rota_id}: {e}", exc_info=True)
        raise AppError("Erro interno ao atualizar rota", 500)


def delete_rota(user_id: str, rota_id: str) -> None:
    """Delete a route; one with trips is only deactivated, so those trips keep it.

    Raises: ForbiddenError, NotFoundError, ConflictError, AppError
    """
    validate_uuid(user_id, "User ID")
    validate_uuid(rota_id, "Rota ID")

    user = db.session.get(User, user_id)
    if not user or user.role != UserRole.GESTOR:
        logger.warning(f"Non-gestor {user_id} attempted to delete route {rota_id}")
        raise ForbiddenError("Permissão negada")

    rota = db.session.get(Rota, rota_id)
    if not rota or not rota.ativa:
        raise NotFoundError("Rota não encontrada")

    if rota.organizacao_id != user.organizacao_id:
        audit_logger.log_security_event(
            event_type="unauthorized_route_deletion",
            severity="critical",
            user_id=user_id,
            details={
                "rota_id": rota_id,
                "user_organizacao": user.organizacao_id,
                "rota_organizacao": rota.organizacao_id,
            },
        )
        logger.error(
            f"Critical: Cross-tenant route deletion attempt by user {user_id} on route {rota_id}"
        )
        raise ForbiddenError("Acesso negado")

    travar_rota(rota.id)
    viagens_da_rota = (
        db.session.query(Viagem.id)
        .outerjoin(HorarioRota, Viagem.horario_rota_id == HorarioRota.id)
        .filter(or_(Viagem.rota_id == rota.id, HorarioRota.rota_id == rota.id))
    )
    if viagens_da_rota.filter(_filtro_viagem_pendente()).first():
        raise ConflictError(
            "Há viagens agendadas ou em andamento nesta rota; "
            "cancele-as ou aguarde a finalização para removê-la"
        )

    try:
        rota_nome = rota.nome

        # The trip FKs are SET NULL: deleting would wipe route, time and direction of past trips.
        if viagens_da_rota.first():
            rota.ativa = False
            for horario in rota.grade_horarios:
                horario.ativo = False
        else:
            db.session.delete(rota)
        db.session.commit()

        audit_logger.log_user_action(
            action="delete",
            user_id=user_id,
            resource_type="rota",
            resource_id=rota_id,
            details={"rota_nome": rota_nome},
        )
        logger.info(f"Route {rota_id} ({rota_nome}) deleted by gestor {user_id}")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting route {rota_id}: {e}", exc_info=True)
        raise AppError("Erro interno ao remover rota", 500)


def get_pontos_by_rota(user_id: str, rota_id: str) -> list[dict[str, Any]]:
    user = db.session.get(User, user_id)
    if not user:
        raise NotFoundError("Usuário não encontrado")

    rota = db.session.get(Rota, rota_id)
    if not rota or not rota.ativa:
        raise NotFoundError("Rota não encontrada")

    rota_pontos = RotaPonto.query.filter_by(rota_id=rota_id).order_by(RotaPonto.ordem.asc()).all()

    resultado = []
    for rp in rota_pontos:
        ponto = rp.ponto
        resultado.append(
            {
                "id": str(ponto.id),
                "apelido": ponto.apelido,
                "latitude": float(ponto.latitude),
                "longitude": float(ponto.longitude),
                "ordem": rp.ordem,
            }
        )

    return resultado
