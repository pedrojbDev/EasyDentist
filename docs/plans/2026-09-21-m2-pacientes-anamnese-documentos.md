# M2 — Pacientes, Anamnese e Documentos: Plano de Implementação

> **Para agentes executores:** SUB-SKILL OBRIGATÓRIA: use
> `superpowers:subagent-driven-development` (recomendado) ou
> `superpowers:executing-plans` para implementar este plano tarefa por tarefa. Os
> passos usam checkboxes (`- [ ]`) para acompanhamento.

**Objetivo:** entregar um MVP completo de pacientes, anamnese versionada e
documentos privados, com API, frontend pt-BR, RBAC, RLS, auditoria e testes E2E.

**Arquitetura:** manter o monólito modular, criando fronteiras explícitas para
`patients`, `anamnesis` e `documents`, além de um adapter de storage S3 privado.
Cada incremento fecha uma fatia verificável de banco, domínio, API, frontend e
testes, preservando o isolamento por clínica já estabelecido no M1.

**Stack:** PostgreSQL 17, SQLAlchemy 2 async, Alembic, FastAPI, Pydantic,
Next.js 15, React 19, TypeScript, Tailwind CSS, S3-compatible storage, Vitest,
Pytest e Playwright.

## Decisões de execução (aprovadas)

- **Método:** subagentes com TDD e revisões independentes (spec + qualidade) por
  incremento; worktree dedicado e plano como primeiro commit.
- **Ritmo:** execução contínua de M2.1 a M2.6, com commit e relatório por
  incremento; revisão reforçada após M2.2 e M2.5; segue automaticamente com os
  gates verdes e para apenas em bloqueio, falha de segurança ou mudança de
  escopo.
- **Prints de referência** (`simples-dental-prints/`, 46 capturas) são
  inspiração de fluxo e organização apenas: não vão para o Git, não são
  copiados para `docs/` e não devem ser reproduzidos pixel a pixel.
  `docs/ui-standards.md` continua sendo a referência obrigatória.
- **Interface:** manter o padrão visual do M1 (tokens, componentes e telas
  existentes) e evoluí-lo com acabamento superior ao das referências
  (hierarquia, densidade, estados vazios, responsividade e microinterações).
  Ao fim de M2.3, M2.4 e M2.5, anexar screenshots Playwright das telas novas
  ao relatório para validação visual.
- **Documentos:** o M2 cobre upload, listagem, download e arquivamento seguros.
  Contratos, consentimentos e receitas geradas ficam fora do escopo.
- **E2E de storage:** todo objeto criado pelo seed/specs usa o prefixo
  `e2e/{run_id}/`; o teardown remove exclusivamente esse prefixo, inclusive em
  falha, e confirma que nenhum objeto daquele run permaneceu.

**Especificação:** `plan.md` §§1–5, `docs/architecture.md`,
`docs/security.md`, `docs/data-model.md`, `docs/ui-standards.md`,
`docs/adr/0003-solid-and-modular-boundaries.md`,
`docs/adr/0005-rls-policies-and-tenant-context.md` e
`docs/adr/0007-membership-rbac.md`.

## Restrições globais

- Manter Python `>=3.12,<3.13`, Node.js `24.19.0`, pnpm `11.10.0` e somente
  versões estáveis e fixadas nos manifests/lockfiles.
- Interface e documentação em pt-BR; identificadores, código, tabelas e rotas em
  inglês.
- Tabelas pertencentes à clínica usam UUID, `clinic_id NOT NULL`, FKs
  tenant-aware e RLS por tenant com `FORCE ROW LEVEL SECURITY`. Tabelas globais
  pertencentes ao usuário (ex.: `professional_profiles`) usam RLS por
  proprietário (`user_id = app.current_user_id`) também com `FORCE ROW LEVEL
SECURITY`; `user_transaction` e `tenant_transaction` funcionam porque ambos
  instalam `app.current_user_id`.
- A clínica ativa vem sempre da rota; `clinic_id` nunca é aceito no corpo quando
  puder ser derivado da URL.
