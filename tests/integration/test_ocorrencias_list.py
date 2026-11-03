from datetime import datetime

import pytest

from app.models.enum import TipoOcorrencia
from app.models.ocorrencia import Ocorrencia


@pytest.mark.integration
def test_listar_ocorrencias_created_at_em_iso(gestor, aluno, _db):
    _db.session.add(Ocorrencia(autor_id=aluno.user.id, tipo=TipoOcorrencia.ATRASO))
    _db.session.commit()

    r = gestor.client.get("/v1/ocorrencias/")
    assert r.status_code == 200
    created_at = r.get_json()[0]["created_at"]
    assert "T" in created_at
    datetime.fromisoformat(created_at)
