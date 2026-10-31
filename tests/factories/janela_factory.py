import uuid
from datetime import time

import factory

from app.models.enum import DiaDaSemana
from app.models.janela import JanelaDisponibilidade


class JanelaDisponibilidadeFactory(factory.Factory):
    class Meta:
        model = JanelaDisponibilidade

    id = factory.LazyFunction(uuid.uuid4)
    organizacao_id = None
    rota_id = None
    motorista_id = None
    veiculo_id = None
    dia = DiaDaSemana.SEG
    # Janela larga de propósito: testes que não estão exercitando o limite da
    # janela não deveriam quebrar dependendo da hora em que a suíte roda.
    hora_inicio = time(0, 0)
    hora_fim = time(23, 59)
    buffer_minutos = 5
    ativo = True
