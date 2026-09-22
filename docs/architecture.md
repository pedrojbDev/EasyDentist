# Arquitetura

## Decisão materializada

EasyDentist será um monólito modular próprio. O frontend Next.js e a API FastAPI
são aplicações independentes no monorepo, executadas junto de PostgreSQL, Mailpit
e armazenamento S3 compatível no Docker Compose local. Não há Redis,
microserviços ou filas externas no MVP.

```text
Browser
  │ same origin /api/v1
  ▼
Next.js (apps/web) ─────► FastAPI (apps/api)
                                  │
                                  ├── PostgreSQL 17
                                  ├── SMTP (Mailpit no desenvolvimento)
                                  └── S3 privado (SeaweedFS no desenvolvimento)
```

O rewrite de Next.js preserva a topologia same-origin em `/api/v1`; o destino
interno é configurado por `API_INTERNAL_BASE_URL`. O serviço FastAPI expõe seu
contrato OpenAPI, que será a fonte do cliente TypeScript em
`apps/web/src/lib/api/generated/` quando os endpoints de domínio existirem.

## Limites de módulos previstos

O backend terá `core`, `auth`, `clinics`, `users`, `patients`, `appointments`,
`clinical_records`, `anamnesis`, `odontogram`, `treatments`, `billing`,
`documents` e `audit`. Esta estrutura é uma reserva de fronteiras: no M1.1 só
existem `core` e a rota técnica de saúde. Não foram criados módulos vazios de
domínio para evitar aparentar implementação antecipada.

As regras de segurança e isolamento pertencem a `auth`, `clinics`, repositories
tenant-aware e PostgreSQL; seu desenho está em `security.md` e sua implementação
começa no M1.2/M1.3, não nesta fundação.

## Convenções duráveis

- O contrato público usa OpenAPI e URLs `/api/v1`.
- IDs de domínio serão UUID; instantes serão `timestamptz`; moeda será armazenada
  em centavos e a configuração inicial será BRL.
- O idioma de interface é pt-BR. `America/Bahia` será o timezone padrão de
  provisionamento no marco correspondente.
- Objetos de documentos serão privados; PostgreSQL guardará apenas metadados,
  checksum, MIME type, tamanho e chave opaca.
- Não se copia OpenDentist no M1.1. A política de auditoria está em
  `open-dentist-audit.md`.
- SeaweedFS é exclusivamente infraestrutura local. Produção exige storage
  gerenciado ou configuração explícita de signing keys, criptografia em repouso
  e backup.

## Fronteiras de código

A ADR 0003 fixa a separação pragmática: routers cuidam só de HTTP; services/use
cases orquestram; repositories persistem; e regras de domínio não dependem de
FastAPI ou SQLAlchemy. `app/main.py` é somente o composition root e a application
factory centraliza a criação de FastAPI e o registro de routers. Ports/`Protocol`
só aparecem em fronteiras externas substituíveis; não existem `BaseService` nem
`BaseRepository` genéricos.

## Estado do M1.2.1

A fundação fornece somente `GET /health` na web e `GET /api/v1/health` na API.
São endpoints operacionais sem dados, credenciais ou autorização. Eles não são a
API pública do Marco 1 e não introduzem autenticação, tenancy ou domínio. O
backend agora possui engine e sessões SQLAlchemy assíncronas, metadata no schema
`app` e Alembic com uma baseline vazia. A ADR 0004 define a separação entre as
roles administrativa, de migration e de runtime.

Ainda não existem tabelas de domínio, RLS, `TenantContext`, repositories,
autenticação ou RBAC. Esses limites permanecem nos incrementos seguintes.

## Estado do M1.2.2

