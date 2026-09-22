# ADR 0010: pacientes, anamnese e documentos do Marco 2

**Status:** Aceito — M2.1, 2026-09-21

## Contexto

O M1 entregou identidade, autenticação, tenancy, RBAC, frontend operacional e
hardening, com RLS forçada nas tabelas tenant-aware e isolamento cross-tenant
provado. O M2 abre o primeiro domínio clínico do produto: pacientes, alertas
clínicos, anamnese versionada e documentos privados. Nenhuma tabela, endpoint
ou tela desses módulos existe ainda.

Este ADR materializa o contrato aprovado no §1 do plano antes de qualquer DDL:
modelos, estados, invariantes, rotas, matriz RBAC, fluxo de upload e estratégia
de compensação do storage. O M2.2 a M2.6 implementam banco, domínio, API,
frontend e prova de segurança sobre este contrato; divergência exige atualizar
explicitamente este documento.

## Decisão

### Fronteiras modulares e dependências (D1)

O M2 cria os módulos `patients`, `anamnesis` e `documents` em `apps/api/app/`,
além de um port de storage em `app/platform/storage.py` com adapter S3 em
`app/platform/s3_storage.py` (M2.5). Cada módulo segue a ADR 0003: routers
cuidam apenas de HTTP, services orquestram, repositories persistem e regras de
domínio não importam FastAPI nem SQLAlchemy. Não há repository, service ou
`Base*` genérico compartilhado entre módulos, e nenhum módulo acessa tabela de
outro fora de sua própria fronteira. O catálogo de anamnese é a única fonte de
IDs clínicos: M2.4 importa `SECTIONS` e os IDs de
`app/anamnesis/templates/cfo_2026_v1.py`, nunca strings soltas. As dependências
novas do M2.5 (`boto3` e `python-multipart`) entram com lockfile atualizado,
verificação de licenças e `pip-audit` no mesmo incremento.

### Perfil profissional global do usuário (D2)

`professional_profiles` é uma tabela **global pertencente ao usuário**, sem
`clinic_id`: `user_id` é a chave primária (FK `users.id`), com
`professional_name`, `cro_number` e `cro_state` (UF de duas letras) obrigatórios,
além de `created_at`/`updated_at`. A RLS é por proprietário — policy de
`SELECT`, `INSERT` e `UPDATE` com `user_id = app.current_user_id` (**sem**
`clinic_id`), `FORCE ROW LEVEL SECURITY` e sem `DELETE` para a role runtime.
`user_transaction` e `tenant_transaction` continuam funcionando porque ambos
instalam `app.current_user_id`; a policy de proprietário ignora a clínica.
`GET/PUT /api/v1/users/me/professional-profile` são estritamente autoescopados
pelo `Principal` e a aplicação **não** afirma validar o registro em base externa
do CFO. A conclusão da anamnese grava um snapshot imutável de nome profissional,
CRO e UF; alterar o perfil depois nunca altera versões já concluídas.

### Pacientes, alertas e estados (D3, D4)

`patients` pertence à clínica (`clinic_id NOT NULL`, FK `clinics.id`, RLS por
tenant com `FORCE ROW LEVEL SECURITY`) e usa UUID, `timestamptz` e FK composta
`(clinic_id, id)` como alvo dos filhos. Campos: `full_name` (obrigatório),
`social_name`, `birth_date` (obrigatório, não futura), `cpf` (opcional,
normalizado para 11 dígitos e validado), `phone` (obrigatório),
`phone_secondary`, `email`, endereço (`postal_code`, `street`, `number`,
`complement`, `district`, `city`, `state`), `occupation`, `nationality`,
`birthplace`, contato de emergência (nome, vínculo e telefone) e responsável
legal (nome, vínculo e telefone), `administrative_notes` e estado
`ACTIVE/ARCHIVED` com `archived_at`. Invariantes:

- nome, nascimento e telefone principal são obrigatórios;
- CPF é validado no service e há índice único parcial `(clinic_id, cpf) WHERE
cpf IS NOT NULL`, de modo que o CPF não se repete dentro da mesma clínica;
- menor de idade exige responsável com nome, vínculo e telefone na criação e
  na edição (validação de aplicação, não `CHECK` volátil);
