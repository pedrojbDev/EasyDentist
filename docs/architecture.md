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
