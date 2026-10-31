"""RF-15 a RF-18 — credencial de embarque, roteiro do motorista e sincronização.

A credencial é a `CredencialEmbarque`: o app do aluno busca o segredo em
`GET /v1/viagens/<id>/credencial-embarque` e desenha o QR `<credencial_id>.<codigo>`,
com um código que muda a cada passo (`credencial_embarque_service`). Este módulo
a emite na consolidação do buffer e concentra as regras que a consomem no
embarque.

Embarque por QR em dois passos (RF-17): a conferência confere a credencial e
devolve o passageiro com a foto, sem embarcar ninguém; o embarque só é
registrado quando o motorista confirma que a foto é da pessoa à sua frente.
Se não for, ele recusa, fica uma ocorrência para o gestor e a credencial fica
recusada: aquele QR não embarca mais ninguém nesta viagem. O passageiro real
embarca pelo fallback manual, conferido pela foto da lista do ponto.
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

# Estados em que o veículo já saiu e o motorista opera o roteiro.
EM_PERCURSO = (StatusViagem.EM_ANDAMENTO,)
# A sincronização (RF-18) também aceita a viagem já encerrada: a fila offline
# pode chegar depois que o motorista finalizou o percurso.
SINCRONIZAVEL = EM_PERCURSO + (StatusViagem.FINALIZADA,)

# EMBARQUE_CONFIRMADO é o QR conferido e confirmado pelo motorista; RECUSA é o QR
# recusado por ele. EMBARQUE é o tipo antigo, de antes da conferência da foto: fica
# aceito no esquema só para ser recusado evento a evento com EVENTO_DESCONTINUADO.
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
    """Quem o motorista espera embarcar: confirmados que não desistiram (RF-19)."""
    return [c for c in viagem.alunos_confirmados if c.confirmacao]


def _foto(registro: AlunosConfirmados) -> dict[str, Any]:
    foto_url = registro.aluno.foto_url if registro.aluno else None
    return {"foto_url": foto_url, "sem_foto": foto_url is None}


def _ponto_atual(viagem: Viagem) -> ViagemPonto | None:
    """A parada que o veículo está atendendo: a primeira ainda não transposta."""
    return next((vp for vp in viagem.pontos_visitados if not vp.visitado), None)


# ==========================================
# RF-15 — emissão das credenciais
# ==========================================


def consolidar_embarque(viagem: Viagem, confirmados: list[AlunosConfirmados]) -> int:
    """Emite as credenciais da rodada e materializa o roteiro do motorista.

    Chamada pela consolidação do buffer (RF-15), dentro da transação dela. Uma
    credencial nova por passageiro confirmado: vale só para este aluno, nesta
    viagem e neste ponto de embarque, e nunca é reaproveitada.
    """
    _materializar_pontos(viagem)

    for registro in confirmados:
        credencial_embarque_service.criar_credencial(
            viagem.id, registro.aluno_id, registro.ponto_embarque_id
        )

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


# ==========================================
# RF-16 — roteiro do motorista
# ==========================================


def roteiro(user_id: IdLike, viagem_id: IdLike) -> dict[str, Any]:
    """RF-16: paradas em ordem, com quantos embarcam e desembarcam em cada uma.

    Vai junto a matriz de permissões (credencial e foto de cada passageiro por
    ponto), que é o que o app baixa antes da partida para conferir embarques
    sem rede (RF-18). É também a lista que o motorista usa no fallback manual.
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
                # O segredo deixa o app conferir o código do QR sem rede (RF-18).
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


def _tolerancia() -> timedelta:
    return timedelta(seconds=current_app.config["SYNC_TOLERANCIA_SEGUNDOS"])


