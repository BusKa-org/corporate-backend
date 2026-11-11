"""On-demand trip request (RF-10) and cancellation (RF-19)."""

import uuid

from sqlalchemy import select

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.core.transaction import transactional
from app.models.base import db
from app.models.enum import StatusSolicitacao, StatusViagem, TipoViagem, UserRole, UserStatus
from app.models.onibus import Onibus
from app.models.rota import Rota
from app.models.user import Aluno, User
from app.models.viagem import AlunosConfirmados, SolicitacaoViagem, Viagem
from app.services import capacidade_service, janelas_service, viagens_service
from app.services.notificacao_service import NotificacaoService
from app.utils import tempo
from app.utils.validators import validate_uuid

EM_VIAGEM = "A conta está em uma viagem em andamento. Aguarde o fim da viagem."


def _buscar_aluno(user_id: str) -> Aluno:
    aluno = db.session.get(Aluno, user_id)
    if not aluno:
        raise ForbiddenError("Apenas alunos podem solicitar viagens")
    return aluno


# shortcut: once PR #16 merges, check disponibilidade_motorista(motorista, agora) here and refuse
# (with livre_a_partir_de in the message) so a request never goes to a resting or off-hours driver.
def _escolher_motorista(janela):
    """The window's driver, or None if the account is not ACTIVE. Locks the driver row."""
    # Locked so a concurrent deactivation either sees this trip or runs before the re-read.
    db.session.execute(
        select(User.id).where(User.id == janela.motorista_id).with_for_update(key_share=True)
    )
    motorista = db.session.get(User, janela.motorista_id, populate_existing=True)
    if motorista is None or motorista.status != UserStatus.ACTIVE:
        return None
    return janela.motorista_id


def _mensagem_fora_da_janela(onibus_id, agora_local) -> str:
    dia = viagens_service._get_dia_semana_enum(agora_local.date())
    janelas = janelas_service.listar_janelas_do_dia(onibus_id, dia)
    if not janelas:
        return "Fora da janela de disponibilidade. Não há operação hoje."

    horarios = []
    for j in janelas:
        horarios.append(f"{j.hora_inicio.strftime('%H:%M')}–{j.hora_fim.strftime('%H:%M')}")
    return f"Fora da janela de disponibilidade. Horários de hoje: {', '.join(horarios)}."


def solicitar_viagem(user_id: str, rota_id: str) -> SolicitacaoViagem:
    """Register the student as interested in the on-demand route's round.

    Raises: ForbiddenError, NotFoundError, ValidationError, ConflictError
    """
    aluno = _buscar_aluno(user_id)

    rota = db.session.get(Rota, validate_uuid(rota_id, "ID da rota"))
    if not rota:
        raise NotFoundError("Rota não encontrada")

    if rota.organizacao_id != aluno.organizacao_id:
        raise ForbiddenError("Acesso negado")

    if rota.tipo == TipoViagem.FIXA:
        raise ValidationError("Rota de horário fixo, use a confirmação de presença")

    if rota.veiculo_padrao_id is None:
        raise ValidationError("Rota sem veículo padrão definido, não é possível solicitar viagem")

    veiculo_id = rota.veiculo_padrao_id

    with transactional():
        # Serializes the first concurrent requests: only one creates the trip.
        db.session.execute(
            select(Onibus.id).where(Onibus.id == veiculo_id).with_for_update(key_share=True)
        )
        # And those of the same student on routes of different vehicles: only one stays active.
        db.session.execute(
            select(User.id).where(User.id == aluno.usuario_id).with_for_update(key_share=True)
        )
        capacidade_service.exigir_conta_ativa(aluno.usuario_id)

        agora_local = tempo.agora_local()
        janela = janelas_service.buscar_janela_ativa(veiculo_id, agora_local)
        if janela is None:
            raise ValidationError(_mensagem_fora_da_janela(veiculo_id, agora_local))

        solicitacao_ativa = (
            db.session.query(SolicitacaoViagem)
            .join(Viagem)
            .filter(
                SolicitacaoViagem.aluno_id == aluno.usuario_id,
                SolicitacaoViagem.status == StatusSolicitacao.ATIVA,
                Viagem.status.in_(viagens_service.ESTADOS_ATIVOS_SOB_DEMANDA),
            )
            .first()
        )
        if solicitacao_ativa:
            raise ConflictError("Você já possui uma solicitação de viagem ativa")

        em_outra_viagem = (
            db.session.query(AlunosConfirmados)
            .join(Viagem)
            .filter(
                AlunosConfirmados.aluno_id == aluno.usuario_id,
                AlunosConfirmados.confirmacao.is_(True),
                Viagem.status == StatusViagem.EM_ANDAMENTO,
            )
            .first()
        )
        if em_outra_viagem:
            raise ConflictError("Você já está em outra viagem em andamento")

        viagem = viagens_service.buscar_viagem_ativa_do_veiculo(veiculo_id)
        if viagem is not None:
            if viagem.status == StatusViagem.EM_ANDAMENTO:
                raise ConflictError("O veículo já está em rota, aguarde a próxima rodada")
            if viagem.rota_id != rota.id:
                raise ConflictError("O veículo está atendendo outra rota no momento")
        else:
            motorista_id = _escolher_motorista(janela)
            if motorista_id is None:
                raise ValidationError("Nenhum motorista ativo nesta janela de disponibilidade")
            viagem = Viagem(
                rota_id=rota.id,
                horario_rota_id=None,
                data=agora_local.date(),
                veiculo_id=veiculo_id,
                motorista_id=motorista_id,
                status=StatusViagem.SOLICITADA,
            )
            db.session.add(viagem)
            db.session.flush()

            NotificacaoService._criar_notificacao_interna(
                usuario_id=motorista_id,
                titulo="Nova solicitação de viagem",
                mensagem=f"Um passageiro solicitou a rota {rota.nome}. Inicie o percurso quando estiver pronto.",
            )

        solicitacao = SolicitacaoViagem(
            viagem_id=viagem.id,
            aluno_id=aluno.usuario_id,
            status=StatusSolicitacao.ATIVA,
        )
        db.session.add(solicitacao)
        db.session.flush()

        return solicitacao


