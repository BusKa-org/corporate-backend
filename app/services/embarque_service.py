"""RF-15 a RF-18 — credencial de embarque, roteiro do motorista e sincronização.

A credencial é um *token* opaco, não uma imagem: o backend emite e valida a
string; desenhar o QR Code na tela é trabalho do app do aluno.

Escopo: a conferência visual por fotografia prevista no RF-15/RF-17 está fora
do escopo desta entrega por decisão do cliente. O que existe aqui é a validação
da credencial contra o roteiro (viagem e ponto corretos) e o fallback manual.
"""

import logging
import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

from app.core.exceptions import AppError, ForbiddenError, NotFoundError, ValidationError
from app.core.transaction import transactional
from app.models.base import db
from app.models.enum import (
    StatusOcorrencia,
    StatusSolicitacao,
    StatusViagem,
    TipoOcorrencia,
    UserRole,
)
from app.models.ocorrencia import Ocorrencia
from app.models.user import User
from app.models.viagem import AlunosConfirmados, TelemetriaViagem, Viagem, ViagemPonto

logger = logging.getLogger(__name__)

IdLike = str | uuid.UUID

# Estados em que o veículo já saiu e o motorista opera o roteiro.
EM_PERCURSO = (StatusViagem.EM_ROTA, StatusViagem.EM_ANDAMENTO)
# A sincronização (RF-18) também aceita a viagem já encerrada: a fila offline
# pode chegar depois que o motorista finalizou o percurso.
SINCRONIZAVEL = EM_PERCURSO + (StatusViagem.FINALIZADA,)

TIPOS_EVENTO = ("EMBARQUE", "EMBARQUE_MANUAL", "CHEGADA_PONTO", "POSICAO")


class EmbarqueRecusado(AppError):
    """RF-17: recusa de embarque.

    O `code` distingue o motivo — o app do motorista precisa saber se a
    credencial é desconhecida, de outra viagem, de outro ponto ou já usada,
    porque a reação do motorista é diferente em cada caso.
    """

    def __init__(self, message: str, code: str, status_code: int = 409):
        super().__init__(message, status_code, code)


def _uuid(valor: IdLike, rotulo: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(valor))
    except (AttributeError, TypeError, ValueError) as e:
        raise ValidationError(f"{rotulo} inválido") from e


def _aware(momento: datetime | None) -> datetime:
    """Carimbo do evento offline; sem fuso, assume UTC."""
    if momento is None:
        return datetime.now(UTC)
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
    """Quem o motorista espera embarcar: confirmados que não desistiram (RF-19)."""
    return [
        c
        for c in viagem.alunos_confirmados
        if c.status == StatusSolicitacao.CONFIRMADO and c.confirmacao
    ]


def _ponto_atual(viagem: Viagem) -> ViagemPonto | None:
    """A parada que o veículo está atendendo: a primeira ainda não transposta."""
    return next((vp for vp in viagem.pontos_visitados if not vp.visitado), None)


# ==========================================
# RF-15 — emissão das credenciais
# ==========================================


def consolidar_embarque(viagem: Viagem, confirmados: list[AlunosConfirmados]) -> int:
    """Emite as credenciais da rodada e materializa o roteiro do motorista.

    Chamada pela consolidação do buffer (RF-15), dentro da transação dela. Um
    token novo por passageiro confirmado, sorteado a cada rodada: a credencial
    vale só para este par aluno/viagem e nunca é reaproveitada.
    """
    _materializar_pontos(viagem)

    for registro in confirmados:
        registro.qr_token = secrets.token_urlsafe(32)

    return len(confirmados)


