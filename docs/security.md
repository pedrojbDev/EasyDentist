# Segurança

Este documento materializa a direção de segurança aprovada e registra o estado
de cada afirmação. O threat model correspondente está em `docs/threat-model.md`
e as decisões do hardening em `docs/adr/0009-hardening-and-operations.md`.

## Estado das afirmações

| Afirmação                                                                                                              | Estado                                                                                                                                                                        |
| ---------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Hash de credenciais (Argon2id), sessões opacas, CSRF, rate limiting, tokens de ação, provisioning                      | Implementado no M1.3 e provado em `tests/integration/test_auth_security_matrix.py` e `test_auth_redaction.py`                                                                 |
| RLS fail-closed, contexto transacional, roles sem `BYPASSRLS`, isolamento por tenant                                   | Implementado no M1.2/M1.4 e provado em `test_tenant_isolation.py`, `test_raw_sql_isolation.py`, `test_rls_fail_closed.py`, `test_pool_tenant_leak.py` e `test_rbac_matrix.py` |
| Frontend same-origin com guarda de sessão e token só em memória                                                        | Implementado no M1.5 (ADR 0008) e provado em `use-fragment-token.test.tsx`                                                                                                    |
| Headers de segurança da API e da web com CSP nonce bloqueante                                                          | **Provado no M1.6.3** (`test_security_headers.py`, `security-headers.test.ts` e fluxos Playwright)                                                                            |
| Logs JSONL com allowlist e redaction sem dados sensíveis                                                               | **Provado no M1.6.4** (`test_structured_logging.py`, `test_logging_redaction.py`, `server-logging.test.ts`)                                                                   |
| Backup `pg_dump -Fc` restaurável em banco limpo com schema, grants, policies e RLS                                     | **Provado no M1.6.5** (`scripts/verify-backup-restore.sh`)                                                                                                                    |
| Ausência de secrets versionados e de dependências vulneráveis                                                          | **Provado no M1.6.6** (`scripts/verify-secrets.sh`, `pnpm audit`, `pip-audit`, licenças)                                                                                      |
| Critério final cross-tenant (duas clínicas, API/SSR/rota/SQL sob role runtime)                                         | **Provado no M1.6.2/M1.6.6** (`isolation.spec.ts`, `test_m16_isolation_gate.py`)                                                                                              |
| Contrato de segurança do M2 (pacientes, anamnese, documentos, storage privado)                                         | **Contratado no M2.1** (ADR 0010); implementação e prova nos M2.2 a M2.6                                                                                                      |
| Storage gerenciado, SMTP real, retenção de backups, criptografia em repouso, gestão externa de secrets e monitoramento | **Fora do escopo de produção** — pré-requisitos operacionais listados em `docs/operations.md`                                                                                 |

## Autenticação (M1.3)

**Implementado no M1.3.1 a M1.3.6:** hashing Argon2id v19 (64 MiB, três
iterações, paralelismo 1, salt de 16 bytes, hash de 32 bytes) com rehash
transparente; tokens de 256 bits em base64url com apenas `SHA-256` persistido e
comparação em tempo constante; sessões opacas com expiração por inatividade de
12 horas e absoluta de 30 dias, `last_seen_at` com throttle de cinco minutos,
revogação individual e global, e cookies com flags por ambiente; CSRF
signed double-submit exigido em toda mutação, com `Origin`/`Referer` na
allowlist e token reemitido vinculado à sessão após o login; rate limiting
atômico em PostgreSQL com backoff progressivo, chaves HMAC e `Retry-After`
(login 5/conta/15min e 20/IP/15min; recuperação e reenvio 3/destinatário/h e
20/IP/h); resolução de IP confiando em `X-Forwarded-For` apenas de proxies
declarados; `AuthSettings` com validação fail-fast (`AUTH_SECRET` de no mínimo
32 bytes em produção); Problem Details (RFC 9457) com `request_id`; outbox de
e-mail com tentativas idempotentes e backoff exponencial; auditoria de eventos
de segurança sem dados sensíveis; verificação de e-mail e recuperação de senha
com tokens de uso único (24 h e 30 min) consumidos atomicamente, respostas
genéricas contra enumeração, e-mails pt-BR com link em fragmento de URL e
entrega outbox-first; reset revogando todas as sessões sem auto-login; e
provisionamento operacional sem cadastro público pela CLI
`python -m app.auth.provision` (usuário sem senha, clínica `PROVISIONING`,
membership OWNER pendente e convite de 72 h) cujo aceite
(`POST /invitations/accept`) consome o token atomicamente, define a senha,
verifica o e-mail e ativa clínica e vínculo. As escritas em `clinics`,
`memberships`, `clinic_settings` e `membership_invitations` ocorrem somente nas
funções `SECURITY DEFINER` `provision_clinic_owner` e `consume_invitation`,
com `EXECUTE` restrito à role runtime.