def cancelar_solicitacao(user_id: str, viagem_id: str) -> SolicitacaoViagem:
    """Cancel the student's active request on the trip. After the start it becomes a dropout.

    Raises: ForbiddenError, NotFoundError, ValidationError
    """
    aluno = _buscar_aluno(user_id)

    viagem = db.session.get(Viagem, validate_uuid(viagem_id, "ID da viagem"))
    if not viagem:
        raise NotFoundError("Viagem não encontrada")

    with transactional():
        viagem = travar_viagem(viagem)
        return cancelar_na_viagem_travada(aluno, viagem)


def travar_viagem(viagem: Viagem) -> Viagem:
    """Lock vehicle and trip and return the re-read trip.

    Same lock order as the request (vehicle, then trip): joining the round, starting
    the route and closing the buffer all wait for the cancellation.
    """
    if viagem.veiculo_id:
        db.session.execute(
            select(Onibus.id).where(Onibus.id == viagem.veiculo_id).with_for_update(key_share=True)
        )
    return (
        db.session.query(Viagem)
        .filter(Viagem.id == viagem.id)
        .with_for_update(key_share=True)
        .populate_existing()
        .one()
    )


def solicitacoes_ativas_do_aluno(aluno_id) -> list[SolicitacaoViagem]:
    return (
        db.session.query(SolicitacaoViagem)
        .join(Viagem, Viagem.id == SolicitacaoViagem.viagem_id)
        .filter(
            SolicitacaoViagem.aluno_id == aluno_id,
            SolicitacaoViagem.status == StatusSolicitacao.ATIVA,
            Viagem.status.in_(viagens_service.ESTADOS_ATIVOS_SOB_DEMANDA),
        )
        .populate_existing()
        .all()
    )


def _confirmacoes_futuras_do_aluno(aluno_id) -> list[AlunosConfirmados]:
    """Fixed-route attendance confirmed on trips that have not started yet."""
    return (
        db.session.query(AlunosConfirmados)
        .join(Viagem, Viagem.id == AlunosConfirmados.viagem_id)
        .filter(
            AlunosConfirmados.aluno_id == aluno_id,
            AlunosConfirmados.confirmacao.is_(True),
            Viagem.status == StatusViagem.AGENDADA,
            Viagem.data >= tempo.agora_local().date(),
        )
        .populate_existing()
        .all()
    )


def aluno_em_viagem_em_andamento(aluno_id) -> bool:
    registro = (
        db.session.query(AlunosConfirmados)
        .join(Viagem, Viagem.id == AlunosConfirmados.viagem_id)
        .filter(
            AlunosConfirmados.aluno_id == aluno_id,
            AlunosConfirmados.confirmacao.is_(True),
            Viagem.status == StatusViagem.EM_ANDAMENTO,
        )
        .first()
    )
    return registro is not None


