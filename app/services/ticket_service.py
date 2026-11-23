"""Tickets de viagem: qual política vale, cobrar na confirmação e devolver.

A conta do saldo (recarga e janela) fica em `ticket_saldo.py`. Aqui entram o banco e as
regras de quando cobrar e quando devolver. Quem chama é responsável pela transação.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.core.transaction import transactional
from app.models.base import db
from app.models.enum import JanelaCota, SentidoViagem, TipoMovimentoTicket, TipoPoliticaTicket
from app.models.grupo import Grupo, GrupoMembro
from app.models.rota import HorarioRota, Rota
from app.models.ticket import MovimentoTicket, PoliticaTicket, SaldoTicket
from app.models.user import Aluno, User
from app.models.viagem import AlunosConfirmados
from app.services.notificacao_service import NotificacaoService
from app.services.ticket_saldo import FUSO, calcular_saldo, proxima_recarga_em
from app.services.user_service import _get_gestor_or_403
from app.utils import audit_logger, validate_uuid


def avisar_passageiro(usuario_id, titulo: str, mensagem: str) -> None:
    """Notificação interna, e push se houver token. Respeita quem desligou as notificações."""
    usuario = db.session.get(User, usuario_id)
    if usuario is None or not usuario.receber_notificacoes:
        return
    NotificacaoService._criar_notificacao_interna(usuario_id, titulo, mensagem)


def _recarrega(politica: PoliticaTicket) -> bool:
    if politica.tipo == TipoPoliticaTicket.COTA:
        return True
    tem_intervalo = (
        politica.recarga_intervalo_minutos is not None and politica.recarga_quantidade is not None
    )
    return politica.tipo == TipoPoliticaTicket.RECARGA and tem_intervalo


def _casa_com_a_viagem(politica: PoliticaTicket, viagem, horario) -> bool:
    """Vigência, rota, sentido e faixa de horário. Campo nulo vale para qualquer viagem."""
    if politica.vigencia_inicio is not None and viagem.data < politica.vigencia_inicio:
        return False
    if politica.vigencia_fim is not None and viagem.data > politica.vigencia_fim:
        return False
    if politica.rota_id is not None and politica.rota_id != horario.rota_id:
        return False
    if politica.sentido is not None and politica.sentido != horario.sentido:
        return False
    if politica.horario_de is not None and horario.horario_saida < politica.horario_de:
        return False
    if politica.horario_ate is not None and horario.horario_saida > politica.horario_ate:
        return False
    return True


def _mais_generosa(candidatas: list[PoliticaTicket]) -> PoliticaTicket:
    """ILIMITADO vence. Entre as demais, vence o maior teto."""
    escolhida = candidatas[0]
    for politica in candidatas:
        if politica.tipo == TipoPoliticaTicket.ILIMITADO:
            return politica
        if politica.teto > escolhida.teto:
            escolhida = politica
    return escolhida


def _grupos_do_passageiro(usuario_id) -> list:
    """Grupos ativos em que a pessoa tem vínculo aberto. Quem está num subgrupo conta no pai."""
    vinculos = GrupoMembro.query.filter(
        GrupoMembro.usuario_id == usuario_id, GrupoMembro.data_fim.is_(None)
    ).all()

    ids: list = []
    for vinculo in vinculos:
        grupo = db.session.get(Grupo, vinculo.grupo_id)
        if grupo is None or not grupo.ativo:
            continue
        if grupo.id not in ids:
            ids.append(grupo.id)
        if grupo.grupo_pai_id is not None and grupo.grupo_pai_id not in ids:
            ids.append(grupo.grupo_pai_id)
    return ids


def _politicas_por_nivel(aluno) -> list[list[PoliticaTicket]]:
    """Políticas do passageiro na ordem de precedência: pessoa, grupo, organização."""
    da_pessoa = PoliticaTicket.query.filter_by(usuario_id=aluno.usuario_id).all()

    do_grupo: list[PoliticaTicket] = []
    grupo_ids = _grupos_do_passageiro(aluno.usuario_id)
    if grupo_ids:
        do_grupo = PoliticaTicket.query.filter(PoliticaTicket.grupo_id.in_(grupo_ids)).all()

    da_organizacao = PoliticaTicket.query.filter(
        PoliticaTicket.organizacao_id == aluno.organizacao_id,
        PoliticaTicket.grupo_id.is_(None),
        PoliticaTicket.usuario_id.is_(None),
    ).all()

    return [da_pessoa, do_grupo, da_organizacao]


def escolher_politica(aluno, viagem, horario) -> PoliticaTicket | None:
    """Vale o primeiro nível que tem política casando com a viagem."""
    for nivel in _politicas_por_nivel(aluno):
        candidatas: list[PoliticaTicket] = []
        for politica in nivel:
            if _casa_com_a_viagem(politica, viagem, horario):
                candidatas.append(politica)
        if candidatas:
            return _mais_generosa(candidatas)
    return None


def _saldo_atual(usuario_id, politica: PoliticaTicket, agora: datetime) -> SaldoTicket:
    """Linha de saldo travada para escrita, já com a recarga ou a janela aplicada."""
    saldo = db.session.get(SaldoTicket, (usuario_id, politica.id), with_for_update=True)
    if saldo is None:
        saldo = SaldoTicket(
            usuario_id=usuario_id,
            politica_id=politica.id,
            quantidade=politica.teto,
            bonus=0,
            referencia_em=agora,
        )
        db.session.add(saldo)
        return saldo

    quantidade, referencia_em = calcular_saldo(
        politica, saldo.quantidade, saldo.referencia_em, agora
    )
    saldo.quantidade = quantidade
    saldo.referencia_em = referencia_em
    return saldo


def registrar_movimento(
    usuario_id, politica_id, viagem_id, tipo: TipoMovimentoTicket, quantidade: int
) -> None:
    db.session.add(
        MovimentoTicket(
            usuario_id=usuario_id,
            politica_id=politica_id,
            viagem_id=viagem_id,
            tipo=tipo,
            quantidade=quantidade,
        )
    )


def _inicio_da_viagem(viagem, horario) -> datetime:
    return datetime.combine(viagem.data, horario.horario_saida, FUSO)


def _validar_antecedencia(politica: PoliticaTicket, inicio: datetime, agora: datetime) -> None:
    faltam = inicio - agora
    minimo = politica.antecedencia_min_horas
    if minimo is not None and faltam < timedelta(hours=minimo):
        raise ConflictError(f"Esta viagem só aceita confirmação com {minimo}h de antecedência")
    maximo = politica.antecedencia_max_dias
    if maximo is not None and faltam > timedelta(days=maximo):
        raise ConflictError(f"Esta viagem só aceita confirmação até {maximo} dias antes")


def _tirar(saldo: SaldoTicket, politica: PoliticaTicket, quantidade: int, agora: datetime) -> int:
    """Tira do bônus primeiro e depois da quantidade. Devolve quanto saiu de fato."""
    tirado = min(quantidade, saldo.bonus + saldo.quantidade)
    estava_cheio = saldo.quantidade >= politica.teto

    do_bonus = min(saldo.bonus, tirado)
    saldo.bonus -= do_bonus
    saldo.quantidade -= tirado - do_bonus

    # O relógio da recarga recomeça quando o primeiro ticket sai de um saldo cheio.
    if estava_cheio and saldo.quantidade < politica.teto:
        saldo.referencia_em = agora
    return tirado


def cobrar_confirmacao(aluno, viagem, horario, registro: AlunosConfirmados, agora: datetime):
    """Gasta os tickets da viagem. Sem política aplicável, não cobra nada."""
    if registro.politica_ticket_id is not None:
        # Já pagou esta viagem. Confirmar de novo não cobra outra vez.
        return

    politica = escolher_politica(aluno, viagem, horario)
    if politica is None:
        return

    _validar_antecedencia(politica, _inicio_da_viagem(viagem, horario), agora)

    if politica.tipo == TipoPoliticaTicket.ILIMITADO:
        registro.politica_ticket_id = politica.id
        registro.tickets_gastos = 0
        return

    custo = viagem.custo_tickets
    saldo = _saldo_atual(aluno.usuario_id, politica, agora)
    if saldo.bonus + saldo.quantidade < custo:
        raise ConflictError("Você não tem tickets suficientes para esta viagem")

    _tirar(saldo, politica, custo, agora)

    registro.politica_ticket_id = politica.id
    registro.tickets_gastos = custo
    registrar_movimento(aluno.usuario_id, politica.id, viagem.id, TipoMovimentoTicket.GASTO, custo)

    if saldo.quantidade + saldo.bonus == 0:
        # A tarefa de recarga avisa quando voltar a ter ticket.
        saldo.aguardando_aviso = _recarrega(politica)
        avisar_passageiro(
            aluno.usuario_id,
            "Seus tickets acabaram",
            f"Você usou o último ticket da política {politica.nome}.",
        )


def devolver_tickets(registro: AlunosConfirmados, viagem, agora: datetime) -> None:
    """Devolve o que a confirmação pagou. A parte que passa do teto vai para o bônus."""
    if registro.politica_ticket_id is None:
        return

    politica = db.session.get(PoliticaTicket, registro.politica_ticket_id)
    gastos = registro.tickets_gastos
    registro.politica_ticket_id = None
    registro.tickets_gastos = 0
    if politica is None or gastos == 0:
        return

    saldo = _saldo_atual(registro.aluno_id, politica, agora)
    cabe_na_quantidade = max(politica.teto - saldo.quantidade, 0)
    para_a_quantidade = min(gastos, cabe_na_quantidade)
    saldo.quantidade += para_a_quantidade
    saldo.bonus += gastos - para_a_quantidade
    saldo.aguardando_aviso = False
    registrar_movimento(
        registro.aluno_id, politica.id, viagem.id, TipoMovimentoTicket.DEVOLUCAO, gastos
    )


def devolver_ao_desmarcar(registro: AlunosConfirmados, viagem, agora: datetime) -> None:
    """Passageiro desmarca. Se faltar menos que o prazo da política, o ticket se perde."""
    if registro.politica_ticket_id is None:
        return

    politica = db.session.get(PoliticaTicket, registro.politica_ticket_id)
    horario = db.session.get(HorarioRota, viagem.horario_rota_id)
    prazo = politica.cancelamento_prazo_horas if politica is not None else None
    if prazo is not None and horario is not None:
        faltam = _inicio_da_viagem(viagem, horario) - agora
        if faltam < timedelta(hours=prazo):
            registro.politica_ticket_id = None
            registro.tickets_gastos = 0
            return

    devolver_tickets(registro, viagem, agora)


def devolver_a_todos_os_confirmados(viagem, agora: datetime) -> None:
    """Viagem cancelada pelo gestor: todo mundo recupera o que pagou."""
    registros = AlunosConfirmados.query.filter(
        AlunosConfirmados.viagem_id == viagem.id,
        AlunosConfirmados.politica_ticket_id.isnot(None),
    ).all()
    for registro in registros:
        devolver_tickets(registro, viagem, agora)


def _registrar_no_show(registro: AlunosConfirmados, politica: PoliticaTicket, viagem, agora):
    """Quem confirmou e não embarcou perde o ticket gasto e paga a penalidade da política."""
    descontado = 0
    if politica.tipo != TipoPoliticaTicket.ILIMITADO and politica.no_show_penalidade > 0:
        saldo = _saldo_atual(registro.aluno_id, politica, agora)
        descontado = _tirar(saldo, politica, politica.no_show_penalidade, agora)
    registrar_movimento(
        registro.aluno_id, politica.id, viagem.id, TipoMovimentoTicket.NO_SHOW, descontado
    )
    mensagem = "Você confirmou a viagem e não embarcou, então o ticket não volta."
    if descontado > 0:
        mensagem += f" Foram descontados mais {descontado} ticket(s) de penalidade."
    avisar_passageiro(registro.aluno_id, "Viagem sem embarque", mensagem)


def tratar_tickets_ao_finalizar(viagem, agora: datetime) -> None:
    """Viagem finalizada. Quem embarcou recebe de volta se a política devolve ao finalizar.
    Quem confirmou e não embarcou é registrado como no-show."""
    registros = AlunosConfirmados.query.filter(
        AlunosConfirmados.viagem_id == viagem.id,
        AlunosConfirmados.confirmacao.is_(True),
        AlunosConfirmados.politica_ticket_id.isnot(None),
    ).all()
    for registro in registros:
        politica = db.session.get(PoliticaTicket, registro.politica_ticket_id)
        if politica is None:
            continue
        if not registro.embarcou:
            _registrar_no_show(registro, politica, viagem, agora)
        elif politica.devolve_ao_finalizar:
            devolver_tickets(registro, viagem, agora)


# ─── Políticas (gestor) ────────────────────────────────────────────────────────

CAMPOS_SIMPLES = (
    "nome",
    "vigencia_inicio",
    "vigencia_fim",
    "teto",
    "recarga_quantidade",
    "recarga_intervalo_minutos",
    "recarga_dias_semana",
    "janela_horas",
    "devolve_ao_finalizar",
    "no_show_penalidade",
    "cancelamento_prazo_horas",
    "antecedencia_min_horas",
    "antecedencia_max_dias",
    "horario_de",
    "horario_ate",
)


def _politica_da_organizacao(gestor, politica_id: str) -> PoliticaTicket:
    politica = db.session.get(PoliticaTicket, validate_uuid(politica_id, "Política"))
    if politica is None or str(politica.organizacao_id) != str(gestor.organizacao_id):
        raise NotFoundError("Política não encontrada")
    return politica


def _exigir_positivo(valor, nome: str) -> None:
    if valor is None or valor < 1:
        raise ValidationError(f"{nome} precisa ser um número maior que zero")


def _nao_pode_ter(politica: PoliticaTicket, campos: tuple[str, ...], tipo: str) -> None:
    for campo in campos:
        if getattr(politica, campo) is not None:
            raise ValidationError(f"O campo {campo} não vale para política {tipo}")


def _validar_regras_do_tipo(politica: PoliticaTicket) -> None:
    if politica.tipo == TipoPoliticaTicket.ILIMITADO:
        _nao_pode_ter(
            politica,
            (
                "teto",
                "recarga_quantidade",
                "recarga_intervalo_minutos",
                "recarga_dias_semana",
                "janela",
                "janela_horas",
            ),
            "ILIMITADO",
        )
        return

    _exigir_positivo(politica.teto, "O teto")

    if politica.tipo == TipoPoliticaTicket.RECARGA:
        _nao_pode_ter(politica, ("janela", "janela_horas"), "RECARGA")
        tem_quantidade = politica.recarga_quantidade is not None
        tem_intervalo = politica.recarga_intervalo_minutos is not None
        if tem_quantidade != tem_intervalo:
            raise ValidationError(
                "Informe a quantidade e o intervalo da recarga, ou nenhum dos dois"
            )
        if tem_quantidade:
            _exigir_positivo(politica.recarga_quantidade, "A quantidade da recarga")
            _exigir_positivo(politica.recarga_intervalo_minutos, "O intervalo da recarga")
        dias = politica.recarga_dias_semana
        if dias is not None:
            if len(dias) == 0:
                raise ValidationError("Informe ao menos um dia da semana ou deixe nulo")
            for dia in dias:
                if dia < 0 or dia > 6:
                    raise ValidationError("Os dias da semana vão de 0 (segunda) a 6 (domingo)")
        return

    # COTA
    _nao_pode_ter(
        politica,
        ("recarga_quantidade", "recarga_intervalo_minutos", "recarga_dias_semana"),
        "COTA",
    )
    if politica.janela is None:
        raise ValidationError("A política COTA precisa de uma janela")
    if politica.janela == JanelaCota.HORAS:
        _exigir_positivo(politica.janela_horas, "O tamanho da janela em horas")
    elif politica.janela_horas is not None:
        raise ValidationError("janela_horas só vale com a janela HORAS")


def _validar_alvo_e_escopo(politica: PoliticaTicket, organizacao_id) -> None:
    if politica.grupo_id is not None and politica.usuario_id is not None:
        raise ValidationError("A política vale para um grupo ou para uma pessoa, nunca os dois")

    if politica.grupo_id is not None:
        grupo = db.session.get(Grupo, politica.grupo_id)
        if grupo is None or grupo.organizacao_id != organizacao_id:
            raise NotFoundError("Grupo não encontrado")

    if politica.usuario_id is not None:
        aluno = db.session.get(Aluno, politica.usuario_id)
        if aluno is None or aluno.organizacao_id != organizacao_id:
            raise NotFoundError("Passageiro não encontrado")

    if politica.rota_id is not None:
        rota = db.session.get(Rota, politica.rota_id)
        if rota is None or rota.organizacao_id != organizacao_id:
            raise NotFoundError("Rota não encontrada")


def _validar_politica(politica: PoliticaTicket, organizacao_id) -> None:
    _validar_regras_do_tipo(politica)
    _validar_alvo_e_escopo(politica, organizacao_id)

    inicio, fim = politica.vigencia_inicio, politica.vigencia_fim
    if inicio is not None and fim is not None and fim < inicio:
        raise ValidationError("vigencia_fim não pode ser antes de vigencia_inicio")
    de, ate = politica.horario_de, politica.horario_ate
    if de is not None and ate is not None and ate < de:
        raise ValidationError("horario_ate não pode ser antes de horario_de")

    for campo in ("no_show_penalidade", "cancelamento_prazo_horas", "antecedencia_min_horas"):
        valor = getattr(politica, campo)
        if valor is not None and valor < 0:
            raise ValidationError(f"{campo} não pode ser negativo")
    if politica.antecedencia_max_dias is not None:
        _exigir_positivo(politica.antecedencia_max_dias, "antecedencia_max_dias")


def _copiar_campos(politica: PoliticaTicket, dados: dict[str, Any]) -> None:
    for campo in CAMPOS_SIMPLES:
        if campo in dados:
            setattr(politica, campo, dados[campo])
    if "tipo" in dados:
        politica.tipo = TipoPoliticaTicket(dados["tipo"])
    if "janela" in dados:
        janela = dados["janela"]
        politica.janela = JanelaCota(janela) if janela is not None else None
    if "sentido" in dados:
        sentido = dados["sentido"]
        politica.sentido = SentidoViagem(sentido) if sentido is not None else None
    if "rota_id" in dados:
        rota_id = dados["rota_id"]
        politica.rota_id = validate_uuid(rota_id, "Rota") if rota_id is not None else None


def criar_politica(gestor_id: str, dados: dict[str, Any]) -> PoliticaTicket:
    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem criar políticas de ticket")

    politica = PoliticaTicket(organizacao_id=gestor.organizacao_id)
    if dados.get("grupo_id") is not None:
        politica.grupo_id = validate_uuid(dados["grupo_id"], "Grupo")
    if dados.get("usuario_id") is not None:
        politica.usuario_id = validate_uuid(dados["usuario_id"], "Passageiro")
    _copiar_campos(politica, dados)
    _validar_politica(politica, gestor.organizacao_id)

    with transactional():
        db.session.add(politica)

    audit_logger.log_user_action(
        action="criar_politica_ticket",
        user_id=gestor_id,
        resource_type="politica_ticket",
        resource_id=str(politica.id),
    )
    return politica


def listar_politicas(gestor_id: str, grupo_id: str | None, usuario_id: str | None):
    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem listar políticas de ticket")
    consulta = PoliticaTicket.query.filter_by(organizacao_id=gestor.organizacao_id)
    if grupo_id is not None:
        consulta = consulta.filter_by(grupo_id=validate_uuid(grupo_id, "Grupo"))
    if usuario_id is not None:
        consulta = consulta.filter_by(usuario_id=validate_uuid(usuario_id, "Passageiro"))
    return consulta.order_by(PoliticaTicket.nome).all()


def obter_politica(gestor_id: str, politica_id: str) -> PoliticaTicket:
    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem ver políticas de ticket")
    return _politica_da_organizacao(gestor, politica_id)


def atualizar_politica(gestor_id: str, politica_id: str, dados: dict[str, Any]) -> PoliticaTicket:
    """Muda só os campos enviados. O alvo (organização, grupo ou pessoa) não muda."""
    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem editar políticas de ticket")
    politica = _politica_da_organizacao(gestor, politica_id)

    with transactional():
        _copiar_campos(politica, dados)
        _validar_politica(politica, gestor.organizacao_id)

    audit_logger.log_user_action(
        action="atualizar_politica_ticket",
        user_id=gestor_id,
        resource_type="politica_ticket",
        resource_id=str(politica.id),
    )
    return politica


def apagar_politica(gestor_id: str, politica_id: str) -> None:
    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem apagar políticas de ticket")
    politica = _politica_da_organizacao(gestor, politica_id)

    com_historico = MovimentoTicket.query.filter_by(politica_id=politica.id).first()
    if com_historico is not None:
        raise ConflictError("Política com histórico não se apaga. Encerre com vigencia_fim")

    with transactional():
        db.session.delete(politica)

    audit_logger.log_user_action(
        action="apagar_politica_ticket",
        user_id=gestor_id,
        resource_type="politica_ticket",
        resource_id=politica_id,
    )


# ─── Saldo do passageiro ───────────────────────────────────────────────────────


def listar_saldos_do_aluno(user_id: str) -> list[dict[str, Any]]:
    """Uma linha por política vigente do nível que vale para o passageiro. Só lê, não grava."""
    aluno = db.session.get(Aluno, user_id)
    if aluno is None:
        raise ForbiddenError("Acesso restrito a passageiros")

    agora = datetime.now(UTC)
    hoje = agora.astimezone(FUSO).date()

    politicas: list[PoliticaTicket] = []
    for nivel in _politicas_por_nivel(aluno):
        for politica in nivel:
            comecou = politica.vigencia_inicio is None or politica.vigencia_inicio <= hoje
            acabou = politica.vigencia_fim is not None and politica.vigencia_fim < hoje
            if comecou and not acabou:
                politicas.append(politica)
        if politicas:
            break

    linhas: list[dict[str, Any]] = []
    for politica in politicas:
        linha: dict[str, Any] = {
            "politica_id": str(politica.id),
            "nome": politica.nome,
            "tipo": politica.tipo.value,
            "teto": politica.teto,
            "quantidade": None,
            "bonus": 0,
            "proxima_recarga_em": None,
            "rota_id": str(politica.rota_id) if politica.rota_id else None,
            "sentido": politica.sentido.value if politica.sentido else None,
            "horario_de": politica.horario_de,
            "horario_ate": politica.horario_ate,
        }
        if politica.tipo != TipoPoliticaTicket.ILIMITADO:
            saldo = db.session.get(SaldoTicket, (aluno.usuario_id, politica.id))
            if saldo is None:
                quantidade, referencia_em, bonus = politica.teto, agora, 0
            else:
                quantidade, referencia_em = calcular_saldo(
                    politica, saldo.quantidade, saldo.referencia_em, agora
                )
                bonus = saldo.bonus
            linha["quantidade"] = quantidade
            linha["bonus"] = bonus
            linha["proxima_recarga_em"] = proxima_recarga_em(
                politica, quantidade, referencia_em, agora
            )
        linhas.append(linha)
    return linhas


# ─── Concessão manual e histórico ──────────────────────────────────────────────


def _membros_atuais(grupo: Grupo) -> list:
    """Quem tem vínculo aberto no grupo ou nos subgrupos dele."""
    grupo_ids = [grupo.id]
    for filho in Grupo.query.filter(Grupo.grupo_pai_id == grupo.id).all():
        grupo_ids.append(filho.id)

    vinculos = GrupoMembro.query.filter(
        GrupoMembro.grupo_id.in_(grupo_ids), GrupoMembro.data_fim.is_(None)
    ).all()
    usuario_ids: list = []
    for vinculo in vinculos:
        if vinculo.usuario_id not in usuario_ids:
            usuario_ids.append(vinculo.usuario_id)
    return usuario_ids


def conceder_tickets(gestor_id: str, dados: dict[str, Any]) -> dict[str, Any]:
    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem conceder tickets")
    politica = _politica_da_organizacao(gestor, dados["politica_id"])
    if politica.tipo == TipoPoliticaTicket.ILIMITADO:
        raise ValidationError("Política ILIMITADO não recebe concessão de tickets")

    usuario_id = dados.get("usuario_id")
    grupo_id = dados.get("grupo_id")
    if (usuario_id is None) == (grupo_id is None):
        raise ValidationError("Informe usuario_id ou grupo_id, só um dos dois")

    if usuario_id is not None:
        aluno = db.session.get(Aluno, validate_uuid(usuario_id, "Passageiro"))
        if aluno is None or aluno.organizacao_id != gestor.organizacao_id:
            raise NotFoundError("Passageiro não encontrado")
        destinatarios = [aluno.usuario_id]
    else:
        grupo = db.session.get(Grupo, validate_uuid(str(grupo_id), "Grupo"))
        if grupo is None or grupo.organizacao_id != gestor.organizacao_id:
            raise NotFoundError("Grupo não encontrado")
        destinatarios = _membros_atuais(grupo)

    quantidade = dados["quantidade"]
    agora = datetime.now(UTC)
    with transactional():
        for destinatario in destinatarios:
            saldo = _saldo_atual(destinatario, politica, agora)
            saldo.bonus += quantidade
            saldo.aguardando_aviso = False
            avisar_passageiro(
                destinatario,
                "Você recebeu tickets",
                f"A organização concedeu {quantidade} ticket(s) da política {politica.nome}.",
            )
            db.session.add(
                MovimentoTicket(
                    usuario_id=destinatario,
                    politica_id=politica.id,
                    tipo=TipoMovimentoTicket.CONCESSAO,
                    quantidade=quantidade,
                    motivo=dados.get("motivo"),
                    criado_por=gestor.id,
                )
            )

    audit_logger.log_user_action(
        action="conceder_tickets",
        user_id=gestor_id,
        resource_type="politica_ticket",
        resource_id=str(politica.id),
    )
    return {
        "politica_id": str(politica.id),
        "passageiros": len(destinatarios),
        "quantidade": quantidade,
    }


def _linhas_de_movimento(consulta) -> list[dict[str, Any]]:
    linhas: list[dict[str, Any]] = []
    for movimento, politica_nome, usuario_nome in consulta:
        linhas.append(
            {
                "id": str(movimento.id),
                "usuario_id": str(movimento.usuario_id),
                "usuario_nome": usuario_nome,
                "politica_id": str(movimento.politica_id),
                "politica_nome": politica_nome,
                "viagem_id": str(movimento.viagem_id) if movimento.viagem_id else None,
                "tipo": movimento.tipo.value,
                "quantidade": movimento.quantidade,
                "motivo": movimento.motivo,
                "criado_por": str(movimento.criado_por) if movimento.criado_por else None,
                "created_at": movimento.created_at,
            }
        )
    return linhas


def _consulta_de_movimentos():
    return (
        db.session.query(MovimentoTicket, PoliticaTicket.nome, User.nome)
        .join(PoliticaTicket, PoliticaTicket.id == MovimentoTicket.politica_id)
        .join(User, User.id == MovimentoTicket.usuario_id)
    )


def listar_movimentos(
    gestor_id: str, usuario_id: str | None, politica_id: str | None, limite: int
) -> list[dict[str, Any]]:
    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem ver o histórico de tickets")
    consulta = _consulta_de_movimentos().filter(
        PoliticaTicket.organizacao_id == gestor.organizacao_id
    )
    if usuario_id is not None:
        consulta = consulta.filter(
            MovimentoTicket.usuario_id == validate_uuid(usuario_id, "Passageiro")
        )
    if politica_id is not None:
        consulta = consulta.filter(
            MovimentoTicket.politica_id == validate_uuid(politica_id, "Política")
        )
    consulta = consulta.order_by(MovimentoTicket.created_at.desc()).limit(min(limite, 500))
    return _linhas_de_movimento(consulta.all())


def listar_movimentos_do_aluno(user_id: str, limite: int) -> list[dict[str, Any]]:
    aluno = db.session.get(Aluno, user_id)
    if aluno is None:
        raise ForbiddenError("Acesso restrito a passageiros")
    consulta = (
        _consulta_de_movimentos()
        .filter(MovimentoTicket.usuario_id == aluno.usuario_id)
        .order_by(MovimentoTicket.created_at.desc())
        .limit(min(limite, 500))
    )
    return _linhas_de_movimento(consulta.all())
