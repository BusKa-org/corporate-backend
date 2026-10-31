"""Foto do aluno: envio pelo próprio aluno e leitura por quem confere o embarque (RF-17)."""

import io
import os

import pytest

from app.models.enum import StatusViagem
from app.models.user import Aluno
from tests.factories.viagem_factory import AlunosConfirmadosFactory, SolicitacaoViagemFactory
from tests.helpers import imagens

SENHA = "StrongPass123!"
PNG = imagens.png()
JPEG = imagens.jpeg()


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


def _confirmar(_db, viagem, aluno, confirmacao=True):
    _db.session.add(
        AlunosConfirmadosFactory(
            viagem_id=viagem.id, aluno_id=aluno.user.id, confirmacao=confirmacao
        )
    )
    _db.session.commit()


def test_gestor_da_organizacao_ve_a_foto_e_os_outros_nao(
    aluno, gestor, other_gestor, other_motorista, other_aluno
):
    assert _enviar(aluno, PNG).status_code == 200
    foto_url = f"/v1/alunos/{aluno.user.id}/foto"

    assert gestor.client.get(foto_url).status_code == 200
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


def test_motorista_sem_viagem_com_o_aluno_nao_ve_foto(aluno, motorista):
    assert _enviar(aluno, PNG).status_code == 200

    assert motorista.client.get(f"/v1/alunos/{aluno.user.id}/foto").status_code == 403


def test_motorista_da_viagem_ve_foto(aluno, motorista, viagem_futura_agendada_com_motorista, _db):
    assert _enviar(aluno, PNG).status_code == 200
    _confirmar(_db, viagem_futura_agendada_com_motorista, aluno)

    resposta = motorista.client.get(f"/v1/alunos/{aluno.user.id}/foto")

    assert resposta.status_code == 200
    assert resposta.data == PNG


def test_motorista_nao_ve_foto_de_quem_nao_confirmou(
    aluno, motorista, viagem_futura_agendada_com_motorista, _db
):
    assert _enviar(aluno, PNG).status_code == 200
    _confirmar(_db, viagem_futura_agendada_com_motorista, aluno, confirmacao=False)

    assert motorista.client.get(f"/v1/alunos/{aluno.user.id}/foto").status_code == 403


def test_motorista_ve_foto_de_trajeto_aceito_no_buffer(aluno, motorista, viagem_buffer_aberto, _db):
    assert _enviar(aluno, PNG).status_code == 200
    _db.session.add(
        SolicitacaoViagemFactory(
            viagem_id=viagem_buffer_aberto.id,
            aluno_id=aluno.user.id,
            ponto_embarque_id=viagem_buffer_aberto.rota.pontos_padrao[0].ponto_id,
            ponto_destino_id=viagem_buffer_aberto.rota.pontos_padrao[1].ponto_id,
        )
    )
    _db.session.commit()

    assert motorista.client.get(f"/v1/alunos/{aluno.user.id}/foto").status_code == 200


def test_motorista_nao_ve_foto_de_interessado_sem_trajeto(
    aluno, motorista, viagem_buffer_aberto, _db
):
    assert _enviar(aluno, PNG).status_code == 200
    _db.session.add(
        SolicitacaoViagemFactory(viagem_id=viagem_buffer_aberto.id, aluno_id=aluno.user.id)
    )
    _db.session.commit()

    assert motorista.client.get(f"/v1/alunos/{aluno.user.id}/foto").status_code == 403


@pytest.mark.parametrize("status", [StatusViagem.FINALIZADA, StatusViagem.CANCELADA])
def test_motorista_nao_ve_foto_depois_que_a_viagem_encerra(
    aluno, motorista, viagem_futura_agendada_com_motorista, _db, status
):
    assert _enviar(aluno, PNG).status_code == 200
    _confirmar(_db, viagem_futura_agendada_com_motorista, aluno)
    viagem_futura_agendada_com_motorista.status = status
    _db.session.commit()

    assert motorista.client.get(f"/v1/alunos/{aluno.user.id}/foto").status_code == 403


