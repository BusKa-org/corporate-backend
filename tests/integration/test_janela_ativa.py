from datetime import UTC, datetime

from app.models.enum import StatusViagem
from app.services import janelas_service, viagens_service
from app.utils import tempo


def _local(hora: int, minuto: int):
    # 2026-11-02 é segunda-feira; o fuso padrão é UTC-3.
    return datetime(2026, 11, 2, hora + 3, minuto, tzinfo=UTC)


def test_agora_local_usa_fuso_configurado(app, relogio):
    with app.app_context():
        relogio.ajustar(_local(10, 0))
        assert tempo.agora_local().hour == 10


def test_janela_inicio_inclusivo_fim_exclusivo(app, janela, onibus, relogio):
    relogio.ajustar(_local(8, 0))
    assert janelas_service.buscar_janela_ativa(onibus.id, tempo.agora_local()) == janela

    relogio.ajustar(_local(11, 59))
    assert janelas_service.buscar_janela_ativa(onibus.id, tempo.agora_local()) == janela

    relogio.ajustar(_local(12, 0))
    assert janelas_service.buscar_janela_ativa(onibus.id, tempo.agora_local()) is None


def test_janela_de_outro_dia_nao_vale(app, janela, onibus, relogio):
    relogio.ajustar(datetime(2026, 11, 3, 13, 0, tzinfo=UTC))  # terça 10:00
    assert janelas_service.buscar_janela_ativa(onibus.id, tempo.agora_local()) is None


def test_viagem_ativa_do_veiculo(app, viagem_solicitada, onibus, _db):
    assert viagens_service.buscar_viagem_ativa_do_veiculo(onibus.id) == viagem_solicitada

    viagem_solicitada.status = StatusViagem.FINALIZADA
    _db.session.commit()
    assert viagens_service.buscar_viagem_ativa_do_veiculo(onibus.id) is None