A prova automatizada do M1.3.6 consolida a matriz do §5 em
`tests/integration/test_auth_security_matrix.py` (banco contendo apenas hashes
— `auth_sessions.token_hash` = SHA-256 do token emitido, credencial Argon2id e
nenhum token bruto em coluna; flags de cookie por ambiente; expiração
idle/absoluta; token revogado/reutilizado ⇒ 401; duas sessões de dispositivos
distintos coexistem; rotação no login preservando o outro dispositivo;
anti-enumeração em login e recuperação; matriz CSRF completa com `GET` isento;
rate limit atômico sob concorrência e consumo single-use concorrente), além da
redaction em `tests/integration/test_auth_redaction.py` (nenhuma senha, token,
cookie ou IP bruto em logs, `auth_audit_events`, `clinic_audit_events` ou
buckets de rate limit — as chaves são HMAC).

- Credenciais locais e providers externos convergirão para
  `Principal(user_id, session_id, auth_method)`; autorização conhecerá apenas
  `user_id`.
- Senhas usarão Argon2id v19: 64 MiB, três iterações, paralelismo 1, salt de
  16 bytes e hash de 32 bytes; o mínimo será 12 e o máximo 128 caracteres.
- Sessões serão opacas: token aleatório de 256 bits em base64url, somente seu
  SHA-256 persistido, comparação em tempo constante, expiração idle de 12 horas
  e absoluta de 30 dias, e atualização de `last_seen_at` no máximo a cada cinco
  minutos.
- Produção usará `__Host-easydent_session`, `Secure`, `HttpOnly`, `Path=/` e
  `SameSite=Lax`; desenvolvimento usará nome distinto e não marcará `Secure`.
  Tokens, cookies e senhas nunca serão registrados em logs.
- CSRF será signed double-submit (cookie legível, header `X-CSRF-Token`, HMAC) e
  toda mutação validará `Origin`/`Referer`. CORS continuará desativado em
  topologia same-origin.
- Verificação, reset e convite terão tokens aleatórios de 256 bits, somente
  hashes persistidos, uso único atômico e validade de 24 h, 30 min e 72 h,
  respectivamente. Links usarão fragmento URL; respostas evitarão enumeração.
- Rate limiting atômico em PostgreSQL: login 5 falhas/conta/15 min e 20/IP/15
  min; recuperação, reenvio e convites 3/destinatário/h e 20/IP/h. Chaves terão
  HMAC e proxies só serão confiados explicitamente.

## Tenant e autorização (M1.2 e M1.4)