def _materializar_pontos(viagem: Viagem) -> None:
    """Copia o circuito para `viagem_ponto`, que é onde o progresso é gravado.

    A rodada sob demanda nasce sem pontos (ela não vem da grade de horários),
    então o roteiro do RF-16 só existe a partir da consolidação.
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


def minha_credencial(user_id: IdLike, viagem_id: IdLike) -> dict[str, Any]:
    """RF-15: o aluno busca a própria credencial.

    A busca é sempre pela identidade do JWT — não há parâmetro que permita
    pedir a credencial de outro aluno.
    """
    registro = db.session.get(
        AlunosConfirmados,
        (_uuid(viagem_id, "ID da viagem"), _uuid(user_id, "ID do aluno")),
    )
    if not registro or registro.status != StatusSolicitacao.CONFIRMADO:
        raise NotFoundError("Você não tem embarque confirmado nesta rodada")

    if not registro.qr_token:
        raise NotFoundError("A credencial é emitida quando a rodada é consolidada")

    return {
        "viagem_id": str(registro.viagem_id),
        "aluno_id": str(registro.aluno_id),
        "qr_token": registro.qr_token,
        "ponto_embarque_id": (
            str(registro.ponto_embarque_id) if registro.ponto_embarque_id else None
        ),
        "ponto_destino_id": str(registro.ponto_destino_id) if registro.ponto_destino_id else None,
        "embarcou": registro.embarcou,
        "embarcado_em": registro.embarcado_em,
    }


# ==========================================
# RF-16 — roteiro do motorista
# ==========================================


def roteiro(user_id: IdLike, viagem_id: IdLike) -> dict[str, Any]:
    """RF-16: paradas em ordem, com quantos embarcam e desembarcam em cada uma.

    Vai junto a matriz de permissões (credenciais válidas por ponto), que é o
    que o app baixa antes da partida para validar embarques sem rede (RF-18).
    """
    viagem = _viagem_do_motorista(user_id, viagem_id, EM_PERCURSO)
    embarques = _embarques(viagem)
    atual = _ponto_atual(viagem)

    pontos = []
    for vp in viagem.pontos_visitados:
        sobem = [c for c in embarques if c.ponto_embarque_id == vp.ponto_id]
        descem = sum(1 for c in embarques if c.ponto_destino_id == vp.ponto_id)
        apelido = vp.ponto.apelido if vp.ponto else "ponto"

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
                "passageiros": [
                    {
                        "aluno_id": str(c.aluno_id),
                        "nome": c.aluno.nome if c.aluno else None,
                        "qr_token": c.qr_token,
                        "embarcou": c.embarcou,
                        "ponto_destino_id": (
                            str(c.ponto_destino_id) if c.ponto_destino_id else None
                        ),
                    }
                    for c in sobem
                ],
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
    """RF-16: conclui a parada corrente e segue para a próxima.

    Marca a parada como transposta com o horário de chegada; a próxima não
    transposta passa a ser o ponto corrente, e é contra ela que os embarques
    são validados (RF-17).
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


# ==========================================
# RF-17 — validação do embarque
# ==========================================


def _registro_por_token(qr_token: str, viagem: Viagem) -> AlunosConfirmados:
    registro = (
        db.session.query(AlunosConfirmados).filter_by(qr_token=(qr_token or "").strip()).first()
    )
    if not registro:
        raise EmbarqueRecusado("Credencial não reconhecida", "CREDENCIAL_DESCONHECIDA", 404)

    if registro.viagem_id != viagem.id:
        raise EmbarqueRecusado("Credencial emitida para outra viagem", "CREDENCIAL_DE_OUTRA_VIAGEM")

    return registro


def _conferir(registro: AlunosConfirmados, ponto_esperado: uuid.UUID | None) -> None:
    """Recusas do RF-17, cada uma com seu código.

    `ponto_esperado` nulo dispensa a conferência de ponto: é o caso do evento
    offline que não informa em qual parada o motorista estava.
    """
    if registro.status != StatusSolicitacao.CONFIRMADO or not registro.confirmacao:
        raise EmbarqueRecusado(
            "Passageiro não consta na lista de embarque desta viagem", "PASSAGEIRO_NAO_PREVISTO"
        )

    if registro.embarcou:
        raise EmbarqueRecusado("Credencial já utilizada nesta viagem", "CREDENCIAL_JA_UTILIZADA")

    if ponto_esperado is not None and registro.ponto_embarque_id != ponto_esperado:
        raise EmbarqueRecusado(
            "Credencial é de outro ponto de embarque", "CREDENCIAL_DE_OUTRO_PONTO"
        )


def _registrar_embarque(registro: AlunosConfirmados, momento: datetime) -> dict[str, Any]:
    registro.embarcou = True
    registro.embarcado_em = momento
    return {
        "viagem_id": str(registro.viagem_id),
        "aluno_id": str(registro.aluno_id),
        "nome": registro.aluno.nome if registro.aluno else None,
        "ponto_embarque_id": (
            str(registro.ponto_embarque_id) if registro.ponto_embarque_id else None
        ),
        "embarcado_em": momento,
    }


def validar_embarque(
    user_id: IdLike,
    viagem_id: IdLike,
    qr_token: str,
    ocorrido_em: datetime | None = None,
) -> dict[str, Any]:
    """RF-17: o motorista lê a credencial e o embarque é registrado.

    Sem a conferência de fotografia (descopada), a leitura da credencial é o
    único vínculo entre a pessoa e a reserva: quem apresentar o token embarca.
    """
    viagem = _viagem_do_motorista(user_id, viagem_id, EM_PERCURSO)
    atual = _ponto_atual(viagem)
    if not atual:
        raise ValidationError("Não há parada em atendimento nesta viagem")

    with transactional():
        registro = _registro_por_token(qr_token, viagem)
        _conferir(registro, atual.ponto_id)
        resultado = _registrar_embarque(registro, _aware(ocorrido_em))

    resultado["manual"] = False
    return resultado