As 14 tabelas do Marco 1 já existem no schema `app`: oito globais de identidade
e autenticação (`users`, `password_credentials`, `external_identities`,
`auth_sessions`, `auth_action_tokens`, `auth_rate_limit_buckets`,
`auth_audit_events`, `email_outbox`) e seis tenant-aware (`clinics`,
`clinic_settings`, `clinic_feature_flags`, `memberships`,
`membership_invitations`, `clinic_audit_events`), criadas pelas migrations
`0002_global_identity` e `0003_tenant_structure`. O padrão de FK composta
`(clinic_id, parent_id)` está materializado em
`membership_invitations → memberships`. A extensão `citext` é criada pelo
bootstrap local do PostgreSQL.

Os grants de DML são emitidos na migration e limitados por finalidade
(auditoria é append-only; `users` não tem `DELETE`). Ainda não existem RLS,
`TenantContext`, repositories, autenticação ou RBAC: nenhuma rota da API expõe
essas tabelas e a proteção por linha entra no M1.2.3.

## Estado do M1.2.3

RLS está ativo e forçado nas seis tabelas tenant-aware, com duas classes de
policy (user-scoped em `clinics`/`memberships`; tenant-scoped nas demais),
verificação de membership ativa via `app.is_active_member()` e exceção
permissiva restrita ao `easydentist_migrator`, conforme a ADR 0005. O contexto
transacional existe em `app/core/context.py` e `app/core/tenancy.py`
(`UserContext`/`TenantContext`, `user_transaction`/`tenant_transaction`) e o
comportamento é fail-closed: sem contexto, nenhuma linha é visível e `WITH
CHECK` rejeita escrita. Repositories, autenticação e RBAC ainda não existem.

## Estado do M1.2.4

Repositories tenant-aware existem em `app/clinics/repositories/`
(`ClinicRepository`, `MembershipRepository`, `ClinicSettingsRepository`): o
contexto é sempre o primeiro parâmetro, não há método unscoped e updates
combinam `id` e `clinic_id`. Erros de integridade são traduzidos em
`app/core/errors.py` (violação de FK → `NotFoundError`; unique →
`ConflictError`), sem revelar a existência de recursos de outro tenant. O
registro tipado de feature flags (`FeatureKey`, vazio no Marco 1, sem chave
especulativa) e o `FeatureFlagService` ficam em `app/clinics/feature_flags.py`,
com default sempre desabilitado. Autenticação e RBAC permanecem nos marcos
seguintes.

## Estado do M1.2.5 (M1.2 concluído)

A suíte de isolamento cobre os repositories nas duas direções, SQL cru com IDs
válidos da outra clínica, transações intercaladas e concorrentes no mesmo pool,
conexões reutilizadas sem contexto e referências cross-tenant (FK traduzida em
`NotFoundError`). O ciclo completo de migrations contra banco novo é validado
por `scripts/verify-migrations.sh`. O critério do M1.2 — uma segunda clínica não
consegue acessar nenhum dado da primeira — está demonstrado por testes
automatizados. Autenticação (M1.3), RBAC (M1.4) e frontend operacional (M1.5)
seguem nos próximos incrementos.

## Estado do M1.3.1

A fundação de autenticação existe: `AuthSettings` com validação fail-fast
(`APP_ENV`, `AUTH_SECRET` de no mínimo 32 bytes em produção, TTLs de sessão,
parâmetros Argon2, proxies confiáveis, SMTP e allowlist de origem),
`PasswordHasher` Argon2id v19 (64 MiB, três iterações, paralelismo 1) com
rehash transparente, tokens de 256 bits com digest SHA-256 e comparação em
tempo constante, Problem Details (RFC 9457) com `request_id` em todas as
respostas de erro, outbox de e-mail com retry exponencial e auditoria de
eventos de segurança. A application factory cria engine e session factory no
lifespan, e `app/models.py` agrega o metadata ORM para que FKs entre módulos
resolvam em runtime. Sessões, CSRF, rate limiting, verificação, recuperação e
provisionamento entram nos incrementos M1.3.2 a M1.3.5.

## Estado do M1.3.2

