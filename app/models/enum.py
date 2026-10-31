import enum


class TipoInstituicao(enum.Enum):
    """Tipo da instituição atendida.

    Os seis primeiros vêm do catálogo escolar herdado (EMEC/INEP). Os dois
    últimos existem porque uma implantação corporativa atende parques
    tecnológicos e centros de inovação, que não são escolas — enquadrá-los
    como universidade seria gravar dado errado só para caber no enum.
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
    # Só rotas sob demanda: o aluno pediu e o motorista ainda não iniciou (RF-10).
    SOLICITADA = "SOLICITADA"
    # Só rotas sob demanda: motorista iniciou, alunos ainda podem entrar (RF-11).
    BUFFER_ABERTO = "BUFFER_ABERTO"
    # Também é o "Em rota" das viagens sob demanda.
    EM_ANDAMENTO = "EM_ANDAMENTO"
    FINALIZADA = "FINALIZADA"
    CANCELADA = "CANCELADA"


class StatusSolicitacao(enum.Enum):
    """ATIVA sem pontos = interessado; ATIVA com pontos = lugar garantido (RF-13/14)."""

    ATIVA = "ATIVA"
    CANCELADA = "CANCELADA"
    # Cancelou depois do início do percurso: no-show previsto (RF-19).
    DESISTENCIA = "DESISTENCIA"
    # Trajeto recusado por lotação (RF-14). Conta nas negações por ponto (RF-21).
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


class NecessidadeAcessibilidade(enum.Enum):
    CADEIRA_DE_RODAS = "CADEIRA_DE_RODAS"
    MOBILIDADE_REDUZIDA = "MOBILIDADE_REDUZIDA"
    DEFICIENCIA_VISUAL = "DEFICIENCIA_VISUAL"
    DEFICIENCIA_AUDITIVA = "DEFICIENCIA_AUDITIVA"
    DEFICIENCIA_INTELECTUAL = "DEFICIENCIA_INTELECTUAL"
    OUTRA = "OUTRA"
