# M1.2 — Banco e Tenancy: Plano de Implementação

> **Para o agente executor:** implemente este plano tarefa por tarefa, um incremento por vez. Passos usam checkbox (`- [ ]`) para rastreamento. **Regra do `plan.md` §4:** ao final de cada incremento, apresente ao usuário o relatório de conclusão (arquivos e comportamentos implementados, comandos executados, resultados, pendências) e **aguarde aprovação antes de iniciar o incremento seguinte** — não haverá avanço silencioso.

**Goal:** Entregar as 14 tabelas do Marco 1, isolamento multi-tenant enforced por PostgreSQL RLS (fail-closed), `TenantContext` obrigatório nos repositories, interface tipada de feature flags e a prova automatizada de isolamento entre duas clínicas.

**Spec:** `plan.md` (§3, §4) · `docs/security.md` · `docs/data-model.md` · `docs/architecture.md` · `docs/adr/0003-solid-and-modular-boundaries.md` · `docs/adr/0004-database-roles-and-migrations.md`

**Tech stack:** Python 3.12.14 · SQLAlchemy 2.0.44 async · asyncpg 0.30.0 · Alembic 1.16.5 · pytest 9.0.3 (+anyio) · PostgreSQL 17 · uv

**Estado pré-existente (M1.2.1, já mergeado):** `apps/api/app/core/database.py` (`Base` com `MetaData(schema="app")` + naming convention, `DatabaseSettings`, `create_database_engine`, `create_session_factory`, `transaction_scope`); Alembic configurado (`migrations/env.py`, `include_schemas`, `compare_type`, `version_table_schema="app"`, exige `MIGRATION_DATABASE_URL` com driver `postgresql+asyncpg`); migration baseline vazia `0001_database_foundation`; roles `easydentist_app` (runtime, sem DDL) e `easydentist_migrator` (dona do schema), ambas `NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS`; serviço `migrate` no profile `tools` do Compose; CI já roda `alembic upgrade head`, `pytest`, `alembic check`, `downgrade base`, `upgrade head`.

## Global Constraints (implícitas em toda tarefa)

- Schema `app` em tudo; usar o `Base` de `app/core/database.py` (naming convention já existente — não redefinir).
- IDs `uuid` com `server_default=func.gen_random_uuid()`; instantes `timestamptz` (`DateTime(timezone=True)`); moeda em centavos (não há colunas monetárias no Marco 1).
- Models em SQLAlchemy 2 style (`Mapped[...]` + `mapped_column`), passando em mypy strict e ruff (`line-length = 100`, regras `E,F,I,UP,B`).
- **GOTCHA SQLAlchemy:** `metadata` é atributo reservado do declarativo. Colunas chamadas `metadata` devem ser declaradas como `event_metadata: Mapped[dict] = mapped_column("metadata", JSONB, ...)`.
- FKs entre tabelas do schema: usar forma qualificada `"app.<tabela>.<coluna>"` em `ForeignKey`/`ForeignKeyConstraint`.
- Migrations rodam somente como `easydentist_migrator`. IDs de revision no estilo existente: `0002_global_identity`, `0003_tenant_structure`, `0004_rls_policies` (cadeia `down_revision` sequencial a partir de `0001_database_foundation`).
- GRANTs de DML para `easydentist_app` são emitidos com `op.execute(...)` na **mesma migration** que cria a tabela (autogenerate não os produz). Downgrade correspondente faz `REVOKE` + `DROP`.
- Testes de integração seguem `apps/api/tests/integration/test_database_foundation.py`: asyncpg direto, env vars `TEST_ADMIN_DATABASE_URL` / `TEST_APP_DATABASE_URL` / `TEST_MIGRATION_DATABASE_URL` (URLs `postgresql://` síncronas), `pytest.skip` se ausente, `@pytest.mark.anyio`.
- Documentação do projeto é em pt-BR; identificadores e SQL em inglês.

### Comandos locais de referência