Sessões e login estão implementados: migration `0005_auth_indexes`; repositories
globais (`SessionRepository`, `PasswordCredentialRepository`,
`UserRepository`); `LocalPasswordAuthenticator` (Argon2id com rehash
transparente e verificação dummy para não revelar existência de conta por
tempo) atrás do port `Authenticator`; `SessionService` com criação, resolução
para `Principal`, expiração idle/absoluta, touch com throttle de cinco minutos
e revogação individual/global; cookies de sessão com flags por ambiente; e os
endpoints `POST /auth/login`, `POST /auth/logout`, `POST /auth/logout-all`,
`GET /auth/me`, `GET /auth/sessions` e `DELETE /auth/sessions/{id}` com
auditoria de eventos. CSRF, rate limiting, verificação, recuperação e
provisionamento entram nos incrementos seguintes.

## Estado do M1.3.3

CSRF e rate limiting estão implementados: `CsrfService` com double-submit
assinado (HMAC-SHA256 sobre token e binding — anônimo ou `session_id`),
`GET /auth/csrf` reemitindo o token vinculado à sessão, e enforcement em todas
as mutações do router (header `X-CSRF-Token` idêntico ao cookie, assinatura
válida e `Origin`/`Referer` na allowlist, com ausência rejeitada); migration
`0006_rate_limit_function` com upsert atômico, janela, bloqueio e backoff
progressivo (`30·2^n` segundos, teto de 15 minutos); `RateLimiter` com chaves
HMAC; login consumindo conta e IP antes da autenticação, limpando o bucket da
conta em caso de sucesso e respondendo `429` com `Retry-After`; resolução de
IP que só confia em `X-Forwarded-For` vindo de proxies declarados. Verificação,
recuperação e provisionamento entram nos incrementos M1.3.4 e M1.3.5.

## Estado do M1.3.4

Verificação de e-mail e recuperação de senha estão implementados:
`ActionTokenService` com tokens de 256 bits, somente digest persistido, validade
de 24 h (verificação) e 30 min (reset) e consumo single-use atômico
(`SELECT … FOR UPDATE`; dois consumes concorrentes produzem exatamente um
sucesso); endpoints `POST /auth/email-verification/resend`,
`POST /auth/email-verification/confirm`, `POST /auth/password/forgot` e
`POST /auth/password/reset` com respostas genéricas contra enumeração (202
sempre em forgot/resend; 400 genérico para token inválido ou reutilizado),
limite de 3/destinatário/h e 20/IP/h e auditoria (`email_verified`,
`password_reset_completed`, `rate_limit_triggered`). O reset atualiza a
credencial, revoga todas as sessões e não faz login automático. Os e-mails
usam templates pt-BR com link em fragmento
(`{PUBLIC_BASE_URL}/verify-email#token=…` e `/reset-password#token=…`) e
entrega outbox-first com `idempotency_key` semântico, tentativa pós-commit e
retry com backoff exponencial. Provisionamento e aceite de convite entram no
M1.3.5.

## Estado do M1.3.5

O provisionamento operacional e o aceite de convite estão implementados: a
migration `0007_invitation_functions` cria as funções `SECURITY DEFINER`
`app.provision_clinic_owner` (cria usuário sem senha se necessário, clínica
`PROVISIONING`, `clinic_settings`, membership OWNER `PENDING`, convite de 72 h
e auditoria `clinic.provisioned`) e `app.consume_invitation` (lock
`SELECT … FOR UPDATE`, guarda de expiração/reuso, credencial, verificação de
e-mail, `PENDING → ACTIVE` e `PROVISIONING → ACTIVE` na mesma transação),
ambas com `search_path` fixo e `EXECUTE` restrito à role runtime. O
`ProvisionService` e a CLI `python -m app.auth.provision` geram o token de 256
bits, enfileiram o e-mail em outbox e imprimem apenas metadados — nunca o
token; slug duplicado vira `ConflictError` sem criar tenant. O endpoint
`POST /api/v1/invitations/accept` consome o convite atomicamente (dois accepts
concorrentes produzem exatamente um sucesso), responde 400 genérico para token
inválido/expirado/reutilizado com estado intacto, 422 para senha fora de
12–128 caracteres, registra `invitation.accepted` (clínica) e
`invitation_accepted` (auditoria de auth), revoga todas as sessões ativas do
usuário ao trocar a senha e não faz login automático. O
template pt-BR do convite usa link em fragmento e nome da clínica. A prova de
segurança consolidada do M1.3 entra no M1.3.6.

