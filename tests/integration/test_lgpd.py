"""Consentimento LGPD e exclusão de conta, pela API HTTP."""

import re
from datetime import UTC, date, datetime, timedelta

from app.models.consentimento import REVOGACAO, Consentimento
from app.models.credencial_embarque import CredencialEmbarque
from app.models.enum import StatusViagem, UserStatus
from app.models.geo import Endereco, Ponto
from app.models.notificacao import Notificacao
from app.models.retencao_legal import RetencaoLegal
from app.models.user import Aluno
from app.models.viagem import AlunosConfirmados
from app.services import conta_service
from app.services.consentimento_service import VERSAO_TERMO_VIGENTE
from app.tasks.retencao_tasks import job_anonimizar_retencoes
from tests.factories.credencial_embarque_factory import CredencialEmbarqueFactory
from tests.factories.geo_factory import PontoFactory
from tests.factories.user_factory import AlunoFactory
from tests.factories.viagem_factory import AlunosConfirmadosFactory, ViagemFactory
from tests.helpers.auth import login_and_get_headers

SENHA = "StrongPass123!"
VIAGEM_INEXISTENTE = "00000000-0000-0000-0000-000000000000"


def _revogar_consentimento(aluno):
    response = aluno.client.delete("/v1/consentimento")
    assert response.status_code == 200


def _excluir(aluno, email, senha):
    return aluno.client.delete("/v1/users/me", json={"email": email, "senha": senha})


# ---------- consentimento ----------


def test_aceitar_e_revogar_muda_o_estado(aluno):
    _revogar_consentimento(aluno)
    assert aluno.client.get("/v1/consentimento").get_json()["pendente"] is True

    response = aluno.client.post("/v1/consentimento", json={"versao": VERSAO_TERMO_VIGENTE})
    assert response.status_code == 200
    assert response.get_json()["pendente"] is False

    _revogar_consentimento(aluno)
    assert aluno.client.get("/v1/consentimento").get_json()["pendente"] is True


def test_aceitar_versao_errada_e_recusado(aluno):
    _revogar_consentimento(aluno)
    response = aluno.client.post("/v1/consentimento", json={"versao": "0.1"})
    assert response.status_code == 400


def test_revogar_sem_consentimento_vigente_da_conflito(aluno):
    _revogar_consentimento(aluno)
    response = aluno.client.delete("/v1/consentimento")
    assert response.status_code == 409


def test_motorista_tambem_aceita_o_termo(motorista):
    response = motorista.client.post("/v1/consentimento", json={"versao": VERSAO_TERMO_VIGENTE})
    assert response.status_code == 200


def test_confirmar_presenca_bloqueia_sem_consentimento(aluno):
    _revogar_consentimento(aluno)
    url = f"/v1/viagens/{VIAGEM_INEXISTENTE}/confirmacao"

    bloqueado = aluno.client.put(url, json={"confirmacao": False})
    assert bloqueado.status_code == 403

    aluno.client.post("/v1/consentimento", json={"versao": VERSAO_TERMO_VIGENTE})
    liberado = aluno.client.put(url, json={"confirmacao": False})
    assert liberado.status_code == 404  # passou pelo bloqueio e não achou a viagem


def test_credencial_de_embarque_bloqueia_sem_consentimento(aluno):
    _revogar_consentimento(aluno)
    url = f"/v1/viagens/{VIAGEM_INEXISTENTE}/credencial-embarque"

    assert aluno.client.get(url).status_code == 403

    aluno.client.post("/v1/consentimento", json={"versao": VERSAO_TERMO_VIGENTE})
    assert aluno.client.get(url).status_code == 404  # passou pelo bloqueio e não achou a credencial


def test_login_e_perfil_trazem_a_flag_de_consentimento_pendente(client, organizacao, _db):
    novo = AlunoFactory(organizacao_id=organizacao.id)
    _db.session.add(novo)
    _db.session.commit()

    login = client.post("/v1/auth/login", json={"email": novo.email, "password": SENHA})
    assert login.status_code == 200
    assert login.get_json()["consentimento_pendente"] is True

    headers = {"Authorization": f"Bearer {login.get_json()['token']}"}
    perfil = client.get("/v1/users/me", headers=headers)
    assert perfil.get_json()["consentimento_pendente"] is True


