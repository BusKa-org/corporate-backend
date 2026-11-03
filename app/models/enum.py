import enum


class TipoInstituicao(enum.Enum):
    """Type of institution served.

    The first six come from the inherited school catalog (EMEC/INEP). The last two
    exist because a corporate deployment serves tech parks and innovation centers,
    which are not schools; filing them as universities would store wrong data.
    """

    INSTITUTO_FEDERAL = "Instituto Federal"
    UNIVERSIDADE_PUBLICA = "Universidade Pública"
    UNIVERSIDADE_PRIVADA = "Universidade Privada"
    ESCOLA_PUBLICA = "Escola Pública"
    ESCOLA_PRIVADA = "Escola Privada"
    ESCOLA_COMUNITARIA = "Escola Comunitária"
    PARQUE_TECNOLOGICO = "Parque Tecnológico"
    CENTRO_INOVACAO = "Centro de Inovação"


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
    # On-demand routes only: the student requested and the driver has not started yet (RF-10).
    SOLICITADA = "SOLICITADA"
    # On-demand routes only: the driver started, students can still join (RF-11).
    BUFFER_ABERTO = "BUFFER_ABERTO"
    # Also the "En route" state of on-demand trips.
    EM_ANDAMENTO = "EM_ANDAMENTO"
    FINALIZADA = "FINALIZADA"
    CANCELADA = "CANCELADA"


class StatusSolicitacao(enum.Enum):
    """ATIVA without stops = interested; ATIVA with stops = seat guaranteed (RF-13/14)."""

    ATIVA = "ATIVA"
    CANCELADA = "CANCELADA"
    # Cancelled after the route started: expected no-show (RF-19).
    DESISTENCIA = "DESISTENCIA"
    # Route rejected because the vehicle is full (RF-14). Counts in the per-stop denials (RF-21).
    NEGADA = "NEGADA"


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


class StatusMotorista(enum.Enum):
    ATIVO = "ATIVO"
    EM_ROTA = "EM_ROTA"
    EM_DESCANSO_OBRIGATORIO = "EM_DESCANSO_OBRIGATORIO"


class NecessidadeAcessibilidade(enum.Enum):
    CADEIRA_DE_RODAS = "CADEIRA_DE_RODAS"
    MOBILIDADE_REDUZIDA = "MOBILIDADE_REDUZIDA"
    DEFICIENCIA_VISUAL = "DEFICIENCIA_VISUAL"
    DEFICIENCIA_AUDITIVA = "DEFICIENCIA_AUDITIVA"
    DEFICIENCIA_INTELECTUAL = "DEFICIENCIA_INTELECTUAL"
    OUTRA = "OUTRA"
