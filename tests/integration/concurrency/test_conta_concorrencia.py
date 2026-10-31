"""Cadastro e conta sob concorrência: convite, PIN, exclusão, foto e troca de senha."""

import io
import os
from datetime import UTC, datetime, timedelta

import pytest

from app.models.convite import PENDENTE, Convite
from app.models.enum import StatusSolicitacao, TipoInstituicao, UserStatus
from app.models.geo import Instituicao
from app.models.onibus import JanelaDisponibilidade
from app.models.password_reset import PasswordResetToken
from app.models.retencao_legal import RetencaoLegal
from app.models.user import Aluno, User
from app.models.viagem import SolicitacaoViagem
from app.services import convite_service
from tests.factories.user_factory import SENHA_PADRAO
from tests.helpers import imagens
from tests.integration.concurrency.conftest import ao_mesmo_tempo, status_de

pytestmark = [pytest.mark.integration, pytest.mark.concurrency]

CPF = "52998224725"
SENHA = "StrongPass123!"


@pytest.fixture()
def convite(_db, organizacao, gestor):
    instituicao = Instituicao(
        fonte="MANUAL",
        codigo_externo="UFCG-1",
        nome="Universidade Federal de Campina Grande",
        sigla="UFCG",
        tipo=TipoInstituicao.UNIVERSIDADE_PUBLICA,
        uf="PB",
        organizacao_id=organizacao.id,
    )
    _db.session.add(instituicao)
    _db.session.flush()
    c = Convite(
        email="corrida@parque.test",
        estado=PENDENTE,
        organizacao_id=organizacao.id,
        criado_por_id=gestor.user.id,
        nome="Ana Corrida",
        cpf=CPF,
        instituicao_id=instituicao.id,
        token="token-da-corrida",
        expira_em=datetime.now(UTC) + timedelta(days=7),
    )
    _db.session.add(c)
    _db.session.commit()
    return c


# ---------- convite ----------


def test_aceite_duplo_do_convite_cria_uma_conta_so(app, _db, convite):
    def aceitar():
        return app.test_client().post(f"/v1/convites/aceite/{convite.token}", json={"senha": SENHA})

    respostas = ao_mesmo_tempo(app, [aceitar, aceitar])

    assert status_de(respostas) == [201, 409]
    _db.session.expire_all()
    assert _db.session.query(Aluno).filter_by(email=convite.email).count() == 1


def _com_pin(_db, convite, pin: str) -> None:
    convite.pin_hash = convite_service._hash_do_pin(convite, pin)
    convite.pin_expira_em = datetime.now(UTC) + timedelta(minutes=10)
    convite.pin_tentativas = 0
    _db.session.commit()


def _validar_pin(app, email, pin):
    return lambda: app.test_client().post(
        "/v1/convites/pin/validar", json={"email": email, "pin": pin}
    )


def test_palpites_de_pin_em_paralelo_nao_furam_o_limite_de_tentativas(app, _db, convite):
    """Dez palpites errados de uma vez contam dez tentativas, e o PIN morre na quinta."""
    _com_pin(_db, convite, "123456")

    tarefas = []
    for palpite in range(10):
        tarefas.append(_validar_pin(app, convite.email, f"{palpite:06d}"))
    respostas = ao_mesmo_tempo(app, tarefas)

    assert status_de(respostas) == [400] * 10
    _db.session.expire_all()
    recarregado = _db.session.get(Convite, convite.id)
    assert recarregado.pin_hash is None
    # E o PIN certo também não vale mais.
    assert _validar_pin(app, convite.email, "123456")().status_code == 400


def test_pin_certo_enviado_duas_vezes_vale_uma_vez(app, _db, convite):
    _com_pin(_db, convite, "123456")

    respostas = ao_mesmo_tempo(
        app,
        [_validar_pin(app, convite.email, "123456"), _validar_pin(app, convite.email, "123456")],
    )

    assert status_de(respostas) == [200, 400]


# ---------- exclusão de conta (LGPD) ----------