# ---------- exclusão de conta ----------


def test_excluir_conta_com_senha_errada_ou_email_diferente(aluno):
    senha_errada = _excluir(aluno, aluno.user.email, "SenhaErrada1!")
    assert senha_errada.status_code == 401

    email_diferente = _excluir(aluno, "outro@buska.test", SENHA)
    assert email_diferente.status_code == 401
    assert (
        email_diferente.get_json()["error"]["message"]
        == senha_errada.get_json()["error"]["message"]
    )

    assert aluno.user.status != UserStatus.DELETED


def test_excluir_conta_so_para_passageiro(motorista):
    response = _excluir(motorista, motorista.user.email, SENHA)
    assert response.status_code == 403


def test_excluir_conta_bloqueia_com_viagem_em_andamento(
    aluno, viagem_futura_iniciada_com_motorista, _db
):
    _db.session.add(
        AlunosConfirmadosFactory(
            viagem_id=viagem_futura_iniciada_com_motorista.id,
            aluno_id=aluno.user.id,
            confirmacao=True,
        )
    )
    _db.session.commit()

    response = _excluir(aluno, aluno.user.email, SENHA)
    assert response.status_code == 409
    assert aluno.user.status != UserStatus.DELETED


def test_excluir_conta_anonimiza_e_preserva_historico(
    aluno, ponto, horario_rota, rota_aluno, viagem_futura_agendada_com_motorista, _db, monkeypatch
):
    emails_enviados = []
    monkeypatch.setattr(
        conta_service, "send_email", lambda to, subject, body_plain: emails_enviados.append(to)
    )

    aluno_id = aluno.user.id
    email_original = aluno.user.email
    cpf_original = aluno.user.cpf
    aluno.user.nome_responsavel = "Responsável Teste"
    aluno.user.matricula = "12345"
    ponto_casa = PontoFactory(organizacao_id=aluno.user.organizacao_id)
    _db.session.add(ponto_casa)
    _db.session.flush()
    _db.session.add(Endereco(ponto_id=ponto_casa.id, logradouro="Rua das Flores", numero="10"))
    aluno.user.ponto_casa_id = ponto_casa.id
    ponto_casa_id = ponto_casa.id
    _db.session.add(Notificacao(usuario_id=aluno_id, titulo="Aviso", mensagem="Teste"))
    _db.session.add(
        CredencialEmbarqueFactory(
            viagem_id=viagem_futura_agendada_com_motorista.id,
            aluno_id=aluno_id,
            ponto_embarque_id=ponto.id,
        )
    )
    viagem_finalizada = ViagemFactory(
        horario_rota_id=horario_rota.id,
        data=date.today(),
        status=StatusViagem.FINALIZADA,
        motorista_id=viagem_futura_agendada_com_motorista.motorista_id,
    )
    _db.session.add(viagem_finalizada)
    _db.session.commit()
    _db.session.add(
        AlunosConfirmadosFactory(
            viagem_id=viagem_finalizada.id, aluno_id=aluno_id, confirmacao=True
        )
    )
    _db.session.add(
        AlunosConfirmadosFactory(
            viagem_id=viagem_futura_agendada_com_motorista.id,
            aluno_id=aluno_id,
            confirmacao=True,
        )
    )
    _db.session.commit()

    response = _excluir(aluno, email_original, SENHA)
    assert response.status_code == 200

    _db.session.expire_all()
    excluido = _db.session.get(Aluno, aluno_id)
    assert excluido.status == UserStatus.DELETED
    assert excluido.nome == "Usuário removido"
    assert excluido.email != email_original
    assert excluido.matricula is None
    assert excluido.nome_responsavel is None
    assert excluido.ponto_casa_id is None
    assert _db.session.get(Ponto, ponto_casa_id) is None
    assert Endereco.query.filter_by(ponto_id=ponto_casa_id).count() == 0

    assert Notificacao.query.filter_by(usuario_id=aluno_id).count() == 0
    assert CredencialEmbarque.query.filter_by(aluno_id=aluno_id).count() == 0
    presencas = AlunosConfirmados.query.filter_by(aluno_id=aluno_id).all()
    assert len(presencas) == 1
    assert presencas[0].viagem_id == viagem_finalizada.id

    ultimo_consentimento = (
        Consentimento.query.filter_by(usuario_id=aluno_id).order_by(Consentimento.id.desc()).first()
    )
    assert ultimo_consentimento.acao == REVOGACAO

    # Retenção legal: e-mail e CPF originais ficam por 10 anos, só na tabela restrita.
    assert excluido.cpf != cpf_original
    retido = _db.session.get(RetencaoLegal, aluno_id)
    assert retido.email == email_original
    assert retido.cpf == cpf_original
    nove_anos_e_meio = timedelta(days=365 * 9 + 180)
    assert retido.reter_ate > datetime.now(UTC) + nove_anos_e_meio

    assert emails_enviados == [email_original]


