"""Trips (Viagem) service - trip management, student confirmations."""

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from flask import current_app
from sqlalchemy import exists, func, select

from app.core.exceptions import (
    AppError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.core.transaction import transactional
from app.extensions import scheduler
from app.models.base import db
from app.models.enum import (
    DiaDaSemana,
    SentidoViagem,
    StatusMotorista,
    StatusSolicitacao,
    StatusViagem,
    TipoViagem,
    UserRole,
)
from app.models.geo import Ponto
from app.models.rota import DiasOperacao, HorarioRota, Rota, RotaAluno, RotaPonto
from app.models.user import Aluno, Motorista, User
from app.models.viagem import (
    AlunosConfirmados,
    SolicitacaoViagem,
    TelemetriaViagem,
    Viagem,
    ViagemPonto,
)
from app.services.notificacao_service import NotificacaoService
from app.tasks.viagem_tasks import realizar_auto_checkin
from app.utils import audit_logger, tempo
from app.utils.geo_utils import calcular_distancia_metros

logger = logging.getLogger(__name__)


def _get_dia_semana_enum(data_obj: date) -> DiaDaSemana:
    """Convert weekday (0=Monday) to DiaDaSemana enum."""
    dias_map = {
        0: DiaDaSemana.SEG,
        1: DiaDaSemana.TER,
        2: DiaDaSemana.QUA,
        3: DiaDaSemana.QUI,
        4: DiaDaSemana.SEX,
        5: DiaDaSemana.SAB,
        6: DiaDaSemana.DOM,
    }
    dia = dias_map.get(data_obj.weekday())
    if not dia:
        raise ValidationError("Data inválida para cálculo do dia da semana")
    return dia


def juntar_rota(query):
    """Join Rota for any trip: on-demand trips have no horario_rota, only rota_id."""
    # rota_id is nullable and older fixed trips may only have horario_rota_id
    return query.outerjoin(HorarioRota, Viagem.horario_rota_id == HorarioRota.id).join(
        Rota, Rota.id == func.coalesce(Viagem.rota_id, HorarioRota.rota_id)
    )


def _rota_id_da_viagem(viagem: Viagem):
    if viagem.rota_id:
        return viagem.rota_id
    if viagem.horario_rota:
        return viagem.horario_rota.rota_id
    return None


def _popular_dados_da_viagem(viagem_obj: Viagem, rota_obj: Rota) -> None:
    """Copia os pontos da rota para a viagem.

    Os passageiros não são mais copiados de uma inscrição permanente: cada
    viagem tem sua própria lista, criada quando o aluno confirma presença
    (viagem fixa) ou quando o buffer da sob demanda fecha (RF-15).
    """
    pontos_rota = (
        db.session.query(RotaPonto).filter_by(rota_id=rota_obj.id).order_by(RotaPonto.ordem).all()
    )

    ordem_real = 1
    for pr in pontos_rota:
        vp = ViagemPonto(
            viagem_id=viagem_obj.id, ponto_id=pr.ponto_id, ordem=ordem_real, visitado=False
        )
        db.session.add(vp)
        ordem_real += 1


def get_proximas_viagens_aluno(user_id: str) -> list[Viagem]:
    """Returns upcoming scheduled trips for the logged student."""
    aluno = db.session.get(User, user_id)
    if not aluno or aluno.role != UserRole.ALUNO:
        raise ForbiddenError("Apenas alunos podem ver sua agenda de viagens")

    hoje = datetime.now(UTC).date()

    query = (
        juntar_rota(db.session.query(Viagem))
        .join(RotaAluno, Rota.id == RotaAluno.rota_id)
        .outerjoin(
            AlunosConfirmados,
            (AlunosConfirmados.viagem_id == Viagem.id) & (AlunosConfirmados.aluno_id == aluno.id),
        )
        # NOTE: ViagemAgendaAlunoResponseSchema._find_confirmacao takes records[0]
        # from alunos_confirmados. This only works correctly because each aluno
        # has at most one confirmation per viagem (composite PK). If this query
        # ever needs to return all students' confirmations, add
        # .options(contains_eager(Viagem.alunos_confirmados)) to pre-filter the
        # relationship to this aluno via the outerjoin above.
        .filter(
            RotaAluno.aluno_id == aluno.id,
            Viagem.status.in_([StatusViagem.AGENDADA, StatusViagem.EM_ANDAMENTO]),
            Viagem.data >= hoje,
        )
        .order_by(Viagem.data.asc(), HorarioRota.horario_saida.asc().nulls_last())
    )

    viagens = query.all()

    return viagens


def confirmar_presenca_aluno(
    user_id: str, viagem_id: str, data: dict[str, Any]
) -> AlunosConfirmados:
    """Student confirms or cancels attendance."""
    aluno = db.session.get(Aluno, user_id)
    if not aluno:
        # fallback to role check (polymorphic table)
        aluno_user = db.session.get(User, user_id)
        if aluno_user and aluno_user.role == UserRole.ALUNO:
            aluno = db.session.get(Aluno, user_id)

    if not aluno:
        raise ForbiddenError("Aluno não encontrado")

    confirmacao: bool = data["confirmacao"]
    ponto_embarque_id = data.get("ponto_embarque_id")

    with transactional():
        viagem = db.session.get(Viagem, viagem_id)
        if not viagem:
            raise NotFoundError("Viagem não encontrada")

        if viagem.rota and viagem.rota.tipo == TipoViagem.SOB_DEMANDA:
            raise ValidationError(
                "Viagens sob demanda não usam confirmação de presença. "
                "Solicite a viagem pela rota (POST /v1/rotas/<id>/solicitacoes)."
            )

        horario = viagem.horario_rota
        if not horario:
            raise NotFoundError("Horário da viagem não encontrado")

        registro = db.session.get(AlunosConfirmados, (viagem.id, aluno.usuario_id))

        if not registro:
            inscricao = db.session.get(RotaAluno, (horario.rota_id, aluno.usuario_id))
            if not inscricao:
                raise ForbiddenError("Você não está inscrito na rota desta viagem")

            registro = AlunosConfirmados(
                viagem_id=viagem.id,
                aluno_id=aluno.usuario_id,
                confirmacao=False,
                ponto_embarque_id=None,
                ponto_destino_id=None,
            )
            db.session.add(registro)

        if confirmacao:
            db.session.execute(select(User.id).where(User.id == aluno.usuario_id).with_for_update())
            inscrito_em_outra = (
                db.session.query(AlunosConfirmados)
                .join(Viagem)
                .filter(
                    AlunosConfirmados.aluno_id == aluno.usuario_id,
                    AlunosConfirmados.viagem_id != viagem.id,
                    AlunosConfirmados.confirmacao.is_(True),
                    Viagem.status == StatusViagem.EM_ANDAMENTO,
                )
                .first()
            )
            if inscrito_em_outra:
                raise ConflictError("Você já está em outra viagem em andamento")

            # schema already enforces ponto_embarque_id presence on confirmacao=True
            ponto_valido = (
                db.session.query(RotaPonto)
                .filter_by(rota_id=horario.rota_id, ponto_id=ponto_embarque_id)
                .first()
            )
            if not ponto_valido:
                raise NotFoundError("Ponto de embarque não encontrado na rota")

            ponto_destino_inferido = None
            if horario.sentido == SentidoViagem.IDA:
                if aluno.instituicao and aluno.instituicao.ponto_id:
                    ponto_destino_inferido = aluno.instituicao.ponto_id
            else:
                if aluno.ponto_casa_id:
                    ponto_destino_inferido = aluno.ponto_casa_id

            registro.confirmacao = True
            registro.ponto_embarque_id = ponto_embarque_id
            registro.ponto_destino_id = ponto_destino_inferido
        else:
            registro.confirmacao = False
            registro.ponto_embarque_id = None
            registro.ponto_destino_id = None

        return registro


def listar_pontos_embarque(user_id: str, viagem_id: str) -> list[dict]:
    """
    Retorna os pontos de embarque disponíveis para uma viagem específica.

    Raises: ForbiddenError, NotFoundError, AppError
    """
    aluno = db.session.get(User, user_id)
    if not aluno or aluno.role != UserRole.ALUNO:
        raise ForbiddenError("Acesso restrito a alunos")

    viagem = db.session.get(Viagem, viagem_id)
    if not viagem:
        raise NotFoundError("Viagem não encontrada")

    rota_id = _rota_id_da_viagem(viagem)
    if not rota_id:
        raise NotFoundError("Rota da viagem não encontrada")

    inscricao = db.session.query(RotaAluno).filter_by(rota_id=rota_id, aluno_id=aluno.id).first()

    if not inscricao:
        raise ForbiddenError("Você não está inscrito na rota desta viagem")

    pontos_query = (
        db.session.query(RotaPonto, Ponto)
        .join(Ponto, RotaPonto.ponto_id == Ponto.id)
        .filter(RotaPonto.rota_id == rota_id)
        .order_by(RotaPonto.ordem)
        .all()
    )

    resultado = []
    for rp, ponto_obj in pontos_query:
        resultado.append(
            {
                "ponto_id": str(ponto_obj.id),
                "apelido": ponto_obj.apelido,
                "latitude": float(ponto_obj.latitude),
                "longitude": float(ponto_obj.longitude),
                "ordem": rp.ordem,
            }
        )

    return resultado


def gerar_viagem(user_id: str, data_input: dict) -> Viagem:
    """
    Gera UMA viagem para UMA rota específica (Modo Manual).

    Raises: ForbiddenError, NotFoundError, ValidationError, ConflictError, AppError
    """
    user = db.session.get(User, user_id)
    if not user or user.role not in (UserRole.GESTOR, UserRole.MOTORISTA):
        raise ForbiddenError("Permissão negada")

    rota_id = data_input.get("rota_id")
    motorista_id = data_input.get("motorista_id")

    data_viagem = data_input.get("data")
    if not data_viagem:
        raise ValidationError("Data é obrigatória")

    rota = db.session.get(Rota, rota_id)
    if not rota:
        raise NotFoundError("Rota não encontrada")

    if rota.organizacao_id != user.organizacao_id:
        raise ForbiddenError("Acesso negado")

    if rota.tipo == TipoViagem.SOB_DEMANDA:
        raise ValidationError(
            "Viagens de rotas sob demanda são criadas pelas solicitações dos alunos, "
            "não manualmente."
        )

    dia_semana = _get_dia_semana_enum(data_viagem)

    horario_selecionado = (
        db.session.query(HorarioRota)
        .join(DiasOperacao)
        .filter(HorarioRota.rota_id == rota.id, DiasOperacao.dia == dia_semana)
        .first()
    )
    if not horario_selecionado:
        raise NotFoundError(f"Horário não encontrado para a rota {rota.nome} no dia {dia_semana}")

    existente = (
        db.session.query(Viagem.id)
        .filter_by(data=data_viagem, horario_rota_id=horario_selecionado.id)
        .first()
    )
    if existente:
        raise ConflictError(
            f"Viagem já gerada para este dia/horário: {data_viagem} {horario_selecionado.horario_saida.strftime('%H:%M')}"
        )

    with transactional():
        nova_viagem = Viagem(
            data=data_viagem,
            horario_rota_id=horario_selecionado.id,
            rota_id=rota.id,
            motorista_id=motorista_id,
            veiculo_id=rota.veiculo_padrao_id,
            status=StatusViagem.AGENDADA,
        )
        db.session.add(nova_viagem)
        db.session.flush()  # ensure nova_viagem.id

        _popular_dados_da_viagem(nova_viagem, rota)

        return nova_viagem


def calcular_fim_descanso(
    periodos: list[tuple[datetime, datetime | None]],
    agora: datetime,
    max_direcao: timedelta,
    descanso: timedelta,
) -> datetime | None:
    """Return when the driver may drive again, or None if they may drive now.

    `periodos` are (inicio, fim) of the driver's trips; fim=None means still driving.
    Trips separated by a gap of at least `descanso` count as a rest and reset the
    continuous driving time.
    """
    bloco_inicio: datetime | None = None
    ultimo_fim: datetime | None = None
    for inicio, fim in sorted(periodos, key=lambda p: p[0]):
        if fim is None:
            fim = agora
        if ultimo_fim is None or inicio - ultimo_fim >= descanso:
            bloco_inicio = inicio
            ultimo_fim = fim
        elif fim > ultimo_fim:
            ultimo_fim = fim

    if bloco_inicio is None or ultimo_fim is None:
        return None
    if agora - ultimo_fim >= descanso:
        return None
    if ultimo_fim - bloco_inicio < max_direcao:
        return None
    return ultimo_fim + descanso


def _agora() -> datetime:
    """Current time; a function so tests can patch it."""
    return tempo.agora_utc()


def _periodos_de_direcao(
    motorista_id: Any, agora: datetime
) -> list[tuple[datetime, datetime | None]]:
    """(inicio_real, fim_real) of the driver's trips started in the last 24 h."""
    # Uma sequência de direção contínua maior que 24 h já teria sido bloqueada antes.
    viagens = (
        db.session.query(Viagem.inicio_real, Viagem.fim_real)
        .filter(
            Viagem.motorista_id == motorista_id,
            Viagem.inicio_real.isnot(None),
            Viagem.inicio_real >= agora - timedelta(hours=24),
        )
        .all()
    )
    periodos: list[tuple[datetime, datetime | None]] = []
    for inicio_real, fim_real in viagens:
        periodos.append((inicio_real, fim_real))
    return periodos


def _fim_descanso_motorista(motorista: Motorista, agora: datetime) -> datetime | None:
    horas_max = current_app.config["MOTORISTA_HORAS_MAX_DIRECAO"]
    minutos_descanso = current_app.config["MOTORISTA_DESCANSO_MINUTOS"]
    return calcular_fim_descanso(
        _periodos_de_direcao(motorista.id, agora),
        agora,
        timedelta(hours=horas_max),
        timedelta(minutes=minutos_descanso),
    )


def motoristas_em_viagem(motorista_ids: list[Any]) -> set[Any]:
    """Ids, among `motorista_ids`, of drivers with a trip EM_ANDAMENTO (one query)."""
    if not motorista_ids:
        return set()
    linhas = (
        db.session.query(Viagem.motorista_id)
        .filter(
            Viagem.motorista_id.in_(motorista_ids),
            Viagem.status == StatusViagem.EM_ANDAMENTO,
        )
        .distinct()
        .all()
    )
    ids: set[Any] = set()
    for (motorista_id,) in linhas:
        ids.add(motorista_id)
    return ids


def status_motorista(
    motorista: Motorista, agora: datetime, em_viagem: bool | None = None
) -> StatusMotorista:
    """Driver state, computed from trips and `descanso_ate` (never stored).

    Pass `em_viagem` (from `motoristas_em_viagem`) to skip the EXISTS query in lists.
    """
    if em_viagem is None:
        em_viagem = db.session.query(
            exists().where(
                Viagem.motorista_id == motorista.id,
                Viagem.status == StatusViagem.EM_ANDAMENTO,
            )
        ).scalar()
    if em_viagem:
        return StatusMotorista.EM_ROTA
    if motorista.descanso_ate is not None and motorista.descanso_ate > agora:
        return StatusMotorista.EM_DESCANSO_OBRIGATORIO
    return StatusMotorista.ATIVO


def disponibilidade_motorista(
    motorista: Motorista, agora: datetime
) -> tuple[bool, str | None, datetime | None]:
    """Whether the driver can start a trip at `agora`, without raising.

    Returns (pode_trabalhar, motivo, livre_a_partir_de). `livre_a_partir_de` is only
    known for a mandatory rest; it is None otherwise.
    """
    fuso = ZoneInfo(current_app.config["TIMEZONE"])
    agora_local = agora.astimezone(fuso)

    status = status_motorista(motorista, agora)
    if status == StatusMotorista.EM_ROTA:
        return False, "Motorista já está em rota", None

    liberado_em = None
    if status == StatusMotorista.EM_DESCANSO_OBRIGATORIO:
        liberado_em = motorista.descanso_ate
    else:
        # Recalcula pelo histórico também: cobre viagens anteriores a `descanso_ate` existir.
        liberado_em = _fim_descanso_motorista(motorista, agora)
    if liberado_em is not None:
        horas_max = current_app.config["MOTORISTA_HORAS_MAX_DIRECAO"]
        minutos_descanso = current_app.config["MOTORISTA_DESCANSO_MINUTOS"]
        horario = liberado_em.astimezone(fuso).strftime("%H:%M")
        motivo = (
            f"Motorista atingiu {horas_max}h de direção contínua e precisa descansar "
            f"{minutos_descanso} min. Poderá dirigir novamente às {horario}."
        )
        return False, motivo, liberado_em

    if motorista.dias_trabalho:
        dia = _get_dia_semana_enum(agora_local.date())
        if dia.value not in motorista.dias_trabalho:
            dias = ", ".join(motorista.dias_trabalho)
            return False, f"Hoje não é dia de trabalho do motorista (dias: {dias})", None

    inicio = motorista.horario_inicio
    fim = motorista.horario_fim
    if inicio is not None and fim is not None:
        hora = agora_local.time()
        if inicio < fim:
            dentro = inicio <= hora < fim
        else:
            # Turno que atravessa a meia-noite, ex.: 22:00-06:00
            dentro = hora >= inicio or hora < fim
        if not dentro:
            motivo = (
                "Fora do horário de trabalho do motorista "
                f"({inicio.strftime('%H:%M')} às {fim.strftime('%H:%M')})"
            )
            return False, motivo, None

    return True, None, None


def _validar_jornada_motorista(motorista: Motorista, agora: datetime) -> None:
    """Block starting a trip while on another trip, during rest or outside working hours."""
    pode, motivo, _ = disponibilidade_motorista(motorista, agora)
    if pode:
        return
    if status_motorista(motorista, agora) == StatusMotorista.EM_ROTA:
        raise ConflictError("Motorista já está em rota em outra viagem")
    raise ForbiddenError(motivo or "Motorista indisponível")


def _gravar_descanso_apos_viagem(motorista: Motorista, agora: datetime) -> None:
    """After a started trip ends (finished or cancelled): store the rest end, if owed."""
    motorista.descanso_ate = _fim_descanso_motorista(motorista, agora)


def list_viagens_motorista(user_id: str) -> list[Viagem]:
    """List trips assigned to the driver."""
    return (
        db.session.query(Viagem).filter_by(motorista_id=user_id).order_by(Viagem.data.desc()).all()
    )


def controlar_viagem(user_id: str, viagem_id: str, data: dict[str, Any]) -> Viagem:
    """Start or finish a trip. Expects schema-validated payload with 'acao'."""
    user = db.session.get(User, user_id)
    viagem = db.session.get(Viagem, viagem_id)

    if not user:
        raise NotFoundError("Usuário não encontrado")

    if not viagem:
        raise NotFoundError("Viagem não encontrada")

    if user.role == UserRole.MOTORISTA and viagem.motorista_id != user.id:
        raise ForbiddenError("Esta viagem não pertence a você")

    acao = data.get("acao")

    with transactional():
        if acao == "INICIAR":
            # Trava viagem e motorista até o commit: dois INICIAR ao mesmo tempo
            # esperam um pelo outro e o segundo vê o estado já atualizado.
            viagem = (
                db.session.query(Viagem)
                .filter(Viagem.id == viagem.id)
                .with_for_update(of=Viagem)
                .populate_existing()
                .one()
            )
            if viagem.status != StatusViagem.AGENDADA:
                raise ValidationError(
                    f"Não é possível iniciar viagem com status {viagem.status.name}"
                )
            agora = _agora()
            if viagem.motorista_id is not None:
                motorista = (
                    db.session.query(Motorista)
                    .filter(Motorista.id == viagem.motorista_id)
                    .with_for_update(of=Motorista)
                    .populate_existing()
                    .one()
                )
                _validar_jornada_motorista(motorista, agora)
                motorista.descanso_ate = None
            viagem.status = StatusViagem.EM_ANDAMENTO
            viagem.inicio_real = agora

            NotificacaoService.notificar_alunos_viagem_iniciada(viagem_id=viagem_id)

        elif acao == "FINALIZAR":
            if viagem.status != StatusViagem.EM_ANDAMENTO:
                raise ValidationError("A viagem precisa estar em andamento para ser finalizada")
            viagem.status = StatusViagem.FINALIZADA
            viagem.fim_real = _agora()
            db.session.flush()
            if viagem.motorista is not None:
                _gravar_descanso_apos_viagem(viagem.motorista, viagem.fim_real)

            rastros = (
                TelemetriaViagem.query.filter_by(viagem_id=viagem.id)
                .order_by(TelemetriaViagem.timestamp.asc())
                .all()
            )

            km_total = 0.0
            if len(rastros) > 1:
                distancia_metros = 0.0
                for i in range(len(rastros) - 1):
                    p1 = rastros[i]
                    p2 = rastros[i + 1]
                    distancia_metros += calcular_distancia_metros(
                        float(p1.latitude),
                        float(p1.longitude),
                        float(p2.latitude),
                        float(p2.longitude),
                    )
                km_total = round(distancia_metros / 1000.0, 2)

            viagem.km_real = km_total
        else:
            raise ValidationError("Ação inválida. Use INICIAR ou FINALIZAR")

        return viagem


def list_viagens_gestor(user_id: str, filters: dict[str, Any]) -> list[Viagem]:
    user = db.session.get(User, user_id)
    if not user or user.role != UserRole.GESTOR:
        raise ForbiddenError("Apenas gestores podem acessar o histórico completo")

    query = juntar_rota(db.session.query(Viagem)).filter(Rota.organizacao_id == user.organizacao_id)

    if filters.get("data_inicio"):
        query = query.filter(Viagem.data >= filters.get("data_inicio"))

    if filters.get("data_fim"):
        query = query.filter(Viagem.data <= filters.get("data_fim"))

    if filters.get("status"):
        query = query.filter(Viagem.status == filters.get("status"))

    if filters.get("motorista_id"):
        query = query.filter(Viagem.motorista_id == filters.get("motorista_id"))

    if filters.get("rota_id"):
        query = query.filter(Rota.id == filters.get("rota_id"))

    return query.order_by(Viagem.data.desc(), Viagem.horario_rota_id).all()


def cancelar_viagem(user_id: str, viagem_id: str) -> dict[str, Any]:
    """Cancela uma viagem e notifica alunos confirmados"""
    user = db.session.get(User, user_id)
    if not user or user.role != UserRole.GESTOR:
        raise ForbiddenError("Apenas gestores podem cancelar viagens")

    viagem = db.session.get(Viagem, viagem_id)
    if not viagem:
        raise NotFoundError("Viagem não encontrada")

    rota = db.session.get(Rota, _rota_id_da_viagem(viagem))
    if not rota or rota.organizacao_id != user.organizacao_id:
        raise ForbiddenError("Acesso negado")

    if viagem.status in (StatusViagem.FINALIZADA, StatusViagem.CANCELADA):
        raise ValidationError(f"Não é possível cancelar uma viagem com status {viagem.status.name}")

    try:
        viagem.status = StatusViagem.CANCELADA
        # A started trip counts toward the driver's driving time, so it needs an end too.
        if viagem.inicio_real and not viagem.fim_real:
            viagem.fim_real = _agora()
            db.session.flush()
            if viagem.motorista is not None:
                _gravar_descanso_apos_viagem(viagem.motorista, viagem.fim_real)

        confirmados = AlunosConfirmados.query.filter_by(viagem_id=viagem.id, confirmacao=True).all()
        data_formatada = viagem.data.strftime("%d/%m/%Y")

        for conf in confirmados:
            NotificacaoService._criar_notificacao_interna(
                usuario_id=conf.aluno_id,
                titulo="Viagem Cancelada",
                mensagem=f"Atenção! A viagem da rota agendada para o dia {data_formatada} foi cancelada pela organização.",
            )

        solicitacoes = SolicitacaoViagem.query.filter_by(
            viagem_id=viagem.id, status=StatusSolicitacao.ATIVA
        ).all()
        for solicitacao in solicitacoes:
            solicitacao.status = StatusSolicitacao.CANCELADA
            solicitacao.cancelada_em = tempo.agora_utc()
            NotificacaoService._criar_notificacao_interna(
                usuario_id=solicitacao.aluno_id,
                titulo="Viagem Cancelada",
                mensagem="Atenção! A viagem sob demanda que você solicitou foi cancelada pela organização. Faça uma nova solicitação se ainda precisar.",
            )

        db.session.commit()

        audit_logger.log_user_action(
            action="cancelar_viagem", user_id=user_id, resource_type="viagem", resource_id=viagem_id
        )

        return {
            "message": "Viagem cancelada com sucesso",
            "alunos_notificados": len(confirmados) + len(solicitacoes),
        }
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao cancelar viagem: {e}")
        raise AppError(f"Erro ao cancelar viagem: {str(e)}", 500)


def atualizar_localizacao(user_id: str, viagem_id: str, data: dict) -> dict:
    """Atualiza o GPS do motorista, salva telemetria e engatilha o Auto-Checkin."""
    user = db.session.get(User, user_id)
    if not user or user.role != UserRole.MOTORISTA:
        raise ForbiddenError("Apenas motoristas podem enviar localização em tempo real")

    viagem = db.session.get(Viagem, viagem_id)
    if not viagem:
        raise NotFoundError("Viagem não encontrada")

    if viagem.status != StatusViagem.EM_ANDAMENTO:
        raise ValidationError(f"A viagem não está em andamento (Status: {viagem.status.name})")

    agora = datetime.now(UTC)

    viagem.motorista_lat = data["latitude"]
    viagem.motorista_lon = data["longitude"]
    viagem.motorista_gps_hora = agora

    rastro = TelemetriaViagem(
        viagem_id=viagem.id, latitude=data["latitude"], longitude=data["longitude"], timestamp=agora
    )
    db.session.add(rastro)
    db.session.commit()

    proximos_pontos = (
        ViagemPonto.query.filter_by(viagem_id=viagem.id, visitado=False)
        .order_by(ViagemPonto.ordem)
        .all()
    )

    if not proximos_pontos:
        return {"message": "Todos os pontos já foram visitados. Viagem quase concluída!"}

    proximo_ponto = proximos_pontos[0]
    ponto_geo = proximo_ponto.ponto

    distancia_metros = calcular_distancia_metros(
        float(data["latitude"]),
        float(data["longitude"]),
        float(ponto_geo.latitude),
        float(ponto_geo.longitude),
    )

    DISTANCIA_GATILHO = 1000

    if distancia_metros <= DISTANCIA_GATILHO and not proximo_ponto.aviso_aproximacao_enviado:
        alunos_neste_ponto = AlunosConfirmados.query.filter_by(
            viagem_id=viagem.id, confirmacao=True, ponto_embarque_id=ponto_geo.id, embarcou=False
        ).all()

        data_execucao = agora + timedelta(minutes=5)

        for conf in alunos_neste_ponto:
            NotificacaoService._criar_notificacao_interna(
                usuario_id=conf.aluno_id,
                titulo="🚌 O Ônibus está chegando!",
                mensagem=f"O motorista está a aproximadamente {int(distancia_metros)}m do seu ponto de embarque ({ponto_geo.apelido}). Prepare-se!",
            )

            job_id = f"checkin_{viagem.id}_{conf.aluno_id}"

            if not scheduler.get_job(job_id):

                scheduler.add_job(
                    id=job_id,
                    func=realizar_auto_checkin,
                    args=[str(viagem.id), str(conf.aluno_id), 1],
                    trigger="date",
                    run_date=data_execucao,
                )

        proximo_ponto.aviso_aproximacao_enviado = True
        db.session.commit()
        return {
            "message": "Localização salva. Ponto próximo alcançado, notificações e auto-checkin engatilhados!",
            "distancia_metros": int(distancia_metros),
        }

    return {
        "message": "Localização atualizada silenciosamente com telemetria.",
        "distancia_metros": int(distancia_metros),
    }


def obter_localizacao_onibus(user_id: str, viagem_id: str) -> dict:
    """
    Retorna a localização atual do ônibus (GPS do motorista) para uma viagem em andamento.
    Aluno (confirmado na viagem) ou motorista da viagem podem consultar.
    """
    user = db.session.get(User, user_id)
    if not user:
        raise ForbiddenError("Acesso negado")

    viagem = db.session.get(Viagem, viagem_id)
    if not viagem:
        raise NotFoundError("Viagem não encontrada")

    if viagem.status != StatusViagem.EM_ANDAMENTO:
        raise ValidationError(
            "A localização do ônibus só está disponível enquanto a viagem está em andamento."
        )

    if user.role == UserRole.MOTORISTA:
        if viagem.motorista_id != user.id:
            raise ForbiddenError("Apenas o motorista desta viagem pode consultar a localização.")
    elif user.role == UserRole.ALUNO:
        conf = AlunosConfirmados.query.filter_by(viagem_id=viagem.id, aluno_id=user_id).first()
        if not conf or not conf.confirmacao:
            raise ForbiddenError(
                "Você precisa estar confirmado nesta viagem para ver a localização do ônibus."
            )
    else:
        raise ForbiddenError(
            "Apenas alunos confirmados ou o motorista podem consultar a localização do ônibus."
        )

    return {
        "latitude": float(viagem.motorista_lat) if viagem.motorista_lat is not None else None,
        "longitude": float(viagem.motorista_lon) if viagem.motorista_lon is not None else None,
        "atualizado_em": (
            viagem.motorista_gps_hora.isoformat() if viagem.motorista_gps_hora else None
        ),
    }


def atualizar_localizacao_aluno(user_id: str, viagem_id: str, data: dict) -> dict:
    """Updates the student's current GPS coordinates for auto-checkin."""
    user = db.session.get(User, user_id)
    if not user or user.role != UserRole.ALUNO:
        raise ForbiddenError("Apenas alunos podem enviar a localização de embarque.")

    viagem = db.session.get(Viagem, viagem_id)
    if not viagem:
        raise NotFoundError("Viagem não encontrada.")

    if viagem.status != StatusViagem.EM_ANDAMENTO:
        raise ValidationError("A viagem precisa de estar em andamento para rastrear o embarque.")

    conf = AlunosConfirmados.query.filter_by(viagem_id=viagem.id, aluno_id=user_id).first()
    if not conf or not conf.confirmacao:
        raise ForbiddenError("O utilizador não está confirmado nesta viagem.")

    if conf.embarcou:
        return {
            "message": "Embarque já realizado. O rastreio em tempo real pode ser desligado.",
            "embarcou": True,
        }

    agora = datetime.now(UTC)

    conf.aluno_lat = data["latitude"]
    conf.aluno_lon = data["longitude"]
    conf.aluno_gps_hora = agora

    db.session.commit()

    return {
        "message": "Localização do aluno atualizada com sucesso para validação de check-in.",
        "embarcou": False,
    }


def obter_progresso_viagem(gestor_id: str, viagem_id: str):
    """Retorna os pontos pelos quais o motorista já passou, em ordem cronológica."""
    user = db.session.get(User, gestor_id)
    if not user or user.role != UserRole.GESTOR:
        raise ForbiddenError("Apenas gestores podem auditar o trajeto")

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
            "horario_passagem": str(vp.chegada_real),
        }
        for vp in pontos_visitados
    ]


# Estados em que a rodada sob demanda ocupa o veículo. Sem viagem nesses estados = Ociosa.
ESTADOS_ATIVOS_SOB_DEMANDA = (
    StatusViagem.SOLICITADA,
    StatusViagem.BUFFER_ABERTO,
    StatusViagem.EM_ANDAMENTO,
)


def buscar_viagem_ativa_do_veiculo(onibus_id) -> Viagem | None:
    return (
        db.session.query(Viagem)
        .filter(
            Viagem.veiculo_id == onibus_id,
            Viagem.status.in_(ESTADOS_ATIVOS_SOB_DEMANDA),
        )
        .order_by(Viagem.created_at.desc())
        .first()
    )
