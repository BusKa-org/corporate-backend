# app/models/__init__.py
# Importados por efeito colateral: registram as tabelas no metadata do
# SQLAlchemy mesmo quando nenhum módulo os importa diretamente.
from .consentimento import Consentimento  # noqa: F401
from .janela import JanelaDisponibilidade  # noqa: F401
from .ocorrencia import Ocorrencia  # noqa: F401
from .telemetria import TelemetriaVeiculo  # noqa: F401
