"""Solicitação de viagem sob demanda (RF-10) e cancelamento (RF-19)."""

from sqlalchemy import select

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.core.transaction import transactional
from app.models.base import db
from app.models.enum import StatusSolicitacao, StatusViagem, TipoViagem
from app.models.onibus import Onibus
from app.models.rota import Rota
from app.models.user import Aluno
from app.models.viagem import AlunosConfirmados, SolicitacaoViagem, Viagem
from app.services import janelas_service, viagens_service
from app.services.notificacao_service import NotificacaoService
from app.utils import tempo


def _buscar_aluno(user_id: str) -> Aluno:
    aluno = db.session.get(Aluno, user_id)
    if not aluno:
        raise ForbiddenError("Apenas alunos podem solicitar viagens")
    return aluno


# shortcut: PR #16 driver availability check (work hours / mandatory rest) plugs in here, so a request never goes to a resting driver; wire it once PR #16 merges.
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

    rota = db.session.get(Rota, rota_id)
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

        # shortcut: no origin/destination or capacity check yet, add RF-13/14 here in Plan 3.
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

    viagem = db.session.get(Viagem, viagem_id)
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

        # shortcut: no capacity to give back yet, decrement the RF-14 load here in Plan 3.
        solicitacao.status = StatusSolicitacao.CANCELADA
        db.session.flush()

        if viagem.status == StatusViagem.SOLICITADA:
            restantes = (
                db.session.query(SolicitacaoViagem.id)
                .filter_by(viagem_id=viagem.id, status=StatusSolicitacao.ATIVA)
                .count()
            )
            if restantes == 0:
                # shortcut: PR #16 driver state reset (back to ATIVO) hooks in here; wire it once PR #16 merges.
                viagem.status = StatusViagem.CANCELADA
                if viagem.motorista_id:
                    NotificacaoService._criar_notificacao_interna(
                        usuario_id=viagem.motorista_id,
                        titulo="Solicitação de viagem cancelada",
                        mensagem="Todos os passageiros cancelaram a solicitação. A viagem foi cancelada.",
                    )

        return solicitacao
