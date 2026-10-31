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


class TipoViagem(enum.Enum):
    FIXA = "FIXA"
    SOB_DEMANDA = "SOB_DEMANDA"


class StatusViagem(enum.Enum):
    AGENDADA = "AGENDADA"
    # Só rotas sob demanda: o aluno pediu e o motorista ainda não iniciou (RF-10).
    SOLICITADA = "SOLICITADA"
    # Só rotas sob demanda: motorista iniciou, alunos ainda podem entrar (RF-11).
    BUFFER_ABERTO = "BUFFER_ABERTO"
    # Também é o "Em rota" das viagens sob demanda.
    EM_ANDAMENTO = "EM_ANDAMENTO"
    FINALIZADA = "FINALIZADA"
    CANCELADA = "CANCELADA"


class StatusSolicitacao(enum.Enum):
    ATIVA = "ATIVA"
    CANCELADA = "CANCELADA"
    # Cancelou depois do início do percurso: no-show previsto (RF-19).
    DESISTENCIA = "DESISTENCIA"


class UserRole(enum.Enum):
    USER = "USER"
    ALUNO = "ALUNO"
    MOTORISTA = "MOTORISTA"
    GESTOR = "GESTOR"

    def __str__(self):
        return self.value


class UserStatus(enum.Enum):
    PENDING_SIGNUP = "PENDING_SIGNUP"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    DELETED = "DELETED"


class TipoOcorrencia(enum.Enum):
    ATRASO = "ATRASO"
    SUPERLOTACAO = "SUPERLOTACAO"
    COMPORTAMENTO = "COMPORTAMENTO"
    CANCELAMENTO = "CANCELAMENTO"
    OUTRO = "OUTRO"


class StatusOcorrencia(enum.Enum):
    ABERTA = "ABERTA"
    RESOLVIDA = "RESOLVIDA"
