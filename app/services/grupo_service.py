"""Grupos de passageiros: o gestor cria grupos e controla quem participa deles."""

from datetime import date
from typing import Any

from sqlalchemy import case, func

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.transaction import transactional
from app.models.base import db
from app.models.convite import Convite
from app.models.enum import StatusViagem, UserStatus
from app.models.grupo import Grupo, GrupoMembro, convite_grupo
from app.models.user import Aluno, User
from app.models.viagem import AlunosConfirmados, Viagem
from app.services.user_service import _get_gestor_or_403
from app.utils import audit_logger, validate_uuid

CAMPOS_DO_GRUPO = ("nome", "descricao", "data_inicio", "data_fim")


def _grupo_da_organizacao(gestor, grupo_id: str) -> Grupo:
    grupo = db.session.get(Grupo, validate_uuid(grupo_id, "Grupo"))
    if grupo is None or str(grupo.organizacao_id) != str(gestor.organizacao_id):
        raise NotFoundError("Grupo não encontrado")
    return grupo


def _tem_filhos(grupo: Grupo) -> bool:
    if grupo.id is None:
        return False
    with db.session.no_autoflush:
        filho = Grupo.query.filter(Grupo.grupo_pai_id == grupo.id).first()
    return filho is not None


def _pai_como_uuid(valor: str | None):
    if valor is None:
        return None
    return validate_uuid(valor, "Grupo pai")


def _validar_pai(grupo: Grupo) -> None:
    """Um nível só: o pai é um grupo raiz da mesma organização, e quem tem filhos não tem pai."""
    if grupo.grupo_pai_id is None:
        return
    if grupo.grupo_pai_id == grupo.id:
        raise ValidationError("Um grupo não pode ser pai de si mesmo")

    pai = db.session.get(Grupo, grupo.grupo_pai_id)
    if pai is None or pai.organizacao_id != grupo.organizacao_id:
        raise ValidationError("Grupo pai inválido")
    if pai.grupo_pai_id is not None:
        raise ValidationError("O grupo pai precisa ser um grupo raiz")
    if _tem_filhos(grupo):
        raise ValidationError("Um grupo com subgrupos não pode ter pai")


def _validar_datas(data_inicio: date | None, data_fim: date | None) -> None:
    if data_inicio is not None and data_fim is not None and data_fim < data_inicio:
        raise ValidationError("A data de fim não pode ser anterior à data de início")


def _validar_nome_livre(grupo: Grupo) -> None:
    # Sem autoflush, o nome repetido chega aqui e não vira erro genérico de integridade.
    with db.session.no_autoflush:
        repetido = Grupo.query.filter(
            Grupo.organizacao_id == grupo.organizacao_id,
            Grupo.nome == grupo.nome,
            Grupo.id != grupo.id,
        ).first()
    if repetido is not None:
        raise ConflictError("Já existe um grupo com este nome", field="nome")


# ─── Grupos ────────────────────────────────────────────────────────────────────


def criar_grupo(gestor_id: str, dados: dict[str, Any]) -> Grupo:
    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem criar grupos")
    _validar_datas(dados.get("data_inicio"), dados.get("data_fim"))

    grupo = Grupo(
        organizacao_id=gestor.organizacao_id,
        grupo_pai_id=_pai_como_uuid(dados.get("grupo_pai_id")),
        nome=dados["nome"],
        descricao=dados.get("descricao"),
        data_inicio=dados.get("data_inicio"),
        data_fim=dados.get("data_fim"),
    )
    _validar_pai(grupo)
    _validar_nome_livre(grupo)

    with transactional():
        db.session.add(grupo)

    audit_logger.log_user_action(
        action="criar_grupo",
        user_id=gestor_id,
        resource_type="grupo",
        resource_id=str(grupo.id),
    )
    return grupo


def listar_grupos(gestor_id: str) -> list[Grupo]:
    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem listar grupos")
    return Grupo.query.filter_by(organizacao_id=gestor.organizacao_id).order_by(Grupo.nome).all()