```sh
# subir banco e aplicar migrations
docker compose -f infra/docker-compose.yml up -d --wait db
docker compose -f infra/docker-compose.yml --profile tools run --rm migrate

# env para testes de integração (valores de dev de infra/.env.example)
export TEST_ADMIN_DATABASE_URL=postgresql://easydentist:easydentist-local-only@127.0.0.1:5433/easydentist
export TEST_APP_DATABASE_URL=postgresql://easydentist_app:easydentist-app-local-only@127.0.0.1:5433/easydentist
export TEST_MIGRATION_DATABASE_URL=postgresql://easydentist_migrator:easydentist-migrator-local-only@127.0.0.1:5433/easydentist
export MIGRATION_DATABASE_URL=postgresql+asyncpg://easydentist_migrator:easydentist-migrator-local-only@127.0.0.1:5433/easydentist

# quality gate (obrigatório ao final de cada incremento, em apps/api)
uv run ruff check . && uv run ruff format --check . && uv run mypy app scripts && uv run pytest
uv run alembic upgrade head && uv run alembic check
docker compose -f infra/docker-compose.yml config --quiet
```

## Decisões travadas (viram ADR 0005 no M1.2.3)

| # | Decisão |
|---|---|
| D1 | **Duas classes de policy:** `clinics` e `memberships` são **user-scoped** (chave `app.current_user_id`; é o que alimenta o seletor de clínica `GET /api/v1/clinics`); `clinic_settings`, `clinic_feature_flags`, `membership_invitations`, `clinic_audit_events` são **tenant-scoped** (`app.current_clinic_id` + `app.is_active_member()`). |
| D2 | **Função `app.is_active_member()` SECURITY DEFINER**, dona = `easydentist_migrator` (não-superuser ⇒ fica contida pelo FORCE RLS), `SET search_path = app, pg_temp`, `REVOKE EXECUTE FROM PUBLIC`, `GRANT EXECUTE TO easydentist_app`. Lê `memberships` filtrando pelos dois GUCs + `status='ACTIVE'`. |
| D3 | **Policy permissiva `FOR ALL TO easydentist_migrator USING (true) WITH CHECK (true)`** nas 6 tabelas tenant. Com FORCE RLS o dono também fica sujeito às policies; sem esta exceção, backfills futuros e o provisionamento quebram. Exceção controlada e auditada (role trusted, sem login interativo). |
| D4 | **Anti-recursão:** policies de `clinics`/`memberships` usam só comparação direta de GUC e subquery simples — nunca chamam `is_active_member()`. Só as 4 tabelas tenant-scoped chamam a função (que internamente roda como migrator, cuja policy permissiva não chama função — recursão impossível). |
| D5 | **Fail-closed:** toda policy usa `NULLIF(current_setting('app.current_x', true), '')` — contexto ausente/vazio ⇒ comparação NULL ⇒ zero linhas / `WITH CHECK` rejeita. |
| D6 | **FKs compostas nascem no schema (M1.2.2):** tabelas tenant recebem `UNIQUE(clinic_id, id)`; `membership_invitations(clinic_id, membership_id)` → `memberships(clinic_id, id)` é a instância comprovadora do padrão (convite acompanha a membership PENDING, conforme provisionamento do plan.md §3). |
| D7 | **`citext`** para `users.email` e `clinics.slug` (extensão trusted, criada no bootstrap pelo admin; volume local precisa ser recriado — mesmo precedente da ADR 0004). |
| D8 | **Sem RLS nas 8 tabelas globais** — controle via grants + camada de aplicação (M1.3). |
| D9 | **Transições sensíveis de membership** (aceite PENDING→ACTIVE, rebaixamento) usarão funções `SECURITY DEFINER` dedicadas — desenho em M1.3/M1.4. M1.2 entrega apenas policies de leitura/gestão. |
| D10 | **Janela sem RLS:** M1.2.2 cria tabelas sem RLS até o M1.2.3 — aceitável porque não existe rota de API expondo dados; declarar no relatório do incremento. |

## Modelo de dados (14 tabelas — especificação completa)

