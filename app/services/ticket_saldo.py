"""Conta do saldo de tickets. Funções puras, sem banco: recebem a política e o saldo salvo
e devolvem o saldo de agora. A recarga nunca depende de job agendado.

Política ILIMITADO não passa por aqui, quem chama trata antes.
"""

from datetime import date, datetime, time, timedelta, timezone

from app.models.enum import JanelaCota, TipoPoliticaTicket

# shortcut: Fortaleza fixa em UTC-3 (sem horário de verão desde 2019), trocar por zoneinfo
# se a plataforma passar a atender outro fuso.
FUSO = timezone(timedelta(hours=-3))


def _dia_permitido(politica, instante: datetime) -> bool:
    dias = politica.recarga_dias_semana
    if dias is None:
        return True
    return instante.astimezone(FUSO).weekday() in dias


def _inicio_da_janela(politica, agora: datetime) -> datetime:
    local = agora.astimezone(FUSO)
    meia_noite = datetime.combine(local.date(), time.min, FUSO)

    if politica.janela == JanelaCota.DIA:
        return meia_noite
    if politica.janela == JanelaCota.SEMANA:
        return meia_noite - timedelta(days=local.weekday())
    if politica.janela == JanelaCota.MES:
        return meia_noite.replace(day=1)

    # HORAS: janelas seguidas contadas a partir da âncora.
    janela = timedelta(hours=politica.janela_horas)
    if politica.vigencia_inicio is not None:
        dia_ancora: date = politica.vigencia_inicio
    else:
        dia_ancora = politica.created_at.astimezone(FUSO).date()
    ancora = datetime.combine(dia_ancora, time.min, FUSO)
    if agora <= ancora:
        return ancora
    janelas_passadas = (agora - ancora) // janela
    return ancora + janelas_passadas * janela


def _fim_da_janela(politica, inicio: datetime) -> datetime:
    if politica.janela == JanelaCota.DIA:
        return inicio + timedelta(days=1)
    if politica.janela == JanelaCota.SEMANA:
        return inicio + timedelta(days=7)
    if politica.janela == JanelaCota.MES:
        # Dia 28 + 4 dias cai sempre no mês seguinte.
        proximo_mes = inicio.replace(day=28) + timedelta(days=4)
        return proximo_mes.replace(day=1)
    return inicio + timedelta(hours=politica.janela_horas)


def _recarregar(politica, quantidade: int, referencia_em: datetime, agora: datetime):
    teto = politica.teto
    quantidade = min(quantidade, teto)
    if politica.recarga_intervalo_minutos is None or politica.recarga_quantidade is None:
        return quantidade, referencia_em
    if politica.recarga_dias_semana is not None and len(politica.recarga_dias_semana) == 0:
        return quantidade, referencia_em
    if quantidade >= teto:
        # Cheio. O relógio recomeça quando o primeiro ticket sai (quem gasta ajusta a referência).
        return quantidade, referencia_em

    intervalo = timedelta(minutes=politica.recarga_intervalo_minutos)
    instante = referencia_em + intervalo
    while instante <= agora and quantidade < teto:
        if _dia_permitido(politica, instante):
            quantidade = min(teto, quantidade + politica.recarga_quantidade)
        referencia_em = instante
        instante = instante + intervalo
    return quantidade, referencia_em


def calcular_saldo(politica, quantidade: int, referencia_em: datetime, agora: datetime):
    """Devolve (quantidade, referencia_em) de agora. Quem chama grava o resultado."""
    if politica.tipo == TipoPoliticaTicket.COTA:
        inicio = _inicio_da_janela(politica, agora)
        if referencia_em < inicio:
            return politica.teto, inicio
        return min(quantidade, politica.teto), referencia_em
    return _recarregar(politica, quantidade, referencia_em, agora)


def proxima_recarga_em(politica, quantidade: int, referencia_em: datetime, agora: datetime):
    """Quando o saldo volta a crescer. Nulo se já está cheio ou se nunca recarrega.
    Recebe o saldo já calculado por `calcular_saldo`."""
    if politica.tipo == TipoPoliticaTicket.COTA:
        if quantidade >= politica.teto:
            return None
        return _fim_da_janela(politica, _inicio_da_janela(politica, agora))

    sem_recarga = politica.recarga_intervalo_minutos is None or politica.recarga_quantidade is None
    if sem_recarga or quantidade >= politica.teto:
        return None
    if politica.recarga_dias_semana is not None and len(politica.recarga_dias_semana) == 0:
        return None

    intervalo = timedelta(minutes=politica.recarga_intervalo_minutos)
    instante = referencia_em + intervalo
    while instante <= agora or not _dia_permitido(politica, instante):
        instante = instante + intervalo
    return instante
