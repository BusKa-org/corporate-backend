# Imported for their side effect: they register the tables in the SQLAlchemy
# metadata even when no module imports them directly.
from .consentimento import Consentimento  # noqa: F401
from .ocorrencia import Ocorrencia  # noqa: F401
from .parametros_operacao import ParametrosOperacao  # noqa: F401
from .telemetria import TelemetriaVeiculo  # noqa: F401
