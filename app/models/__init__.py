# app/models/__init__.py
from .ocorrencia import Ocorrencia  # noqa: F401 — ensures table is registered
from .ticket import MovimentoTicket, PoliticaTicket, SaldoTicket  # noqa: F401