def travar_viagens_do_aluno(aluno_id) -> dict[uuid.UUID, Viagem]:
    """Lock the trips of the student's requests and confirmations. Call before locking the
    student: same order as the rest of the system (vehicle, trip, then student).
    """
    viagem_ids: list[uuid.UUID] = []
    for solicitacao in solicitacoes_ativas_do_aluno(aluno_id):
        viagem_ids.append(solicitacao.viagem_id)
    for confirmacao in _confirmacoes_futuras_do_aluno(aluno_id):
        if confirmacao.viagem_id not in viagem_ids:
            viagem_ids.append(confirmacao.viagem_id)

    veiculo_ids: list[uuid.UUID] = []
    for viagem in db.session.query(Viagem).filter(Viagem.id.in_(viagem_ids)).all():
        if viagem.veiculo_id and viagem.veiculo_id not in veiculo_ids:
            veiculo_ids.append(viagem.veiculo_id)
    # Every vehicle first, then every trip, each in id order: locking trip by trip (vehicle,
    # trip, vehicle, trip...) could take two vehicles in opposite orders and deadlock.
    db.session.execute(
        select(Onibus.id)
        .where(Onibus.id.in_(veiculo_ids))
        .order_by(Onibus.id)
        .with_for_update(key_share=True)
    )
    viagens = (
        db.session.query(Viagem)
        .filter(Viagem.id.in_(viagem_ids))
        .order_by(Viagem.id)
        .with_for_update(key_share=True)
        .populate_existing()
        .all()
    )

    viagens_travadas: dict[uuid.UUID, Viagem] = {}
    for viagem in viagens:
        viagens_travadas[viagem.id] = viagem
    return viagens_travadas


def liberar_aluno(
    aluno: Aluno,
    viagens_travadas: dict[uuid.UUID, Viagem],
    msg_em_viagem: str = EM_VIAGEM,
    retirar_confirmacoes: bool = True,
) -> None:
    """Cancel the student's requests (RF-19) and withdraw future confirmations, without commit.

    `viagens_travadas` comes from `travar_viagens_do_aluno`, and the student row must be
    locked since then, so no new request or confirmation can appear.
    """
    if aluno_em_viagem_em_andamento(aluno.usuario_id):
        raise ConflictError(msg_em_viagem)

    solicitacoes = solicitacoes_ativas_do_aluno(aluno.usuario_id)
    confirmacoes = _confirmacoes_futuras_do_aluno(aluno.usuario_id)
    viagem_ids: list[uuid.UUID] = []
    for solicitacao in solicitacoes:
        viagem_ids.append(solicitacao.viagem_id)
    for confirmacao in confirmacoes:
        viagem_ids.append(confirmacao.viagem_id)
    for viagem_id in viagem_ids:
        travada = viagens_travadas.get(viagem_id)
        if travada is None:
            # Joined a trip between the read and the lock: locking it now would invert the order.
            raise ConflictError("As viagens da conta mudaram. Tente novamente.")
        if travada.status == StatusViagem.EM_ANDAMENTO:
            raise ConflictError(msg_em_viagem)

    for solicitacao in solicitacoes:
        cancelar_na_viagem_travada(aluno, viagens_travadas[solicitacao.viagem_id])
    if not retirar_confirmacoes:
        return
    # Same effect as the student cancelling the confirmation.
    for confirmacao in confirmacoes:
        confirmacao.confirmacao = False
        confirmacao.ponto_embarque_id = None
        confirmacao.ponto_destino_id = None


def cancelar_na_viagem_travada(aluno: Aluno, viagem: Viagem) -> SolicitacaoViagem:
    """Cancellation rules (RF-19), without commit. The trip must be locked (`travar_viagem`)."""
    solicitacao = (
        db.session.query(SolicitacaoViagem)
        .filter_by(
            viagem_id=viagem.id,
            aluno_id=aluno.usuario_id,
            status=StatusSolicitacao.ATIVA,
        )
        .populate_existing()
        .first()
    )
    if not solicitacao:
        raise NotFoundError("Solicitação ativa não encontrada para esta viagem")

    if viagem.status in (StatusViagem.FINALIZADA, StatusViagem.CANCELADA):
        raise ValidationError(
            f"Não é possível cancelar a solicitação de uma viagem com status {viagem.status.name}"
        )

    solicitacao.cancelada_em = tempo.agora_utc()

    if viagem.status == StatusViagem.EM_ANDAMENTO:
        # The seat is not reopened: the vehicle already left counting on the passenger.
        solicitacao.status = StatusSolicitacao.DESISTENCIA
        # Leaves the driver's boarding list (RF-16/RF-17).
        passageiro = db.session.get(AlunosConfirmados, (viagem.id, aluno.usuario_id))
        if passageiro:
            passageiro.confirmacao = False
        if viagem.motorista_id:
            NotificacaoService._criar_notificacao_interna(
                usuario_id=viagem.motorista_id,
                titulo="Desistência de passageiro",
                mensagem=f"O passageiro {aluno.nome} desistiu da viagem em andamento.",
            )
        return solicitacao

    if viagem.status not in (StatusViagem.SOLICITADA, StatusViagem.BUFFER_ABERTO):
        raise ValidationError(
            f"Não é possível cancelar a solicitação de uma viagem com status {viagem.status.name}"
        )

    # The load vector only counts ATIVA requests: cancelling already gives the leg back (RF-14).
    solicitacao.status = StatusSolicitacao.CANCELADA
    db.session.flush()

    if viagem.status == StatusViagem.SOLICITADA:
        restantes = (
            db.session.query(SolicitacaoViagem.id)
            .filter_by(viagem_id=viagem.id, status=StatusSolicitacao.ATIVA)
            .count()
        )
        if restantes == 0:
            viagem.status = StatusViagem.CANCELADA
            if viagem.motorista_id:
                NotificacaoService._criar_notificacao_interna(
                    usuario_id=viagem.motorista_id,
                    titulo="Solicitação de viagem cancelada",
                    mensagem="Todos os passageiros cancelaram a solicitação. A viagem foi cancelada.",
                )

    return solicitacao


