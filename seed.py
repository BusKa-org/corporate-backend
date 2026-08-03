"""Dados de desenvolvimento do MeBusKá Corporativo.

Monta uma operação genérica e completa: uma organização, instituições
atendidas, o circuito de pontos ordenados, um veículo, janelas de
disponibilidade e algumas rodadas encerradas para o dashboard (RF-21) ter série
histórica.

**Nada aqui é de nenhum cliente.** Nomes, siglas, coordenadas e capacidade são
valores de demonstração. Os dados reais de cada implantação — instituições,
circuito, veículo — moram no repositório de deploy do cliente, que semeia por
cima deste produto. Ver `docs/plugins.md` e `ARQUITETURA_REPOSITORIOS.md`.

Idempotente: rodar de novo não duplica nada.

    make seed
"""

from datetime import UTC, date, datetime, time, timedelta

from werkzeug.security import generate_password_hash

from app import create_app
from app.models.base import db
from app.models.consentimento import Consentimento
from app.models.enum import (
    DiaDaSemana,
    StatusSolicitacao,
    StatusViagem,
    TipoInstituicao,
    UserRole,
    UserStatus,
)
from app.models.geo import Instituicao, Ponto
from app.models.janela import JanelaDisponibilidade
from app.models.onibus import Onibus
from app.models.organizacao import Organizacao
from app.models.rota import Rota, RotaPonto
from app.models.telemetria import TelemetriaVeiculo
from app.models.user import Aluno, Gestor, Motorista
from app.models.viagem import AlunosConfirmados, Viagem, ViagemPonto

app = create_app()

SENHA_DEV = "buska123"
ORG_SIGLA = "DEMO"
CAPACIDADE_DEMO = 20
TERMO_VERSAO = "1.0"

# Coordenadas arbitrárias, só para os pontos não ficarem sobrepostos no mapa.
CIRCUITO = [
    ("Ponto 1 — Sede", -7.2100, -35.9100),
    ("Ponto 2 — Campus Norte", -7.2160, -35.9080),
    ("Ponto 3 — Campus Sul", -7.2320, -35.8940),
    ("Ponto 4 — Centro de Pesquisa", -7.2380, -35.8900),
]

INSTITUICOES = [
    ("Instituição Demonstração A", "DEMOA", TipoInstituicao.UNIVERSIDADE_PUBLICA, 1),
    ("Instituição Demonstração B", "DEMOB", TipoInstituicao.UNIVERSIDADE_PUBLICA, 2),
    ("Parque Demonstração", "DEMOP", TipoInstituicao.PARQUE_TECNOLOGICO, 0),
    ("Centro Demonstração", "DEMOC", TipoInstituicao.CENTRO_INOVACAO, 3),
]

PESSOAS = [
    ("Ana Carolina Ferreira", "ana@demo.dev", "11111111011", "DEMOP"),
    ("Bruno Almeida Santos", "bruno@demo.dev", "11111111022", "DEMOA"),
    ("Carla Nogueira Lima", "carla@demo.dev", "11111111033", "DEMOB"),
    ("Diego Martins Rocha", "diego@demo.dev", "11111111044", "DEMOC"),
    ("Elaine Souza Barbosa", "elaine@demo.dev", "11111111055", "DEMOA"),
    ("Felipe Cardoso Melo", "felipe@demo.dev", "11111111066", "DEMOP"),
]


def _ja_semeado() -> bool:
    return db.session.query(Organizacao).filter_by(sigla=ORG_SIGLA).first() is not None


def _organizacao() -> Organizacao:
    org = Organizacao(nome="Organização Demonstração", sigla=ORG_SIGLA)
    db.session.add(org)
    db.session.flush()
    return org


def _pontos(org: Organizacao) -> list[Ponto]:
    pontos = []
    for apelido, lat, lon in CIRCUITO:
        p = Ponto(organizacao_id=org.id, latitude=lat, longitude=lon, apelido=apelido)
        db.session.add(p)
        pontos.append(p)
    db.session.flush()
    return pontos


def _instituicoes(org: Organizacao, pontos: list[Ponto]) -> dict[str, Instituicao]:
    por_sigla = {}
    for nome, sigla, tipo, indice in INSTITUICOES:
        inst = Instituicao(
            nome=nome,
            sigla=sigla,
            tipo=tipo,
            # MANUAL, não EMEC/INEP: registros curados, não importados de
            # catálogo. O código externo é a própria sigla, que é estável.
            fonte="MANUAL",
            codigo_externo=sigla,
            uf="PB",
            organizacao_id=org.id,
            ponto_id=pontos[indice].id,
            situacao="ATIVA",
        )
        db.session.add(inst)
        por_sigla[sigla] = inst
    db.session.flush()
    return por_sigla