**Implementado no M1.2.3 (ADR 0005).** O contexto de tenant viaja em
`app.current_user_id` e `app.current_clinic_id`, sempre definidos dentro da
transação com `set_config(..., is_local = true)`; toda policy lê os parâmetros
com `NULLIF(current_setting(..., true), '')` e falha fechado sem contexto. As
seis tabelas tenant-aware usam `FORCE ROW LEVEL SECURITY`, com policies
user-scoped (`clinics`, `memberships`) e tenant-scoped (as demais), verificação
de membership ativa por função `SECURITY DEFINER` mínima e exceção permissiva
restrita à role de migration. A role da aplicação não é dona das tabelas e não
tem `BYPASSRLS`.

Repositories exigem `TenantContext`/`UserContext` como primeiro parâmetro, e
updates combinam `id` e `clinic_id` (M1.2.4). O contexto recebido é validado
contra o contexto gravado na transação: divergência falha com
`ContextMismatchError`, fechando o cenário de usuário pertencente a duas
clínicas em que um `clinic_id` incorreto chegaria ao repository. Violações de
integridade são traduzidas para erros de domínio que não revelam existência (FK
→ `NotFoundError`; unique → `ConflictError`). A prova automatizada de isolamento
(M1.2.5) cobre duas clínicas em ambas as direções, SQL cru com IDs válidos da
outra clínica, transações intercaladas/concorrentes no mesmo pool, conexões
reutilizadas sem contexto e referências cross-tenant.

Falhas cross-tenant responderão 404 quando os routers existirem (M1.3+). Rotas
tenant-aware seguirão `/api/v1/clinics/{clinic_id}/...` e o `clinic_id`
recebido do frontend nunca será autorização por si só.

RBAC será default-deny e terá OWNER, ADMIN, DENTIST, ASSISTANT e RECEPTIONIST;
somente OWNER promove OWNER e o último OWNER não pode ser removido/rebaixado.
Registros clínicos serão aditivos e terão autor profissional.

**Implementado no M1.4 (ADR 0007, incrementos M1.4.1 a M1.4.6):** a matriz papel
× permissão vive em `app/clinics/rbac.py` com default deny e cobre as nove
permissões dos endpoints de clínica, settings, membros e convites; permissões
clínicas são declaradas nos marcos que criarem os endpoints. Erros de
autorização respondem 403 (`PermissionDeniedError`). O contexto tenant é
revalidado por requisição (404 cross-tenant para qualquer papel), as transições
de vínculo ocorrem somente nas funções `SECURITY DEFINER`
`create_member_invitation`, `change_member_role`, `remove_membership` e
`consume_invitation` v2 — as três primeiras **verificam que `p_clinic_id` e
`p_actor_user_id` coincidem com os GUCs `app.current_clinic_id` e
`app.current_user_id` da transação** (`context_mismatch`, fail-closed; o
serviço as executa sempre em `tenant_transaction`), de modo que uma chamada
direta com ator ou clínica forjados não é aceita —, a serialização por clínica
impede que dois OWNERs se auto-rebaixem/removam em paralelo (testes
concorrentes dedicados), o aceite de convite de equipe preserva a credencial e
as sessões de quem já tem senha (`password_not_allowed` se o cliente enviar
senha) e o e-mail dos membros é restrito a OWNER/ADMIN
(`memberships:read-contact`). A auditoria de clínica (`membership.invited`,
`membership.role_changed`, `membership.removed`, `invitation.accepted`) não
contém token, senha, cookie ou IP bruto.

## Frontend (M1.5, ADR 0008)

O frontend fala apenas com `/api/v1` na mesma origem (rewrite do Next); a
sessão continua em cookie `HttpOnly` e o CSRF é obtido de `GET /auth/csrf` e
enviado no header `X-CSRF-Token` imediatamente antes de cada mutação. Nenhum
token é persistido em JavaScript: tokens de verificação, reset e convite são
lidos do fragmento de URL para a memória do componente, o fragmento é limpo com
`history.replaceState` e o token é descartado após o sucesso (mantido apenas
para nova tentativa). Server Components usam um cliente próprio que encaminha
**somente** o header `Cookie` da requisição, com `cache: 'no-store'` e sem
CSRF; nenhum outro header do usuário é repassado. A guarda de sessão é
server-side (`GET /auth/me` + redirect) e o cliente browser **redireciona
globalmente para o login ao receber 401** em qualquer requisição autenticada
(a exceção é o próprio `POST /auth/login`, cujo 401 é uma credencial inválida e
permanece tratado no formulário); a UI esconde ações conforme o papel,
mas o backend permanece a autoridade (403/404 tratados). A validação de campo é
feita no cliente; erros 422 da API são genéricos, e a anti-enumeração do
backend (login e recuperação) é preservada nas mensagens.