- contato de emergência, quando informado, exige nome e telefone;
- arquivar é mudança de estado: nenhum endpoint e nenhum grant remove linhas
  fisicamente.

`patient_alerts` também é da clínica: FK composta `(clinic_id, patient_id)`,
`kind` em `ALLERGY/MEDICATION/CLINICAL_RISK/OTHER`, `description`, estado
`ACTIVE/RESOLVED` com `resolved_at`, autoria e datas. Resolver um alerta
preserva o histórico; não há exclusão física.

### Anamnese versionada (D5)

`anamneses` é da clínica e referencia o paciente por FK composta. Campos:
`status` em `DRAFT/FINAL`, `version_number` (nulo no rascunho, obrigatório na
versão final), `template` (`cfo_2026_v1`), `payload` JSONB tipado, `base_version_id`
opcional, autoria (`author_user_id`) e snapshot profissional, `created_at`,
`updated_at` e `finalized_at`. Invariantes:

- **um rascunho por paciente**, garantido por índice único parcial
  `(clinic_id, patient_id) WHERE status = 'DRAFT'`; a segunda criação concorrente
  recebe 409;
- **versão final é imutável**: um trigger `BEFORE UPDATE OR DELETE` rejeita
  qualquer alteração de linha com `OLD.status = 'FINAL'`, e a role runtime não
  possui `DELETE` na tabela (defesa em profundidade);
- a numeração é sequencial por paciente e atribuída na conclusão
  (`MAX(version_number) + 1`), com `UNIQUE (clinic_id, patient_id,
version_number)`;
- a conclusão é atômica: service verifica papel (`anamnesis:finalize`), perfil
  profissional existente e payload completo contra o catálogo, trava o paciente
  (`SELECT … FOR UPDATE`) como ponto único de serialização e grava estado,
  número, data e snapshot na mesma transação; duas conclusões concorrentes
  produzem exatamente uma versão final;
- criar revisão aceita `base_version_id` de uma versão **FINAL do mesmo
  paciente** e copia o payload como novo `DRAFT`; assim que concluída, passa a
  ser a versão vigente;
- `PATCH` só aceita `DRAFT`; nenhuma rota altera ou apaga versão final.

### Documentos privados (D6)

`patient_documents` guarda apenas metadados (`id`, `clinic_id`, `patient_id`,
`category` em `ADMINISTRATIVE/CLINICAL`, `title`, `original_filename`,
`detected_mime`, `size_bytes`, `sha256`, `storage_key`, autoria, estado
`ACTIVE/ARCHIVED`, `archived_at` e datas) e referência o paciente por FK
composta. O objeto permanece em storage S3 privado, acessível apenas pela API;
a role runtime não possui `DELETE` e nenhum endpoint realiza exclusão física.
Arquivar apenas muda o estado do metadado; o objeto é preservado.

### Rotas e paginação (D7)

Perfil profissional (autoescopado):

- `GET/PUT /api/v1/users/me/professional-profile`

Pacientes e alertas:

- `GET/POST /api/v1/clinics/{clinic_id}/patients`
- `GET/PATCH /api/v1/clinics/{clinic_id}/patients/{patient_id}`
- `POST /api/v1/clinics/{clinic_id}/patients/{patient_id}/archive`
- `POST /api/v1/clinics/{clinic_id}/patients/{patient_id}/restore`
- `GET/POST /api/v1/clinics/{clinic_id}/patients/{patient_id}/alerts`
- `PATCH /api/v1/clinics/{clinic_id}/patients/{patient_id}/alerts/{alert_id}`

Anamnese:

- `GET/POST /api/v1/clinics/{clinic_id}/patients/{patient_id}/anamneses`
- `GET/PATCH /api/v1/clinics/{clinic_id}/patients/{patient_id}/anamneses/{anamnesis_id}`
- `POST /api/v1/clinics/{clinic_id}/patients/{patient_id}/anamneses/{anamnesis_id}/finalize`

Documentos:

- `GET/POST /api/v1/clinics/{clinic_id}/patients/{patient_id}/documents`
- `GET /api/v1/clinics/{clinic_id}/patients/{patient_id}/documents/{document_id}`
- `GET /api/v1/clinics/{clinic_id}/patients/{patient_id}/documents/{document_id}/content`
- `POST /api/v1/clinics/{clinic_id}/patients/{patient_id}/documents/{document_id}/archive`
- `POST /api/v1/clinics/{clinic_id}/patients/{patient_id}/documents/{document_id}/restore`

`clinic_id` e `patient_id` vêm sempre da rota e nunca do corpo. Listagens usam
`limit`, `offset` e filtros com resposta `{items, total, limit, offset}`.
Pacientes e documentos arquivados ficam ocultos por padrão, mas continuam
acessíveis diretamente para restauração. Recurso de outro tenant e permissão
insuficiente não revelam existência: cross-tenant responde 404 genérico e papel
sem permissão responde 403. O OpenAPI é a fonte do contrato e o cliente
TypeScript é regenerado a cada incremento.

### Matriz RBAC explícita (D8)

O M2 declara quatorze permissões novas em `app/clinics/rbac.py`, mantendo
`default deny`:

| Permissão                         | OWNER | ADMIN | DENTIST | ASSISTANT | RECEPTIONIST |
| --------------------------------- | ----- | ----- | ------- | --------- | ------------ |
| `patients:read`                   | ✓     | ✓     | ✓       | ✓         | ✓            |
| `patients:create`                 | ✓     | ✓     |         |           | ✓            |
| `patients:update`                 | ✓     | ✓     |         |           | ✓            |
| `patients:archive`                | ✓     | ✓     |         |           |              |
| `patient-alerts:read`             | ✓     |       | ✓       | ✓         |              |
| `patient-alerts:manage`           | ✓     |       | ✓       |           |              |
| `anamnesis:read`                  | ✓     |       | ✓       | ✓         |              |
| `anamnesis:create`                | ✓     |       | ✓       |           |              |
| `anamnesis:update`                | ✓     |       | ✓       |           |              |
| `anamnesis:finalize`              | ✓     |       | ✓       |           |              |
| `documents-administrative:read`   | ✓     | ✓     | ✓       | ✓         | ✓            |
| `documents-administrative:manage` | ✓     | ✓     |         |           | ✓            |
| `documents-clinical:read`         | ✓     |       | ✓       | ✓         |              |
| `documents-clinical:manage`       | ✓     |       | ✓       |           |              |

Leituras clínicas continuam indisponíveis a ADMIN e RECEPTIONIST: `anamnesis`,
`patient-alerts` e `documents-clinical` não aparecem para esses papéis. A
conclusão de anamnese exige `anamnesis:finalize` **e** perfil profissional do
autor; ASSISTANT lê mas não conclui nem altera. A matriz é provada por testes
parametrizados de todos os papéis × permissões no M2.6, além dos testes de
endpoint de cada incremento.

### Upload e compensação do storage (D9)

O upload (M2.5) lê o corpo em blocos, rejeita arquivo vazio, aplica limite de
10 MB (413), detecta o MIME por magic bytes entre PDF, JPEG e PNG (415 para o
resto) e calcula tamanho e SHA-256 no servidor. A chave do objeto é opaca,
gerada pela API sem PII (nunca vem do cliente), e o harness E2E usa o prefixo
`e2e/{run_id}/`, removido no teardown exclusivamente por prefixo. A ordem é:
validar → gravar o objeto no S3 → persistir o metadado ativo. Se o metadado
falhar, o objeto é removido em compensação best-effort; se o S3 falhar, a
resposta é 503 e nenhum metadado ativo é criado. Falha da compensação vira
evento operacional sem conteúdo, para reconciliação — não há exclusão física de
documento. O download autoriza pelo metadado/RLS e pela categoria **antes** de
tocar no storage, serve `Content-Disposition: attachment` com o MIME detectado
pelo servidor e nunca aceita chave, MIME ou checksum do cliente.

### Conclusão não é assinatura (D10)

