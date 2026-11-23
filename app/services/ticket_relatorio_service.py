"""Relatório de consumo de tickets por política e, dentro de uma política, por passageiro.

Os tickets (gastos, devolvidos, concedidos) vêm do histórico e respeitam o período pela data
do movimento. As viagens vêm de `alunos_confirmados` e respeitam o período pela data da viagem.
"""

from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import case, func

from app.core.exceptions import NotFoundError, ValidationError
from app.models.base import db
from app.models.enum import StatusViagem, TipoMovimentoTicket
from app.models.ticket import MovimentoTicket, PoliticaTicket
from app.models.user import User
from app.models.viagem import AlunosConfirmados, Viagem
from app.services.ticket_saldo import FUSO
from app.services.user_service import _get_gestor_or_403
from app.utils import validate_uuid


def _soma_do_tipo(tipo: TipoMovimentoTicket):
    """Soma as quantidades dos movimentos de um tipo. Os outros tipos entram como zero."""
    return func.coalesce(
        func.sum(case((MovimentoTicket.tipo == tipo, MovimentoTicket.quantidade), else_=0)), 0
    )


def _condicao_do_periodo(de: date | None, ate: date | None) -> list:
    condicoes: list = []
    if de is not None:
        condicoes.append(MovimentoTicket.created_at >= datetime.combine(de, time.min, FUSO))
    if ate is not None:
        depois = datetime.combine(ate + timedelta(days=1), time.min, FUSO)
        condicoes.append(MovimentoTicket.created_at < depois)
    return condicoes


def _viagens_confirmadas(de: date | None, ate: date | None, agrupar_por):
    """Viagens com ticket pago ou liberado por uma política, contadas por política ou por pessoa."""
    consulta = (
        db.session.query(agrupar_por, func.count(AlunosConfirmados.viagem_id))
        .join(Viagem, Viagem.id == AlunosConfirmados.viagem_id)
        .filter(
            AlunosConfirmados.politica_ticket_id.isnot(None),
            AlunosConfirmados.confirmacao.is_(True),
            Viagem.status != StatusViagem.CANCELADA,
        )
    )
    if de is not None:
        consulta = consulta.filter(Viagem.data >= de)
    if ate is not None:
        consulta = consulta.filter(Viagem.data <= ate)
    return consulta.group_by(agrupar_por)


def _alvo(politica: PoliticaTicket) -> str:
    if politica.usuario_id is not None:
        return "PESSOA"
    if politica.grupo_id is not None:
        return "GRUPO"
    return "ORGANIZACAO"


def consumo_por_politica(
    gestor_id: str,
    de: date | None,
    ate: date | None,
    grupo_id: str | None,
) -> list[dict[str, Any]]:
    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem ver o consumo de tickets")
    _validar_periodo(de, ate)

    # O período entra na condição do join, assim política sem movimento no período aparece zerada.
    condicao_do_join = MovimentoTicket.politica_id == PoliticaTicket.id
    for condicao in _condicao_do_periodo(de, ate):
        condicao_do_join = condicao_do_join & condicao

    consulta = (
        db.session.query(
            PoliticaTicket,
            _soma_do_tipo(TipoMovimentoTicket.GASTO),
            _soma_do_tipo(TipoMovimentoTicket.DEVOLUCAO),
            _soma_do_tipo(TipoMovimentoTicket.CONCESSAO),
            func.count(
                case((MovimentoTicket.tipo == TipoMovimentoTicket.NO_SHOW, MovimentoTicket.id))
            ),
            func.count(
                func.distinct(
                    case(
                        (
                            MovimentoTicket.tipo == TipoMovimentoTicket.GASTO,
                            MovimentoTicket.usuario_id,
                        )
                    )
                )
            ),
        )
        .outerjoin(MovimentoTicket, condicao_do_join)
        .filter(PoliticaTicket.organizacao_id == gestor.organizacao_id)
    )
    if grupo_id is not None:
        consulta = consulta.filter(PoliticaTicket.grupo_id == validate_uuid(grupo_id, "Grupo"))
    linhas = consulta.group_by(PoliticaTicket.id).order_by(PoliticaTicket.nome).all()

    viagens_por_politica: dict = {}
    for politica_id, total in _viagens_confirmadas(
        de, ate, AlunosConfirmados.politica_ticket_id
    ).all():
        viagens_por_politica[politica_id] = total

    resultado: list[dict[str, Any]] = []
    for politica, gastos, devolvidos, concedidos, no_shows, passageiros in linhas:
        resultado.append(
            {
                "politica_id": str(politica.id),
                "nome": politica.nome,
                "alvo": _alvo(politica),
                "tipo": politica.tipo.value,
                "gastos": gastos,
                "devolvidos": devolvidos,
                "concedidos": concedidos,
                "no_shows": no_shows,
                "consumo_liquido": gastos - devolvidos,
                "passageiros": passageiros,
                "viagens": viagens_por_politica.get(politica.id, 0),
            }
        )
    return resultado


def consumo_por_passageiro(
    gestor_id: str, politica_id: str, de: date | None, ate: date | None
) -> list[dict[str, Any]]:
    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem ver o consumo de tickets")
    _validar_periodo(de, ate)

    politica = db.session.get(PoliticaTicket, validate_uuid(politica_id, "Política"))
    if politica is None or politica.organizacao_id != gestor.organizacao_id:
        raise NotFoundError("Política não encontrada")

    linhas = (
        db.session.query(
            MovimentoTicket.usuario_id,
            User.nome,
            _soma_do_tipo(TipoMovimentoTicket.GASTO),
            _soma_do_tipo(TipoMovimentoTicket.DEVOLUCAO),
            _soma_do_tipo(TipoMovimentoTicket.CONCESSAO),
            func.count(
                case((MovimentoTicket.tipo == TipoMovimentoTicket.NO_SHOW, MovimentoTicket.id))
            ),
        )
        .join(User, User.id == MovimentoTicket.usuario_id)
        .filter(MovimentoTicket.politica_id == politica.id, *_condicao_do_periodo(de, ate))
        .group_by(MovimentoTicket.usuario_id, User.nome)
        .order_by(User.nome)
        .all()
    )

    viagens_por_pessoa: dict = {}
    consulta_viagens = _viagens_confirmadas(de, ate, AlunosConfirmados.aluno_id).filter(
        AlunosConfirmados.politica_ticket_id == politica.id
    )
    for usuario_id, total in consulta_viagens.all():
        viagens_por_pessoa[usuario_id] = total

    resultado: list[dict[str, Any]] = []
    for usuario_id, nome, gastos, devolvidos, concedidos, no_shows in linhas:
        resultado.append(
            {
                "usuario_id": str(usuario_id),
                "nome": nome,
                "gastos": gastos,
                "devolvidos": devolvidos,
                "concedidos": concedidos,
                "no_shows": no_shows,
                "consumo_liquido": gastos - devolvidos,
                "viagens": viagens_por_pessoa.get(usuario_id, 0),
            }
        )
    return resultado


def _validar_periodo(de: date | None, ate: date | None) -> None:
    if de is not None and ate is not None and ate < de:
        raise ValidationError("O período termina antes de começar")