def test_exclusao_dupla_da_conta_anonimiza_uma_vez(app, _db, aluno):
    email = aluno.user.email

    def excluir():
        return app.test_client().delete(
            "/v1/users/me", json={"email": email, "senha": SENHA_PADRAO}, headers=aluno.headers
        )

    respostas = ao_mesmo_tempo(app, [excluir, excluir])

    codigos = status_de(respostas)
    assert codigos[0] == 200
    # A segunda vê a conta já excluída (credenciais não conferem) ou esbarra na retenção.
    assert codigos[1] in (401, 409)
    _db.session.expire_all()
    retencao = _db.session.get(RetencaoLegal, aluno.user.id)
    assert retencao.email == email


def test_exclusao_contra_solicitacao_nao_deixa_conta_excluida_com_solicitacao_ativa(
    app, _db, aluno, rota_sob_demanda, janela, relogio
):
    email = aluno.user.email

    def excluir():
        return app.test_client().delete(
            "/v1/users/me", json={"email": email, "senha": SENHA_PADRAO}, headers=aluno.headers
        )

    def solicitar():
        return app.test_client().post(
            f"/v1/rotas/{rota_sob_demanda.id}/solicitacoes", headers=aluno.headers
        )

    respostas = ao_mesmo_tempo(app, [excluir, solicitar])

    # Qualquer ordem vale (exclusão antes: 403 na solicitação; solicitação antes: a exclusão
    # cancela ou pede para tentar de novo), desde que nenhuma dê 500.
    for codigo in status_de(respostas):
        assert codigo in (200, 201, 403, 409)
    _db.session.expire_all()
    excluida = _db.session.get(User, aluno.user.id).status == UserStatus.DELETED
    ativas = (
        _db.session.query(SolicitacaoViagem)
        .filter_by(aluno_id=aluno.user.id, status=StatusSolicitacao.ATIVA)
        .count()
    )
    assert not (excluida and ativas)


# ---------- foto ----------


def test_envios_simultaneos_de_foto_deixam_um_arquivo_so(app, _db, aluno, tmp_path, monkeypatch):
    """PNG e JPEG ao mesmo tempo: sem lock, cada envio apagava o arquivo do outro."""
    monkeypatch.setitem(app.config, "FOTOS_ALUNO_DIR", str(tmp_path))

    def enviar(conteudo, nome):
        return lambda: app.test_client().put(
            "/v1/alunos/me/foto",
            data={"foto": (io.BytesIO(conteudo), nome)},
            content_type="multipart/form-data",
            headers=aluno.headers,
        )

    # Várias rodadas: a janela entre gravar e apagar a outra extensão é curta.
    for _ in range(10):
        respostas = ao_mesmo_tempo(
            app, [enviar(imagens.png(), "foto.png"), enviar(imagens.jpeg(), "foto.jpg")]
        )
        assert status_de(respostas) == [200, 200]
        arquivos = os.listdir(tmp_path)
        assert len(arquivos) == 1, arquivos


# ---------- troca de senha pelo link ----------


def test_link_de_troca_de_senha_usado_duas_vezes_ao_mesmo_tempo(app, _db, aluno):
    registro = PasswordResetToken(
        user_id=aluno.user.id,
        token="link-da-corrida",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    _db.session.add(registro)
    _db.session.commit()

    def trocar(senha):
        return lambda: app.test_client().post(
            "/v1/auth/reset-password",
            json={"token": "link-da-corrida", "new_password": senha, "confirm_password": senha},
        )

    respostas = ao_mesmo_tempo(app, [trocar("PrimeiraSenha1!"), trocar("SegundaSenha2!")])

    assert status_de(respostas) == [200, 400]
    _db.session.expire_all()
    assert _db.session.query(PasswordResetToken).count() == 0
    assert _db.session.get(User, aluno.user.id) is not None


# ---------- janela de disponibilidade ----------


def test_janelas_sobrepostas_criadas_ao_mesmo_tempo(app, _db, gestor, onibus, motorista):
    def criar(inicio, fim):
        return lambda: app.test_client().post(
            f"/v1/onibus/{onibus.id}/janelas",
            json={
                "motorista_id": str(motorista.user.id),
                "dia": "SEG",
                "hora_inicio": inicio,
                "hora_fim": fim,
            },
            headers=gestor.headers,
        )

    respostas = ao_mesmo_tempo(app, [criar("08:00", "12:00"), criar("10:00", "14:00")])

    assert status_de(respostas) == [201, 409]
    _db.session.expire_all()
    assert _db.session.query(JanelaDisponibilidade).filter_by(onibus_id=onibus.id).count() == 1
