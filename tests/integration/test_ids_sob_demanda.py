"""Ids malformados nos endpoints sob demanda respondem 400, não 500."""

import pytest


@pytest.mark.parametrize(
    "ator,metodo,caminho",
    [
        ("gestor", "delete", "/v1/onibus/{onibus}/janelas/nao-e-uuid"),
        ("aluno", "post", "/v1/rotas/nao-e-uuid/solicitacoes"),
        ("aluno", "get", "/v1/rotas/nao-e-uuid/viagem-ativa"),
        ("aluno", "delete", "/v1/viagens/nao-e-uuid/solicitacao"),
        ("motorista", "post", "/v1/viagens/nao-e-uuid/iniciar-percurso"),
    ],
)
def test_id_malformado_retorna_400(request, onibus, ator, metodo, caminho):
    actor = request.getfixturevalue(ator)
    r = getattr(actor.client, metodo)(caminho.format(onibus=onibus.id))
    assert r.status_code == 400, r.get_data(as_text=True)
