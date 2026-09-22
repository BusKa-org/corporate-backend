# RF-15 — Credencial QR de embarque vinculada à foto do passageiro

Status: pronto para implementação. Gerado a partir de uma sessão de grilling
em 2026-09-21, registrada na conversa que originou este arquivo.

## Problem Statement

No modelo do PaqTcPB, um passageiro só pode embarcar depois que o motorista
confirma, visualmente, que a pessoa na porta da van é quem o sistema espera
(RF-17, RF-MOT-06). Hoje não existe nenhuma credencial digital que carregue
essa identidade de forma verificável: o sistema aceita a solicitação de
viagem, mas não emite nada que o motorista possa ler e conferir contra uma
foto. Sem essa credencial, RF-17 não tem o que ler, e a conferência de foto
vira um processo manual sem registro.

O passageiro também usa dois tipos de viagem, rota definida (horário fixo,
cadastrado pelo gestor) e rota por demanda (buffer e vetor de capacidade,
RF-10 a RF-14). Os dois precisam do mesmo passo de confirmação por QR, mas
são produzidos por mecanismos de aceitação diferentes, e só um deles (rota
por demanda) está especificado em detalhe hoje.

## Solution

Um módulo isolado, `CredencialEmbarque`, que recebe uma decisão já tomada
("este aluno está confirmado nesta viagem, neste ponto de embarque") e emite
uma credencial única: um token opaco, vinculado à viagem, ao aluno e ao ponto
de embarque, com expiração e marca de uso. O módulo não decide quem embarca,
só emite e valida a credencial de quem já foi aceito. Isso o mantém
utilizável pelos dois tipos de viagem, mesmo com o gatilho de rota definida
ainda não especificado, e independente da futura reescrita do fluxo de
aceitação (Plan 2 no `TODO.md`, hoje `AlunosConfirmados`/`RotaAluno`).

A foto do passageiro passa a existir como campo próprio no cadastro do
`Aluno`. A credencial referencia o aluno; a foto é buscada por junção no
momento da validação, nunca embutida no conteúdo do QR.

## User Stories

1. Como passageiro com embarque confirmado, quero receber uma credencial de
   embarque, para apresentá-la ao motorista na hora de entrar na van.
2. Como passageiro, quero que minha credencial só valha para a viagem em que
   fui confirmado, para que ela não sirva de embarque em outra viagem minha
   ou de outra pessoa.
3. Como passageiro, quero que minha credencial esteja ligada ao ponto de
   embarque que eu declarei, para que o motorista só a aceite no ponto
   certo.
4. Como motorista (consumidor futuro desta credencial, via RF-17), quero
   recuperar a foto cadastrada do passageiro a partir da credencial, para
   comparar com a pessoa à minha frente.
5. Como sistema, quero que a credencial expire, para que uma viagem presa em
   estado "em andamento" por falha operacional não mantenha credenciais
   válidas indefinidamente.
6. Como sistema, quero marcar a credencial como usada assim que o embarque
   for confirmado, para impedir que a mesma credencial sirva para embarcar
   duas vezes.
7. Como desenvolvedor do próximo passo (Plan 2, ciclo de vida da viagem),
   quero chamar "gerar credencial" a partir de qualquer mecanismo que decida
   quem está confirmado, seja o motor de buffer e capacidade da rota por
   demanda, seja o que vier a existir para rota definida, sem reescrever
   este módulo para cada um.
8. Como desenvolvedor, quero que a geração de credencial não dependa da
   tabela `AlunosConfirmados`, porque essa tabela está marcada para
   reescrita no `TODO.md` (débito de código item 1) e uma dependência direta
   duplicaria o trabalho de migração.
9. Como sistema, quero recusar a geração de uma segunda credencial para o
   mesmo par viagem/aluno/ponto, para não acumular credenciais órfãs
   quando a mesma decisão de aceitação for reprocessada.
10. Como sistema, quero que o conteúdo do QR seja apenas um identificador
    opaco, sem dados do passageiro embutidos, para que o app do motorista
    dependa da cópia local da "matriz de permissões" (RF-18), não do
    conteúdo do próprio código.
11. Como time de segurança, quero que o token seja gerado por um gerador
    aleatório criptográfico de tamanho comparável ao já usado em
    `PasswordResetToken`, para que não seja adivinhável por tentativa.
12. Como passageiro sem foto cadastrada, quero que o sistema ainda gere
    minha credencial, deixando a ausência de foto como responsabilidade do
    fluxo de conferência (RF-17), não um bloqueio na emissão.
