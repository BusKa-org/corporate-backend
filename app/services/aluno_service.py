"""Student (Aluno) service - profile management and gestor queries."""

import logging
import os
import tempfile
from typing import IO, Any, cast

from flask import current_app
from sqlalchemy import select

from app.core.exceptions import (
    AppError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.models.base import db
from app.models.enum import StatusSolicitacao, StatusViagem, UserRole, UserStatus
from app.models.geo import Endereco, Ponto
from app.models.user import Aluno, User
from app.models.viagem import AlunosConfirmados, SolicitacaoViagem, Viagem
from app.services.user_service import _get_gestor_or_403, _get_user_or_404
from app.utils.imagem import dimensoes, remover_metadados
from app.utils.validators import validate_uuid

logger = logging.getLogger(__name__)


def sem_repetidas(necessidades: list[str]) -> list[str]:
    """Remove repeated needs, keeping the order in which they appeared."""
    resultado: list[str] = []
    for necessidade in necessidades:
        if necessidade not in resultado:
            resultado.append(necessidade)
    return resultado


def update_me(user_id: str, data: dict[str, Any]) -> Aluno:
    """Update the student's profile. Raises NotFoundError, AppError."""
    aluno = db.session.get(Aluno, user_id)
    if not aluno:
        raise NotFoundError("Aluno não encontrado")

    try:
        for field in (
            "nome",
            "telefone",
            "matricula",
            "nome_responsavel",
            "cpf_responsavel",
            "observacao_acessibilidade",
        ):
            if field in data:
                setattr(aluno, field, data[field])
        if "necessidades_acessibilidade" in data:
            aluno.necessidades_acessibilidade = sem_repetidas(data["necessidades_acessibilidade"])

        if "endereco_casa" in data:
            end_data = data["endereco_casa"]

            if aluno.ponto_casa:
                ponto_casa = cast(Ponto, aluno.ponto_casa)
                ponto_casa.latitude = end_data.get("latitude")
                ponto_casa.longitude = end_data.get("longitude")
                if "nome" in data:
                    ponto_casa.apelido = f"Casa: {data['nome']}"

                endereco_bd = Endereco.query.filter_by(ponto_id=aluno.ponto_casa_id).first()

                if endereco_bd:
                    endereco_bd.logradouro = end_data.get("logradouro")
                    endereco_bd.numero = end_data.get("numero")
                    endereco_bd.bairro = end_data.get("bairro")
                    endereco_bd.cidade = end_data.get("cidade")
                    endereco_bd.cep = end_data.get("cep")
                else:
                    novo_end = Endereco(
                        ponto_id=aluno.ponto_casa_id,
                        logradouro=end_data.get("logradouro"),
                        numero=end_data.get("numero"),
                        bairro=end_data.get("bairro"),
                        cidade=end_data.get("cidade"),
                        cep=end_data.get("cep"),
                    )
                    db.session.add(novo_end)
            else:
                novo_ponto = Ponto(
                    organizacao_id=aluno.organizacao_id,
                    latitude=end_data.get("latitude"),
                    longitude=end_data.get("longitude"),
                    apelido=f"Casa: {data.get('nome', aluno.nome)}",
                )
                db.session.add(novo_ponto)
                db.session.flush()

                novo_end = Endereco(
                    ponto_id=novo_ponto.id,
                    logradouro=end_data.get("logradouro"),
                    numero=end_data.get("numero"),
                    bairro=end_data.get("bairro"),
                    cidade=end_data.get("cidade"),
                    cep=end_data.get("cep"),
                )
                db.session.add(novo_end)

                aluno.ponto_casa_id = novo_ponto.id

        db.session.commit()
        return aluno

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating student profile: {e}")
        raise AppError(f"Erro ao atualizar perfil: {str(e)}", 500)


def get_aluno_by_id(gestor_id: str, aluno_id: str) -> Aluno:
    """Manager gets the full details of one student. Raises ForbiddenError, NotFoundError."""
    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem consultar alunos")
    aluno = db.session.get(Aluno, aluno_id)

    if not aluno:
        raise NotFoundError("Aluno não encontrado")
    if str(aluno.organizacao_id) != str(gestor.organizacao_id):
        raise ForbiddenError("Aluno não pertence à sua organização")

    return aluno


def list_alunos_gestor(gestor_id: str, status: str | None = None) -> list[Aluno]:
    """List the organization's students (managers only), optionally filtered by status."""
    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem listar alunos")
    q = db.session.query(Aluno).filter_by(organizacao_id=gestor.organizacao_id)
    if status:
        try:
            q = q.filter(Aluno.status == UserStatus[status])
        except KeyError:
            pass
    return q.all()


# File extension by type. The type comes from the first bytes, not from the
# file name or the Content-Type sent by the client.
EXTENSOES_FOTO = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def _tipo_da_imagem(inicio: bytes) -> str | None:
    if inicio.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if inicio.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if inicio[0:4] == b"RIFF" and inicio[8:12] == b"WEBP":
        return "image/webp"
    return None


def _caminho_foto(aluno_id: str, extensao: str) -> str:
    return os.path.join(current_app.config["FOTOS_ALUNO_DIR"], f"{aluno_id}.{extensao}")


def apagar_foto(aluno_id: str) -> None:
    """Delete the student's photo file, whatever its extension."""
    for extensao in EXTENSOES_FOTO.values():
        caminho = _caminho_foto(aluno_id, extensao)
        if os.path.exists(caminho):
            os.remove(caminho)


def salvar_foto(user_id: str, arquivo: IO[bytes]) -> Aluno:
    """Student uploads their own photo (used to check boarding, RF-17)."""
    # Lock the student until commit: two simultaneous uploads (PNG and JPEG) would
    # delete each other's file and the photo would vanish.
    db.session.execute(select(User.id).where(User.id == user_id).with_for_update(key_share=True))
    aluno = db.session.get(Aluno, user_id)
    if not aluno:
        raise NotFoundError("Aluno não encontrado")

    limite = current_app.config["FOTO_ALUNO_MAX_BYTES"]
    conteudo = arquivo.read(limite + 1)
    if len(conteudo) > limite:
        raise ValidationError(f"A foto deve ter no máximo {limite // 1024} KB")

    tipo = _tipo_da_imagem(conteudo[:12])
    if tipo is None:
        raise ValidationError("A foto deve ser JPEG, PNG ou WEBP")

    largura, altura = dimensoes(conteudo, tipo)
    max_pixels = current_app.config["FOTO_ALUNO_MAX_PIXELS"]
    if largura * altura > max_pixels:
        raise ValidationError(
            f"A foto deve ter no máximo {max_pixels / 1_000_000:g} megapixels "
            f"(enviada: {largura}x{altura})"
        )

    conteudo = remover_metadados(conteudo, tipo)

    # Write to a temp file and only then swap it in: if the write fails midway, the
    # old photo is still there.
    pasta = current_app.config["FOTOS_ALUNO_DIR"]
    os.makedirs(pasta, exist_ok=True)
    extensao = EXTENSOES_FOTO[tipo]
    descritor, temporario = tempfile.mkstemp(dir=pasta, suffix=".tmp")
    try:
        with os.fdopen(descritor, "wb") as destino:
            destino.write(conteudo)
        os.replace(temporario, _caminho_foto(str(aluno.id), extensao))
    except OSError:
        if os.path.exists(temporario):
            os.remove(temporario)
        logger.exception("Falha ao gravar a foto do aluno %s", aluno.id)
        raise AppError("Erro ao salvar a foto", 500)

    # E.g. switched from PNG to JPEG: the photo with the other extension is removed.
    for outra_extensao in EXTENSOES_FOTO.values():
        if outra_extensao == extensao:
            continue
        caminho_antigo = _caminho_foto(str(aluno.id), outra_extensao)
        if os.path.exists(caminho_antigo):
            os.remove(caminho_antigo)

    aluno.foto_url = f"/v1/alunos/{aluno.id}/foto"
    db.session.commit()
    return aluno


def _e_passageiro_do_motorista(aluno_id, motorista_id) -> bool:
    passageiro = (
        db.session.query(AlunosConfirmados)
        .join(Viagem, Viagem.id == AlunosConfirmados.viagem_id)
        .filter(
            AlunosConfirmados.aluno_id == aluno_id,
            AlunosConfirmados.confirmacao.is_(True),
            Viagem.motorista_id == motorista_id,
            Viagem.status.in_([StatusViagem.AGENDADA, StatusViagem.EM_ANDAMENTO]),
        )
        .first()
    )
    if passageiro is not None:
        return True

    # On demand, during the buffer, the passenger is whoever already had their route accepted.
    trajeto_aceito = (
        db.session.query(SolicitacaoViagem)
        .join(Viagem, Viagem.id == SolicitacaoViagem.viagem_id)
        .filter(
            SolicitacaoViagem.aluno_id == aluno_id,
            SolicitacaoViagem.status == StatusSolicitacao.ATIVA,
            SolicitacaoViagem.ponto_embarque_id.isnot(None),
            Viagem.motorista_id == motorista_id,
            Viagem.status == StatusViagem.BUFFER_ABERTO,
        )
        .first()
    )
    return trajeto_aceito is not None


def buscar_foto(user_id: str, aluno_id: str) -> tuple[str, str]:
    """Path and type of the photo file.

    Allowed: the student, the organization's manager, and the driver of a trip not
    yet finished where the student confirmed presence (the one who checks boarding).
    Raises NotFoundError, ForbiddenError.
    """
    quem_pede: User = _get_user_or_404(user_id)
    aluno = db.session.get(Aluno, validate_uuid(aluno_id, "Aluno ID"))
    if not aluno:
        raise NotFoundError("Aluno não encontrado")

    if quem_pede.id != aluno.id:
        if quem_pede.role not in (UserRole.GESTOR, UserRole.MOTORISTA):
            raise ForbiddenError("Sem permissão para ver esta foto")
        if quem_pede.organizacao_id != aluno.organizacao_id:
            raise ForbiddenError("Aluno não pertence à sua organização")
        if quem_pede.role == UserRole.MOTORISTA and not _e_passageiro_do_motorista(
            aluno.id, quem_pede.id
        ):
            raise ForbiddenError("Aluno não é passageiro de uma viagem sua")

    for tipo, extensao in EXTENSOES_FOTO.items():
        caminho = _caminho_foto(str(aluno.id), extensao)
        if os.path.exists(caminho):
            return caminho, tipo
    raise NotFoundError("Aluno sem foto cadastrada")