def _equipe(org: Organizacao, senha: str) -> tuple[Gestor, Motorista]:
    gestor = Gestor(
        organizacao_id=org.id,
        nome="Maria das Graças Silva",
        email="gestor@demo.dev",
        senha_hash=senha,
        cpf="12345678901",
        telefone="83999990001",
        role=UserRole.GESTOR,
        status=UserStatus.ACTIVE,
        signup_completed_at=datetime.now(UTC),
    )
    motorista = Motorista(
        organizacao_id=org.id,
        nome="José Ribamar da Costa",
        email="motorista@demo.dev",
        senha_hash=senha,
        cpf="12345678902",
        telefone="83999990002",
        cnh="98765432100",
        role=UserRole.MOTORISTA,
        status=UserStatus.ACTIVE,
        signup_completed_at=datetime.now(UTC),
    )
    db.session.add_all([gestor, motorista])
    db.session.flush()
    return gestor, motorista


def _alunos(org: Organizacao, insts: dict[str, Instituicao], senha: str) -> list[Aluno]:
    criados = []
    for indice, (nome, email, cpf, sigla) in enumerate(PESSOAS):
        # O último fica pendente de aprovação, para a fila do gestor (RF-02)
        # não nascer vazia.
        pendente = indice == len(PESSOAS) - 1
        aluno = Aluno(
            organizacao_id=org.id,
            nome=nome,
            email=email,
            senha_hash=senha,
            cpf=cpf,
            telefone=f"8398888{indice:04d}",
            role=UserRole.ALUNO,
            status=UserStatus.PENDING_APPROVAL if pendente else UserStatus.ACTIVE,
            signup_completed_at=None if pendente else datetime.now(UTC),
            instituicao_id=insts[sigla].id,
        )
        db.session.add(aluno)
        criados.append(aluno)
    db.session.flush()

    # Consentimento vigente para quem já está ativo — sem ele o RF-10 barra a
    # solicitação e o ambiente de desenvolvimento não sai do lugar.
    for aluno in criados:
        if aluno.status == UserStatus.ACTIVE:
            db.session.add(
                Consentimento(
                    usuario_id=aluno.id,
                    versao_termo=TERMO_VERSAO,
                    aceito_em=datetime.now(UTC),
                    ip_origem="127.0.0.1",
                )
            )
    db.session.flush()
    return criados


def _frota_e_circuito(org, motorista, pontos) -> tuple[Onibus, Rota]:
    veiculo = Onibus(
        organizacao_id=org.id,
        placa="DEM0A20",
        modelo="Veículo de Demonstração",
        capacidade=CAPACIDADE_DEMO,
    )
    db.session.add(veiculo)
    db.session.flush()

    rota = Rota(
        organizacao_id=org.id,
        nome="Circuito Demonstração",
        motorista_padrao_id=motorista.usuario_id,
        veiculo_padrao_id=veiculo.id,
    )
    db.session.add(rota)
    db.session.flush()

    for ordem, ponto in enumerate(pontos, start=1):
        db.session.add(RotaPonto(rota_id=rota.id, ponto_id=ponto.id, ordem=ordem))
    db.session.flush()
    return veiculo, rota


def _janelas(org, rota, motorista, veiculo) -> None:
    """Manhã e tarde, de segunda a sexta."""
    uteis = (DiaDaSemana.SEG, DiaDaSemana.TER, DiaDaSemana.QUA, DiaDaSemana.QUI, DiaDaSemana.SEX)
    for dia in uteis:
        for inicio, fim in ((time(7, 0), time(12, 0)), (time(13, 0), time(18, 0))):
            db.session.add(
                JanelaDisponibilidade(
                    organizacao_id=org.id,
                    rota_id=rota.id,
                    motorista_id=motorista.usuario_id,
                    veiculo_id=veiculo.id,
                    dia=dia,
                    hora_inicio=inicio,
                    hora_fim=fim,
                    buffer_minutos=5,
                    ativo=True,
                )
            )
    db.session.flush()