def test_gestor_nao_envia_foto(gestor, pasta_de_fotos):
    resposta = gestor.client.put(
        "/v1/alunos/me/foto",
        data={"foto": (io.BytesIO(PNG), "foto.png")},
        content_type="multipart/form-data",
    )

    assert resposta.status_code in (403, 404)
    assert os.listdir(pasta_de_fotos) == []


def test_put_foto_sem_campo_retorna_400(aluno, pasta_de_fotos):
    resposta = aluno.client.put("/v1/alunos/me/foto", data={}, content_type="multipart/form-data")

    assert resposta.status_code == 400
    assert os.listdir(pasta_de_fotos) == []


def test_trocar_foto_png_por_jpeg_deixa_um_arquivo(aluno, pasta_de_fotos):
    assert _enviar(aluno, PNG).status_code == 200
    assert _enviar(aluno, JPEG, nome="foto.jpg").status_code == 200

    assert os.listdir(pasta_de_fotos) == [f"{aluno.user.id}.jpg"]
    foto = aluno.client.get(f"/v1/alunos/{aluno.user.id}/foto")
    assert foto.mimetype == "image/jpeg"
    assert foto.data == JPEG


def test_falha_ao_gravar_mantem_foto_antiga(aluno, pasta_de_fotos, monkeypatch, _db):
    assert _enviar(aluno, PNG).status_code == 200

    def falha(*args, **kwargs):
        raise OSError("disco cheio")

    monkeypatch.setattr(os, "replace", falha)
    resposta = _enviar(aluno, JPEG, nome="foto.jpg")

    assert resposta.status_code == 500
    assert os.listdir(pasta_de_fotos) == [f"{aluno.user.id}.png"]
    with open(pasta_de_fotos / f"{aluno.user.id}.png", "rb") as arquivo:
        assert arquivo.read() == PNG
    _db.session.expire_all()
    assert _db.session.get(Aluno, aluno.user.id).foto_url == f"/v1/alunos/{aluno.user.id}/foto"


def test_foto_sem_metadados(aluno, pasta_de_fotos):
    resposta = _enviar(aluno, imagens.jpeg(com_exif=True), nome="foto.jpg")

    assert resposta.status_code == 200, resposta.get_data(as_text=True)
    with open(pasta_de_fotos / f"{aluno.user.id}.jpg", "rb") as arquivo:
        guardado = arquivo.read()
    assert b"Exif" not in guardado
    assert guardado == JPEG


def test_foto_corrompida_e_recusada(aluno, pasta_de_fotos, _db):
    resposta = _enviar(aluno, PNG[:-12])

    assert resposta.status_code == 400
    assert os.listdir(pasta_de_fotos) == []
    _db.session.refresh(aluno.user)
    assert aluno.user.foto_url is None


def test_get_foto_aluno_sem_foto_404(aluno):
    assert aluno.client.get(f"/v1/alunos/{aluno.user.id}/foto").status_code == 404


def test_get_foto_id_invalido_400(aluno):
    assert aluno.client.get("/v1/alunos/nao-e-uuid/foto").status_code == 400


def test_foto_no_limite_de_pixels_e_aceita_e_acima_e_recusada(
    aluno, app, pasta_de_fotos, monkeypatch
):
    monkeypatch.setitem(app.config, "FOTO_ALUNO_MAX_PIXELS", 100)
    no_limite = imagens.png(largura=10, altura=10)
    assert _enviar(aluno, no_limite).status_code == 200

    resposta = _enviar(aluno, imagens.jpeg(largura=11, altura=10), nome="foto.jpg")

    assert resposta.status_code == 400
    assert "megapixels" in resposta.get_data(as_text=True)
    assert os.listdir(pasta_de_fotos) == [f"{aluno.user.id}.png"]
    with open(pasta_de_fotos / f"{aluno.user.id}.png", "rb") as arquivo:
        assert arquivo.read() == no_limite
