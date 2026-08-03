def test_get_aluno_agenda_requires_auth(client):
    r = client.get("/v1/viagens/aluno/agenda")
    assert r.status_code in (401, 422)


def test_get_aluno_agenda_only_allows_aluno(gestor):
    r = gestor.client.get("/v1/viagens/aluno/agenda")
    assert r.status_code == 403


def test_get_aluno_agenda_success(
    aluno, rota_aluno, viagem_futura_agendada_com_motorista, dia_operacao
):
    # rota_aluno e dia_operacao garantem que a viagem está "no contexto" do aluno/rota
    r = aluno.client.get("/v1/viagens/aluno/agenda")
    assert r.status_code == 200, r.get_data(as_text=True)

    data = r.get_json() or {}
    print(data)
    assert "items" in data
    assert "total" in data

    assert data["total"] >= 1
    assert isinstance(data["items"], list)
    # contrato mínimo esperado do ViagemResponseSchema
    first = data["items"][0]
    assert "viagem_id" in first
    assert "data" in first
    assert "status_confirmacao" in first