13. Como auditor, quero que cada credencial registre quando foi criada, para
    reconstituir a sequência de emissões de uma viagem.
14. Como sistema, quero que consultar uma credencial (validar o token) não
    tenha efeito colateral, para que leituras repetidas do mesmo QR, antes
    da confirmação efetiva do motorista, não alterem seu estado.
15. Como responsável pela arquitetura do repositório, quero que este código
    fique em `app/` do `corporate-backend`, seguindo a prática já
    documentada em `AGENTS.md` (implementar direto contra a estrutura
    herdada, generalizar depois), e não em `mebuska-deploy`, porque o
    acordo de IP que justificaria essa separação ainda não foi assinado
    (`TODO.md`, seção "Blocking").
16. Como gestor, quero que uma viagem cancelada ou já finalizada não permita
    a geração de novas credenciais, para não emitir crachás de embarque
    para uma viagem que não vai mais rodar.

## Implementation Decisions

- **Novo model**, `app/models/credencial_embarque.py`, classe
  `CredencialEmbarque`, tabela própria (`credencial_embarque`), sem alterar
  `AlunosConfirmados`:
  - `id` (UUID, chave primária)
  - `viagem_id` (FK `viagem.id`, `ondelete=CASCADE`)
  - `aluno_id` (FK `aluno.usuario_id`, `ondelete=CASCADE`)
  - `ponto_embarque_id` (FK `ponto.id`)
  - `token` (string, único, gerado com `secrets.token_urlsafe(32)`, mesmo
    padrão de `app/services/auth_service.py` para `PasswordResetToken`)
  - `expires_at` (datetime com timezone)
  - `usado` (boolean, default `False`)
  - `created_at` (datetime com timezone, `server_default=db.func.now()`)
  - Restrição de unicidade em `(viagem_id, aluno_id, ponto_embarque_id)`,
    cobrindo a história 9.

- **Novo campo**, `foto_url` (string, nullable) na classe `Aluno`, hoje
  dentro de `app/models/user.py` (o split para `app/models/aluno.py`
  descrito no PR `docs-agents-instructions` ainda não está em `main`; a
  coluna entra onde a classe está agora). Sem endpoint de upload, sem
  storage novo: o campo só existe para a credencial poder referenciar uma
  foto quando ela existir. Preenchimento do campo é responsabilidade de
  outra tarefa.

- **Novo service**, `app/services/credencial_embarque_service.py`, seguindo
  a convenção do repositório de que o service layer é dono da lógica de
  negócio (`AGENTS.md`, "Conventions enforced by tooling"):
  - `gerar_credencial(viagem_id, aluno_id, ponto_embarque_id)`: valida que a
    viagem existe e não está `CANCELADA`/`FINALIZADA` (história 16), gera o
    token, persiste e retorna a `CredencialEmbarque`. Levanta
    `ConflictError` se já existir credencial para o mesmo trio
    viagem/aluno/ponto (história 9), usando as exceções tipadas de
    `app/core/exceptions.py`, não `Exception` cru.
  - `validar_credencial(token)`: busca por token; levanta `NotFoundError` se
    não existir, `ValidationError` se `usado` for `True` ou `expires_at` já
    tiver passado. Não altera nenhum estado (história 14, só leitura). Não
    marca `usado`, não compara foto: isso pertence ao RF-17, fora deste
    escopo.

- **Endpoint HTTP de leitura, adicionado depois da primeira versão desta
  spec.** `GET /v1/viagens/<id>/credencial-embarque`, restrito ao papel
  `ALUNO`, devolve a credencial do aluno autenticado para aquela viagem
  (`app/api/controllers/viagens_controller.py`,
  `credencial_embarque_service.buscar_credencial_do_aluno`). Corrige um erro
  da primeira versão desta spec, que descartava qualquer endpoint HTTP: sem
  algum jeito de o app do passageiro buscar a própria credencial, a história
  1 ("quero receber uma credencial de embarque") não tem como acontecer,
  mesmo com o gatilho de geração (Plan 2) resolvido. Continuam fora: gerar a
  credencial via HTTP (isso é o Plan 2 chamando o service direto, não um
  endpoint) e validar por token (isso é RF-17, do lado do motorista).

- **Sem geração de imagem QR no backend.** O service devolve o token como
  string; renderizar o código de barras 2D é responsabilidade do cliente
  (app do passageiro), que já teria essa lib no lado mobile. Evita
  adicionar dependência nova ao backend para um problema que não é dele.