- RBAC permanece `default deny`; a UI apenas espelha permissões e a API continua
  sendo a autoridade.
- Dados clínicos, CPF, conteúdo de arquivos e respostas de anamnese nunca entram
  em logs ou metadata de auditoria.
- Não há exclusão física de pacientes, anamneses concluídas ou documentos.
- OpenAPI é a fonte do contrato e qualquer alteração de endpoint exige
  regeneração e verificação de drift dos tipos TypeScript.
- Cada incremento termina com testes, relatório de conclusão e aprovação antes
  do incremento seguinte.

---

## 1. Decisões consolidadas

### 1.1 Modelo de dados

- `professional_profiles`: perfil global do usuário com nome profissional, CRO
  e UF, isolado por RLS de proprietário (`user_id = app.current_user_id`, sem
  `clinic_id`). A conclusão da anamnese grava um snapshot desses campos.
- `patients`: `clinic_id`, nome, nome social opcional, nascimento, CPF opcional,
  contatos, endereço, ocupação/nacionalidade/naturalidade opcionais, contato de
  emergência, responsável legal, observações administrativas e estado
  `ACTIVE/ARCHIVED`.
  - Nome, nascimento e telefone principal são obrigatórios.
  - CPF é validado e normalizado; índice único parcial `(clinic_id, cpf)`.
  - Menores exigem responsável com nome, vínculo e telefone.
- `patient_alerts`: alergia, medicação, risco clínico ou outro alerta; estados
  `ACTIVE/RESOLVED`.
- `anamneses`: paciente, estado `DRAFT/FINAL`, número da versão, template,
  payload tipado, versão de origem, autoria e datas.
  - Apenas um rascunho por paciente, garantido por índice parcial.
  - Versões finais bloqueiam `UPDATE` e `DELETE` no banco.
  - Nova revisão copia a última versão final.
- `patient_documents`: categoria `ADMINISTRATIVE/CLINICAL`, título, nome
  original, MIME detectado, tamanho, SHA-256, chave opaca, autor e estado
  `ACTIVE/ARCHIVED`.
  - O objeto permanece em storage privado; nenhum endpoint realiza exclusão
    física.

### 1.2 Questionário `cfo_2026_v1`