## Roles PostgreSQL e schema (M1.2)

A role runtime `easydentist_app` não é dona do schema `app`, não executa DDL e
possui `NOBYPASSRLS`. Alembic usa exclusivamente `easydentist_migrator`, também
sem privilégios administrativos ou `BYPASSRLS`. A credencial de migration não é
injetada no processo normal da API.

As 14 tabelas do Marco 1 existem no schema `app`, com grants de DML mínimos por
finalidade (auditoria append-only; `users` e `clinic_settings` sem `DELETE`;
`memberships` somente leitura para a role runtime, pois escrita de vínculo e
papel fica reservada às funções dedicadas do M1.3/M1.4). RLS e o contexto
transacional estão implementados no M1.2.3 (ADR 0005). Nenhuma rota da API
expõe essas tabelas neste incremento.

## Hardening (M1.6, ADR 0009)

**Implementado no M1.6:** headers de segurança em toda resposta da API
(`nosniff`, `DENY`, `strict-origin-when-cross-origin`, `Permissions-Policy`,
COOP/CORP e CSP `default-src 'none'`) e no Next.js (CSP bloqueante com nonce por
resposta, sem `unsafe-inline` para scripts, `object-src` bloqueado, recursos,
conexões, fontes e formulários restritos à mesma origem, imagens `data:`
permitidas e rewrite `/api/v1` isento para preservar os headers da API); HSTS
somente em produção. Todas as rotas HTML são renderizadas dinamicamente para
que o nonce alcance os scripts gerados pelo Next, inclusive a página 404
customizada, e o `X-Powered-By` foi removido. Logs de API e web são JSONL com
allowlist em `snake_case` — sem corpo, cookie, token, senha, header de
autorização, e-mail, IP bruto ou query string — correlacionados por request ID
(a web gera `x-request-id`, o SSR o encaminha e a API o reutiliza quando é um
UUID válido), com access log textual do Uvicorn desativado (`--no-access-log`),
exceções reduzidas a `error_type` (sem mensagem ou traceback) e metadata de
auditoria sanitizada por allowlist de evento (campos desconhecidos são
descartados). Na web, o evento registra `method` e `route` normalizada (UUIDs
viram `{id}`) no início da requisição; `status_code`, `duration_ms` e
`error_type` são observáveis apenas na API, e respostas 500 também recebem os
headers de segurança e o `x-request-id`. Os detalhes de leitura estão em
`docs/operations.md`. O gate
`scripts/verify-secrets.sh` (também `pnpm run secrets`) varre apenas arquivos
versionados com padrões explícitos — chaves privadas, access keys, tokens
conhecidos, URLs com credenciais e segredos atribuídos —, exige que somente
`infra/.env.example` seja um arquivo de exemplo versionado e confirma que
`.env`, dumps e artefatos de teste estão ignorados; a saída aponta apenas
`arquivo:linha`, nunca o valor encontrado. Produção rejeita explicitamente o
segredo padrão de desenvolvimento. O runbook operacional e a prova de
restauração estão em `docs/operations.md` e `scripts/verify-backup-restore.sh`.

Os fluxos web completos passam a ser exercitados por Playwright contra o
Compose (`pnpm e2e`), incluindo login, recuperação por Mailpit, verificação,
convite, seletor de clínica, settings, equipe, sessões e o critério cross-tenant
com duas clínicas (`workers: 1` e dados sintéticos removidos no teardown).