def _credencial_do_qr(
    qr: str, viagem: Viagem, momento: datetime, conferir_codigo: bool = True
) -> CredencialEmbarque:
    """Regras da credencial lida, as mesmas online e offline.

    `momento` é o relógio do servidor online, ou o carimbo já limitado do evento
    offline. A recusa não confere o código: ela só fecha a porta, e o código
    pode ter girado enquanto o motorista olhava a foto.
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
    """Trava as credenciais e depois a linha do passageiro, sempre nessa ordem.

    Duas confirmações simultâneas do mesmo passageiro se enfileiram aqui: a
    segunda lê `embarcou`/`usado` já gravados pela primeira. A ordem fixa evita
    deadlock entre o QR, o manual e a fila offline.
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
    """Recusas do RF-17, cada uma com seu código.

    `credencial` nula é o fallback manual, que não tem QR lido por trás.
    `ponto_esperado` nulo dispensa a conferência de ponto: é o caso do evento
    offline que não informa em qual parada o motorista estava.
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

    # A credencial é de uso único, inclusive quando o embarque foi manual.
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
    """Confirma o embarque por QR, online ou da fila offline.

    Com `ja_aplicado_ok` (fila offline reenviada), um passageiro que já embarcou
    devolve None em vez de recusar; uma credencial recusada recusa sempre.
    """
    credencial = _credencial_do_qr(qr, viagem, momento)
    registro = _travar_registro(viagem.id, credencial.aluno_id)

    if ja_aplicado_ok and registro is not None and registro.embarcou:
        if credencial.recusada_em is None:
            return None

    registro = _conferir(registro, credencial, ponto_esperado)

    # Sem foto não há o que conferir: o QR sozinho não embarca ninguém.
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
    """`POST .../validacao` antigo, que embarcava na leitura. Falha alto para o app velho."""
    raise EmbarqueRecusado(
        "Esta versão do app do motorista não é mais suportada. Atualize o app para "
        "conferir a foto do passageiro antes de confirmar o embarque.",
        "ENDPOINT_DESCONTINUADO",
        410,
    )


def checkin_embarque(user_id: IdLike, viagem_id: IdLike, qr: str) -> dict[str, Any]:
    """RF-17 passo 1: confere a credencial lida e devolve o passageiro com a foto.

    Só leitura: não embarca ninguém nem marca a credencial como usada. Uma
    credencial fora do roteiro é recusada aqui, sem mostrar foto (fluxo
    secundário 2). Sem foto cadastrada, volta `sem_foto` e o motorista segue
    pelo fallback manual.
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
    """RF-17 passo 2: a foto confere e o motorista confirma; o embarque é registrado.

    Refaz todas as conferências da leitura, com as linhas travadas: entre a
    leitura e a confirmação o mesmo QR pode ter sido usado em outro aparelho.
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
    """RF-17 fluxo secundário 1: a foto não é da pessoa e o motorista recusa.

    O embarque não é registrado e a credencial fica recusada: o mesmo QR não
    embarca mais ninguém nesta viagem, nem online nem pela fila offline. O
    passageiro real, se aparecer, embarca pelo fallback manual depois de o
    motorista conferir a foto da lista do ponto. A recusa vira ocorrência
    aberta para o gestor. Não há como desfazer a recusa pela API.
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
    """RF-17 fallback: falhou a leitura, o motorista acha o aluno na lista do ponto.

    O motorista confere o rosto pela foto da lista do ponto (o roteiro traz a
    foto de cada passageiro). Não há credencial lida por trás, então cada uso
    fica registrado como ocorrência, para o gestor auditar. É também o caminho
    do passageiro real depois de uma recusa e do aluno sem foto.
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

    Os eventos são aplicados em ordem de `ocorrido_em` (empate: ordem da fila),
    e os resultados saem nessa mesma ordem. Assim uma RECUSA anterior bloqueia o
    EMBARQUE_CONFIRMADO do mesmo QR que veio depois, no mesmo lote ou num próximo.

    Idempotência sem tabela de eventos: o efeito de cada evento é uma mudança
    de estado que já é observável (o passageiro embarcou, a parada foi
    transposta), então reenviar o lote encontra o estado pronto e não faz nada.
    As exceções são a posição e a recusa, que são append-only: o `id` da linha
    (telemetria ou ocorrência) é derivado do identificador do evento (UUIDv5),
    e a chave primária cuida da duplicata.

    Eventos chegam fora de ordem e atrasados, então valem pelo carimbo que
    trazem, nunca pela hora em que chegaram; um carimbo no futuro além da
    tolerância é recusado.
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
        ocorrencia_id = uuid.uuid5(uuid.NAMESPACE_OID, str(evento.get("evento_id")))
        if db.session.get(Ocorrencia, ocorrencia_id):
            return "ja_aplicado"
        credencial = _credencial_do_qr(
            evento.get("qr_token") or "", viagem, momento, conferir_codigo=False
        )
        registro = _travar_registro(viagem.id, credencial.aluno_id)
        if registro is None:
            raise EmbarqueRecusado(
                "Passageiro não consta na lista de embarque desta viagem",
                "PASSAGEIRO_NAO_PREVISTO",
            )
        # Sem `_conferir`: o embarque manual do passageiro real pode vir antes, e
        # a recusa ainda precisa chegar ao gestor e fechar o QR.
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
