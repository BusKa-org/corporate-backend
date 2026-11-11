import uuid

import pytest

from app.core.exceptions import ValidationError
from app.utils.validators import validate_uuid


def test_validate_uuid_preserva_ids_que_nao_sao_v4():
    # uuid.UUID(..., version=4) rewrote the version bits, turning a v1 id into a different id.
    original = uuid.uuid1()
    assert validate_uuid(str(original)) == original


def test_validate_uuid_aceita_v4():
    original = uuid.uuid4()
    assert validate_uuid(str(original)) == original


def test_validate_uuid_recusa_texto_invalido():
    with pytest.raises(ValidationError):
        validate_uuid("abc", "ID da viagem")