def _historico(org, rota, motorista, veiculo, pontos, alunos) -> int:
    """Rodadas encerradas nos últimos dias, para o RF-21 ter série histórica.

    Inclui negações de propósito: o estrangulamento por ponto é o indicador que
    o gestor olha primeiro, e ele nasce vazio sem isto.
    """
    ativos = [a for a in alunos if a.status == UserStatus.ACTIVE]
    rodadas = 0

    for dias_atras in range(1, 6):
        dia = date.today() - timedelta(days=dias_atras)
        viagem = Viagem(
            data=dia,
            rota_id=rota.id,
            motorista_id=motorista.usuario_id,
            veiculo_id=veiculo.id,
            status=StatusViagem.FINALIZADA,
            inicio_real=datetime.combine(dia, time(8, 0), tzinfo=UTC),
            fim_real=datetime.combine(dia, time(8, 40), tzinfo=UTC),
            km_real=12.5,
        )
        db.session.add(viagem)
        db.session.flush()

        for ordem, ponto in enumerate(pontos, start=1):
            db.session.add(
                ViagemPonto(
                    viagem_id=viagem.id,
                    ponto_id=ponto.id,
                    ordem=ordem,
                    visitado=True,
                    chegada_real=datetime.combine(dia, time(8, ordem * 10), tzinfo=UTC),
                )
            )

        # A cada duas rodadas, o primeiro da lista é recusado no gargalo em vez
        # de embarcar. Ele não pode aparecer nos dois papéis: a linha da rodada
        # tem chave (viagem, aluno).
        houve_negacao = dias_atras % 2 == 0 and bool(ativos)
        confirmados = ativos[1:] if houve_negacao else ativos

        for indice, aluno in enumerate(confirmados):
            origem, destino = pontos[0], pontos[2 if indice % 2 else 3]
            db.session.add(
                AlunosConfirmados(
                    viagem_id=viagem.id,
                    aluno_id=aluno.usuario_id,
                    status=StatusSolicitacao.CONFIRMADO,
                    confirmacao=True,
                    ponto_embarque_id=origem.id,
                    ponto_destino_id=destino.id,
                    embarcou=True,
                    embarcado_em=datetime.combine(dia, time(8, 5), tzinfo=UTC),
                    declarado_em=datetime.combine(dia, time(7, 55), tzinfo=UTC),
                )
            )

        # Sempre no mesmo ponto, para o estrangulamento aparecer no relatório.
        if houve_negacao:
            db.session.add(
                AlunosConfirmados(
                    viagem_id=viagem.id,
                    aluno_id=ativos[0].usuario_id,
                    status=StatusSolicitacao.NEGADO,
                    confirmacao=False,
                    ponto_embarque_id=pontos[1].id,
                    ponto_destino_id=pontos[3].id,
                    declarado_em=datetime.combine(dia, time(7, 58), tzinfo=UTC),
                )
            )

        db.session.add(
            TelemetriaVeiculo(
                veiculo_id=veiculo.id,
                viagem_id=viagem.id,
                timestamp=datetime.combine(dia, time(8, 40), tzinfo=UTC),
                nivel_bateria=90 - dias_atras * 3,
                consumo_kwh=4.2,
                autonomia_km=120,
                odometro_km=1000 + dias_atras * 12.5,
            )
        )
        rodadas += 1

    db.session.flush()
    return rodadas


def _rodada_ociosa(rota, motorista, veiculo) -> None:
    """A rodada de hoje, esperando a primeira solicitação (RF-10)."""
    db.session.add(
        Viagem(
            data=date.today(),
            rota_id=rota.id,
            motorista_id=motorista.usuario_id,
            veiculo_id=veiculo.id,
            status=StatusViagem.OCIOSA,
        )
    )
    db.session.flush()


def seed_demo_data() -> None:
    print("\n" + "=" * 60)
    print("MeBusKá Corporativo — dados de demonstração")
    print("=" * 60 + "\n")

    if _ja_semeado():
        print("Já semeado. Nada a fazer.\n")
        return

    senha = generate_password_hash(SENHA_DEV)

    org = _organizacao()
    print(f"Organização: {org.nome} ({org.sigla})")

    pontos = _pontos(org)
    print(f"Circuito: {len(pontos)} pontos ordenados")

    insts = _instituicoes(org, pontos)
    print(f"Instituições: {', '.join(insts)}")

    _gestor, motorista = _equipe(org, senha)
    alunos = _alunos(org, insts, senha)
    print(f"Pessoas: 1 gestor, 1 motorista, {len(alunos)} usuários")

    veiculo, rota = _frota_e_circuito(org, motorista, pontos)
    _janelas(org, rota, motorista, veiculo)
    print(f"Frota: {veiculo.placa} ({veiculo.capacidade} lugares); janelas seg-sex, manhã e tarde")

    rodadas = _historico(org, rota, motorista, veiculo, pontos, alunos)
    _rodada_ociosa(rota, motorista, veiculo)
    print(f"Histórico: {rodadas} rodadas finalizadas + a rodada ociosa de hoje")

    db.session.commit()

    print("\n" + "-" * 60)
    print(f"Senha de todos os acessos: {SENHA_DEV}")
    print("  gestor@demo.dev        gestor")
    print("  motorista@demo.dev     motorista")
    for nome, email, _cpf, sigla in PESSOAS:
        print(f"  {email:<22} {nome} ({sigla})")
    print(f"\n{PESSOAS[-1][1]} está PENDING_APPROVAL, para exercitar o RF-02.")
    print("-" * 60 + "\n")


def seed_database() -> None:
    with app.app_context():
        try:
            seed_demo_data()
        except Exception as e:
            db.session.rollback()
            print(f"\nErro: {e}")
            raise


if __name__ == "__main__":
    seed_database()