def atualizar_grupo(gestor_id: str, grupo_id: str, dados: dict[str, Any]) -> Grupo:
    """Muda só os campos enviados. Mandar `data_fim: null` reabre o grupo."""
    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem editar grupos")
    grupo = _grupo_da_organizacao(gestor, grupo_id)

    with transactional():
        for campo in CAMPOS_DO_GRUPO:
            if campo in dados:
                setattr(grupo, campo, dados[campo])
        if "grupo_pai_id" in dados:
            grupo.grupo_pai_id = _pai_como_uuid(dados["grupo_pai_id"])
        _validar_datas(grupo.data_inicio, grupo.data_fim)
        _validar_pai(grupo)
        _validar_nome_livre(grupo)

    audit_logger.log_user_action(
        action="atualizar_grupo",
        user_id=gestor_id,
        resource_type="grupo",
        resource_id=str(grupo.id),
    )
    return grupo


def apagar_grupo(gestor_id: str, grupo_id: str) -> None:
    """Apaga o grupo e, em cascata, o histórico de vínculos dele. Bloqueado se tiver subgrupos."""
    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem apagar grupos")
    grupo = _grupo_da_organizacao(gestor, grupo_id)
    if _tem_filhos(grupo):
        raise ConflictError("Apague os subgrupos antes de apagar este grupo")

    with transactional():
        db.session.delete(grupo)

    audit_logger.log_user_action(
        action="apagar_grupo",
        user_id=gestor_id,
        resource_type="grupo",
        resource_id=grupo_id,
    )


# ─── Membros ───────────────────────────────────────────────────────────────────


def _vinculo_aberto(grupo_id, usuario_id) -> GrupoMembro | None:
    return GrupoMembro.query.filter(
        GrupoMembro.grupo_id == grupo_id,
        GrupoMembro.usuario_id == usuario_id,
        GrupoMembro.data_fim.is_(None),
    ).first()


def adicionar_membro(gestor_id: str, grupo_id: str, usuario_id: str) -> GrupoMembro:
    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem adicionar membros")
    grupo = _grupo_da_organizacao(gestor, grupo_id)
    if grupo.encerrado:
        raise ConflictError("O grupo está encerrado")

    aluno = db.session.get(Aluno, validate_uuid(usuario_id, "Passageiro"))
    organizacao_diferente = aluno is not None and aluno.organizacao_id != gestor.organizacao_id
    if aluno is None or organizacao_diferente or aluno.status == UserStatus.DELETED:
        raise NotFoundError("Passageiro não encontrado")

    if _vinculo_aberto(grupo.id, aluno.id) is not None:
        raise ConflictError("O passageiro já participa deste grupo")

    vinculo = GrupoMembro(grupo_id=grupo.id, usuario_id=aluno.id)
    with transactional():
        db.session.add(vinculo)

    audit_logger.log_user_action(
        action="adicionar_membro_grupo",
        user_id=gestor_id,
        resource_type="grupo",
        resource_id=str(grupo.id),
        details={"usuario_id": str(aluno.id)},
    )
    return vinculo


def remover_membro(gestor_id: str, grupo_id: str, usuario_id: str) -> None:
    """Fecha o vínculo aberto. O histórico fica, e quem volta ganha um vínculo novo."""
    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem remover membros")
    grupo = _grupo_da_organizacao(gestor, grupo_id)

    vinculo = _vinculo_aberto(grupo.id, validate_uuid(usuario_id, "Passageiro"))
    if vinculo is None:
        raise NotFoundError("O passageiro não participa deste grupo")

    with transactional():
        vinculo.data_fim = date.today()

    audit_logger.log_user_action(
        action="remover_membro_grupo",
        user_id=gestor_id,
        resource_type="grupo",
        resource_id=str(grupo.id),
        details={"usuario_id": usuario_id},
    )


