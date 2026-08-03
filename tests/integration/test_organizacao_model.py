import pytest
from sqlalchemy.exc import IntegrityError

from app.models.organizacao import Organizacao


def test_organizacao_persists_and_defaults_ativo(_db):
    org = Organizacao(nome="Fundação PaqTcPB", sigla="PAQTCPB")
    _db.session.add(org)
    _db.session.commit()

    fetched = _db.session.get(Organizacao, org.id)
    assert fetched.nome == "Fundação PaqTcPB"
    assert fetched.sigla == "PAQTCPB"
    assert fetched.ativo is True
    assert fetched.__tablename__ == "organizacao"


def test_organizacao_sigla_is_unique(_db):
    _db.session.add(Organizacao(nome="A", sigla="DUP"))
    _db.session.commit()
    _db.session.add(Organizacao(nome="B", sigla="DUP"))
    with pytest.raises(IntegrityError):
        _db.session.commit()
    _db.session.rollback()