Todas as colunas `id` são `uuid NOT NULL DEFAULT gen_random_uuid()` PK. Salvo indicação, tabelas têm `created_at timestamptz NOT NULL DEFAULT now()` e `updated_at timestamptz NOT NULL DEFAULT now()` (mantido pela aplicação, sem triggers). CKs usam `CheckConstraint` (nomes gerados pela naming convention).

### Globais (migration `0002_global_identity`) — sem `updated_at` onde indicado

| Tabela | Colunas e constraints |
|---|---|
| `users` | `email` citext NOT NULL UNIQUE; `status` text NOT NULL DEFAULT `'ACTIVE'` CK `IN ('ACTIVE','DISABLED')`; `email_verified_at` timestamptz NULL |
| `password_credentials` | `user_id` uuid PK FK→`app.users.id`; `password_hash` text NOT NULL; `changed_at` timestamptz NOT NULL (sem `created_at`/`updated_at`) |
| `external_identities` | `user_id` uuid FK→`app.users.id` NOT NULL; `provider` text NOT NULL; `subject` text NOT NULL; UNIQUE(`provider`,`subject`) (sem `updated_at`) |
| `auth_sessions` | `user_id` uuid FK NOT NULL; `token_hash` bytea NOT NULL UNIQUE; `last_seen_at` timestamptz NOT NULL; `idle_expires_at` timestamptz NOT NULL; `absolute_expires_at` timestamptz NOT NULL; `revoked_at` timestamptz NULL; `replaced_by_session_id` uuid NULL FK→`app.auth_sessions.id` (sem `updated_at`) |
| `auth_action_tokens` | `user_id` uuid FK NOT NULL; `token_hash` bytea NOT NULL UNIQUE; `purpose` text NOT NULL CK `IN ('EMAIL_VERIFICATION','PASSWORD_RESET')`; `expires_at` timestamptz NOT NULL; `consumed_at` timestamptz NULL (sem `updated_at`) |
| `auth_rate_limit_buckets` | `bucket_key` bytea PK; `attempt_count` integer NOT NULL DEFAULT 0; `window_started_at` timestamptz NOT NULL; `blocked_until` timestamptz NULL (sem `created_at`/`updated_at`) |
| `auth_audit_events` | `event_type` text NOT NULL; `user_id` uuid NULL FK→`app.users.id`; `occurred_at` timestamptz NOT NULL DEFAULT now(); `event_metadata` → coluna `"metadata"` jsonb NOT NULL DEFAULT `'{}'` (sem `updated_at`) |
| `email_outbox` | `idempotency_key` text NOT NULL UNIQUE; `recipient` citext NOT NULL; `template` text NOT NULL; `payload` jsonb NOT NULL DEFAULT `'{}'`; `status` text NOT NULL DEFAULT `'PENDING'` CK `IN ('PENDING','SENT','FAILED')`; `attempt_count` integer NOT NULL DEFAULT 0; `next_attempt_at` timestamptz NULL; `sent_at` timestamptz NULL |

Grants em `0002` (via `op.execute`): `users`, `password_credentials`, `external_identities`, `auth_sessions`, `auth_action_tokens`, `email_outbox` → `SELECT, INSERT, UPDATE`; `auth_rate_limit_buckets` → `SELECT, INSERT, UPDATE, DELETE`; `auth_audit_events` → `SELECT, INSERT`. Todos `TO easydentist_app`.

### Tenant-aware (migration `0003_tenant_structure`)

