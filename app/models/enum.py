import enum


class TipoInstituicao(enum.Enum):
    INSTITUTO_FEDERAL = "Instituto Federal"
    UNIVERSIDADE_PUBLICA = "Universidade Pública"
    UNIVERSIDADE_PRIVADA = "Universidade Privada"
    ESCOLA_PUBLICA = "Escola Pública"
    ESCOLA_PRIVADA = "Escola Privada"
    ESCOLA_COMUNITARIA = "Escola Comunitária"


class DiaDaSemana(enum.Enum):
    SEG = "SEG"
    TER = "TER"
    QUA = "QUA"
    QUI = "QUI"
    SEX = "SEX"
    SAB = "SAB"
    DOM = "DOM"


class SentidoViagem(enum.Enum):
    IDA = "IDA"
    VOLTA = "VOLTA"
    CIRCULAR = "CIRCULAR"


class StatusViagem(enum.Enum):
    """Ciclo da rodada sob demanda (DRT), mais os estados herdados.

    Fluxo corporativo (RF-10 a RF-16):
        OCIOSA -> SOLICITADA -> BUFFER_ABERTO -> EM_ROTA -> FINALIZADA

    AGENDADA/EM_ANDAMENTO pertencem ao fluxo de viagem programada herdado do
    produto municipal, que continua em uso. Removê-los é decisão de negócio,
    não limpeza — ver TODO.md.
    """

    OCIOSA = "OCIOSA"
    SOLICITADA = "SOLICITADA"
    BUFFER_ABERTO = "BUFFER_ABERTO"
    EM_ROTA = "EM_ROTA"

    AGENDADA = "AGENDADA"
    EM_ANDAMENTO = "EM_ANDAMENTO"
    FINALIZADA = "FINALIZADA"
    CANCELADA = "CANCELADA"


class StatusSolicitacao(enum.Enum):
    """Situação de um aluno dentro de uma rodada.

    INTERESSADO   solicitou o veículo (RF-10), ainda sem trajeto declarado
    CONFIRMADO    declarou origem/destino e passou na validação de capacidade
    NEGADO        trajeto recusado por pico de ocupação (RF-14) — conta como
                  negação por ponto no dashboard (RF-21)
    CANCELADO     desistiu durante o buffer, capacidade devolvida (RF-19)
    """

    INTERESSADO = "INTERESSADO"
    CONFIRMADO = "CONFIRMADO"
    NEGADO = "NEGADO"
    CANCELADO = "CANCELADO"


class UserRole(enum.Enum):
    USER = "USER"
    ALUNO = "ALUNO"
    MOTORISTA = "MOTORISTA"
    GESTOR = "GESTOR"

    def __str__(self):
        return self.value


class UserStatus(enum.Enum):
    """Situação da conta.

    REJECTED é distinto de DISABLED de propósito: sem ele, DISABLED acumularia
    três significados sem relação entre si — conta anonimizada por exclusão
    (RF-20), conta desativada pelo gestor, e candidato recusado no cadastro
    (RF-02). O painel do gestor não conseguiria distingui-los, e o recusado
    receberia no login uma mensagem sobre conta desativada em vez da recusa.
    """

    PENDING_SIGNUP = "PENDING_SIGNUP"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    REJECTED = "REJECTED"


class TipoOcorrencia(enum.Enum):
    ATRASO = "ATRASO"
    SUPERLOTACAO = "SUPERLOTACAO"
    COMPORTAMENTO = "COMPORTAMENTO"
    CANCELAMENTO = "CANCELAMENTO"
    OUTRO = "OUTRO"


class StatusOcorrencia(enum.Enum):
    ABERTA = "ABERTA"
    RESOLVIDA = "RESOLVIDA"