## Estado do M1.3.6 (M1.3 concluído)

A prova de segurança consolidada existe: a matriz do §5 em
`tests/integration/test_auth_security_matrix.py` cobre apenas-hashes no banco,
flags de cookie por ambiente, expiração idle/absoluta, revogação/reuso ⇒ 401,
sessões concorrentes de dois dispositivos, rotação no login, anti-enumeração
em login/recuperação, a matriz CSRF completa (inclusive `GET` isento) e o rate
limit atômico com consumo single-use sob concorrência. A redaction em
`tests/integration/test_auth_redaction.py` demonstra que logs,
`auth_audit_events`, `clinic_audit_events` e buckets de rate limit (chaves
HMAC) não contêm senha, token, cookie ou IP bruto. O contrato do `Authenticator`
passa com o provider local e com o provider fake
(`tests/integration/test_authenticator.py`). `scripts/verify-migrations.sh`
valida a cadeia completa (0001→0007) em banco descartável, e o Compose completo
sobe com saúde verde para db, storage, api e web, incluindo o proxy same-origin
e o round-trip S3 assinado. Os 11 endpoints de auth do Marco 1 estão
implementados; RBAC e convites de equipe entram no M1.4.

## Estado do M1.4.1

A fundação do RBAC existe: `app/clinics/rbac.py` declara `Role` e `Permission`
como `StrEnum`, o mapa `ROLE_PERMISSIONS` e `role_allows(role, permission)` com
default deny — nesta etapa as nove permissões dos endpoints de clínica, settings,
membros e convites (`clinic:read`, `clinic:update-legal-name`, `settings:read`,
`settings:update`, `memberships:read`, `memberships:read-contact`,
`memberships:manage-role`, `memberships:remove`, `invitations:create`); OWNER
detém todas, ADMIN acumula a leitura com a gestão (sem `clinic:update-legal-name`),
e DENTIST, ASSISTANT e RECEPTIONIST têm apenas leitura. A matriz é exercitada
por teste parametrizado (todos os papéis × todas as permissões, positivo e
negativo, papel desconhecido e permissão não declarada). `PermissionDeniedError`
em `app/core/errors.py` é mapeada para 403 pelo handler de Problem Details. O
ADR 0007 fixa as demais decisões (contexto tenant por requisição, transições via
funções `SECURITY DEFINER`, serialização do último OWNER, aceite com senha
opcional e exposição de contato restrita). O contexto tenant, os endpoints e a
gestão de equipe entram nos incrementos M1.4.2 a M1.4.6.

## Estado do M1.4.2

O contexto tenant por requisição e a leitura de clínicas existem:
`app/clinics/dependencies.py` expõe `get_membership`, que resolve o `Principal`
e o `clinic_id` da rota, consulta a membership do usuário em `user_transaction`
(policy `memberships_user_select`) e devolve
`ClinicMembership(TenantContext, Role)`; qualquer membership ausente ou não
`ACTIVE` (assim como clínica inexistente ou de outro tenant) resulta em
**404 genérico**, e o resultado é cacheado por requisição. O router
`/api/v1/clinics` oferece `GET /clinics` (somente memberships `ACTIVE`, com o
papel de cada clínica para o seletor do M1.5) e `GET /clinics/{clinic_id}`
(clínica + papel), este último rodando em `tenant_transaction` para a RLS
revalidar. A revogação de um vínculo tem efeito na requisição seguinte. Os
A escrita de clínica e settings, a gestão de equipe e os convites entram nos
incrementos seguintes.

## Estado do M1.4.3