def declarar_trajeto(user_id: str, viagem_id: str, data: dict) -> SolicitacaoViagem:
    """RF-13: the student declares origin and destination in the buffer; capacity decides (RF-14).

    Whoever got the buffer notice without having requested joins the trip right here.
    Raises: ForbiddenError, NotFoundError, ValidationError, ConflictError
    """
    aluno = _buscar_aluno(user_id)

    viagem = db.session.get(Viagem, validate_uuid(viagem_id, "ID da viagem"))
    if not viagem:
        raise NotFoundError("Viagem não encontrada")

    ja_solicitou = (
        db.session.query(SolicitacaoViagem.id)
        .filter_by(viagem_id=viagem.id, aluno_id=aluno.usuario_id, status=StatusSolicitacao.ATIVA)
        .first()
    )
    if not ja_solicitou and viagem.status == StatusViagem.BUFFER_ABERTO and viagem.rota_id:
        solicitar_viagem(user_id, str(viagem.rota_id))

    try:
        return capacidade_service.validar_e_reservar(
            viagem.id, aluno.usuario_id, data["ponto_origem_id"], data["ponto_destino_id"]
        )
    except ConflictError as e:
        raise ConflictError(f"{e.message}. Tente novamente na próxima rodada.") from e


def buscar_rodada_ativa(user_id: str, rota_id: str) -> dict:
    """Active round of the on-demand route, for users who missed the push (RF-12, secondary flow).

    Without a round, returns viagem None and today's windows.
    Raises: ForbiddenError, NotFoundError, ValidationError
    """
    user = db.session.get(User, user_id)
    if not user or user.role not in (UserRole.ALUNO, UserRole.GESTOR, UserRole.MOTORISTA):
        raise ForbiddenError("Acesso negado")

    rota = db.session.get(Rota, validate_uuid(rota_id, "ID da rota"))
    if not rota:
        raise NotFoundError("Rota não encontrada")

    if rota.organizacao_id != user.organizacao_id:
        raise ForbiddenError("Acesso negado")

    if rota.tipo == TipoViagem.FIXA:
        raise ValidationError("Rota de horário fixo não tem rodada sob demanda")

    resultado: dict = {"viagem": None, "minha_solicitacao": None, "janelas_hoje": []}
    if rota.veiculo_padrao_id is None:
        return resultado

    agora_local = tempo.agora_local()
    dia = viagens_service._get_dia_semana_enum(agora_local.date())
    resultado["janelas_hoje"] = janelas_service.listar_janelas_do_dia(rota.veiculo_padrao_id, dia)

    viagem = viagens_service.buscar_viagem_ativa_do_veiculo(rota.veiculo_padrao_id)
    # Vehicle busy with another route: this route has no round.
    if viagem is None or viagem.rota_id != rota.id:
        return resultado

    segundos_restantes = None
    if viagem.status == StatusViagem.BUFFER_ABERTO and viagem.buffer_fim:
        segundos_restantes = int((viagem.buffer_fim - tempo.agora_utc()).total_seconds())
        if segundos_restantes < 0:
            segundos_restantes = 0

    resultado["viagem"] = {
        "id": viagem.id,
        "status": viagem.status.value,
        "rota_id": viagem.rota_id,
        "created_at": viagem.created_at,
        "inicio_real": viagem.inicio_real,
        "buffer_fim": viagem.buffer_fim,
        "segundos_restantes_buffer": segundos_restantes,
        "motorista": viagem.motorista,
        "veiculo": viagem.veiculo,
    }

    if user.role == UserRole.ALUNO:
        resultado["minha_solicitacao"] = (
            db.session.query(SolicitacaoViagem)
            .filter_by(viagem_id=viagem.id, aluno_id=user.id, status=StatusSolicitacao.ATIVA)
            .first()
        )

    return resultado
