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