Clínica e settings estão editáveis: `PATCH /clinics/{clinic_id}` altera apenas
`legal_name` e exige `clinic:update-legal-name` (exclusiva de OWNER — a matriz
de teste confirma 403 para ADMIN, DENTIST, ASSISTANT e RECEPTIONIST);
`GET/PATCH /clinics/{clinic_id}/settings` expõe `display_name`, `timezone`,
`locale` e `currency`, com leitura para todos os papéis e escrita para
OWNER/ADMIN (`settings:update`). A timezone é validada contra
`zoneinfo.available_timezones()` e a moeda contra `^[A-Z]{3}$`, ambos → 422;
`require_permission` no RBAC traduz papel sem permissão em
`PermissionDeniedError` → 403. Todos os acessos cross-tenant (com IDs válidos
da outra clínica) respondem 404 para qualquer papel. A gestão de equipe entra
no M1.4.4.

## Estado do M1.4.4

A gestão de equipe existe: a migration `0008_membership_management` traz
`create_member_invitation`, `change_member_role` e `remove_membership`
(SECURITY DEFINER, `EXECUTE` só para a role runtime) e a `consume_invitation`
v2 — senha opcional, exigida apenas para usuário sem credencial, e
`password_not_allowed` quando já existe credencial. `change_member_role` e
`remove_membership` serializam toda operação por clínica
(`SELECT … FROM app.clinics … FOR UPDATE`) antes de travar o alvo e contar
OWNERs, de modo que dois OWNERs não consigam se rebaixar ou remover
simultaneamente (testes concorrentes: 1×200 + 1×409 e 1×204 + 1×403 com
exatamente um OWNER restante). O `MembershipService` traduz os erros nomeados
das funções (`not_permitted`→403, `last_owner`→409, `invalid_role`→422,
`membership_not_found`→404) e os endpoints `GET/PATCH/DELETE
/clinics/{id}/memberships` exigem `memberships:read`, `memberships:manage-role`
e `memberships:remove`; ADMIN gerencia apenas papéis não-OWNER/ADMIN, e o e-mail
dos membros só aparece com `memberships:read-contact` (OWNER/ADMIN). A remoção
é física, auditada (`membership.removed`) e tem efeito imediato, liberando a
constraint única para reconvite. O aceite com `password` opcional também está
adaptado (`password_required`/`password_not_allowed` → 422). Os convites de
equipe por endpoint entram no M1.4.5.

## Estado do M1.4.5

Convites de equipe e o aceite completo existem: `POST
/clinics/{id}/invitations` exige `invitations:create`, valida o papel no schema
(desconhecido ⇒ 422) e aplica o rate limit compartilhado de recuperação
(3/destinatário/h e 20/IP/h, consumido antes da ação — tentativas duplicadas
também gastam orçamento e a 4ª responde 429 com `Retry-After`). A função
`create_member_invitation` reutiliza ou cria o usuário, grava membership
`PENDING` e invitation de 72 h na mesma transação da linha de outbox, com audit
`membership.invited`; e-mail `team-invitation` em pt-BR com nome da clínica,
papel rotulado, link em fragmento e `idempotency_key` semântico. Usuário já
membro ⇒ 409; ADMIN convida apenas papéis não-OWNER/ADMIN; DENTIST, ASSISTANT e
RECEPTIONIST recebem 403. O aceite (`POST /invitations/accept`, senha opcional)
ativa a membership: novo usuário define senha (verificação de e-mail e
revogação de sessões), usuário existente entra sem trocar senha nem revogar
sessões (`password_not_allowed` se enviar senha); sem senha para usuário novo ⇒
`password_required` 422. O helper de rate limit foi movido para
`app/platform/rate_limit.py` e reusado por auth e clinics. A prova de
autorização consolidada entra no M1.4.6.

## Estado do M1.4.6 (M1.4 concluído)