| Tabela | Colunas e constraints |
|---|---|
| `clinics` | `slug` citext NOT NULL UNIQUE; `legal_name` text NOT NULL; `status` text NOT NULL DEFAULT `'PROVISIONING'` CK `IN ('PROVISIONING','ACTIVE','SUSPENDED')` |
| `clinic_settings` | `clinic_id` uuid PK FK→`app.clinics.id`; `display_name` text NOT NULL; `timezone` text NOT NULL DEFAULT `'America/Bahia'`; `locale` text NOT NULL DEFAULT `'pt-BR'`; `currency` char(3) NOT NULL DEFAULT `'BRL'`; `preferences` jsonb NOT NULL DEFAULT `'{}'` |
| `clinic_feature_flags` | PK composta (`clinic_id` uuid FK→`app.clinics.id`, `key` text); `enabled` boolean NOT NULL DEFAULT false; `config` jsonb NULL; `changed_by_user_id` uuid NULL FK→`app.users.id` |
| `memberships` | `clinic_id` uuid FK→`app.clinics.id` NOT NULL; `user_id` uuid FK→`app.users.id` NOT NULL; `role` text NOT NULL CK `IN ('OWNER','ADMIN','DENTIST','ASSISTANT','RECEPTIONIST')`; `status` text NOT NULL DEFAULT `'PENDING'` CK `IN ('PENDING','ACTIVE','SUSPENDED')`; UNIQUE(`user_id`,`clinic_id`); **UNIQUE(`clinic_id`,`id`)** |
| `membership_invitations` | `clinic_id` uuid NOT NULL; `membership_id` uuid NOT NULL; **ForeignKeyConstraint(`clinic_id`,`membership_id`)→`app.memberships`(`clinic_id`,`id`)**; `email` citext NOT NULL; `token_hash` bytea NOT NULL UNIQUE; `expires_at` timestamptz NOT NULL; `accepted_at` timestamptz NULL; UNIQUE(`clinic_id`,`id`) |
| `clinic_audit_events` | `clinic_id` uuid FK→`app.clinics.id` NOT NULL; `actor_user_id` uuid NULL FK→`app.users.id`; `event_type` text NOT NULL; `entity_type` text NULL; `entity_id` uuid NULL; `occurred_at` timestamptz NOT NULL DEFAULT now(); `event_metadata` → coluna `"metadata"` jsonb NOT NULL DEFAULT `'{}'` (sem `created_at`/`updated_at`) |

Grants em `0003`: `clinics` → `SELECT, UPDATE`; `clinic_settings` → `SELECT, UPDATE`; `clinic_feature_flags` → `SELECT`; `memberships` → `SELECT, INSERT, UPDATE, DELETE`; `membership_invitations` → `SELECT, INSERT`; `clinic_audit_events` → `SELECT, INSERT`. Todos `TO easydentist_app`. (RLS ainda restringe as linhas a partir do M1.2.3; grant sem policy não expõe nada.)

## Contratos de código

```python
# app/core/context.py
from dataclasses import dataclass
from uuid import UUID

@dataclass(frozen=True, slots=True)
class UserContext:
    user_id: UUID

@dataclass(frozen=True, slots=True)
class TenantContext:
    user_id: UUID
    clinic_id: UUID
```

```python
# app/core/tenancy.py — set_config SEMPRE com bind param e is_local=True
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.context import TenantContext, UserContext


@asynccontextmanager
async def user_transaction(
    session_factory: async_sessionmaker[AsyncSession], context: UserContext
) -> AsyncIterator[AsyncSession]:
    session = session_factory()
    try:
        await session.execute(
            text("SELECT set_config('app.current_user_id', :value, true)"),
            {"value": str(context.user_id)},
        )
        yield session
        await session.commit()
    except BaseException:
        await session.rollback()
        raise
    finally:
        await session.close()


@asynccontextmanager
async def tenant_transaction(
    session_factory: async_sessionmaker[AsyncSession], context: TenantContext
) -> AsyncIterator[AsyncSession]:
    session = session_factory()
    try:
        await session.execute(
            text("SELECT set_config('app.current_user_id', :user_id, true), "
                 "set_config('app.current_clinic_id', :clinic_id, true)"),
            {"user_id": str(context.user_id), "clinic_id": str(context.clinic_id)},
        )
        yield session
        await session.commit()
    except BaseException:
        await session.rollback()
        raise
    finally:
        await session.close()
```

```python
# app/core/errors.py
class DomainError(Exception): ...
class NotFoundError(DomainError): ...
class ConflictError(DomainError): ...

def translate_integrity_error(error: IntegrityError) -> DomainError:
    """ForeignKeyViolationError -> NotFoundError; UniqueViolationError -> ConflictError;
    demais IntegrityError -> DomainError. Inspecionar error.orig (asyncpg)."""
```

