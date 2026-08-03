"""Guards against municipal-only surface reappearing in the corporate product.

Note: RotaAluno (the enrollment roster) is deliberately retained — see
app/models/rota.py. It is replaced by per-trip declaration (RF-13/RF-14) in
the upcoming trip-lifecycle refactor, not here. Only join/leave management
and batch trip generation are municipal-only and removed in this task.
"""

import pytest


def test_agendamento_tasks_module_is_gone():
    with pytest.raises(ModuleNotFoundError):
        import app.tasks.agendamento_tasks  # noqa: F401


def test_subscription_management_endpoints_are_gone(client):
    """Join/leave a route is municipal; DRT replaces it with per-trip declaration.
    The RotaAluno roster itself stays until the lifecycle refactor replaces it."""
    import uuid

    assert client.post(f"/v1/rotas/{uuid.uuid4()}/inscricao").status_code == 404
    assert client.post("/v1/viagens/gerar-lote").status_code == 404