A prova de autorização do M1.4 existe: `tests/integration/test_rbac_matrix.py`
cobre os cinco papéis contra os nove endpoints de tenancy (positivo e negativo,
incluindo 403 para ADMIN em `legal_name` e para papéis operacionais na gestão),
o 404 cross-tenant para todos os papéis com IDs válidos da outra clínica,
`memberships:read-contact` (e-mail só para OWNER/ADMIN), efeito imediato do
rebaixamento, as guardas de último OWNER e "ADMIN não promove OWNER", e a
redaction da auditoria de clínica (sem token, senha, cookie ou IP). O gate
completo fecha o marco: `scripts/verify-migrations.sh` valida 0001→0008 em
banco descartável, o Compose completo sobe com saúde verde (db, storage, api e
web, proxy same-origin e round-trip S3) e os 10 endpoints de Tenancy do §4
estão implementados. RBAC e convites de equipe do Marco 1 estão concluídos;
Playwright e hardening final entram no M1.6 e o frontend no M1.5.

## Estado do M1.5.1

A fundação do frontend operacional existe (ADR 0008): o contrato é gerado a
partir do OpenAPI (`apps/api/scripts/export_openapi.py`, executável por
`python -m scripts.export_openapi` e com `--check` para drift), versionado em
`apps/web/src/lib/api/generated/openapi.json`, com tipos `schema.d.ts` gerados
por `openapi-typescript` (`pnpm gen:api`); os jobs `api` e `web` do CI falham
por drift. O acesso à API tem duas superfícies: `src/lib/api/client.ts`
(navegador: URL relativa same-origin, cookies automáticos, `X-CSRF-Token`
obtido de `GET /auth/csrf` antes de cada mutação, `ApiError` com
`status/title/detail?/requestId?/retryAfter?`) e `src/lib/api/server-client.ts`
(Server Components: `API_INTERNAL_BASE_URL`, encaminhamento explícito e
restrito do header `Cookie`, `cache: 'no-store'`, sem CSRF em GET). O ambiente
de testes de componente foi habilitado com jsdom e Testing Library (smoke de
interação com o `Button`), somando 21 testes web verdes; as novas dependências
de teste passaram pelo gate de licenças (exceções exatas para transitivas
MIT-0/BlueOak-1.0.0/CC0-1.0 em `scripts/js-license-exceptions.json`) e pelo
audit sem vulnerabilidades. As telas e fluxos do marco entram nos incrementos
M1.5.2 a M1.5.6.

## Estado do M1.5.2

Login, guarda de sessão e seletor de clínica existem: `/login` (formulário com
validação de campo no cliente, mensagem genérica para credenciais inválidas e
tempo de espera no 429) redireciona para `/clinics` após o login; o grupo
autenticado `(app)` valida a sessão no servidor (`GET /auth/me` pelo
`server-client` + `redirect('/login')` em 401) e declara
`dynamic = 'force-dynamic'`; o cabeçalho mostra o usuário e oferece **"Sair"**
(`POST /auth/logout`, sessão atual) e **"Sair de todos os dispositivos"**
(`POST /auth/logout-all`, com confirmação); `/` redireciona para `/clinics`, que
lista as clínicas ativas com papel e situação em pt-BR e navega para
`/clinics/{id}` (página de identidade provisória, aprofundada no M1.5.4).
`/login` também redireciona quem já tem sessão. O gate do frontend passa a
rodar `build` antes de `typecheck` porque o `typedRoutes` depende dos tipos de
rota gerados pelo build (mesma ordem no CI). Os fluxos de recuperação,
verificação e convite entram no M1.5.3.

## Estado do M1.5.3

Recuperação, verificação de e-mail e aceite de convite existem: `/forgot-password`
(validação de e-mail no cliente e confirmação idêntica para qualquer endereço,
preservando a anti-enumeração), `/reset-password`, `/verify-email` e
`/accept-invitation` (compatíveis com os links `#token=` emitidos pela API). O
hook `useFragmentToken` lê o token do fragmento **primeiro para o estado**,
limpa o hash com `history.replaceState` e o mantém apenas em memória para nova
tentativa após falha (botão "Tentar novamente" reenvia o mesmo token); fragmento
sem token ou com outro conteúdo é ignorado, e o token nunca vai para query
string. `/reset-password` valida 12–128 caracteres e confirmação, trata 400 como
link inválido e oferece o login após o sucesso; `/verify-email` confirma
automaticamente ao carregar e mantém o token para retry; `/accept-invitation`
permite deixar a senha em branco (usuário existente apenas ativa o acesso) e,
sem alegar a causa exata, orienta o primeiro acesso de forma genérica no 422
(`password_required` não tem `code` estável na API — registrado no ADR 0008). O
cabeçalho e os formulários continuam a compartilhar o cliente browser com CSRF
por mutação. A gestão de clínica e settings entra no M1.5.4.