Repositories em `app/clinics/repositories/` (sem `BaseRepository` genérico — ADR 0003). Convenção: contexto é **sempre o primeiro parâmetro**; não existe método unscoped; leituras cross-tenant retornam `None` (a camada de API mapeará para 404 nos marcos seguintes):

- `ClinicRepository(session)`: `list_for_user(ctx: UserContext) -> Sequence[Clinic]` · `get(ctx: TenantContext) -> Clinic | None` · `update_legal_name(ctx: TenantContext, legal_name: str) -> Clinic | None` (atualiza `updated_at`)
- `MembershipRepository(session)`: `list_for_user(ctx: UserContext) -> Sequence[Membership]` · `list_for_clinic(ctx: TenantContext) -> Sequence[Membership]` · `get(ctx: TenantContext, membership_id: UUID) -> Membership | None`
- `ClinicSettingsRepository(session)`: `get(ctx: TenantContext) -> ClinicSettings | None` · `update(ctx: TenantContext, *, display_name: str | None = None, timezone: str | None = None, locale: str | None = None, currency: str | None = None) -> ClinicSettings | None`

```python
# app/clinics/feature_flags.py
class FeatureKey(StrEnum):
    """Registro central tipado. Começa VAZIO no M1.2; chaves novas exigem entrada aqui."""

class FeatureFlagService:
    def __init__(self, repository: FeatureFlagRepository) -> None: ...
    async def is_enabled(self, ctx: TenantContext, key: FeatureKey) -> bool:
        """Linha ausente ou flag desconhecida -> False (default desabilitado).
        Chave fora do enum é impossível em tempo de tipo (mypy strict)."""
```

`FeatureFlagRepository(session)`: `get_row(ctx: TenantContext, key: str) -> ClinicFeatureFlag | None`.

---

## Incremento M1.2.2 — Entidades estruturais

- [ ] **T1 — Bootstrap citext**
  - Modificar `infra/postgres/init/001-create-roles.sh`: adicionar `SELECT format('CREATE EXTENSION IF NOT EXISTS citext') \gexec` executado pelo admin no bloco SQL (antes dos GRANTs de schema).
  - Adicionar nota em `docs/implementation-divergences.md`: volumes locais criados antes do M1.2.2 precisam ser recriados (`docker compose ... down --volumes`) para obter a extensão — mesmo precedente da ADR 0004.
  - Verificar: `docker compose -f infra/docker-compose.yml down --volumes && docker compose -f infra/docker-compose.yml up -d --wait db` e `psql "$TEST_ADMIN_DATABASE_URL" -c "SELECT extname FROM pg_extension"` lista `citext`.

- [ ] **T2 — `app/users/models.py`** (`User` conforme tabela acima) + `app/users/__init__.py`
  - Teste `apps/api/tests/test_models.py`: metadata do `User` (tabela `app.users`, colunas, CK de status, unique de email).

- [ ] **T3 — `app/auth/models.py`** (7 tabelas globais restantes) + `app/auth/__init__.py`
  - Testes de metadata: FKs para `app.users`, UNIQUE de `token_hash`/`idempotency_key`, CKs de `purpose`/`status`, auto-FK de `auth_sessions.replaced_by_session_id`.

- [ ] **T4 — `app/clinics/models.py`** (6 tabelas tenant) + `app/clinics/__init__.py`
  - Testes de metadata: `UNIQUE(clinic_id, id)` em memberships/invitations, `ForeignKeyConstraint` composta de invitations, PK de `clinic_settings` (`clinic_id`) e de `clinic_feature_flags` (`clinic_id`,`key`), UNIQUE(`user_id`,`clinic_id`).
  - Garantir que todos os models sejam importados (via `app.auth.models`, `app.users.models`, `app.clinics.models`) antes de `Base.metadata` ser usado pelo Alembic — importar os módulos em `migrations/env.py` (linha única `from app import auth, clinics, users  # noqa: F401` ou equivalente nos `__init__`).

