"""Support for race condition tests.

The suite's `_db` fixture really writes (create_all/commit/drop_all, no
transaction rolled back at the end), so one thread sees what the other
committed. Each thread opens its own app context, with its own session and
connection, and the race happens in Postgres, as in production.
"""

import threading
from collections.abc import Callable
from typing import Any

import pytest
from flask_jwt_extended import create_access_token

from app.models.consentimento import ACEITE, Consentimento
from app.services.consentimento_service import VERSAO_TERMO_VIGENTE
from tests.conftest import Actor, AuthenticatedClient
from tests.factories.user_factory import AlunoFactory


def ao_mesmo_tempo(app, tarefas: list[Callable[[], Any]]) -> list[Any]:
    """Run each task in its own thread, all released together by a barrier.

    Returns each task's result, in list order. An unhandled exception becomes the
    result itself, so the test shows what went wrong.
    """
    # Without the barrier one thread would finish before the other starts and the
    # test would become a sequential case.
    largada = threading.Barrier(len(tarefas), timeout=10)
    resultados: list[Any] = [None] * len(tarefas)

    def rodar(indice: int) -> None:
        with app.app_context():
            try:
                largada.wait()
                resultados[indice] = tarefas[indice]()
            except Exception as e:  # noqa: BLE001 — o teste inspeciona o erro
                resultados[indice] = e

    threads = []
    for indice in range(len(tarefas)):
        thread = threading.Thread(target=rodar, args=(indice,))
        threads.append(thread)
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
        assert not thread.is_alive(), "deadlock: uma thread não terminou"

    return resultados


def status_de(respostas: list[Any]) -> list[int]:
    """The HTTP statuses of the responses, in ascending order."""
    codigos = []
    for resposta in respostas:
        assert not isinstance(resposta, Exception), f"a thread levantou {resposta!r}"
        codigos.append(resposta.status_code)
    return sorted(codigos)


@pytest.fixture()
def novo_aluno(client, app, _db, organizacao):
    """Factory of students with the terms accepted, for tests that need several."""

    def criar() -> Actor:
        u = AlunoFactory(organizacao_id=organizacao.id)
        _db.session.add(u)
        _db.session.commit()
        _db.session.add(Consentimento(usuario_id=u.id, versao=VERSAO_TERMO_VIGENTE, acao=ACEITE))
        _db.session.commit()
        with app.app_context():
            token = create_access_token(identity=str(u.id))
        headers = {"Authorization": f"Bearer {token}"}
        return Actor(user=u, headers=headers, client=AuthenticatedClient(client, headers))

    return criar
