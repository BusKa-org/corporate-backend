"""Foto do aluno: envio pelo próprio aluno e leitura por quem confere o embarque (RF-17)."""

import io
import os

import pytest

SENHA = "StrongPass123!"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture(autouse=True)
def pasta_de_fotos(app, tmp_path, monkeypatch):
    monkeypatch.setitem(app.config, "FOTOS_ALUNO_DIR", str(tmp_path))
    return tmp_path


def _enviar(aluno, conteudo, nome="foto.png"):
    return aluno.client.put(
        "/v1/alunos/me/foto",
        data={"foto": (io.BytesIO(conteudo), nome)},
        content_type="multipart/form-data",
    )


def test_aluno_envia_foto_e_consegue_ver(aluno, pasta_de_fotos):
    resposta = _enviar(aluno, PNG)

    assert resposta.status_code == 200, resposta.get_data(as_text=True)
    foto_url = f"/v1/alunos/{aluno.user.id}/foto"
    assert resposta.get_json()["foto_url"] == foto_url
    assert os.listdir(pasta_de_fotos) == [f"{aluno.user.id}.png"]

    foto = aluno.client.get(foto_url)
    assert foto.status_code == 200
    assert foto.mimetype == "image/png"
    assert foto.data == PNG


def test_foto_que_nao_e_imagem_e_recusada(aluno, pasta_de_fotos):
    # O nome diz .png, mas o conteúdo não é: vale o conteúdo.
    resposta = _enviar(aluno, b"<html>nao sou imagem</html>")

    assert resposta.status_code == 400
    assert os.listdir(pasta_de_fotos) == []


def test_foto_acima_do_limite_e_recusada(aluno, app, pasta_de_fotos, monkeypatch):
    monkeypatch.setitem(app.config, "FOTO_ALUNO_MAX_BYTES", 32)

    resposta = _enviar(aluno, PNG)

    assert resposta.status_code == 400
    assert os.listdir(pasta_de_fotos) == []


def test_gestor_e_motorista_da_organizacao_veem_a_foto_e_os_outros_nao(
    aluno, gestor, motorista, other_gestor, other_motorista, other_aluno
):
    assert _enviar(aluno, PNG).status_code == 200
    foto_url = f"/v1/alunos/{aluno.user.id}/foto"

    assert gestor.client.get(foto_url).status_code == 200
    assert motorista.client.get(foto_url).status_code == 200
    assert other_gestor.client.get(foto_url).status_code == 403
    assert other_motorista.client.get(foto_url).status_code == 403
    assert other_aluno.client.get(foto_url).status_code == 403


def test_excluir_conta_apaga_o_arquivo_da_foto(aluno, pasta_de_fotos, _db):
    assert _enviar(aluno, PNG).status_code == 200

    resposta = aluno.client.delete("/v1/users/me", json={"email": aluno.user.email, "senha": SENHA})

    assert resposta.status_code in (200, 204), resposta.get_data(as_text=True)
    assert os.listdir(pasta_de_fotos) == []
    _db.session.refresh(aluno.user)
    assert aluno.user.foto_url is None