- [ ] **T5 — Migration `0002_global_identity`**
  - `uv run alembic revision --autogenerate -m "global identity tables"` → renomear revision para `0002_global_identity`, curar: adicionar os GRANTs de `0002` via `op.execute` (upgrade) e REVOKE+DROP (downgrade).
  - Criar `apps/api/tests/integration/conftest.py`: fixtures asyncpg para as 3 roles (admin/app/migrator) com skip se env ausente + helpers `seed_user(conn, ...)` reutilizáveis.
  - Teste de integração `test_global_identity_schema.py`: as 8 tabelas existem no schema `app`; app role consegue `SELECT/INSERT` em `users`; app role **não** consegue `DELETE` em `auth_audit_events` (append-only por grant).

- [ ] **T6 — Migration `0003_tenant_structure`** (mesmo fluxo: autogenerate → renomear → curar grants)
  - Teste de integração `test_tenant_structure_schema.py`: FK composta rejeita invitation com `(clinic_A, membership_de_B)` (via migrator, `asyncpg.ForeignKeyViolationError`); UNIQUE(`user_id`,`clinic_id`) rejeita duplicata; PK composta de flags funciona.

- [ ] **T7 — Docs + relatório M1.2.2**
  - `docs/architecture.md`: atualizar "Estado do M1.2.x"; `docs/data-model.md`: marcar tabelas como materializadas; `docs/security.md`: nota de que as tabelas ainda **não** têm RLS (D10).
  - Quality gate completo + `alembic check` limpo + `downgrade base`/`upgrade head` OK.
  - **Relatório ao usuário e AGUARDAR aprovação.** Declarar explicitamente a janela sem RLS (D10).

## Incremento M1.2.3 — TenantContext e RLS

- [ ] **T1 — ADR 0005** `docs/adr/0005-rls-policies-and-tenant-context.md` com D1–D5, D8, D9 e a matriz de policies por tabela (abaixo).

- [ ] **T2 — Migration `0004_rls_policies`**

Função (exata):

```sql
CREATE FUNCTION app.is_active_member() RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
  SELECT EXISTS (
    SELECT 1 FROM app.memberships m
    WHERE m.clinic_id::text = NULLIF(current_setting('app.current_clinic_id', true), '')
      AND m.user_id::text   = NULLIF(current_setting('app.current_user_id', true), '')
      AND m.status = 'ACTIVE'
  );
$$;
REVOKE ALL ON FUNCTION app.is_active_member() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.is_active_member() TO easydentist_app;
```

Para cada uma das 6 tabelas: `ALTER TABLE app.<t> ENABLE ROW LEVEL SECURITY;` + `ALTER TABLE app.<t> FORCE ROW LEVEL SECURITY;` + policies:

```sql
-- clinics
CREATE POLICY clinics_user_select ON app.clinics FOR SELECT TO easydentist_app
  USING (EXISTS (
    SELECT 1 FROM app.memberships m
    WHERE m.clinic_id = id
      AND m.user_id::text = NULLIF(current_setting('app.current_user_id', true), '')
      AND m.status = 'ACTIVE'));
CREATE POLICY clinics_tenant_update ON app.clinics FOR UPDATE TO easydentist_app
  USING (id::text = NULLIF(current_setting('app.current_clinic_id', true), '') AND app.is_active_member())
  WITH CHECK (id::text = NULLIF(current_setting('app.current_clinic_id', true), '') AND app.is_active_member());

-- memberships
CREATE POLICY memberships_user_select ON app.memberships FOR SELECT TO easydentist_app
  USING (user_id::text = NULLIF(current_setting('app.current_user_id', true), ''));
CREATE POLICY memberships_tenant_all ON app.memberships FOR ALL TO easydentist_app
  USING (clinic_id::text = NULLIF(current_setting('app.current_clinic_id', true), '') AND app.is_active_member())
  WITH CHECK (clinic_id::text = NULLIF(current_setting('app.current_clinic_id', true), '') AND app.is_active_member());

-- clinic_settings: SELECT + UPDATE tenant-scope (mesma forma, coluna clinic_id)
-- clinic_feature_flags: SELECT tenant-scope apenas
-- membership_invitations: SELECT + INSERT tenant-scope (INSERT: só WITH CHECK)
-- clinic_audit_events: SELECT + INSERT tenant-scope (append-only)

-- em TODAS as 6:
CREATE POLICY <tabela>_migrator_all ON app.<tabela> FOR ALL TO easydentist_migrator
  USING (true) WITH CHECK (true);
```