def listar_membros(gestor_id: str, grupo_id: str) -> list[dict[str, Any]]:
    """Vínculos do grupo e dos subgrupos dele, atuais e antigos, com as viagens de cada um."""
    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem ver os membros")
    grupo = _grupo_da_organizacao(gestor, grupo_id)

    # Quem está num subgrupo conta como membro do pai.
    grupo_ids = [grupo.id]
    for filho in Grupo.query.filter(Grupo.grupo_pai_id == grupo.id).all():
        grupo_ids.append(filho.id)

    # O período de um vínculo termina na saída da pessoa, no fim do grupo dele ou hoje, o que vier antes.
    hoje = date.today()
    fim_do_periodo = func.least(
        func.coalesce(GrupoMembro.data_fim, hoje), func.coalesce(Grupo.data_fim, hoje), hoje
    )

    linhas = (
        db.session.query(
            GrupoMembro,
            Grupo,
            User.nome,
            func.count(case((Viagem.status != StatusViagem.CANCELADA, Viagem.id))),
            func.count(case((Viagem.status == StatusViagem.FINALIZADA, Viagem.id))),
            func.count(case((AlunosConfirmados.embarcou.is_(True), Viagem.id))),
        )
        .join(Grupo, Grupo.id == GrupoMembro.grupo_id)
        .join(User, User.id == GrupoMembro.usuario_id)
        .outerjoin(
            AlunosConfirmados,
            (AlunosConfirmados.aluno_id == GrupoMembro.usuario_id)
            & AlunosConfirmados.confirmacao.is_(True),
        )
        .outerjoin(
            Viagem,
            (Viagem.id == AlunosConfirmados.viagem_id)
            & (Viagem.data >= GrupoMembro.data_inicio)
            & (Viagem.data <= fim_do_periodo),
        )
        .filter(GrupoMembro.grupo_id.in_(grupo_ids))
        .group_by(GrupoMembro.id, Grupo.id, User.nome)
        .order_by(GrupoMembro.data_inicio.desc(), User.nome)
        .all()
    )

    membros: list[dict[str, Any]] = []
    for vinculo, grupo_do_vinculo, nome, confirmadas, finalizadas, com_presenca in linhas:
        membros.append(
            {
                "grupo_id": str(grupo_do_vinculo.id),
                "grupo_nome": grupo_do_vinculo.nome,
                "usuario_id": str(vinculo.usuario_id),
                "nome": nome,
                "data_inicio": vinculo.data_inicio,
                "data_fim": vinculo.data_fim,
                "atual": vinculo.data_fim is None and not grupo_do_vinculo.encerrado,
                "viagens_confirmadas": confirmadas,
                "viagens_finalizadas": finalizadas,
                "viagens_com_presenca": com_presenca,
            }
        )
    return membros


# ─── Convite ───────────────────────────────────────────────────────────────────


def grupos_do_convite(valores: Any, organizacao_id) -> list[Grupo]:
    """Grupos pedidos no convite. Cada um precisa ser da organização e não estar encerrado."""
    if valores is None:
        return []
    if not isinstance(valores, list):
        raise ValidationError("O campo grupo_ids deve ser uma lista")

    grupos: list[Grupo] = []
    for valor in valores:
        grupo = db.session.get(Grupo, validate_uuid(valor, "Grupo"))
        if grupo is None or str(grupo.organizacao_id) != str(organizacao_id):
            raise ValidationError("Grupo inválido")
        if grupo.encerrado:
            raise ValidationError(f"O grupo {grupo.nome} está encerrado")
        if grupo not in grupos:
            grupos.append(grupo)
    return grupos


def entrar_nos_grupos_do_convite(convite: Convite, aluno: Aluno) -> None:
    """Chamado dentro da transação que conclui o convite. Grupo que encerrou nesse meio tempo é ignorado."""
    grupos = (
        Grupo.query.join(convite_grupo, convite_grupo.c.grupo_id == Grupo.id)
        .filter(convite_grupo.c.convite_id == convite.id)
        .all()
    )
    for grupo in grupos:
        if grupo.encerrado:
            continue
        db.session.add(GrupoMembro(grupo_id=grupo.id, usuario_id=aluno.id))
