"""Boarding credential, driver itinerary and offline sync (RF-15 to RF-18).

The credential is `CredencialEmbarque`: the student app fetches the secret from
`GET /v1/viagens/<id>/credencial-embarque` and draws the QR
`<credencial_id>.<codigo>`, with a code that changes every step
(`credencial_embarque_service`). This module issues it when the buffer is
consolidated and holds the rules that consume it at boarding.

QR boarding in two steps (RF-17): the check-in checks the credential and returns
the passenger with the photo, boarding no one; boarding is only recorded when the
driver confirms the photo is the person in front of them. If not, they reject it,
an incident is opened for the manager and the credential is rejected: that QR
boards no one else on this trip. The real passenger boards via the manual
fallback, checked against the stop list photo.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from flask import current_app

from app.core.exceptions import AppError, ForbiddenError, NotFoundError, ValidationError
from app.core.transaction import transactional
from app.models.base import db
from app.models.credencial_embarque import CredencialEmbarque
from app.models.enum import StatusOcorrencia, StatusViagem, TipoOcorrencia, UserRole
from app.models.ocorrencia import Ocorrencia
from app.models.user import User
from app.models.viagem import AlunosConfirmados, TelemetriaViagem, Viagem, ViagemPonto
from app.services import credencial_embarque_service
from app.utils import tempo

logger = logging.getLogger(__name__)

IdLike = str | uuid.UUID

# States where the vehicle has left and the driver runs the itinerary.
EM_PERCURSO = (StatusViagem.EM_ANDAMENTO,)
# Sync (RF-18) also accepts a finished trip: the offline queue may arrive after
# the driver ended the route.
SINCRONIZAVEL = EM_PERCURSO + (StatusViagem.FINALIZADA,)

# EMBARQUE_CONFIRMADO is a QR checked and confirmed by the driver; RECUSA is a QR
# they rejected. EMBARQUE is the old type, from before the photo check: it stays
# in the schema only to be rejected event by event with EVENTO_DESCONTINUADO.
TIPOS_EVENTO = (
    "EMBARQUE_CONFIRMADO",
    "EMBARQUE_MANUAL",
    "RECUSA",
    "CHEGADA_PONTO",
    "POSICAO",
    "EMBARQUE",
)

MOTIVOS_RECUSA = ("FOTO_NAO_CONFERE", "SEM_FOTO")


class EmbarqueRecusado(AppError):
    """RF-17: boarding rejection.

    The `code` tells the reason apart: the driver app needs to know whether the
    credential is unknown, from another trip, from another stop or already used,
    because the driver reacts differently in each case.
    """

    def __init__(self, message: str, code: str, status_code: int = 409):
        super().__init__(message, status_code, code)


def _uuid(valor: IdLike, rotulo: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(valor))
    except (AttributeError, TypeError, ValueError) as e:
        raise ValidationError(f"{rotulo} inválido") from e


def _aware(momento: datetime | None) -> datetime:
    """Offline event timestamp; without a time zone, assumes UTC."""
    if momento is None:
        return tempo.agora_utc()
    return momento if momento.tzinfo else momento.replace(tzinfo=UTC)


def _viagem_do_motorista(user_id: IdLike, viagem_id: IdLike, estados: tuple) -> Viagem:
    user = db.session.get(User, _uuid(user_id, "ID do usuário"))
    if not user or user.role != UserRole.MOTORISTA:
        raise ForbiddenError("Apenas o motorista opera o roteiro da viagem")

    viagem = db.session.get(Viagem, _uuid(viagem_id, "ID da viagem"))
    if not viagem:
        raise NotFoundError("Viagem não encontrada")

    if str(viagem.motorista_id) != str(user.id):
        raise ForbiddenError("Esta viagem não pertence a você")

    if viagem.status not in estados:
        raise ValidationError(f"Operação indisponível com a viagem em {viagem.status.name}")

    return viagem


def _embarques(viagem: Viagem) -> list[AlunosConfirmados]:
    """Who the driver expects to board: confirmed passengers who did not drop out (RF-19)."""
    return [c for c in viagem.alunos_confirmados if c.confirmacao]


def _foto(registro: AlunosConfirmados) -> dict[str, Any]:
    foto_url = registro.aluno.foto_url if registro.aluno else None
    return {"foto_url": foto_url, "sem_foto": foto_url is None}


def _ponto_atual(viagem: Viagem) -> ViagemPonto | None:
    """The stop the vehicle is serving: the first one not yet passed."""
    return next((vp for vp in viagem.pontos_visitados if not vp.visitado), None)


# RF-15: credential issuing


def consolidar_embarque(viagem: Viagem, confirmados: list[AlunosConfirmados]) -> int:
    """Issue the round's credentials and materialize the driver's itinerary.

    Called by the buffer consolidation (RF-15), inside its transaction. One new
    credential per confirmed passenger: valid only for this student, on this trip
    and at this boarding stop, and never reused.
    """
    _materializar_pontos(viagem)

    for registro in confirmados:
        credencial_embarque_service.criar_credencial(
            viagem.id, registro.aluno_id, registro.ponto_embarque_id
        )

    return len(confirmados)


def _materializar_pontos(viagem: Viagem) -> None:
    """Copy the circuit into `viagem_ponto`, where progress is recorded.

    The on-demand round is born without stops (it does not come from the
    timetable), so the RF-16 itinerary only exists after consolidation.
    """
    if viagem.pontos_visitados:
        return

    rota = viagem.rota or (viagem.horario_rota.rota if viagem.horario_rota else None)
    if not rota:
        raise ValidationError("Viagem sem circuito de pontos definido")

    for ordem, rp in enumerate(rota.pontos_padrao, start=1):
        db.session.add(
            ViagemPonto(viagem_id=viagem.id, ponto_id=rp.ponto_id, ordem=ordem, visitado=False)
        )
    db.session.flush()


# RF-16: driver itinerary


def roteiro(user_id: IdLike, viagem_id: IdLike) -> dict[str, Any]:
    """RF-16: stops in order, with how many board and get off at each one.

    Includes the permission matrix (each passenger's credential and photo per
    stop), which the app downloads before departure to check boardings offline
    (RF-18). It is also the list the driver uses in the manual fallback.
    """
    viagem = _viagem_do_motorista(user_id, viagem_id, EM_PERCURSO)
    embarques = _embarques(viagem)
    atual = _ponto_atual(viagem)

    credencial_por_aluno: dict[uuid.UUID, CredencialEmbarque] = {}
    ativas = CredencialEmbarque.query.filter_by(viagem_id=viagem.id, revogada_em=None).all()
    for credencial in ativas:
        credencial_por_aluno[credencial.aluno_id] = credencial

    pontos = []
    for vp in viagem.pontos_visitados:
        sobem = [c for c in embarques if c.ponto_embarque_id == vp.ponto_id]
        descem = sum(1 for c in embarques if c.ponto_destino_id == vp.ponto_id)
        apelido = vp.ponto.apelido if vp.ponto else "ponto"

        passageiros = []
        for c in sobem:
            credencial = credencial_por_aluno.get(c.aluno_id)
            passageiro = {
                "aluno_id": str(c.aluno_id),
                "nome": c.aluno.nome if c.aluno else None,
                # The secret lets the app check the QR code offline (RF-18).
                "credencial_id": str(credencial.id) if credencial else None,
                "qr_segredo": credencial.segredo if credencial else None,
                "embarcou": c.embarcou,
                "ponto_destino_id": str(c.ponto_destino_id) if c.ponto_destino_id else None,
            }
            passageiro.update(_foto(c))
            passageiros.append(passageiro)

        pontos.append(
            {
                "ponto_id": str(vp.ponto_id),
                "apelido": apelido,
                "ordem": vp.ordem,
                "visitado": bool(vp.visitado),
                "chegada_real": vp.chegada_real,
                "embarcam": len(sobem),
                "desembarcam": descem,
                "instrucao": f"Aproximando-se de {apelido}: "
                f"embarcam {len(sobem)}, desembarcam {descem}",
                "passageiros": passageiros,
            }
        )

    return {
        "viagem_id": str(viagem.id),
        "status": viagem.status.name,
        "pontos": pontos,
        "ponto_atual_id": str(atual.ponto_id) if atual else None,
        "instrucao_atual": next(
            (p["instrucao"] for p in pontos if atual and p["ponto_id"] == str(atual.ponto_id)),
            None,
        ),
    }


def avancar_ponto(
    user_id: IdLike, viagem_id: IdLike, ocorrido_em: datetime | None = None
) -> dict[str, Any]:
    """RF-16: completes the current stop and moves to the next one.

    Marks the stop as passed with the arrival time; the next unpassed stop becomes
    the current one, and boardings are validated against it (RF-17).
    """
    viagem = _viagem_do_motorista(user_id, viagem_id, EM_PERCURSO)

    with transactional():
        atual = _ponto_atual(viagem)
        if not atual:
            raise ValidationError("Todos os pontos do roteiro já foram transpostos")
        _marcar_visitado(atual, _aware(ocorrido_em))

    return roteiro(user_id, viagem_id)


def _marcar_visitado(vp: ViagemPonto, momento: datetime) -> None:
    vp.visitado = True
    vp.chegada_real = momento


# RF-17: boarding validation


def _tolerancia() -> timedelta:
    return timedelta(seconds=current_app.config["SYNC_TOLERANCIA_SEGUNDOS"])


def _credencial_do_qr(
    qr: str, viagem: Viagem, momento: datetime, conferir_codigo: bool = True
) -> CredencialEmbarque:
    """Rules for the scanned credential, the same online and offline.

    `momento` is the server clock online, or the already-clamped offline event
    timestamp. The rejection does not check the code: it only closes the door, and
    the code may have rotated while the driver looked at the photo.
    """
    partes = credencial_embarque_service.separar_qr(qr)
    credencial = db.session.get(CredencialEmbarque, partes[0]) if partes else None
    if partes is None or credencial is None:
        raise EmbarqueRecusado("Credencial não reconhecida", "CREDENCIAL_DESCONHECIDA", 404)

    if credencial.viagem_id != viagem.id:
        raise EmbarqueRecusado("Credencial emitida para outra viagem", "CREDENCIAL_DE_OUTRA_VIAGEM")

    if credencial.revogada_em is not None:
        raise EmbarqueRecusado(
            "Credencial substituída por outra mais recente", "CREDENCIAL_DESATUALIZADA"
        )

    emitida_em = credencial.created_at
    if emitida_em is not None and momento < emitida_em - _tolerancia():
        raise EmbarqueRecusado(
            "Evento anterior à emissão da credencial", "EVENTO_ANTES_DA_CREDENCIAL", 422
        )

    if momento >= credencial.expires_at:
        raise EmbarqueRecusado("Credencial de embarque expirada", "CREDENCIAL_EXPIRADA")

    if conferir_codigo and not credencial_embarque_service.codigo_confere(
        credencial, partes[1], momento
    ):
        raise EmbarqueRecusado(
            "Código do QR expirado ou inválido: peça ao aluno para abrir o QR de novo",
            "CODIGO_EXPIRADO",
        )

    return credencial


def _travar_registro(viagem_id: uuid.UUID, aluno_id: uuid.UUID) -> AlunosConfirmados | None:
    """Lock the credentials and then the passenger row, always in that order.

    Two concurrent confirmations of the same passenger queue up here: the second
    reads `embarcou`/`usado` already saved by the first. The fixed order avoids
    deadlock between the QR, the manual flow and the offline queue.
    """
    db.session.query(CredencialEmbarque).filter_by(viagem_id=viagem_id, aluno_id=aluno_id).order_by(
        CredencialEmbarque.id
    ).with_for_update().populate_existing().all()

    return (
        db.session.query(AlunosConfirmados)
        .filter_by(viagem_id=viagem_id, aluno_id=aluno_id)
        .with_for_update()
        .populate_existing()
        .one_or_none()
    )


def _conferir(
    registro: AlunosConfirmados | None,
    credencial: CredencialEmbarque | None,
    ponto_esperado: uuid.UUID | None,
) -> AlunosConfirmados:
    """RF-17 rejections, each with its own code.

    A null `credencial` is the manual fallback, with no scanned QR behind it.
    A null `ponto_esperado` skips the stop check: the case of an offline event
    that does not say which stop the driver was at.
    """
    if registro is None or not registro.confirmacao:
        raise EmbarqueRecusado(
            "Passageiro não consta na lista de embarque desta viagem", "PASSAGEIRO_NAO_PREVISTO"
        )

    if credencial is not None:
        if credencial.recusada_em is not None:
            raise EmbarqueRecusado(
                "Credencial recusada pelo motorista nesta viagem: embarque só pela lista do ponto",
                "CREDENCIAL_RECUSADA",
            )
        if credencial.ponto_embarque_id != registro.ponto_embarque_id:
            raise EmbarqueRecusado(
                "Credencial emitida para um ponto que não é mais o do passageiro",
                "CREDENCIAL_DESATUALIZADA",
            )
        if credencial.usado:
            raise EmbarqueRecusado(
                "Credencial já utilizada nesta viagem", "CREDENCIAL_JA_UTILIZADA"
            )

    if registro.embarcou:
        raise EmbarqueRecusado("Credencial já utilizada nesta viagem", "CREDENCIAL_JA_UTILIZADA")

    if ponto_esperado is not None and registro.ponto_embarque_id != ponto_esperado:
        raise EmbarqueRecusado(
            "Credencial é de outro ponto de embarque", "CREDENCIAL_DE_OUTRO_PONTO"
        )

    return registro


def _registrar_embarque(registro: AlunosConfirmados, momento: datetime) -> dict[str, Any]:
    registro.embarcou = True
    registro.embarcado_em = momento

    # The credential is single use, even when boarding was manual.
    credenciais = CredencialEmbarque.query.filter_by(
        viagem_id=registro.viagem_id, aluno_id=registro.aluno_id
    ).all()
    for credencial in credenciais:
        credencial.usado = True
    return {
        "viagem_id": str(registro.viagem_id),
        "aluno_id": str(registro.aluno_id),
        "nome": registro.aluno.nome if registro.aluno else None,
        "ponto_embarque_id": (
            str(registro.ponto_embarque_id) if registro.ponto_embarque_id else None
        ),
        "embarcado_em": momento,
    }


def _ocorrencia(
    viagem: Viagem,
    motorista_id: IdLike,
    descricao: str,
    status: StatusOcorrencia,
    ocorrencia_id: uuid.UUID | None = None,
) -> Ocorrencia:
    ocorrencia = Ocorrencia(
        id=ocorrencia_id or uuid.uuid4(),
        autor_id=_uuid(motorista_id, "ID do motorista"),
        viagem_id=viagem.id,
        tipo=TipoOcorrencia.OUTRO,
        status=status,
        descricao=descricao,
    )
    db.session.add(ocorrencia)
    return ocorrencia


def _embarque_por_qr(
    viagem: Viagem,
    qr: str,
    ponto_esperado: uuid.UUID | None,
    momento: datetime,
    ja_aplicado_ok: bool = False,
) -> dict[str, Any] | None:
    """Confirm QR boarding, online or from the offline queue.

    With `ja_aplicado_ok` (resent offline queue), a passenger who already boarded
    returns None instead of a rejection; a rejected credential always rejects.
    """
    credencial = _credencial_do_qr(qr, viagem, momento)
    registro = _travar_registro(viagem.id, credencial.aluno_id)

    if ja_aplicado_ok and registro is not None and registro.embarcou:
        if credencial.recusada_em is None:
            return None

    registro = _conferir(registro, credencial, ponto_esperado)

    # Without a photo there is nothing to check: the QR alone boards no one.
    if _foto(registro)["sem_foto"]:
        raise EmbarqueRecusado(
            "Aluno sem foto cadastrada: embarque só pela lista do ponto, no fallback manual",
            "SEM_FOTO_EXIGE_MANUAL",
        )

    resultado = _registrar_embarque(registro, momento)
    resultado.update(_foto(registro))
    resultado["manual"] = False
    return resultado


def _parada_em_atendimento(viagem: Viagem) -> ViagemPonto:
    atual = _ponto_atual(viagem)
    if not atual:
        raise ValidationError("Não há parada em atendimento nesta viagem")
    return atual


def endpoint_descontinuado() -> None:
    """Old `POST .../validacao`, which boarded on scan. Fails loudly for the old app."""
    raise EmbarqueRecusado(
        "Esta versão do app do motorista não é mais suportada. Atualize o app para "
        "conferir a foto do passageiro antes de confirmar o embarque.",
        "ENDPOINT_DESCONTINUADO",
        410,
    )


def checkin_embarque(user_id: IdLike, viagem_id: IdLike, qr: str) -> dict[str, Any]:
    """RF-17 step 1: checks the scanned credential and returns the passenger with the photo.

    Read only: boards no one and does not mark the credential as used. A
    credential outside the itinerary is rejected here, without showing a photo
    (secondary flow 2). With no photo on file, returns `sem_foto` and the driver
    uses the manual fallback.
    """
    viagem = _viagem_do_motorista(user_id, viagem_id, EM_PERCURSO)
    atual = _parada_em_atendimento(viagem)

    credencial = _credencial_do_qr(qr, viagem, tempo.agora_utc())
    registro = db.session.get(AlunosConfirmados, (viagem.id, credencial.aluno_id))
    registro = _conferir(registro, credencial, atual.ponto_id)

    resultado = {
        "viagem_id": str(viagem.id),
        "aluno_id": str(registro.aluno_id),
        "nome": registro.aluno.nome if registro.aluno else None,
        "ponto_embarque_id": (
            str(registro.ponto_embarque_id) if registro.ponto_embarque_id else None
        ),
        "ponto_destino_id": str(registro.ponto_destino_id) if registro.ponto_destino_id else None,
    }
    resultado.update(_foto(registro))
    return resultado


def confirmar_embarque(user_id: IdLike, viagem_id: IdLike, qr: str) -> dict[str, Any]:
    """RF-17 step 2: the photo matches and the driver confirms; the boarding is recorded.

    Redoes all the scan checks with the rows locked: between the scan and the
    confirmation the same QR may have been used on another device.
    """
    viagem = _viagem_do_motorista(user_id, viagem_id, EM_PERCURSO)
    atual = _parada_em_atendimento(viagem)

    with transactional():
        resultado = _embarque_por_qr(viagem, qr, atual.ponto_id, tempo.agora_utc())

    assert resultado is not None
    return resultado


def recusar_embarque(
    user_id: IdLike,
    viagem_id: IdLike,
    qr: str,
    motivo: str,
    observacao: str | None = None,
) -> dict[str, Any]:
    """RF-17 secondary flow 1: the photo is not the person and the driver rejects.

    The boarding is not recorded and the credential is rejected: the same QR boards
    no one else on this trip, online or via the offline queue. The real passenger,
    if they show up, boards via the manual fallback after the driver checks the
    stop list photo. The rejection becomes an open incident for the manager. It
    cannot be undone through the API.
    """
    viagem = _viagem_do_motorista(user_id, viagem_id, EM_PERCURSO)
    atual = _parada_em_atendimento(viagem)

    momento = tempo.agora_utc()
    with transactional():
        credencial = _credencial_do_qr(qr, viagem, momento, conferir_codigo=False)
        registro = _travar_registro(viagem.id, credencial.aluno_id)
        registro = _conferir(registro, credencial, atual.ponto_id)
        ocorrencia = _registrar_recusa(
            viagem, registro, credencial, motivo, observacao, user_id, momento
        )

    return {
        "viagem_id": str(viagem.id),
        "aluno_id": str(registro.aluno_id),
        "motivo": motivo,
        "ocorrencia_id": str(ocorrencia.id),
    }


def _registrar_recusa(
    viagem: Viagem,
    registro: AlunosConfirmados,
    credencial: CredencialEmbarque,
    motivo: str,
    observacao: str | None,
    motorista_id: IdLike,
    momento: datetime,
    ocorrencia_id: uuid.UUID | None = None,
) -> Ocorrencia:
    if motivo not in MOTIVOS_RECUSA:
        raise ValidationError(f"Motivo de recusa desconhecido: {motivo}")

    if credencial.recusada_em is None:
        credencial.recusada_em = momento
        credencial.motivo_recusa = motivo

    descricao = (
        f"Embarque recusado ({motivo}) do aluno {registro.aluno_id} "
        f"no ponto {registro.ponto_embarque_id}."
    )
    if observacao:
        descricao = f"{descricao} Observação do motorista: {observacao}"
    return _ocorrencia(viagem, motorista_id, descricao, StatusOcorrencia.ABERTA, ocorrencia_id)


def confirmar_manual(user_id: IdLike, viagem_id: IdLike, aluno_id: IdLike) -> dict[str, Any]:
    """RF-17 fallback: the scan failed, the driver finds the student in the stop's list.

    The driver checks the face against the stop list photo (the itinerary carries
    each passenger's photo). There is no scanned credential behind it, so each use
    is recorded as an incident for the manager to audit. It is also the path for
    the real passenger after a rejection and for a student with no photo.
    """
    viagem = _viagem_do_motorista(user_id, viagem_id, EM_PERCURSO)
    atual = _parada_em_atendimento(viagem)

    with transactional():
        resultado = _embarque_manual(viagem, aluno_id, atual.ponto_id, tempo.agora_utc(), user_id)

    assert resultado is not None
    return resultado


def _embarque_manual(
    viagem: Viagem,
    aluno_id: IdLike,
    ponto_esperado: uuid.UUID | None,
    momento: datetime,
    motorista_id: IdLike,
    ja_aplicado_ok: bool = False,
) -> dict[str, Any] | None:
    registro = _travar_registro(viagem.id, _uuid(aluno_id, "ID do aluno"))
    if ja_aplicado_ok and registro is not None and registro.embarcou:
        return None

    registro = _conferir(registro, None, ponto_esperado)
    resultado = _registrar_embarque(registro, momento)
    resultado.update(_foto(registro))

    # ponytail: o "foi manual" mora numa ocorrência em vez de numa coluna nova —
    # o esquema está fechado e a tabela existe justamente para registrar
    # desvios de operação. Vira coluna se o dashboard precisar contar isso.
    conferencia = "sem foto cadastrada" if resultado["sem_foto"] else "foto da lista do ponto"
    _ocorrencia(
        viagem,
        motorista_id,
        f"Embarque manual (falha de leitura do QR) do aluno {registro.aluno_id} "
        f"no ponto {registro.ponto_embarque_id}. Conferência: {conferencia}.",
        StatusOcorrencia.RESOLVIDA,
    )

    resultado["manual"] = True
    return resultado


# RF-18: batch sync of the offline queue


def sincronizar(
    user_id: IdLike, viagem_id: IdLike, eventos: list[dict[str, Any]]
) -> dict[str, Any]:
    """RF-18: applies the queue the driver app accumulated offline.

    Each event is applied in its own transaction and the result comes back per
    event: an invalid event does not break the batch, and the app knows exactly
    what it can remove from the queue (§2.3.2).

    Events are applied in `ocorrido_em` order (ties: queue order), and results come
    out in that same order. So an earlier RECUSA blocks a later EMBARQUE_CONFIRMADO
    of the same QR, in the same batch or a later one.

    Idempotency without an events table: each event's effect is a state change that
    is already observable (the passenger boarded, the stop was passed), so resending
    the batch finds the state done and does nothing. The exceptions are position and
    rejection, which are append-only: the row `id` (telemetry or incident) is derived
    from the trip and the event identifier (UUIDv5), and the primary key handles duplicates.

    Events arrive out of order and late, so they count by the timestamp they carry,
    never by arrival time; a timestamp in the future beyond the tolerance is rejected.
    """
    viagem = _viagem_do_motorista(user_id, viagem_id, SINCRONIZAVEL)
    limite = tempo.agora_utc() + _tolerancia()

    fila = []
    for posicao, evento in enumerate(eventos):
        fila.append((_aware(evento.get("ocorrido_em")), posicao, evento))
    fila.sort(key=lambda item: (item[0], item[1]))

    resultados = []
    for momento, _posicao, evento in fila:
        evento_id = evento.get("evento_id")
        try:
            if momento > limite:
                raise EmbarqueRecusado(
                    "Horário do evento no futuro: confira o relógio do aparelho",
                    "EVENTO_NO_FUTURO",
                    422,
                )
            with transactional():
                situacao = _aplicar_evento(viagem, evento, momento, user_id)
            resultados.append({"evento_id": evento_id, "situacao": situacao})
        except AppError as e:
            logger.info(f"Evento offline recusado: viagem={viagem.id} evento={evento_id} {e.code}")
            resultados.append(
                {
                    "evento_id": evento_id,
                    "situacao": "recusado",
                    "codigo": e.code,
                    "mensagem": e.message,
                }
            )

    return {
        "recebidos": len(eventos),
        "aplicados": sum(1 for r in resultados if r["situacao"] == "aplicado"),
        "ja_aplicados": sum(1 for r in resultados if r["situacao"] == "ja_aplicado"),
        "recusados": sum(1 for r in resultados if r["situacao"] == "recusado"),
        "resultados": resultados,
    }


def _aplicar_evento(
    viagem: Viagem, evento: dict[str, Any], momento: datetime, motorista_id: IdLike
) -> str:
    tipo = evento.get("tipo")
    ponto_id = evento.get("ponto_id")
    ponto_esperado = _uuid(ponto_id, "ID do ponto") if ponto_id else None

    if tipo == "EMBARQUE":
        raise EmbarqueRecusado(
            "Evento EMBARQUE descontinuado: atualize o app do motorista, que agora "
            "envia EMBARQUE_CONFIRMADO depois de conferir a foto",
            "EVENTO_DESCONTINUADO",
            410,
        )

    if tipo == "EMBARQUE_CONFIRMADO":
        resultado = _embarque_por_qr(
            viagem, evento.get("qr_token") or "", ponto_esperado, momento, ja_aplicado_ok=True
        )
        return "ja_aplicado" if resultado is None else "aplicado"

    if tipo == "RECUSA":
        ocorrencia_id = _id_do_evento(viagem, evento)
        if db.session.get(Ocorrencia, ocorrencia_id):
            return "ja_aplicado"
        credencial = _credencial_do_qr(
            evento.get("qr_token") or "", viagem, momento, conferir_codigo=False
        )
        registro = _travar_registro(viagem.id, credencial.aluno_id)
        # Again after the lock: the same queue resent in parallel may have saved the rejection.
        if db.session.get(Ocorrencia, ocorrencia_id):
            return "ja_aplicado"
        if registro is None:
            raise EmbarqueRecusado(
                "Passageiro não consta na lista de embarque desta viagem",
                "PASSAGEIRO_NAO_PREVISTO",
            )
        # No `_conferir`: the real passenger's manual boarding may come first, and the
        # rejection still needs to reach the manager and close the QR.
        _registrar_recusa(
            viagem,
            registro,
            credencial,
            evento.get("motivo") or "",
            evento.get("observacao"),
            motorista_id,
            momento,
            ocorrencia_id,
        )
        return "aplicado"

    if tipo == "EMBARQUE_MANUAL":
        resultado = _embarque_manual(
            viagem,
            evento.get("aluno_id") or "",
            ponto_esperado,
            momento,
            motorista_id,
            ja_aplicado_ok=True,
        )
        return "ja_aplicado" if resultado is None else "aplicado"

    if tipo == "CHEGADA_PONTO":
        if ponto_esperado is None:
            raise ValidationError("Evento de chegada sem ponto")
        vp = db.session.get(ViagemPonto, (viagem.id, ponto_esperado))
        if not vp:
            raise NotFoundError("Ponto não pertence ao roteiro desta viagem")
        if vp.visitado:
            return "ja_aplicado"
        _marcar_visitado(vp, momento)
        return "aplicado"

    if tipo == "POSICAO":
        return _aplicar_posicao(viagem, evento, momento)

    raise ValidationError(f"Tipo de evento desconhecido: {tipo}")


def _id_do_evento(viagem: Viagem, evento: dict[str, Any]) -> uuid.UUID:
    """Stable id of the record saved by the event, so a resent queue does not duplicate.

    Includes the trip: `evento_id` comes from the app and is only unique within the trip's queue.
    """
    return uuid.uuid5(uuid.NAMESPACE_OID, f"{viagem.id}:{evento.get('evento_id')}")


def _aplicar_posicao(viagem: Viagem, evento: dict[str, Any], momento: datetime) -> str:
    latitude, longitude = evento.get("latitude"), evento.get("longitude")
    if latitude is None or longitude is None:
        raise ValidationError("Evento de posição sem coordenadas")

    # Lock the trip: the same queue resent in parallel neither saves the trail twice
    # nor replaces the current position with an older one.
    db.session.query(Viagem).filter(Viagem.id == viagem.id).with_for_update(
        key_share=True
    ).populate_existing().one()

    rastro_id = _id_do_evento(viagem, evento)
    if db.session.get(TelemetriaViagem, rastro_id):
        return "ja_aplicado"

    db.session.add(
        TelemetriaViagem(
            id=rastro_id,
            viagem_id=viagem.id,
            latitude=latitude,
            longitude=longitude,
            timestamp=momento,
        )
    )

    # The vehicle's current position is the latest by event timestamp, not the
    # last to arrive: the offline queue comes out of order.
    if viagem.motorista_gps_hora is None or viagem.motorista_gps_hora < momento:
        viagem.motorista_lat = latitude
        viagem.motorista_lon = longitude
        viagem.motorista_gps_hora = momento

    return "aplicado"