Downgrade: drop policies → drop function → disable RLS. Migration reversível (CI testa `downgrade base`).

- [ ] **T3 — `app/core/context.py`** (contrato acima) + testes unitários (frozen, slots, igualdade por valor).

- [ ] **T4 — `app/core/tenancy.py`** (contrato acima) + testes de integração: dentro de `tenant_transaction`, `current_setting('app.current_clinic_id', true)` retorna o valor; após commit, conexão reutilizada tem contexto vazio (ponte para a T3 do M1.2.5).

- [ ] **T5 — Suite fail-closed** (`tests/integration/test_rls_fail_closed.py`, app role via asyncpg):
  - sem GUCs: `SELECT` em cada uma das 6 tabelas retorna 0 linhas (seed prévio via migrator);
  - GUC com UUID de outra clínica/ usuário inexistente: 0 linhas;
  - `INSERT` em `clinic_settings` sem contexto: violação de `WITH CHECK` (`asyncpg.InsufficientPrivilegeError` ou `CheckViolationError` — afirmar o tipo real observado);
  - `EXECUTE` na função como migrator-negado: app role **pode** executar; verificar `prosecdef` e owner no catálogo (`pg_proc`/`pg_roles`): owner = `easydentist_migrator`, `rolsuper = false`.

- [ ] **T6 — Matriz de policies** (`tests/integration/test_rls_policies.py`): seed via migrator de 2 usuários, 2 clínicas, memberships cruzadas (user1 ACTIVE em A, user2 ACTIVE em B):
  - user1 com contexto de A: vê `clinics` = {A}, `memberships` user-scope = só as próprias, `memberships` tenant-scope (contexto A) = só membros de A;
  - user1 sem membership em B + contexto B: 0 linhas em todas as tenant-scoped;
  - app role não faz `UPDATE/DELETE` em `clinic_audit_events` (sem policy ⇒ default-deny) nem `UPDATE` em `clinic_feature_flags`;
  - `pg_policies` confere exatamente as policies planejadas (nomes, roles, comandos).

- [ ] **T7 — Docs + relatório M1.2.3**
  - `docs/security.md`: mover RLS/contexto transacional para implementado; referenciar ADR 0005. `docs/architecture.md`: estado.
  - Quality gate completo. **Relatório ao usuário e AGUARDAR aprovação.**

## Incremento M1.2.4 — Repositories e services

- [ ] **T1 — `app/core/errors.py`** (contrato acima) + testes unitários do `translate_integrity_error` com `IntegrityError` simulados.

- [ ] **T2 — `app/clinics/repositories/__init__.py` + `clinic_repository.py`** (`ClinicRepository`) + integração: seed via migrator; `list_for_user` retorna só clínicas do usuário; `get` cross-tenant ⇒ `None`; `update_legal_name` persiste e atualiza `updated_at`; update cross-tenant ⇒ `None` (0 linhas).
  - Convenção obrigatória: updates/deletes filtram por `id` **e** `clinic_id` (`plan.md` §3), mesmo com RLS ativo — defesa em camadas.

- [ ] **T3 — `membership_repository.py`** (`MembershipRepository`) + integração (mesmas propriedades).

- [ ] **T4 — `clinic_settings_repository.py`** + integração: `update` com kwargs parciais; defaults `America/Bahia`/`pt-BR`/`BRL` presentes no insert (seed) e respeitados.

- [ ] **T5 — `app/clinics/feature_flags.py`** (`FeatureKey` vazio, `FeatureFlagRepository`, `FeatureFlagService`) + integração: flag ausente ⇒ `False`; linha `enabled=true` ⇒ `True`; linha `enabled=false` ⇒ `False`; `config` lida quando presente. Teste unitário: `FeatureKey` é `StrEnum` e esvaziado (documentar que a primeira chave real exige migration de seed operacional, fora do M1.2).