Implementar com redação própria, baseado na anamnese e inventário odontológico
do Anexo 1 do
[Manual do Prontuário do CFO de 2026](https://website.cfo.org.br/wp-content/uploads/2026/03/CFO_Manual_do_Prontuario_Ebook.pdf):

- queixa principal e histórias atual, médica, odontológica, familiar e social;
- condições digestivas, hepáticas, cardiovasculares, respiratórias, renais,
  motoras, infecciosas, endócrinas e metabólicas;
- alergias, anestesia, sangramento, cicatrização, cirurgias, gestação,
  neoplasias, condições psicológicas, deficiências, medicamentos e hábitos;
- inventário odontológico: higiene, dor, sangramento, mobilidade, halitose,
  xerostomia, ATM, sensibilidade, lesões, bruxismo, dieta, endodontia, próteses
  e cirurgias anteriores;
- respostas estruturadas em `YES/NO/UNKNOWN`, opções e detalhes textuais.

Exame físico, odontograma e plano de tratamento permanecem nos M4/M5.

### 1.3 APIs públicas

- Perfil profissional:
  - `GET/PUT /api/v1/users/me/professional-profile`
- Pacientes:
  - `GET/POST /api/v1/clinics/{clinic_id}/patients`
  - `GET/PATCH /api/v1/clinics/{clinic_id}/patients/{patient_id}`
  - `POST /api/v1/clinics/{clinic_id}/patients/{patient_id}/archive`
  - `POST /api/v1/clinics/{clinic_id}/patients/{patient_id}/restore`
- Alertas:
  - `GET/POST /api/v1/clinics/{clinic_id}/patients/{patient_id}/alerts`
  - `PATCH /api/v1/clinics/{clinic_id}/patients/{patient_id}/alerts/{alert_id}`
- Anamneses:
  - `GET/POST /api/v1/clinics/{clinic_id}/patients/{patient_id}/anamneses`
  - `GET/PATCH /api/v1/clinics/{clinic_id}/patients/{patient_id}/anamneses/{anamnesis_id}`
  - `POST /api/v1/clinics/{clinic_id}/patients/{patient_id}/anamneses/{anamnesis_id}/finalize`
  - a criação aceita `base_version_id` opcional para iniciar uma revisão;
- Documentos:
  - `GET/POST /api/v1/clinics/{clinic_id}/patients/{patient_id}/documents`
  - `GET /api/v1/clinics/{clinic_id}/patients/{patient_id}/documents/{document_id}`
  - `GET /api/v1/clinics/{clinic_id}/patients/{patient_id}/documents/{document_id}/content`
  - `POST /api/v1/clinics/{clinic_id}/patients/{patient_id}/documents/{document_id}/archive`
  - `POST /api/v1/clinics/{clinic_id}/patients/{patient_id}/documents/{document_id}/restore`

Listagens usam `limit`, `offset`, filtros e resposta
`{items, total, limit, offset}`. Pacientes arquivados ficam ocultos por padrão,
mas continuam diretamente acessíveis para restauração.

### 1.4 Matriz RBAC

- `OWNER`: acesso integral; precisa de perfil profissional para concluir
  anamnese.
- `ADMIN`: cadastro e arquivamento de pacientes e documentos administrativos;
  sem conteúdo clínico.
- `DENTIST`: lê pacientes; gerencia alertas, anamneses e documentos clínicos;
  lê documentos administrativos.
- `ASSISTANT`: leitura de pacientes, alertas, anamneses e documentos; nenhuma
  conclusão ou alteração clínica.
- `RECEPTIONIST`: cria/edita pacientes e gerencia documentos administrativos;
  sem alertas, anamneses ou documentos clínicos.

Adicionar permissões explícitas para pacientes, alertas, anamnese e documentos
administrativos/clínicos, mantendo `default deny`.

---

## 2. Incrementos de implementação

### M2.1 — Contrato e decisões arquiteturais

**Arquivos:**

- Criar: `docs/adr/0010-m2-patients-anamnesis-documents.md`
- Modificar: `docs/architecture.md`, `docs/security.md`, `docs/data-model.md`
- Modificar: `docs/open-dentist-audit.md`, `docs/third-party-licenses.md`
- Criar: `apps/api/app/anamnesis/templates/cfo_2026_v1.py`
- Testar: `apps/api/tests/test_anamnesis_template.py`

**Entrega:** contrato arquitetural, matriz de permissões e catálogo clínico
versionado, sem criar endpoints ou tabelas prematuramente.

- [ ] Registrar no ADR os modelos, estados, invariantes, rotas, matriz RBAC,
      fluxo de upload e estratégia de compensação do S3.
- [ ] Materializar `cfo_2026_v1` como catálogo imutável, com IDs estáveis de
      seção/pergunta e respostas tipadas.
- [ ] Criar testes que comprovem unicidade dos IDs, ordem determinística,
      versão fixa e presença de todas as seções aprovadas.
- [ ] Documentar que conclusão não equivale a assinatura ICP-Brasil nem
      substitui ciência/assinatura do paciente.
- [ ] Rodar `pnpm format:check` e os testes unitários do catálogo.
- [ ] Emitir relatório de M2.1 e aguardar aprovação.

### M2.2 — Banco, RLS e fundação

**Arquivos:**

- Criar: `apps/api/migrations/versions/0009_m2_patient_foundation.py`
- Criar: `apps/api/migrations/versions/0010_m2_anamnesis.py`
- Criar: `apps/api/migrations/versions/0011_m2_documents.py`
- Criar: `apps/api/app/patients/models.py`
- Criar: `apps/api/app/anamnesis/models.py`
- Criar: `apps/api/app/documents/models.py`
- Modificar: `apps/api/app/users/models.py`, `apps/api/app/models.py`
- Testar: `apps/api/tests/integration/test_m2_schema.py`
- Testar: `apps/api/tests/integration/test_m2_rls.py`

**Entrega:** schema completo e isolado, ainda sem superfície HTTP.

- [ ] Escrever primeiro testes de schema, constraints, FKs compostas, índices
      parciais, grants e downgrade.
- [ ] Implementar `0009` com `professional_profiles`, `patients` e
      `patient_alerts`.
- [ ] Implementar `0010` com `anamneses`, unicidade do rascunho, numeração de
      versões e trigger que rejeita alteração/remoção de `FINAL`.
- [ ] Implementar `0011` com `patient_documents`, categorias, estados e
      checksum SHA-256.
- [ ] Criar policies fail-closed e `FORCE ROW LEVEL SECURITY` em todas as
      tabelas tenant-aware.
- [ ] Provar RLS sem contexto, nas duas direções entre clínicas, por repository
      e por SQL cru sob a role runtime.
- [ ] Rodar Alembic do zero, `alembic check`, downgrade até `0008` e novo
      upgrade até `head`.
- [ ] Emitir relatório de M2.2 e aguardar aprovação.

### M2.3 — Pacientes ponta a ponta

**Arquivos:**

- Criar: `apps/api/app/patients/cpf.py`, `schemas.py`, `services.py`,
  `routers.py`
- Criar: `apps/api/app/patients/repositories/patient_repository.py`
- Criar: `apps/api/app/patients/repositories/patient_alert_repository.py`
- Modificar: `apps/api/app/clinics/rbac.py`, `apps/api/app/application.py`
- Criar: `apps/web/src/features/patients/`
- Criar: `apps/web/src/app/(app)/clinics/[clinicId]/patients/`
- Testar: `apps/api/tests/integration/test_patient_endpoints.py`
- Testar: `apps/web/src/features/patients/*.test.tsx`

**Entrega:** cadastro operacional completo, busca e alertas clínicos.

- [ ] Escrever testes unitários para normalização/checksum de CPF, nascimento
      futuro, menor/responsável, busca e paginação.
- [ ] Expandir `Permission` e a matriz dos cinco papéis com permissões de
      pacientes e alertas; provar todos os pares papel × permissão.
- [ ] Implementar repositories que sempre recebam `TenantContext`, filtrem por
      `clinic_id` e nunca ofereçam métodos unscoped.
- [ ] Implementar services, schemas e endpoints de CRUD sem delete,
      arquivamento/restauração, busca e alertas.
- [ ] Mapear CPF duplicado a 409, validação a 422, papel insuficiente a 403 e
      qualquer recurso cross-tenant a 404.
- [ ] Registrar auditoria somente com IDs, estado e tipo de ação.
- [ ] Criar lista, busca, paginação, cadastro, detalhe, edição e ações de
      arquivamento/restauração na web, mantendo `docs/ui-standards.md` e os
      componentes/tokens do M1, com acabamento superior às referências visuais
      (prints apenas para fluxo, fora do Git) e screenshots no relatório.
- [ ] Criar área de alertas visível apenas para os papéis clínicos aprovados.
- [ ] Regenerar OpenAPI/tipos TypeScript e verificar ausência de drift.
- [ ] Rodar suítes API/web e emitir relatório de M2.3.

### M2.4 — Anamnese ponta a ponta

**Arquivos:**

- Criar: `apps/api/app/users/schemas.py`, `routers.py`
- Criar: `apps/api/app/users/repositories/professional_profile_repository.py`
- Criar: `apps/api/app/anamnesis/schemas.py`, `repositories.py`, `services.py`,
  `routers.py`
- Criar: `apps/web/src/features/anamnesis/`
- Criar: `apps/web/src/app/(app)/clinics/[clinicId]/patients/[patientId]/anamnesis/`
- Testar: `apps/api/tests/integration/test_anamnesis_endpoints.py`
- Testar: `apps/api/tests/integration/test_anamnesis_concurrency.py`
- Testar: `apps/web/src/features/anamnesis/*.test.tsx`

**Entrega:** rascunho, conclusão imutável, histórico e revisão com autoria.

- [ ] Escrever testes dos endpoints do perfil profissional, restringindo
      leitura/escrita ao próprio usuário.
- [ ] Implementar perfil com nome profissional, número CRO e UF; a aplicação
      não afirma validar o registro em base externa.
- [ ] Criar modelos Pydantic explícitos para cada seção de `cfo_2026_v1` e
      rejeitar chaves desconhecidas.
- [ ] Implementar criação de rascunho vazio ou baseado em versão final,
      atualização apenas de `DRAFT` e listagem cronológica.
- [ ] Implementar conclusão atômica que verifica papel, perfil profissional e
      payload completo, atribui a próxima versão e grava snapshot da autoria.
- [ ] Provar concorrência: dois rascunhos simultâneos produzem um sucesso e um
      409; duas conclusões simultâneas criam uma única versão final.
- [ ] Criar formulário web por seções, resumo de pendências, confirmação de
      conclusão e histórico somente leitura, mantendo o padrão visual do M1
      (`docs/ui-standards.md`), com polimento acima das referências e
      screenshots no relatório.
- [ ] Garantir que ADMIN/RECEPTIONIST não recebam nenhum payload ou indicação
      de existência clínica.
- [ ] Regenerar contrato, rodar suítes e emitir relatório de M2.4.

### M2.5 — Documentos ponta a ponta

**Arquivos:**

- Modificar: `apps/api/pyproject.toml`, `apps/api/uv.lock`
- Criar: `apps/api/app/platform/storage.py`, `s3_storage.py`
- Criar: `apps/api/app/documents/schemas.py`, `repositories.py`, `services.py`,
  `routers.py`
- Modificar: `apps/api/app/application.py`
- Criar: `apps/web/src/features/documents/`
- Criar: `apps/web/src/app/(app)/clinics/[clinicId]/patients/[patientId]/documents/`
- Testar: `apps/api/tests/test_storage.py`
- Testar: `apps/api/tests/integration/test_document_endpoints.py`
- Testar: `apps/web/src/features/documents/*.test.tsx`

**Entrega:** arquivos privados com upload/download controlados pela API.

- [ ] Adicionar `boto3` e `python-multipart`, atualizar lock e validar licenças,
      vulnerabilidades e compatibilidade.
- [ ] Definir `ObjectStorage` com operações de put, stream, delete de
      compensação e verificação de objeto; implementar adapter S3.
- [ ] Carregar configuração S3 no lifespan com validação fail-fast, sem expor
      credenciais em erros ou logs.
- [ ] Escrever testes para PDF/JPEG/PNG válidos, magic bytes falsos, arquivo
      vazio, limite exato e excesso de 10 MB.
- [ ] Implementar leitura em blocos, SHA-256, chave aleatória sem PII e upload
      antes da ativação do metadado.
- [ ] Compensar o objeto quando a persistência falhar; falha S3 responde 503
      sem criar documento ativo.
- [ ] Autorizar sempre por metadado/RLS antes do acesso ao S3 e servir conteúdo
      com `Content-Disposition: attachment` e MIME detectado pelo servidor.
- [ ] Aplicar a matriz separada de documentos administrativos e clínicos.
- [ ] Criar UI de listagem, filtros, upload, download, arquivamento e
      restauração, no padrão visual do M1 (`docs/ui-standards.md`) e com
      screenshots no relatório; contratos, consentimentos e receitas geradas
      permanecem fora do M2.
- [ ] Regenerar contrato, rodar suítes e emitir relatório de M2.5.

### M2.6 — Prova de segurança e fechamento

**Arquivos:**

- Criar: `apps/api/tests/integration/test_m2_rbac_matrix.py`
- Criar: `apps/api/tests/integration/test_m2_isolation_gate.py`
- Criar: `apps/web/e2e/patients.spec.ts`
- Criar: `apps/web/e2e/anamnesis.spec.ts`
- Criar: `apps/web/e2e/documents.spec.ts`
- Modificar: `apps/api/scripts/seed_e2e.py`, `docs/operations.md`,
  `docs/architecture.md`, `docs/security.md`

**Entrega:** evidência automatizada do marco completo e documentação de operação.

- [ ] Consolidar todos os papéis contra todos os endpoints novos, com cenários
      positivos, negativos e `default deny`.
- [ ] Provar cross-tenant com IDs válidos da outra clínica em API, repository,
      SQL cru e chaves de documentos.
- [ ] Provar que CPF, respostas, filename, conteúdo e chave S3 não aparecem em
      logs, Problem Details ou metadata de auditoria.
- [ ] Adicionar Playwright para cadastro/edição/arquivamento de paciente,
      rascunho/conclusão/revisão de anamnese e upload/download/arquivamento de
      documento.
- [ ] Estender `apps/api/scripts/seed_e2e.py` e o teardown para o storage:
      objetos sob `e2e/{run_id}/`, remoção exclusiva desse prefixo mesmo em
      falha e verificação de que nenhum objeto do run permaneceu.
- [ ] Validar round-trip de arquivo com mesmo tamanho e SHA-256, incluindo
      negação anônima e por categoria clínica.
- [ ] Rodar migrations do zero, backup/restauração, Compose completo e prova de
      storage privado.
- [ ] Rodar lint, format, typecheck, testes, build, licenças, audits e scanner de
      secrets.
- [ ] Atualizar documentação e registrar limitações de produção: storage
      gerenciado, criptografia/backup, antimalware e assinatura/ciência do
      paciente.
- [ ] Emitir relatório final do M2 e aguardar aprovação antes do M3.

---

## 3. Critérios finais de aceite

- CPF inválido falha; duplicado falha somente dentro da mesma clínica.
- Menor sem responsável é rejeitado.
- Busca por nome, CPF e telefone respeita tenant e paginação.
- Arquivamento não remove registros nem objetos.
- RLS falha sem contexto e bloqueia IDs válidos de outro tenant.
- A matriz cobre todos os papéis e permissões, inclusive `default deny`.
- ADMIN e RECEPTIONIST nunca recebem payload clínico.
- Dois rascunhos concorrentes resultam em apenas um.
- Duas conclusões concorrentes produzem uma única versão final.
- Versão final não pode ser alterada ou apagada; correção cria nova revisão.
- Alterar o perfil profissional não modifica snapshots antigos.
- Arquivos maiores que 10 MB retornam 413; formato inválido retorna 415.
- Arquivos anônimos, cross-tenant ou de categoria proibida nunca são entregues.
- Upload/download preserva tamanho e checksum.
- Falhas de S3 não criam metadados ativos; falhas de banco executam
  compensação.
- Logs e auditoria não contêm CPF, respostas, nomes de arquivo, conteúdo ou
  chave S3.
- OpenAPI, cliente TypeScript e UI permanecem sincronizados.

## 4. Premissas e fora do escopo

- O M2 é full-stack e será liberado para todas as clínicas, sem feature flag.
- Não haverá exclusão física nem expurgo. A preservação atende ao requisito de
  integridade e evita contrariar a guarda mínima prevista na
  [Lei 13.787/2018](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13787.htm).
- Dados de saúde serão tratados como sensíveis e protegidos por segregação
  clínica, RLS, auditoria e minimização de logs, em linha com a definição da
  [ANPD](https://www.gov.br/anpd/pt-br/acesso-a-informacao/perguntas-frequentes).
- Ficam fora do M2: portal do paciente, PDFs gerados, assinatura eletrônica do
  paciente, ICP-Brasil, antivírus, exportação integral, templates configuráveis,
  agenda, exame físico, odontograma, evolução clínica e tratamentos.
- Produção continua condicionada a storage gerenciado, criptografia/backup,
  antimalware e definição do processo de assinatura ou ciência do paciente.
