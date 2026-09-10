# 0001. Produto do zero em vez de continuar o fork do municipal-backend

Status: aceita. Data: 2026-09-09.

## Contexto

Este repositório nasceu em 03/08/2026 como cópia integral do
`municipal-backend`, via `git archive`. `ARQUITETURA_REPOSITORIOS.md` seção 3
registra o problema que isso trouxe: código do BusKá (Aluno, Instituicao,
gerenciamento de inscrição em rota) misturado com código genérico (User,
Motorista, Ponto) na mesma árvore, sem fronteira mecânica entre os dois.

## Decisão

Este repositório passa a ser escrito do zero como o produto do Parque
Tecnológico da Paraíba, não mais como fork do `municipal-backend`. Mantém a
mesma stack e o mesmo pipeline de verificação (`black`, `ruff`, `mypy`,
`pytest`, `pre-commit`, CI, Conventional Commits, a convenção de `AGENTS.md`
e `docs/adr/`). Não mantém nenhuma linha de código de domínio herdada do
fork: `Aluno`, `Instituicao`, `Organizacao` (tenant multi-cliente), as rotas
e serviços de rota escolar saem todos.

## Por que

`ARQUITETURA_REPOSITORIOS.md` seção 4 já registra que cliente corporativo não
compartilha runtime como prefeitura compartilha: cada cliente corporativo tem
seu próprio deploy. Isso remove a necessidade do modelo `Organizacao`
multi-tenant inteiro, que só faz sentido pro lado municipal. Sem essa
simplificação, qualquer extração futura de núcleo compartilhado teria que
desfazer decisões deste repositório que nunca deveriam ter sido tomadas aqui
primeiro.

## Consequência

O domínio (`Passageiro`, `Projeto`, o motor de rota sob demanda, telemetria
de bateria) é escrito direto para o que o Parque Tecnológico precisa, sem
generalização prematura pra um núcleo compartilhado que ainda não existe. Se
um segundo cliente corporativo aparecer, a extração parte deste repositório,
não do `municipal-backend` — ao contrário do que `ARQUITETURA_REPOSITORIOS.md`
seção 6 previa antes desta decisão, que assumia a extração vindo do
`municipal-backend` e este repositório sendo aposentado.
