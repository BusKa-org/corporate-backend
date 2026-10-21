"""Student (Aluno) service - profile management and gestor queries."""

import logging
import os
from typing import IO, Any, cast

from flask import current_app

from app.core.exceptions import (
    AppError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.models.base import db
from app.models.enum import UserRole, UserStatus
from app.models.geo import Endereco, Ponto
from app.models.user import Aluno, User
from app.services.user_service import _get_gestor_or_403, _get_user_or_404
from app.utils.validators import validate_uuid

logger = logging.getLogger(__name__)


def update_me(user_id: str, data: dict[str, Any]) -> Aluno:
    """
    Atualiza perfil do aluno.

    Returns: Aluno object
    Raises: NotFoundError, AppError
    """
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
            "necessidades_acessibilidade",
            "observacao_acessibilidade",
        ):
            if field in data:
                setattr(aluno, field, data[field])

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
    """
    Gestor retrieves full details for a single aluno.

    Raises: ForbiddenError, NotFoundError
    """
    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem consultar alunos")
    aluno = db.session.get(Aluno, aluno_id)

    if not aluno:
        raise NotFoundError("Aluno não encontrado")
    if str(aluno.organizacao_id) != str(gestor.organizacao_id):
        raise ForbiddenError("Aluno não pertence à sua organização")

    return aluno


def list_alunos_gestor(gestor_id: str, status: str | None = None) -> list[Aluno]:
    """
    Lista alunos da organização (apenas para gestores).
    Optionally filter by status (e.g. 'PENDING_APPROVAL').

    Returns: List of Aluno objects
    Raises: ForbiddenError
    """
    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem listar alunos")
    q = db.session.query(Aluno).filter_by(organizacao_id=gestor.organizacao_id)
    if status:
        try:
            q = q.filter(Aluno.status == UserStatus[status])
        except KeyError:
            pass
    return q.all()


# Extensão do arquivo por tipo. O tipo vem dos primeiros bytes, não do nome nem do
# Content-Type enviado pelo cliente.
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
    """Remove o arquivo da foto do aluno, qualquer que seja a extensão."""
    for extensao in EXTENSOES_FOTO.values():
        caminho = _caminho_foto(aluno_id, extensao)
        if os.path.exists(caminho):
            os.remove(caminho)


def salvar_foto(user_id: str, arquivo: IO[bytes]) -> Aluno:
    """
    Aluno envia a própria foto (usada na conferência do embarque, RF-17).

    Raises: NotFoundError, ValidationError
    """
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

    os.makedirs(current_app.config["FOTOS_ALUNO_DIR"], exist_ok=True)
    apagar_foto(str(aluno.id))
    with open(_caminho_foto(str(aluno.id), EXTENSOES_FOTO[tipo]), "wb") as destino:
        destino.write(conteudo)

    aluno.foto_url = f"/v1/alunos/{aluno.id}/foto"
    db.session.commit()
    return aluno


def buscar_foto(user_id: str, aluno_id: str) -> tuple[str, str]:
    """
    Caminho e tipo do arquivo da foto. Podem ver: o próprio aluno, e gestor ou
    motorista da mesma organização.

    Raises: NotFoundError, ForbiddenError
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

    for tipo, extensao in EXTENSOES_FOTO.items():
        caminho = _caminho_foto(str(aluno.id), extensao)
        if os.path.exists(caminho):
            return caminho, tipo
    raise NotFoundError("Aluno sem foto cadastrada")