def confirmar_manual(
    user_id: IdLike,
    viagem_id: IdLike,
    aluno_id: IdLike,
    ocorrido_em: datetime | None = None,
) -> dict[str, Any]:
    """RF-17 fallback: falhou a leitura, o motorista acha o aluno na lista do ponto.

    Sem a conferência de fotografia (descopada) este caminho não tem nenhuma
    verificação de identidade por trás: vale a palavra do motorista. Por isso
    cada uso fica registrado como ocorrência, para o gestor auditar.
    """
    viagem = _viagem_do_motorista(user_id, viagem_id, EM_PERCURSO)
    atual = _ponto_atual(viagem)
    if not atual:
        raise ValidationError("Não há parada em atendimento nesta viagem")

    with transactional():
        resultado = _embarque_manual(viagem, aluno_id, atual.ponto_id, _aware(ocorrido_em), user_id)

    return resultado


def _embarque_manual(
    viagem: Viagem,
    aluno_id: IdLike,
    ponto_esperado: uuid.UUID | None,
    momento: datetime,
    motorista_id: IdLike,
) -> dict[str, Any]:
    registro = db.session.get(AlunosConfirmados, (viagem.id, _uuid(aluno_id, "ID do aluno")))
    if not registro:
        raise EmbarqueRecusado(
            "Passageiro não consta na lista de embarque desta viagem", "PASSAGEIRO_NAO_PREVISTO"
        )

    _conferir(registro, ponto_esperado)
    resultado = _registrar_embarque(registro, momento)

    # ponytail: o "foi manual" mora numa ocorrência em vez de numa coluna nova —
    # o esquema está fechado e a tabela existe justamente para registrar
    # desvios de operação. Vira coluna se o dashboard precisar contar isso.
    db.session.add(
        Ocorrencia(
            autor_id=_uuid(motorista_id, "ID do motorista"),
            viagem_id=viagem.id,
            tipo=TipoOcorrencia.OUTRO,
            status=StatusOcorrencia.RESOLVIDA,
            descricao=(
                f"Embarque manual (falha de leitura do QR) do aluno {registro.aluno_id} "
                f"no ponto {registro.ponto_embarque_id}. Sem conferência de identidade."
            ),
        )
    )

    resultado["manual"] = True
    return resultado


# ==========================================
# RF-18 — sincronização em lote da fila offline
# ==========================================


def sincronizar(
    user_id: IdLike, viagem_id: IdLike, eventos: list[dict[str, Any]]
) -> dict[str, Any]:
    """RF-18: aplica a fila que o app do motorista acumulou sem rede.

    Cada evento é aplicado na própria transação, e o resultado vem por evento:
    um evento inválido não derruba o lote, e o app sabe exatamente o que pode
    tirar da fila (§2.3.2).

    Idempotência sem tabela de eventos: o efeito de cada evento é uma mudança
    de estado que já é observável (o passageiro embarcou, a parada foi
    transposta), então reenviar o lote encontra o estado pronto e não faz nada.
    A exceção é a posição, que é append-only: o `id` da linha de telemetria é
    derivado do identificador do evento (UUIDv5), e a chave primária cuida da
    duplicata.

    Eventos chegam fora de ordem e atrasados, então valem pelo carimbo que
    trazem, nunca pela hora em que chegaram.
    """
    viagem = _viagem_do_motorista(user_id, viagem_id, SINCRONIZAVEL)

    resultados = []
    for evento in eventos:
        evento_id = evento.get("evento_id")
        try:
            with transactional():
                situacao = _aplicar_evento(viagem, evento, user_id)
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


def _aplicar_evento(viagem: Viagem, evento: dict[str, Any], motorista_id: IdLike) -> str:
    tipo = evento.get("tipo")
    momento = _aware(evento.get("ocorrido_em"))
    ponto_id = evento.get("ponto_id")
    ponto_esperado = _uuid(ponto_id, "ID do ponto") if ponto_id else None

    if tipo == "EMBARQUE":
        registro = _registro_por_token(evento.get("qr_token") or "", viagem)
        if registro.embarcou:
            return "ja_aplicado"
        _conferir(registro, ponto_esperado)
        _registrar_embarque(registro, momento)
        return "aplicado"

    if tipo == "EMBARQUE_MANUAL":
        aluno_id = _uuid(evento.get("aluno_id") or "", "ID do aluno")
        ja_embarcado = db.session.get(AlunosConfirmados, (viagem.id, aluno_id))
        if ja_embarcado is not None and ja_embarcado.embarcou:
            return "ja_aplicado"
        _embarque_manual(viagem, aluno_id, ponto_esperado, momento, motorista_id)
        return "aplicado"

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


def _aplicar_posicao(viagem: Viagem, evento: dict[str, Any], momento: datetime) -> str:
    latitude, longitude = evento.get("latitude"), evento.get("longitude")
    if latitude is None or longitude is None:
        raise ValidationError("Evento de posição sem coordenadas")

    rastro_id = uuid.uuid5(uuid.NAMESPACE_OID, str(evento.get("evento_id")))
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

    # A posição corrente do veículo é a mais recente pelo carimbo do evento, e
    # não a que chegou por último — a fila offline vem fora de ordem.
    if viagem.motorista_gps_hora is None or viagem.motorista_gps_hora < momento:
        viagem.motorista_lat = latitude
        viagem.motorista_lon = longitude
        viagem.motorista_gps_hora = momento

    return "aplicado"
