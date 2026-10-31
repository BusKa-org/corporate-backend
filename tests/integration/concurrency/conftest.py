"""Apoio aos testes de condição de corrida.

O fixture `_db` da suíte já grava de verdade (create_all/commit/drop_all, sem
transação revertida no fim), então uma thread enxerga o que a outra commitou.
Basta cada thread abrir o próprio contexto da aplicação: com ele vêm uma sessão
e uma conexão só dela, e a disputa acontece no Postgres, como em produção.
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
    """Roda cada tarefa na sua thread, todas soltas juntas por uma barreira.

    Devolve o resultado de cada tarefa, na ordem da lista. Uma exceção não
    tratada vira o próprio resultado, para o teste mostrar o que deu errado.
    """
    # Sem a barreira uma thread terminaria antes da outra começar e o teste
    # viraria um caso sequencial.
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
    """Os status HTTP das respostas, em ordem crescente."""
    codigos = []
    for resposta in respostas:
        assert not isinstance(resposta, Exception), f"a thread levantou {resposta!r}"
        codigos.append(resposta.status_code)
    return sorted(codigos)


@pytest.fixture()
def novo_aluno(client, app, _db, organizacao):
    """Fábrica de alunos com o termo aceito, para testes que precisam de vários."""

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
