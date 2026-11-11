"""Malformed ids on the on-demand endpoints answer 400 or 404, never 500."""

import pytest


@pytest.mark.parametrize(
    "ator,metodo,caminho",
    [
        ("gestor", "delete", "/v1/onibus/{onibus}/janelas/nao-e-uuid"),
    ],
)
def test_id_malformado_retorna_400(request, onibus, ator, metodo, caminho):
    actor = request.getfixturevalue(ator)
    r = getattr(actor.client, metodo)(caminho.format(onibus=onibus.id))
    assert r.status_code == 400, r.get_data(as_text=True)


# Trip and on-demand route ids use the <uuid:...> converter: a malformed id never reaches the service.
@pytest.mark.parametrize(
    "ator,metodo,caminho",
    [
        ("aluno", "post", "/v1/viagens/nao-e-uuid/declaracao"),
        ("aluno", "get", "/v1/viagens/nao-e-uuid/pontos-embarque"),
        ("aluno", "get", "/v1/viagens/nao-e-uuid/credencial-embarque"),
        ("aluno", "put", "/v1/viagens/nao-e-uuid/confirmacao"),
        ("motorista", "put", "/v1/viagens/nao-e-uuid/acao"),
        ("gestor", "put", "/v1/viagens/nao-e-uuid/cancelar"),
        ("aluno", "delete", "/v1/viagens/nao-e-uuid/solicitacao"),
        ("motorista", "post", "/v1/viagens/nao-e-uuid/iniciar-percurso"),
        ("gestor", "get", "/v1/dashboard/viagens/nao-e-uuid/progresso"),
        ("gestor", "get", "/v1/dashboard/viagens/nao-e-uuid/trajeto-real"),
        ("aluno", "post", "/v1/rotas/nao-e-uuid/solicitacoes"),
        ("aluno", "get", "/v1/rotas/nao-e-uuid/viagem-ativa"),
        ("motorista", "get", "/v1/embarque/viagens/nao-e-uuid/roteiro"),
        ("motorista", "post", "/v1/embarque/viagens/nao-e-uuid/roteiro/avancar"),
        ("motorista", "post", "/v1/embarque/viagens/nao-e-uuid/checkin"),
        ("motorista", "post", "/v1/embarque/viagens/nao-e-uuid/confirmacao"),
        ("motorista", "post", "/v1/embarque/viagens/nao-e-uuid/recusa"),
        ("motorista", "post", "/v1/embarque/viagens/nao-e-uuid/manual"),
        ("motorista", "post", "/v1/embarque/viagens/nao-e-uuid/sincronizacao"),
    ],
)
def test_id_de_viagem_malformado_retorna_404(request, ator, metodo, caminho):
    actor = request.getfixturevalue(ator)
    r = getattr(actor.client, metodo)(caminho)
    assert r.status_code == 404, r.get_data(as_text=True)