Concluir a anamnese registra autoria, data e snapshot profissional, mas **não**
é assinatura digital ICP-Brasil, não usa certificado e não substitui a ciência
ou a assinatura do paciente. A interface pt-BR não pode rotular a conclusão como
"assinatura"; o texto e os estados devem falar em "concluir" e "concluída".
Assinatura do paciente, PDF gerado e certificação ficam fora do M2.

### Minimização de dados, logs e auditoria (D11)

CPF, respostas de anamnese, nomes de arquivo, conteúdo de arquivo e chave de
storage nunca entram em logs, Problem Details ou metadata de auditoria. A
auditoria clínica registra apenas IDs, tipo de entidade, ação, estado e, quando
necessário ao diagnóstico, IDs de paciente/clínica/usuário; o mesmo vale para
documentos (categoria e ação, sem título ou nome original). Não há expurgo nem
exclusão física de paciente, anamnese concluída ou documento; a preservação
atende à integridade clínica e à guarda mínima da Lei 13.787/2018.

### Catálogo clínico versionado (D12)

O questionário `cfo_2026_v1` é um catálogo imutável em
`app/anamnesis/templates/cfo_2026_v1.py`, com `AnswerType`
(`YES_NO_UNKNOWN`, `SINGLE_CHOICE`, `TEXT`), vocabulário fechado
`YES/NO/UNKNOWN`, `Option`, `Question` e `Section` congelados (`frozen`,
`slots`) e tuplas determinísticas. Seções e perguntas têm IDs estáveis em
inglês; títulos, enunciados, alternativas e complementos textuais são redação
própria em pt-BR, inspirada na estrutura do Anexo 1 do Manual do Prontuário do
CFO de 2026 **apenas como referência**, sem cópia de texto. O catálogo cobre
queixa principal; histórias atual, médica, odontológica, familiar e social; as
oito seções de condições sistêmicas materializadas (digestivas, hepáticas,
cardiovasculares, respiratórias, renais, motoras, infecciosas e
endócrino-metabólicas); alergias, anestesia, sangramento, cicatrização,
cirurgias, gestação, neoplasias, condições psicológicas, deficiências,
medicamentos e hábitos; e o inventário odontológico com higiene, dor,
sangramento, mobilidade, halitose, xerostomia, ATM, sensibilidade, lesões,
bruxismo, dieta, endodontia, próteses e cirurgias anteriores. Qualquer mudança
de conteúdo exige um novo identificador de template e uma nova versão de
anamnese, nunca a mutação deste. Testes unitários provam unicidade dos IDs,
ordem determinística, versão fixa e cobertura de todas as seções e tópicos
aprovados.

### Sequência de implementação (D13)

M2.1 entrega somente este contrato e o catálogo, sem tabela, migration, rota ou
tela. M2.2 cria `professional_profiles`, `patients`, `patient_alerts`,
`anamneses` e `patient_documents` com constraints, índices parciais, trigger,
grants e RLS (tenant e proprietário) provados sem contexto e nas duas direções.
M2.3 implementa pacientes e alertas; M2.4, anamnese e perfil profissional; M2.5,
documentos e storage; M2.6 consolida a prova de RBAC, isolamento, redaction e
E2E com Playwright.

## Consequências

- O schema e as rotas do M2 têm um contrato único e anterior ao código; M2.2 a
  M2.5 implementam exatamente estes modelos, estados e permissões.
- A imutabilidade de versões finais, o rascunho único e a conclusão serializada
  eliminam edição silenciosa de registro clínico e corridas de versionamento.
- A separação entre conteúdo administrativo e clínico fica explícita em
  permissões distintas, na API e na UI, com `default deny`.
- O perfil profissional global com RLS de proprietário preserva o snapshot de
  autoria mesmo quando o usuário muda de nome ou CRO.
- Documentos permanecem privados e sem exclusão física; qualquer acesso exige
  autorização por metadado antes do storage, e falhas não deixam metadado ativo.
- Permanecem como pré-requisitos de produção, fora do M2: storage gerenciado,
  criptografia em repouso, backup/retenção, antimalware e o processo de
  assinatura ou ciência do paciente.