def test_conta_excluida_nao_faz_login_com_o_email_antigo(client, organizacao, _db):
    novo = AlunoFactory(organizacao_id=organizacao.id)
    _db.session.add(novo)
    _db.session.commit()
    email_original = novo.email
    headers = login_and_get_headers(client, email_original, SENHA)

    response = client.delete(
        "/v1/users/me", json={"email": email_original, "senha": SENHA}, headers=headers
    )
    assert response.status_code == 200

    login = client.post("/v1/auth/login", json={"email": email_original, "password": SENHA})
    assert login.status_code == 401


# ---------- anonimização depois do prazo de retenção ----------


def test_job_troca_e_mail_e_cpf_vencidos_por_hash_e_nao_mexe_nos_outros(organizacao, _db):
    vencido = AlunoFactory(organizacao_id=organizacao.id)
    no_prazo = AlunoFactory(organizacao_id=organizacao.id)
    _db.session.add_all([vencido, no_prazo])
    _db.session.commit()
    agora = datetime.now(UTC)
    _db.session.add(
        RetencaoLegal(
            usuario_id=vencido.id,
            email="velho@parque.test",
            cpf="52998224725",
            reter_ate=agora - timedelta(days=1),
        )
    )
    _db.session.add(
        RetencaoLegal(
            usuario_id=no_prazo.id,
            email="recente@parque.test",
            cpf="11144477735",
            reter_ate=agora + timedelta(days=30),
        )
    )
    _db.session.commit()

    job_anonimizar_retencoes()

    _db.session.expire_all()
    anonimizado = _db.session.get(RetencaoLegal, vencido.id)
    assert anonimizado.anonimizado_em is not None
    for valor in (anonimizado.email, anonimizado.cpf):
        assert re.fullmatch(r"[0-9a-f]{64}", valor)
    assert "velho" not in anonimizado.email
    assert anonimizado.cpf != "52998224725"

    intacto = _db.session.get(RetencaoLegal, no_prazo.id)
    assert intacto.email == "recente@parque.test"
    assert intacto.cpf == "11144477735"
    assert intacto.anonimizado_em is None


def test_job_nao_refaz_a_anonimizacao_de_quem_ja_foi(organizacao, _db):
    aluno = AlunoFactory(organizacao_id=organizacao.id)
    _db.session.add(aluno)
    _db.session.commit()
    _db.session.add(
        RetencaoLegal(
            usuario_id=aluno.id,
            email="velho@parque.test",
            cpf="52998224725",
            reter_ate=datetime.now(UTC) - timedelta(days=1),
        )
    )
    _db.session.commit()

    job_anonimizar_retencoes()
    _db.session.expire_all()
    primeiro = _db.session.get(RetencaoLegal, aluno.id)
    email_hash, cpf_hash, quando = primeiro.email, primeiro.cpf, primeiro.anonimizado_em

    job_anonimizar_retencoes()

    _db.session.expire_all()
    segundo = _db.session.get(RetencaoLegal, aluno.id)
    assert (segundo.email, segundo.cpf, segundo.anonimizado_em) == (email_hash, cpf_hash, quando)