## Estado do M1.5.4

Clínica e settings são editáveis conforme a matriz: `/clinics/{id}` mostra
identidade (razão social, slug, papel e situação) e exibe o formulário de
`legal_name` **somente para OWNER** (validação 1–200 no cliente, confirmação de
sucesso, 403 tratado); `/clinics/{id}/settings` mostra nome comercial, fuso
horário, idioma e moeda em modo leitura para todos os papéis e formulário
editável para OWNER/ADMIN, com validação local do fuso contra
`Intl.supportedValuesOf('timeZone')` (sugestões via `datalist`) e da moeda
`^[A-Z]{3}$`, mensagens de campo, 403/422/429 tratados e confirmação de
sucesso. A API de feature ganhou `updateClinic`, `getSettings` e
`updateSettings` (browser) e `getClinicSettingsOnServer` (server), todas
tipadas pelo contrato gerado. Equipe, papéis e convites entram no M1.5.5.

## Estado do M1.5.5

A gestão de equipe existe: `/clinics/{id}/members` lista os vínculos em pt-BR
(papel, situação e data de entrada; a coluna **E-mail só aparece quando a API a
devolve**, o que depende de `memberships:read-contact` — a UI não tenta inferir
o papel de contato), com ações espelhando a matriz: OWNER gerencia qualquer
linha e pode atribuir os cinco papéis; ADMIN só toca em linhas que não sejam
OWNER/ADMIN e seu seletor oferece apenas DENTIST/ASSISTANT/RECEPTIONIST; os
demais papéis não veem ações. A troca de papel atualiza a linha com o retorno
da API e a remoção pede confirmação, refletindo o vínculo removido; 403/404/409
(inclusive o último OWNER) e 429 têm mensagens próprias. O formulário de convite
(`/clinics/{id}/members`) valida o e-mail, filtra os papéis pelo papel do ator
(OWNER: todos; ADMIN: sem OWNER/ADMIN), mostra a confirmação com a data de
expiração (72 h) e trata 409 ("já participa"), 403, 422 e 429. As páginas usam
o `server-client` para os dados iniciais e as mutações usam o cliente browser
com CSRF. Sessões e o fechamento do marco entram no M1.5.6.

## Estado do M1.5.6 (M1.5 concluído)

O frontend operacional do Marco 1 está completo: `/sessions` lista as sessões
do usuário com a atual marcada ("Esta sessão"), permite revogar outro
dispositivo, encerrar a sessão atual (com confirmação e volta ao login) e
"sair de todos os dispositivos"; sessões já revogadas em outro lugar somem da
lista com aviso (404). O cabeçalho ganhou navegação para Clínicas e Sessões. O
polimento fechou estados vazios (clínicas, vínculos e sessões), tabelas com
rolagem horizontal em telas estreitas, cabeçalhos de tabela com `scope="col"` e
um hook `useFocusFirstInvalid` compartilhado que move o foco para o primeiro
campo inválido em todos os formulários. Com isso o M1.5 cobre login,
recuperação, verificação, convite, seletor de clínica, clínica/settings,
equipe/convites e sessões; os fluxos web completos em Playwright ficam no M1.6,
junto do hardening (headers, logs estruturados, restauração de banco e
threat model).

## Estado do M1.6.1

