# API contracts

Swagger UI (`/docs`) is the full reference. This file lists contract details that the
generated docs do not show.

## Foto do aluno

### `PUT /v1/alunos/me/foto`

Aluno envia a própria foto, usada pelo motorista na conferência do embarque (RF-15/RF-17).

- `multipart/form-data`, campo `foto`. Sem o campo: 400.
- Tipo decidido pelos primeiros bytes, não pelo nome nem pelo `Content-Type`: JPEG, PNG
  ou WEBP. Outro tipo, arquivo corrompido ou acima de `FOTO_ALUNO_MAX_BYTES`
  (padrão 5 MB): 400.
- Metadados são removidos antes de gravar: EXIF/GPS, XMP e comentários (JPEG), `eXIf`,
  `tEXt`, `zTXt`, `iTXt` e `tIME` (PNG), `EXIF` e `XMP ` (WEBP). O perfil de cor fica.
- A foto nova substitui a anterior. Se a gravação falhar (500), a anterior continua.
- Só aluno: outro papel recebe 404.
- 200: o perfil do aluno, com `foto_url` = `/v1/alunos/<id>/foto`.

### `GET /v1/alunos/<aluno_id>/foto`

Devolve a imagem (`image/jpeg`, `image/png` ou `image/webp`).

- Podem ver: o próprio aluno; o gestor da organização do aluno; o motorista de uma viagem
  `AGENDADA` ou `EM_ANDAMENTO` em que o aluno confirmou presença. Os demais: 403.
- `aluno_id` que não é UUID: 400. Aluno inexistente ou sem foto: 404.

## Acessibilidade do aluno

`necessidades_acessibilidade` (lista de `CADEIRA_DE_RODAS`, `MOBILIDADE_REDUZIDA`,
`DEFICIENCIA_VISUAL`, `DEFICIENCIA_AUDITIVA`, `DEFICIENCIA_INTELECTUAL`, `OUTRA`) e
`observacao_acessibilidade` (texto, até 500 caracteres) são aceitos em
`PUT /v1/alunos/me` e no aceite do convite (`POST /v1/convites/aceite/<token>`). Valor fora
da lista ou texto acima do limite: 400. Itens repetidos são guardados uma vez só, na ordem
em que vieram. Aparecem para o gestor (`GET /v1/alunos/<id>`) e para o motorista na lista
de passageiros da viagem. A exclusão da conta apaga os dois campos.
