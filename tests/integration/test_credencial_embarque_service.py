"""Testes de integração do serviço de credencial de embarque."""

from datetime import UTC, datetime

import pytest

from app.core.exceptions import NotFoundError, ValidationError
from app.models.credencial_embarque import CredencialEmbarque
from app.models.enum import StatusViagem
from app.services import credencial_embarque_service
from tests.factories.geo_factory import PontoFactory
from tests.factories.viagem_factory import AlunosConfirmadosFactory, ViagemFactory


def _gerar(viagem, aluno, ponto):
    return credencial_embarque_service.gerar_credencial(
        viagem_id=viagem.id, aluno_id=aluno.user.id, ponto_embarque_id=ponto.id
    )


def _confirmado(_db, viagem, aluno, ponto):
    registro = AlunosConfirmadosFactory(
        viagem_id=viagem.id, aluno_id=aluno.user.id, confirmacao=True, ponto_embarque_id=ponto.id
    )
    _db.session.add(registro)
    _db.session.commit()
    return registro


def test_gerar_credencial_sucesso(_db, aluno, ponto, viagem_futura_agendada_com_motorista):
    credencial = _gerar(viagem_futura_agendada_com_motorista, aluno, ponto)

    assert len(bytes.fromhex(credencial.segredo)) == 32
    assert credencial.viagem_id == viagem_futura_agendada_com_motorista.id
    assert credencial.aluno_id == aluno.user.id
    assert credencial.ponto_embarque_id == ponto.id
    assert credencial.usado is False
    assert credencial.recusada_em is None
    assert credencial.expires_at > datetime.now(UTC)


def test_gerar_credencial_de_novo_no_mesmo_ponto_devolve_a_mesma(
    _db, aluno, ponto, viagem_futura_agendada_com_motorista
):
    primeira = _gerar(viagem_futura_agendada_com_motorista, aluno, ponto)
    segunda = _gerar(viagem_futura_agendada_com_motorista, aluno, ponto)

    assert segunda.id == primeira.id
    assert CredencialEmbarque.query.count() == 1


def test_gerar_credencial_em_outro_ponto_revoga_a_anterior(
    _db, aluno, ponto, organizacao, viagem_futura_agendada_com_motorista
):
    outro_ponto = PontoFactory(organizacao_id=organizacao.id)
    _db.session.add(outro_ponto)
    _db.session.commit()

    antiga = _gerar(viagem_futura_agendada_com_motorista, aluno, ponto)
    nova = _gerar(viagem_futura_agendada_com_motorista, aluno, outro_ponto)

    _db.session.refresh(antiga)
    assert antiga.revogada_em is not None
    assert nova.revogada_em is None
    assert nova.ponto_embarque_id == outro_ponto.id
    assert (
        credencial_embarque_service.credencial_ativa(
            viagem_futura_agendada_com_motorista.id, aluno.user.id
        ).id
        == nova.id
    )


@pytest.mark.parametrize("status", [StatusViagem.CANCELADA, StatusViagem.FINALIZADA])
def test_gerar_credencial_viagem_nao_ativa_levanta_validation(_db, aluno, ponto, status):
    viagem = ViagemFactory(status=status)
    _db.session.add(viagem)
    _db.session.commit()

    with pytest.raises(ValidationError):
        _gerar(viagem, aluno, ponto)


def test_gerar_credencial_viagem_nao_encontrada(_db, aluno, ponto):
    with pytest.raises(NotFoundError):
        credencial_embarque_service.gerar_credencial(
            viagem_id="00000000-0000-0000-0000-000000000000",
            aluno_id=aluno.user.id,
            ponto_embarque_id=ponto.id,
        )


def test_validar_credencial_foi_removida():
    """As regras da credencial lida moram só em embarque_service."""
    assert not hasattr(credencial_embarque_service, "validar_credencial")


def test_get_credencial_embarque_requires_auth(client, viagem_futura_agendada_com_motorista):
    r = client.get(f"/v1/viagens/{viagem_futura_agendada_com_motorista.id}/credencial-embarque")
    assert r.status_code in (401, 422)


def test_get_credencial_embarque_only_allows_aluno(gestor, viagem_futura_agendada_com_motorista):
    r = gestor.client.get(
        f"/v1/viagens/{viagem_futura_agendada_com_motorista.id}/credencial-embarque"
    )
    assert r.status_code == 403


def test_get_credencial_embarque_not_generated_yet(aluno, viagem_futura_agendada_com_motorista):
    r = aluno.client.get(
        f"/v1/viagens/{viagem_futura_agendada_com_motorista.id}/credencial-embarque"
    )
    assert r.status_code == 404


def test_get_credencial_embarque_sucesso(_db, aluno, ponto, viagem_futura_agendada_com_motorista):
    _confirmado(_db, viagem_futura_agendada_com_motorista, aluno, ponto)
    credencial = _gerar(viagem_futura_agendada_com_motorista, aluno, ponto)

    r = aluno.client.get(
        f"/v1/viagens/{viagem_futura_agendada_com_motorista.id}/credencial-embarque"
    )

    assert r.status_code == 200
    assert r.json["credencial_id"] == str(credencial.id)
    assert r.json["segredo"] == credencial.segredo
    assert (r.json["algoritmo"], r.json["passo_segundos"], r.json["digitos"]) == ("SHA1", 30, 6)
    assert "token" not in r.json


def test_get_credencial_embarque_devolve_a_do_ponto_atual(
    _db, aluno, ponto, organizacao, viagem_futura_agendada_com_motorista
):
    outro_ponto = PontoFactory(organizacao_id=organizacao.id)
    _db.session.add(outro_ponto)
    _db.session.commit()
    _gerar(viagem_futura_agendada_com_motorista, aluno, ponto)
    registro = _confirmado(_db, viagem_futura_agendada_com_motorista, aluno, ponto)
    registro.ponto_embarque_id = outro_ponto.id
    _db.session.commit()
    url = f"/v1/viagens/{viagem_futura_agendada_com_motorista.id}/credencial-embarque"

    # O ponto mudou e ninguém reemitiu: a credencial antiga não é mais a dele.
    assert aluno.client.get(url).status_code == 404

    nova = _gerar(viagem_futura_agendada_com_motorista, aluno, outro_ponto)
    _db.session.commit()
    r = aluno.client.get(url)
    assert r.status_code == 200
    assert r.json["credencial_id"] == str(nova.id)
    assert r.json["ponto_embarque_id"] == str(outro_ponto.id)


def test_get_credencial_embarque_nao_vaza_para_outro_aluno(
    _db, aluno, other_aluno, ponto, viagem_futura_agendada_com_motorista
):
    _confirmado(_db, viagem_futura_agendada_com_motorista, aluno, ponto)
    _gerar(viagem_futura_agendada_com_motorista, aluno, ponto)

    r = other_aluno.client.get(
        f"/v1/viagens/{viagem_futura_agendada_com_motorista.id}/credencial-embarque"
    )

    assert r.status_code == 404