O contrato do hardening está documentado na ADR 0009 e em `docs/threat-model.md`.
O threat model enumera ativos (sessões, tokens, credenciais, dados clínicos,
memberships, backups, logs e segredos), fronteiras de confiança (browser,
Next.js, FastAPI, PostgreSQL runtime, PostgreSQL migrator, Mailpit e storage) e
15 ameaças com mitigação e evidência — teste automatizado ou limitação
operacional explícita. A ADR 0009 fixa as decisões de E2E contra o Compose com
fixtures determinísticas e `workers: 1`, headers de segurança (CSP nonce
bloqueante na web e CSP restritiva na API, HSTS só em produção), logs JSONL com
allowlist e redaction, backup/restauração com `pg_dump -Fc`/`pg_restore` em
PostgreSQL descartável, scanner de secrets, rejeição do segredo padrão de
desenvolvimento em produção e o critério cross-tenant de ponta a ponta. O M1.6
não altera domínio clínico; storage, SMTP, retenção de backups, criptografia e
gestão externa de secrets permanecem pré-requisitos operacionais.

## Estado do M1.6 (M1.6 concluído)

O hardening do Marco 1 está implementado e provado. O harness Playwright
(`playwright.config.ts`, `apps/web/e2e/`, `apps/api/scripts/seed_e2e.py`) roda
contra o Compose com 17 cenários — autenticação, recuperação e verificação por
Mailpit, convite, seletor, settings, equipe, sessões, headers, CSP sem violações
e isolamento cross-tenant nas duas direções. A API ganhou
`SecurityHeadersMiddleware` e o Next.js um middleware de CSP com nonce por
resposta, sem `unsafe-inline` para scripts. Logs de API e web são JSONL com
allowlist, `error_type` sem traceback e correlação por request ID
(`x-request-id` gerado na web e reutilizado na API); o access log textual do
Uvicorn foi desativado. `scripts/verify-backup-restore.sh` prova
`pg_dump -Fc`/`pg_restore` em PostgreSQL descartável com schema, revisão
Alembic, grants, policies, `FORCE ROW LEVEL SECURITY`, `NOBYPASSRLS` e
isolamento sob a role runtime; `docs/operations.md` registra o runbook.
`scripts/verify-secrets.sh` varre arquivos versionados e
`tests/integration/test_m16_isolation_gate.py` consolida a prova de RLS,
cookies e 404 cross-tenant. O CI ganhou o job `hardening` (secrets, Compose,
migrations, health, Playwright e backup/restore). O gate global do M1.6 passa
por completo; produção continua condicionada aos pré-requisitos operacionais de
`docs/operations.md`.

## Estado do M2.1

O contrato do Marco 2 está materializado na ADR 0010: pacientes, alertas,
anamnese versionada e documentos privados, com modelos, estados, invariantes,
rotas, matriz RBAC, fluxo de upload e compensação do S3. Os módulos
`patients`, `anamnesis` e `documents` e o port de storage em
`app/platform/storage.py` serão criados nos incrementos M2.2 a M2.5, sem
repository, service ou `Base*` genérico compartilhado entre eles (ADR 0003).

O catálogo clínico `cfo_2026_v1` existe em
`app/anamnesis/templates/cfo_2026_v1.py` como estrutura imutável (seções,
perguntas, opções e tipos de resposta `YES_NO_UNKNOWN`, `SINGLE_CHOICE` e
`TEXT`), com IDs estáveis e ordem determinística. A redação é própria em pt-BR,
baseada no Anexo 1 do Manual do Prontuário do CFO de 2026 apenas como
referência. O M2.4 importará os IDs do catálogo nos schemas Pydantic; qualquer
mudança de conteúdo exige um novo identificador de template.

Nenhuma tabela, migration, rota, tela ou dependência nova foi criada no M2.1;
o M2.2 começa pelo schema com RLS de tenant e de proprietário do usuário
(`professional_profiles`) provada sem contexto e nas duas direções. A conclusão
de anamnese registra autoria e snapshot profissional, mas não é assinatura
ICP-Brasil nem substitui a ciência ou assinatura do paciente.
