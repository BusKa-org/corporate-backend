import pytest

from app.models.enum import TipoInstituicao, UserStatus
from app.models.geo import Instituicao
from tests.factories.user_factory import AlunoFactory


@pytest.fixture()
def instituicao(_db, organizacao):
    i = Instituicao(
        fonte="MANUAL",
        codigo_externo="UFCG",
        nome="UFCG",
        tipo=TipoInstituicao.UNIVERSIDADE_PUBLICA,
        uf="PB",
        organizacao_id=organizacao.id,
    )
    _db.session.add(i)
    _db.session.commit()
    return i


@pytest.fixture()
def pendentes(_db, organizacao, other_organizacao, instituicao):
    def novo(email, org=organizacao, status=UserStatus.PENDING_APPROVAL, inst=None):
        a = AlunoFactory(organizacao_id=org.id, email=email, status=status, instituicao_id=inst)
        _db.session.add(a)
        return a

    alunos = {
        "time": novo("Ana@Specific-Team.corp.org", inst=instituicao.id),
        "time2": novo("bia@specific-team.corp.org"),
        "curinga": novo("caio@notspecific-team.corp.org"),
        "sub": novo("davi@sub.specific-team.corp.org"),
        "outra_org": novo("eva@specific-team.corp.org", org=other_organizacao),
        "ativo": novo("fabi@specific-team.corp.org", status=UserStatus.ACTIVE),
    }
    _db.session.commit()
    return alunos


def _aprovados(r):
    assert r.status_code == 200, r.get_data(as_text=True)
    return sorted(a["email"].lower() for a in r.get_json()["items"])


def test_aprova_por_dominio(gestor, pendentes, _db):
    r = gestor.client.post("/v1/alunos/aprovar", json={"dominio": "*@specific-team.corp.org"})
    assert _aprovados(r) == ["ana@specific-team.corp.org", "bia@specific-team.corp.org"]

    _db.session.expire_all()
    assert pendentes["curinga"].status == UserStatus.PENDING_APPROVAL
    assert pendentes["outra_org"].status == UserStatus.PENDING_APPROVAL


def test_aprova_por_emails_individual(gestor, pendentes):
    r = gestor.client.post("/v1/alunos/aprovar", json={"emails": ["BIA@specific-team.corp.org"]})
    assert _aprovados(r) == ["bia@specific-team.corp.org"]


def test_aprova_por_instituicao_combinada_com_dominio(gestor, pendentes, instituicao):
    r = gestor.client.post(
        "/v1/alunos/aprovar",
        json={"instituicao_id": str(instituicao.id), "dominio": "specific-team.corp.org"},
    )
    assert _aprovados(r) == ["ana@specific-team.corp.org"]


@pytest.mark.parametrize("body", [{}, {"dominio": "not a domain"}, {"emails": []}])
def test_rejeita_pedido_sem_filtro_valido(gestor, body):
    assert gestor.client.post("/v1/alunos/aprovar", json=body).status_code == 400


def test_apenas_gestor_aprova(aluno):
    r = aluno.client.post("/v1/alunos/aprovar", json={"dominio": "buska.test"})
    assert r.status_code == 403


def test_login_bloqueado_ate_aprovacao(client, gestor, pendentes):
    login = {"email": "bia@specific-team.corp.org", "password": "StrongPass123!"}
    assert client.post("/v1/auth/login", json=login).status_code == 403

    gestor.client.post("/v1/alunos/aprovar", json={"emails": [login["email"]]})
    assert client.post("/v1/auth/login", json=login).status_code == 200


def test_adulto_que_conclui_cadastro_aguarda_aprovacao(aluno_pending, instituicao, _db):
    aluno_pending.user.instituicao_id = instituicao.id
    _db.session.commit()

    r = aluno_pending.client.put(
        "/v1/alunos/me",
        json={
            "nome": "Adulto",
            "matricula": "123456",
            "endereco_casa": {
                "logradouro": "Rua A",
                "numero": "1",
                "bairro": "Centro",
                "cidade": "Campina Grande",
                "cep": "58400000",
                "latitude": -7.2,
                "longitude": -35.9,
            },
        },
    )
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["status"] == UserStatus.PENDING_APPROVAL.value