## Pacientes, anamnese e documentos (M2.1, ADR 0010)

**Contratado no M2.1; implementado e provado nos M2.2 a M2.6.** O contrato fixa:

- **Isolamento.** `professional_profiles` é global e pertence ao usuário: RLS
  por proprietário (`user_id = app.current_user_id`), sem `clinic_id`, com
  `FORCE ROW LEVEL SECURITY` e sem `DELETE` para a role runtime. As tabelas
  `patients`, `patient_alerts`, `anamneses` e `patient_documents` pertencem à
  clínica, usam `clinic_id NOT NULL`, FK composta, RLS por tenant e
  `FORCE ROW LEVEL SECURITY`; recurso de outro tenant responde 404 genérico.
- **RBAC.** Quatorze permissões explícitas para pacientes, alertas, anamnese e
  documentos administrativos/clínicos, mantendo `default deny`. ADMIN e
  RECEPTIONIST nunca recebem conteúdo clínico (alertas, anamnese ou documentos
  clínicos); ASSISTANT lê, mas não conclui nem altera; a conclusão exige
  `anamnesis:finalize`, que só DENTIST e OWNER possuem, além de perfil
  profissional do autor.
- **Anamnese.** Um único rascunho por paciente (índice parcial); versões finais
  são imutáveis por trigger e sem `DELETE`; a numeração é sequencial por
  paciente e atribuída na conclusão, que é atômica e serializada por lock do
  paciente, grava snapshot de autoria e resiste a conclusões concorrentes. A
  revisão nasce de uma versão final do mesmo paciente.
- **Documentos.** Metadados no PostgreSQL e objeto em storage S3 privado com
  chave opaca sem PII; validação de vazio, limite de 10 MB, MIME por magic bytes
  (PDF/JPEG/PNG) e SHA-256 calculados no servidor; upload antes da ativação do
  metadado, com compensação do objeto se a persistência falhar e 503 sem
  metadado ativo se o S3 falhar; download somente após autorização por
  metadado/RLS, com `Content-Disposition: attachment`. Não há exclusão física de
  documento nem de objeto.
- **Dados sensíveis.** CPF, respostas de anamnese, nomes de arquivo, conteúdo e
  chave de storage nunca entram em logs, Problem Details ou metadata de
  auditoria; a auditoria registra apenas IDs, estado, ação e categoria. Não há
  expurgo nem exclusão física de paciente, anamnese concluída ou documento.
- **Natureza da conclusão.** Concluir a anamnese não é assinatura ICP-Brasil,
  não usa certificado e não substitui a ciência ou assinatura do paciente; a UI
  não pode rotular a operação como "assinatura".

## Operação local

`infra/.env.example` contém apenas credenciais de desenvolvimento e é o único
arquivo de exemplo permitido pelo scanner de secrets. O arquivo `infra/.env` é
ignorado por Git. Produção deverá injetar segredos externamente e nunca
reutilizar esses valores, inclusive o `AUTH_SECRET` padrão de desenvolvimento,
que é rejeitado explicitamente em `APP_ENV=production`. SeaweedFS não publica API
fora do host; Mailpit é estritamente uma ferramenta local e não deve estar em
qualquer ambiente público. O runbook completo está em `docs/operations.md`.

SeaweedFS existe somente para integração local no M1.1. Antes de uma implantação
de produção, deve haver storage gerenciado ou uma configuração revisada que
defina signing keys, criptografia em repouso e backup/restauração. O check local
exercita AWS Signature v4 e confirma que um objeto privado não é legível sem
credenciais; ele não é uma aprovação de segurança para produção. Da mesma forma,
backup/restore local não define retenção, expiração ou criptografia: esses
requisitos permanecem em `docs/operations.md` como pré-requisitos de produção.
