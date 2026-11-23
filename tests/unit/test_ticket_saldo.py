from datetime import date, datetime, timedelta
from types import SimpleNamespace

from app.models.enum import JanelaCota, TipoPoliticaTicket
from app.services.ticket_saldo import FUSO, calcular_saldo, proxima_recarga_em


def _local(dia: int, hora: int, minuto: int = 0) -> datetime:
    """Instante em novembro de 2026, no fuso de Fortaleza. 20 é sexta, 23 é segunda."""
    return datetime(2026, 11, dia, hora, minuto, tzinfo=FUSO)


def _recarga(teto, quantidade=None, intervalo=None, dias=None):
    return SimpleNamespace(
        tipo=TipoPoliticaTicket.RECARGA,
        teto=teto,
        recarga_quantidade=quantidade,
        recarga_intervalo_minutos=intervalo,
        recarga_dias_semana=dias,
    )


def _cota(janela, teto=2, janela_horas=None, vigencia_inicio=None):
    return SimpleNamespace(
        tipo=TipoPoliticaTicket.COTA,
        teto=teto,
        janela=janela,
        janela_horas=janela_horas,
        vigencia_inicio=vigencia_inicio,
        created_at=_local(1, 12),
    )


# Os cinco casos da issue.


def test_uma_agendada_por_vez_nao_recarrega():
    politica = _recarga(teto=1)
    quantidade, _ = calcular_saldo(politica, 0, _local(20, 10), _local(25, 10))
    assert quantidade == 0


def test_uma_por_dia_de_segunda_a_sexta_pula_o_fim_de_semana():
    politica = _recarga(teto=1, quantidade=1, intervalo=24 * 60, dias=[0, 1, 2, 3, 4])
    gasto_na_sexta = _local(20, 10)

    sabado, _ = calcular_saldo(politica, 0, gasto_na_sexta, _local(21, 11))
    domingo, _ = calcular_saldo(politica, 0, gasto_na_sexta, _local(22, 11))
    segunda, _ = calcular_saldo(politica, 0, gasto_na_sexta, _local(23, 11))

    assert (sabado, domingo, segunda) == (0, 0, 1)


def test_evento_com_tres_tickets_e_sem_recarga():
    politica = _recarga(teto=3)
    quantidade, _ = calcular_saldo(politica, 1, _local(20, 10), _local(25, 10))
    assert quantidade == 1


def test_estilo_duolingo_recarrega_um_a_cada_duas_horas():
    politica = _recarga(teto=5, quantidade=1, intervalo=120)
    gasto = _local(23, 8)

    quantidade, referencia = calcular_saldo(politica, 0, gasto, _local(23, 13))

    assert quantidade == 2
    assert referencia == _local(23, 12)


def test_recarga_nunca_passa_do_teto():
    politica = _recarga(teto=5, quantidade=1, intervalo=120)
    quantidade, _ = calcular_saldo(politica, 3, _local(1, 8), _local(23, 8))
    assert quantidade == 5


def test_reduzir_o_teto_corta_o_saldo():
    politica = _recarga(teto=5, quantidade=1, intervalo=120)
    quantidade, _ = calcular_saldo(politica, 8, _local(23, 8), _local(23, 8, 30))
    assert quantidade == 5


def test_dias_vazios_nao_recarregam():
    politica = _recarga(teto=3, quantidade=1, intervalo=60, dias=[])
    quantidade, _ = calcular_saldo(politica, 0, _local(1, 8), _local(23, 8))
    assert quantidade == 0
    assert proxima_recarga_em(politica, 0, _local(1, 8), _local(23, 8)) is None


# COTA


def test_cota_por_dia_volta_a_encher_na_meia_noite():
    politica = _cota(JanelaCota.DIA)
    referencia = _local(22, 0)

    mesmo_dia = calcular_saldo(politica, 0, referencia, _local(22, 23, 59))
    dia_seguinte = calcular_saldo(politica, 0, referencia, _local(23, 0, 1))

    assert mesmo_dia == (0, referencia)
    assert dia_seguinte == (2, _local(23, 0))


def test_cota_por_semana_comeca_na_segunda():
    politica = _cota(JanelaCota.SEMANA)
    referencia = _local(16, 0)  # segunda da semana anterior

    domingo = calcular_saldo(politica, 0, referencia, _local(22, 20))
    segunda = calcular_saldo(politica, 0, referencia, _local(23, 1))

    assert domingo[0] == 0
    assert segunda == (2, _local(23, 0))


def test_cota_por_mes_comeca_no_dia_um():
    politica = _cota(JanelaCota.MES)
    referencia = _local(1, 0)

    quantidade, _ = calcular_saldo(politica, 0, referencia, _local(30, 23))
    assert quantidade == 0

    dezembro = datetime(2026, 12, 1, 0, 5, tzinfo=FUSO)
    quantidade, inicio = calcular_saldo(politica, 0, referencia, dezembro)
    assert quantidade == 2
    assert inicio == datetime(2026, 12, 1, tzinfo=FUSO)


def test_cota_por_horas_conta_a_partir_da_vigencia():
    politica = _cota(JanelaCota.HORAS, janela_horas=6, vigencia_inicio=date(2026, 11, 23))

    # Janelas: 00h-06h, 06h-12h, 12h-18h.
    quantidade, inicio = calcular_saldo(politica, 0, _local(23, 1), _local(23, 13))

    assert quantidade == 2
    assert inicio == _local(23, 12)


# Próxima recarga


def test_proxima_recarga_da_recarga_por_intervalo():
    politica = _recarga(teto=5, quantidade=1, intervalo=120)
    proxima = proxima_recarga_em(politica, 0, _local(23, 12), _local(23, 13))
    assert proxima == _local(23, 14)


def test_proxima_recarga_pula_dia_proibido():
    politica = _recarga(teto=1, quantidade=1, intervalo=24 * 60, dias=[0, 1, 2, 3, 4])
    proxima = proxima_recarga_em(politica, 0, _local(20, 10), _local(21, 11))
    assert proxima == _local(23, 10)


def test_sem_proxima_recarga_quando_cheio_ou_sem_recarga():
    com_recarga = _recarga(teto=3, quantidade=1, intervalo=60)
    sem_recarga = _recarga(teto=3)
    agora = _local(23, 10)

    assert proxima_recarga_em(com_recarga, 3, agora, agora) is None
    assert proxima_recarga_em(sem_recarga, 0, agora, agora) is None


def test_proxima_janela_da_cota():
    politica = _cota(JanelaCota.DIA)
    proxima = proxima_recarga_em(politica, 0, _local(23, 0), _local(23, 15))
    assert proxima == _local(23, 0) + timedelta(days=1)