- **Token opaco, não JWT assinado.** RF-18 já resolve a validação offline
  por outro caminho: o app do motorista baixa a "matriz de permissões"
  inteira (roteiro, credenciais, fotos) antes da viagem, e valida contra
  esse dado local. O token só precisa bater com uma linha já sincronizada,
  não precisa se autoverificar. `pyjwt` é dependência do projeto, mas não é
  necessário aqui.

- **Migração Alembic** cobrindo a tabela `credencial_embarque` e a coluna
  `foto_url` em `usuario`/`aluno` (conforme o schema atual de herança
  Aluno/User), numa revisão só, seguindo o padrão de migrações existente em
  `migrations/versions/`.

- **Fora deste módulo, documentado como pendência**: o gatilho que decide
  quando chamar `gerar_credencial` (fim do buffer para rota por demanda,
  algo ainda não especificado para rota definida) pertence ao Plan 2
  (`TODO.md`) e não é resolvido aqui.

## Testing Decisions

Testes de serviço, no padrão de integração já usado no repositório
(`tests/integration/`, contra Postgres real, não SQLite, como em
`test_viagens_aluno_confirmacao.py` e `test_viagens_service.py`). Testar
comportamento externo do `credencial_embarque_service` (o que ele aceita, o
que devolve, o que levanta), não detalhes internos como o formato exato do
token.

Casos a cobrir em `tests/integration/test_credencial_embarque_service.py`:

- Geração bem-sucedida devolve uma credencial com token não vazio, viagem,
  aluno e ponto corretos, `usado=False`, `expires_at` no futuro.
- Gerar duas vezes para o mesmo trio viagem/aluno/ponto levanta
  `ConflictError` na segunda chamada.
- Gerar para uma viagem `CANCELADA` ou `FINALIZADA` levanta
  `ValidationError`.
- Validar um token existente e ainda válido devolve a credencial
  correspondente.
- Validar um token inexistente levanta `NotFoundError`.
- Validar um token marcado como `usado` levanta `ValidationError`.
- Validar um token com `expires_at` no passado levanta `ValidationError`.
- Validar o mesmo token duas vezes seguidas não altera nenhuma coluna
  (prova de que a leitura não tem efeito colateral).

Não existe hoje um arquivo de teste para `PasswordResetToken` no
repositório, então esse padrão de token com expiração não tem teste
próprio para copiar diretamente; o código de `auth_service.py` (geração e
checagem de expiração) serve de referência de implementação, não de
prior art de teste.

## Out of Scope

- Geração de imagem/QR code renderizado (fica no cliente).
- Endpoint HTTP para gerar a credencial ou para validar por token (o de
  leitura pelo próprio aluno existe, ver Implementation Decisions).
- RF-16 (roteiro do motorista) e RF-17 (leitura do QR, comparação de foto,
  confirmação do embarque, marcação de `usado`).
- Upload, armazenamento e edição da foto do passageiro (`foto_url` fica
  como coluna vazia até outra tarefa resolver isso).
- O gatilho real de geração em produção: nem o fim do buffer (RF-11 a
  RF-14, Plan 2) nem o mecanismo equivalente para rota definida, que ainda
  não foi especificado em nenhum documento revisado.
- Qualquer mudança em `AlunosConfirmados` ou `RotaAluno`.
- Sincronização offline (RF-18) e fila de eventos do app do motorista.

## Further Notes

- `Requisitos Motoristas.docx` descreve dois tipos de viagem (rota definida
  e rota por demanda) que não aparecem em `Documento de Requisitos.docx`.
  Os dois documentos concordam no fluxo de QR e foto, então esta spec não
  fica bloqueada por essa divergência, mas o Plan 2 (ciclo de vida da
  viagem) vai precisar reconciliar os dois documentos antes de desenhar o
  gatilho que este módulo espera receber.
- A colocação deste código em `app/` do `corporate-backend`, e não em
  `mebuska-deploy`, segue a prática documentada em `AGENTS.md` (PR aberto,
  ainda não mergeado no momento desta spec) e está condicionada ao acordo
  de IP com o PaqTcPB continuar em aberto (`TODO.md`, seção "Blocking";
  `ARQUITETURA_REPOSITORIOS.md`, seções 4 a 6). Se esse acordo for
  assinado antes da implementação, vale reconfirmar se este módulo ainda
  deve nascer aqui ou já direto em `mebuska-deploy`.
- O split de `Aluno` para `app/models/aluno.py`, descrito no PR
  `docs-agents-instructions`, ainda não está em `main`. Se esse PR for
  mergeado antes desta implementação, `foto_url` nasce no arquivo novo,
  não em `user.py`.
