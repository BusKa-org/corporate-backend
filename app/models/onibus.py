"""Onibus (veículo) e telemetria de bateria.

A van é elétrica: além de posição, precisa de SoC, autonomia e consumo por
km. TODO.md plan 8 (RF-22). `TelemetrySource` fica como interface aqui; o
adaptador do veículo específico é infraestrutura de deploy, não deste
módulo.
"""