- [ ] **T6 — Docs + relatório M1.2.4**
  - `docs/architecture.md`: repositories/tenant context no estado. Quality gate. **Relatório e AGUARDAR aprovação.**

## Incremento M1.2.5 — Prova de isolamento

- [ ] **T1 — Suíte duas clínicas** (`tests/integration/test_tenant_isolation.py`): fixtures `clinic_a`/`clinic_b` com usuários e memberships ACTIVE; para **cada** repository, ambas as direções: A não lê/altera B e vice-versa, **mesmo conhecendo UUIDs válidos da outra clínica** (critério do `plan.md` §5).

- [ ] **T2 — Abuso via SQL cru** (app role asyncpg, sem repositories):
  - `SET LOCAL app.current_clinic_id = '<clinic_b>'` dentro de transação com `app.current_user_id` de usuário sem membership em B ⇒ 0 linhas nas 4 tabelas tenant-scoped;
  - `UPDATE app.clinic_settings SET display_name='x' WHERE clinic_id='<b>'` com contexto de A ⇒ 0 linhas afetadas;
  - `DELETE FROM app.memberships WHERE clinic_id='<b>'` com contexto de A ⇒ 0 linhas;
  - RLS continua ativa contra consulta incorreta (sem `WHERE clinic_id`): só retorna linhas do contexto (critério do `plan.md` §5).

- [ ] **T3 — Pool interleaving** (`tests/integration/test_pool_tenant_leak.py`, engine SQLAlchemy real contra o banco):
  - abrir `tenant_transaction(A)` e `tenant_transaction(B)` concorrentemente (`asyncio.gather`), intercalar queries, cada uma vê apenas o próprio tenant;
  - após commit de ambas, adquirir nova sessão do pool e, **sem setar contexto**, `SELECT` em `clinic_settings` ⇒ 0 linhas (prova de que `is_local=True` não vaza para a conexão reutilizada).

- [ ] **T4 — FK cross-tenant limpa**: `INSERT` de invitation `(clinic_A, membership_de_B)` como app role com contexto de A ⇒ `IntegrityError`; `translate_integrity_error` ⇒ `NotFoundError` (não expõe existência do recurso). Teste unitário do mapeamento + integração da violação real.

- [ ] **T5 — Validação de migrations do zero**: script `scripts/verify-migrations.sh` (recreate volume → `upgrade head` → `alembic check` → `downgrade base` → `upgrade head`) espelhando o CI; documentar no README (seção de qualidade).

- [ ] **T6 — Relatório final M1.2**
  - `docs/security.md`: itens de M1.2 marcados como implementados; `docs/architecture.md`: "Estado do M1.2" final; `docs/implementation-divergences.md` se algo divergiu.
  - Quality gate completo + Compose válido.
  - **Relatório final: critério de aceite do `plan.md` — "uma segunda clínica não consegue acessar nenhum dado da primeira" — com evidência dos testes.**

## Self-review do plano (já executado)

- **Cobertura da spec:** `plan.md` §4 M1.2 — roles ✅ (M1.2.1), migrations globais+tenant-aware ✅ (M1.2.2), contexto transacional + RLS + FKs compostas ✅ (M1.2.2/M1.2.3), repositories exigindo `TenantContext` + interface tipada de feature flags ✅ (M1.2.4), isolamento com duas clínicas ✅ (M1.2.5). Critérios de `plan.md` §5 aplicáveis a M1.2 ✅ (fail-closed, SQL incorreto bloqueado, RLS sem contexto, cross-tenant com IDs conhecidos).
- **Sem placeholders:** todas as tabelas, constraints, grants, policies e assinaturas estão especificados acima.
- **Consistência de tipos:** `UserContext`/`TenantContext` (T3 do M1.2.3) → consumidos por `user_transaction`/`tenant_transaction` (T4) → repositories (M1.2.4) → suítes (M1.2.5). `translate_integrity_error` (T1 do M1.2.4) → usado na T4 do M1.2.5.
