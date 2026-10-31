"""Solicitação de viagem sob demanda (RF-10) e cancelamento (RF-19)."""

from sqlalchemy import select

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.core.transaction import transactional
from app.models.base import db
from app.models.enum import StatusSolicitacao, StatusViagem, TipoViagem, UserRole
from app.models.onibus import Onibus
from app.models.rota import Rota
from app.models.user import Aluno, User
from app.models.viagem import AlunosConfirmados, SolicitacaoViagem, Viagem
from app.services import capacidade_service, janelas_service, viagens_service
from app.services.notificacao_service import NotificacaoService
from app.utils import tempo
from app.utils.validators import validate_uuid


def _buscar_aluno(user_id: str) -> Aluno:
    aluno = db.session.get(Aluno, user_id)
    if not aluno:
        raise ForbiddenError("Apenas alunos podem solicitar viagens")
    return aluno


# shortcut: once PR #16 merges, check disponibilidade_motorista(motorista, agora) here and refuse
# (with livre_a_partir_de in the message) so a request never goes to a resting or off-hours driver.
def _escolher_motorista(janela):
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
    """
    Registra o aluno como interessado na rodada da rota sob demanda.

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
        # Serializa as primeiras solicitações concorrentes: só uma cria a viagem.
        db.session.execute(select(Onibus.id).where(Onibus.id == veiculo_id).with_for_update())
        # E as do mesmo aluno em rotas de veículos diferentes: só uma fica ativa.
        db.session.execute(
            select(User.id).where(User.id == aluno.usuario_id).with_for_update(key_share=True)
        )

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
    """
    Cancela a solicitação ativa do aluno na viagem. Depois do início vira desistência.

    Raises: ForbiddenError, NotFoundError, ValidationError
    """
    aluno = _buscar_aluno(user_id)

    viagem = db.session.get(Viagem, validate_uuid(viagem_id, "ID da viagem"))
    if not viagem:
        raise NotFoundError("Viagem não encontrada")

    solicitacao = (
        db.session.query(SolicitacaoViagem)
        .filter_by(
            viagem_id=viagem.id,
            aluno_id=aluno.usuario_id,
            status=StatusSolicitacao.ATIVA,
        )
        .first()
    )
    if not solicitacao:
        raise NotFoundError("Solicitação ativa não encontrada para esta viagem")

    if viagem.status in (StatusViagem.FINALIZADA, StatusViagem.CANCELADA):
        raise ValidationError(
            f"Não é possível cancelar a solicitação de uma viagem com status {viagem.status.name}"
        )

    with transactional():
        solicitacao.cancelada_em = tempo.agora_utc()

        if viagem.status == StatusViagem.EM_ANDAMENTO:
            # Lugar não é reaberto: o veículo já saiu contando com o passageiro.
            solicitacao.status = StatusSolicitacao.DESISTENCIA
            # Sai da lista de embarque do motorista (RF-16/RF-17).
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

        # O vetor de carga só conta solicitações ATIVA: cancelar já devolve o trecho (RF-14).
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
    """
    RF-13: o aluno declara origem e destino durante o buffer; a capacidade decide (RF-14).
    Quem recebeu o aviso do buffer sem ter solicitado entra na viagem aqui mesmo.

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
    """
    Rodada ativa da rota sob demanda, para quem abre o app sem ter recebido o push
    (RF-12, fluxo secundário). Sem rodada, devolve viagem None e as janelas de hoje.

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
    # Veículo ocupado com outra rota: para esta rota não há rodada.
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
