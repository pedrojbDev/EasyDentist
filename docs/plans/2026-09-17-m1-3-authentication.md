# M1.3 — Autenticação: Plano de Implementação

> **Para o agente executor:** implemente tarefa por tarefa, um incremento por vez. Passos usam checkbox (`- [ ]`). **Regra do `plan.md` §4:** ao final de cada incremento, apresente ao usuário o relatório de conclusão (arquivos e comportamentos implementados, comandos executados, resultados, pendências) e **aguarde aprovação antes de iniciar o incremento seguinte** — não haverá avanço silencioso.

**Goal:** Autenticação local completa do Marco 1 — Argon2id, sessões opacas com cookies, CSRF signed double-submit, rate limiting atômico em PostgreSQL, verificação de e-mail, recuperação de senha, provisionamento de clínicas e aceite do convite OWNER — com o contrato `Authenticator` desacoplado da autorização.

**Spec:** `plan.md` §3 (Autenticação, CSRF, Verificação e recuperação, Rate limiting, Provisionamento inicial), §4 (API pública do Marco 1), §5 (testes obrigatórios) · `docs/security.md` · `docs/adr/0003-solid-and-modular-boundaries.md` · `docs/adr/0005-rls-policies-and-tenant-context.md`

**Tech stack:** Python 3.12.14 · FastAPI 0.141.1 · SQLAlchemy 2.0.44 async · asyncpg 0.30.0 · Alembic 1.16.5 · pytest 9.0.3 (+anyio) · httpx (testes de endpoint via ASGI) · PostgreSQL 17 · **nova dependência: `argon2-cffi`** (MIT — verificada contra `ALLOWED_LICENSES` de `apps/api/scripts/check_licenses.py`; `argon2-cffi-bindings` MIT, `cffi` MIT, `pycparser` BSD)

**Estado pré-existente (M1.2 mergeado, `53f34e2`):** as 8 tabelas globais de auth já criadas (`users`, `password_credentials`, `external_identities`, `auth_sessions`, `auth_action_tokens`, `auth_rate_limit_buckets`, `auth_audit_events`, `email_outbox`) com grants por finalidade; `UserContext`/`TenantContext` + transações com GUCs; `translate_integrity_error`; infra de testes (3 roles asyncpg, `seeded_tenants`, helpers); `scripts/verify-migrations.sh` descartável; CI verde. `create_app()` é mínimo (sem engine/settings/lifespan — cabe ao M1.3.1).

## Global Constraints

- ADR 0003: routers só HTTP; services orquestram; repositories persistem; **sem** `BaseService`/`BaseRepository` genéricos; regras de domínio não importam FastAPI/SQLAlchemy.
- **Sem JWT**; sem cadastro público; `external_identities` permanece vazio (OIDC futuro). Tokens **sempre no corpo**, nunca na rota; links usam **fragmento de URL**.
- Repositories de auth são **globais** (parâmetro `user_id` explícito) — **não usam** `ensure_context_matches` (guard exclusivo dos tenant-repositories do M1.2).
- mypy strict (`app`, `scripts`), ruff 100 colunas, documentação pt-BR.
- **Gotcha Prettier (lição M1.2):** todo `.md` novo precisa passar em `prettier --check .` a partir da raiz — o Prettier 3 respeita `.gitignore` e ignora `.worktrees/`; validar em clone limpo ou a partir da raiz.
- Migrations: `0005_auth_indexes`, `0006_rate_limit_function`, `0007_invitation_functions`; reversíveis; emendas só pré-merge; **qualificar `public.citext` nos DDL** de funções (o `search_path` delas é `app, pg_temp`).
- Quality gate por incremento: `ruff check`/`format --check`, `mypy app scripts`, `pytest`, `alembic check`, Compose; relatório e **aguardar aprovação**.

### Comandos de referência

```sh
docker compose -f infra/docker-compose.yml up -d --wait db
docker compose -f infra/docker-compose.yml --profile tools run --rm migrate
export TEST_ADMIN_DATABASE_URL=postgresql://easydentist:easydentist-local-only@127.0.0.1:5433/easydentist
export TEST_APP_DATABASE_URL=postgresql://easydentist_app:easydentist-app-local-only@127.0.0.1:5433/easydentist
export TEST_MIGRATION_DATABASE_URL=postgresql://easydentist_migrator:easydentist-migrator-local-only@127.0.0.1:5433/easydentist
# gate (apps/api): ruff check/format --check · mypy app scripts · pytest (env acima) · alembic check
# CLI de provisionamento (M1.3.5):
#   uv run python -m app.auth.provision --email a@b.c --name "Clínica X" --slug clinica-x --timezone America/Bahia
```

## Decisões travadas (viram ADR 0006)

| #   | Decisão                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| D1  | **`Authenticator` como `Protocol`** (port, ADR 0003): `LocalPasswordAuthenticator` (verifica Argon2id) + fake nos testes de contrato. `Principal(user_id, session_id, auth_method)` é tudo que a autorização conhece.                                                                                                                                                                                                                                                                                         |
| D2  | **`APP_ENV`** (`development`/`production`): dev usa `easydent_session`/`easydent_csrf` (sem `Secure`); produção `__Host-easydent_session`/`__Host-easydent_csrf` (`Secure`); sessão `HttpOnly`, CSRF legível; `Path=/`, sem `Domain`, `SameSite=Lax`; `Max-Age` = TTL absoluto (30d). Produção **falha no boot** sem `AUTH_SECRET` ≥ 32 bytes.                                                                                                                                                                |
| D3  | **CSRF signed double-submit:** valor = `token ‧ HMAC-SHA256(AUTH_SECRET, "csrf:" ‖ binding)`, binding = `session_id` (autenticado) ou `anonymous`. `GET /auth/csrf` emite cookie anônimo; pós-login reemite **vinculado à sessão**. Toda mutação valida header == cookie + assinatura + `Origin`/`Referer` na allowlist (**ausência de ambos rejeita**).                                                                                                                                                      |
| D4  | **`AUTH_SECRET`** único para HMAC de CSRF e chaves de rate limit; dev default em `.env.example`; nunca em logs.                                                                                                                                                                                                                                                                                                                                                                                               |
| D5  | **Rate limit atômico:** função `app.consume_rate_limit` (upsert `ON CONFLICT` — serializa por chave). **Consume pré-autenticação** em toda tentativa de login (bloqueia mesmo sob concorrência); **sucesso limpa o bucket da conta** (senha correta reseta falhas). Janela 15min; **backoff progressivo** `30·2^(excedentes)`s, teto 15min; `Retry-After` no 429. Limites do plano: login 5/conta/15min e 20/IP/15min; recuperação/reenvio 3/destinatário/h e 20/IP/h. Chaves = `HMAC(kind ‖ identificador)`. |
| D6  | **Anti-enumeração:** respostas genéricas e indistinguíveis em login, forgot, resend, confirm e aceite de convite.                                                                                                                                                                                                                                                                                                                                                                                             |
| D7  | **E-mail outbox-first:** linha em `email_outbox` na mesma transação da ação; tentativa pós-commit com `attempt_count`/`next_attempt_at`; `EmailSender` Protocol + `smtplib`/`asyncio.to_thread` (sem dependência nova; Mailpit no dev); `idempotency_key` semântico (ex. `invitation:{id}`); retries no próximo enqueue.                                                                                                                                                                                      |
| D8  | **Escrita de `memberships`/`clinics` só via funções `SECURITY DEFINER`** (dona `easydentist_migrator`, `search_path` fixo, `EXECUTE` só para app) — `provision_clinic_owner` e `consume_invitation`; consistente com o lockdown do ADR 0005. A CLI roda com credenciais da API (app role). Slug existente ⇒ erro limpo (`ConflictError`); usuário reutilizado idempotentemente.                                                                                                                               |
| D9  | **Aceite de convite não faz login automático** (mesma semântica do reset); consumo do token é **atômico** (`SELECT … FOR UPDATE` + guarda `accepted_at IS NULL`).                                                                                                                                                                                                                                                                                                                                             |
| D10 | **Senhas 12–128 caracteres, sem regras de composição**; Argon2id v19, 64 MiB, t=3, **p=1**, salt 16B, hash 32B; **rehash transparente no login** quando parâmetros mudarem.                                                                                                                                                                                                                                                                                                                                   |
| D11 | **Problem Details (RFC 9457)** com `request_id` (middleware + header `X-Request-Id`) em todos os erros da API; títulos pt-BR.                                                                                                                                                                                                                                                                                                                                                                                 |
| D12 | **Auditoria mínima:** `login_succeeded`, `login_failed`, `logout`, `session_revoked`, `password_reset_completed`, `email_verified`, `invitation_accepted`, `rate_limit_triggered` — metadados **nunca** contêm senha, token, cookie ou IP bruto (IP vive só HMAC'd nos buckets).                                                                                                                                                                                                                              |
| D13 | **Sessões:** login sempre cria sessão nova (outros dispositivos permanecem); reset revoga **todas**; `touch` (≥ 5min) deslza `idle_expires_at`; expiradas são resolvidas lazy (sem jobs); `replaced_by_session_id` fica reservado para uso futuro.                                                                                                                                                                                                                                                            |
| D14 | **`GET /auth/me` = só identidade** (`id`, `email`, `email_verified_at`, `status`); memberships vêm com `GET /clinics` no M1.4. Sem endpoints de feature flags.                                                                                                                                                                                                                                                                                                                                                |

## Contratos de código

```python
# app/auth/principal.py
@dataclass(frozen=True, slots=True)
class Principal:
    user_id: UUID
    session_id: UUID
    auth_method: str  # "password"

# app/auth/authenticator.py
class Authenticator(Protocol):
    async def authenticate(self, email: str, password: str) -> UUID | None: ...

# app/auth/passwords.py — argon2-cffi PasswordHasher(t=3, memory=65536, p=1, salt_len=16, hash_len=32)
class PasswordHasher:
    def hash(self, password: str) -> str: ...
    def verify_and_rehash(self, password: str, password_hash: str) -> tuple[bool, str | None]: ...

# app/auth/tokens.py
def generate_token() -> str: ...            # secrets.token_urlsafe(32) → 256 bits base64url
def token_digest(token: str) -> bytes: ...  # sha256 → bytea (única forma persistida)
def tokens_match(a: bytes, b: bytes) -> bool: ...  # hmac.compare_digest

# app/auth/settings.py — fail-fast: produção exige AUTH_SECRET ≥ 32 bytes
@dataclass(frozen=True, slots=True)
class AuthSettings:
    app_env: str
    auth_secret: bytes
    session_cookie_name: str
    csrf_cookie_name: str
    cookie_secure: bool
    session_idle_ttl: timedelta          # 12h
    session_absolute_ttl: timedelta      # 30d
    last_seen_throttle: timedelta        # 5min
    argon2_time_cost: int                # 3
    argon2_memory_kib: int               # 65536
    argon2_parallelism: int              # 1
    trusted_proxies: tuple[str, ...]
    allowed_origins: tuple[str, ...]
    smtp_host: str
    smtp_port: int
    smtp_sender: str
    public_base_url: str
    @classmethod
    def from_environment(cls, environment=None) -> AuthSettings: ...

# app/auth/csrf.py
class CsrfService:
    def issue(self, binding: str) -> str: ...           # "token.assinatura"
    def verify(self, value: str, binding: str) -> bool: ...

# app/auth/ratelimit.py — chaves: HMAC-SHA256(secret, kind ‖ identificador)
@dataclass(frozen=True, slots=True)
class RateDecision:
    allowed: bool
    retry_after_seconds: int
class RateLimiter:
    async def consume(self, kind: str, identifier: str, limit: int, window_seconds: int) -> RateDecision: ...
    async def clear(self, kind: str, identifier: str) -> None: ...

# app/auth/emails.py — smtplib + asyncio.to_thread (sem dependência nova)
class EmailSender(Protocol):
    async def send(self, recipient: str, subject: str, body: str) -> None: ...

# app/auth/sessions.py
class SessionService:
    async def create(self, user_id: UUID) -> tuple[UUID, str]: ...   # (session_id, token)
    async def resolve(self, token: str) -> Principal | None: ...     # valida revogado/idle/absoluto
    async def touch_if_due(self, session_id: UUID) -> None: ...      # ≥5min; deslza idle
    async def revoke(self, user_id: UUID, session_id: UUID) -> bool: ...
    async def revoke_all(self, user_id: UUID) -> None: ...

# app/auth/action_tokens.py — consumo single-use atômico
class ActionTokenService:
    async def issue(self, purpose: str, user_id: UUID, ttl: timedelta) -> str: ...
    async def consume(self, purpose: str, token: str) -> UUID | None: ...

# app/auth/cookies.py — nomes/flags por APP_ENV (D2)
def set_session_cookie(response, token, settings) -> None: ...
def clear_session_cookie(response, settings) -> None: ...
def set_csrf_cookie(response, value, settings) -> None: ...

# app/platform/problems.py — RFC 9457 + request_id (middleware, X-Request-Id)
```

## Migrations

**`0005_auth_indexes`** (M1.3.2 — índices, reversível):

```python
op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"], schema="app")
op.create_index("ix_auth_action_tokens_user_id", "auth_action_tokens", ["user_id"], schema="app")
op.create_index("ix_email_outbox_delivery", "email_outbox", ["status", "next_attempt_at"], schema="app")
# downgrade: drop_index na ordem inversa
```

**`0006_rate_limit_function`** (M1.3.3 — upsert atômico; backoff progressivo):

```sql
CREATE FUNCTION app.consume_rate_limit(
  p_bucket_key bytea, p_max_attempts int, p_window_seconds int
) RETURNS TABLE (allowed boolean, retry_after_seconds int)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
DECLARE
  v_row app.auth_rate_limit_buckets%ROWTYPE;
  v_now timestamptz := now();
BEGIN
  INSERT INTO app.auth_rate_limit_buckets AS b
    (bucket_key, attempt_count, window_started_at, blocked_until)
  VALUES (p_bucket_key, 1, v_now, NULL)
  ON CONFLICT (bucket_key) DO UPDATE SET
    attempt_count = CASE
      WHEN b.window_started_at < v_now - make_interval(secs => p_window_seconds) THEN 1
      ELSE b.attempt_count + 1
    END,
    window_started_at = CASE
      WHEN b.window_started_at < v_now - make_interval(secs => p_window_seconds) THEN v_now
      ELSE b.window_started_at
    END,
    blocked_until = CASE
      WHEN (CASE
             WHEN b.window_started_at < v_now - make_interval(secs => p_window_seconds) THEN 1
             ELSE b.attempt_count + 1
           END) > p_max_attempts
      THEN v_now + least(
             make_interval(secs => 30 * power(2, b.attempt_count - p_max_attempts)),
             interval '15 minutes')
      ELSE b.blocked_until
    END
  RETURNING * INTO v_row;

  IF v_row.blocked_until IS NOT NULL AND v_row.blocked_until > v_now THEN
    RETURN QUERY SELECT false, ceil(extract(epoch FROM (v_row.blocked_until - v_now)))::int;
  END IF;
  RETURN QUERY SELECT true, 0;
END;
$$;
REVOKE ALL ON FUNCTION app.consume_rate_limit(bytea, int, int) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.consume_rate_limit(bytea, int, int) TO easydentist_app;
-- downgrade: DROP FUNCTION app.consume_rate_limit(bytea, int, int)
```

**`0007_invitation_functions`** (M1.3.5 — escrita de memberships/clinics só aqui; D8):

```sql
CREATE FUNCTION app.provision_clinic_owner(
  p_email public.citext, p_name text, p_slug public.citext,
  p_timezone text, p_invitation_token_hash bytea
) RETURNS TABLE (user_id uuid, clinic_id uuid, invitation_expires_at timestamptz)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
DECLARE
  v_user_id uuid; v_clinic_id uuid; v_membership_id uuid;
  v_expires_at timestamptz := now() + interval '72 hours';
BEGIN
  SELECT u.id INTO v_user_id FROM app.users u WHERE u.email = p_email;
  IF v_user_id IS NULL THEN
    INSERT INTO app.users (email) VALUES (p_email) RETURNING id INTO v_user_id;
  END IF;
  INSERT INTO app.clinics (slug, legal_name, status)
    VALUES (p_slug, p_name, 'PROVISIONING') RETURNING id INTO v_clinic_id;
  INSERT INTO app.clinic_settings (clinic_id, display_name, timezone)
    VALUES (v_clinic_id, p_name, p_timezone);
  INSERT INTO app.memberships (clinic_id, user_id, role, status)
    VALUES (v_clinic_id, v_user_id, 'OWNER', 'PENDING') RETURNING id INTO v_membership_id;
  INSERT INTO app.membership_invitations (clinic_id, membership_id, email, token_hash, expires_at)
    VALUES (v_clinic_id, v_membership_id, p_email, p_invitation_token_hash, v_expires_at);
  INSERT INTO app.clinic_audit_events (clinic_id, actor_user_id, event_type, entity_type, entity_id)
    VALUES (v_clinic_id, v_user_id, 'clinic.provisioned', 'clinic', v_clinic_id);
  RETURN QUERY SELECT v_user_id, v_clinic_id, v_expires_at;
END;
$$;

CREATE FUNCTION app.consume_invitation(
  p_token_hash bytea, p_password_hash text
) RETURNS TABLE (user_id uuid, clinic_id uuid)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
DECLARE
  v_invitation app.membership_invitations%ROWTYPE;
  v_membership app.memberships%ROWTYPE;
  v_now timestamptz := now();
BEGIN
  SELECT * INTO v_invitation FROM app.membership_invitations i
    WHERE i.token_hash = p_token_hash FOR UPDATE;
  IF v_invitation.id IS NULL OR v_invitation.accepted_at IS NOT NULL
     OR v_invitation.expires_at <= v_now THEN
    RAISE EXCEPTION 'invitation_unusable';
  END IF;
  SELECT * INTO v_membership FROM app.memberships m WHERE m.id = v_invitation.membership_id;
  UPDATE app.users u SET email_verified_at = v_now WHERE u.id = v_membership.user_id;
  INSERT INTO app.password_credentials (user_id, password_hash, changed_at)
    VALUES (v_membership.user_id, p_password_hash, v_now)
    ON CONFLICT (user_id) DO UPDATE
      SET password_hash = EXCLUDED.password_hash, changed_at = EXCLUDED.changed_at;
  UPDATE app.memberships m SET status = 'ACTIVE', updated_at = v_now WHERE m.id = v_membership.id;
  UPDATE app.clinics c SET status = 'ACTIVE', updated_at = v_now
    WHERE c.id = v_invitation.clinic_id AND c.status = 'PROVISIONING';
  UPDATE app.membership_invitations i SET accepted_at = v_now, updated_at = v_now
    WHERE i.id = v_invitation.id;
  INSERT INTO app.clinic_audit_events (clinic_id, actor_user_id, event_type, entity_type, entity_id)
    VALUES (v_invitation.clinic_id, v_membership.user_id, 'invitation.accepted', 'membership',
            v_membership.id);
  RETURN QUERY SELECT v_membership.user_id, v_invitation.clinic_id;
END;
$$;
REVOKE ALL ON FUNCTION app.provision_clinic_owner(public.citext, text, public.citext, text, bytea) FROM PUBLIC;
GRANT EXECUTE  ON FUNCTION app.provision_clinic_owner(public.citext, text, public.citext, text, bytea) TO easydentist_app;
REVOKE ALL ON FUNCTION app.consume_invitation(bytea, text) FROM PUBLIC;
GRANT EXECUTE  ON FUNCTION app.consume_invitation(bytea, text) TO easydentist_app;
-- downgrade: DROP FUNCTION IF EXISTS nas duas, ordem inversa
```

## Endpoints (prefixo `/api/v1`)

| #   | Rota                                  | Auth | CSRF    | Body              | Sucesso                                                   | Erros                         |
| --- | ------------------------------------- | ---- | ------- | ----------------- | --------------------------------------------------------- | ----------------------------- |
| 1   | POST /auth/login                      | —    | anônimo | {email, password} | 200 {user} + cookies sessão/CSRF                          | 401 genérico; 429+Retry-After |
| 2   | GET /auth/csrf                        | —    | —       | —                 | 200 {csrf_token} + cookie                                 | —                             |
| 3   | POST /auth/logout                     | sim  | sim     | —                 | 204 + limpa cookies                                       | 401                           |
| 4   | POST /auth/logout-all                 | sim  | sim     | —                 | 204 (revoga todas)                                        | 401                           |
| 5   | GET /auth/me                          | sim  | —       | —                 | 200 {id, email, email_verified_at, status}                | 401                           |
| 6   | GET /auth/sessions                    | sim  | —       | —                 | 200 [{id, created_at, last_seen_at, expires_at, current}] | 401                           |
| 7   | DELETE /auth/sessions/{id}            | sim  | sim     | —                 | 204 (limpa cookie se atual)                               | 401; 404 genérico             |
| 8   | POST /auth/email-verification/resend  | sim  | sim     | —                 | 202 sempre                                                | 429                           |
| 9   | POST /auth/email-verification/confirm | —    | sim     | {token}           | 204                                                       | 400 genérico                  |
| 10  | POST /auth/password/forgot            | —    | sim     | {email}           | 202 sempre                                                | 429                           |
| 11  | POST /auth/password/reset             | —    | sim     | {token, password} | 204 + revoga todas                                        | 400 genérico; 422 senha       |
| 12  | POST /invitations/accept              | —    | sim     | {token, password} | 204                                                       | 400 genérico; 422 senha       |

## Incrementos e tarefas

### Incremento M1.3.1 — Fundação

- [x] **T1 — ADR 0006** `docs/adr/0006-authentication-design.md` com D1–D14 e a matriz de eventos de auditoria.
- [x] **T2 — Dependência argon2-cffi**: `uv add argon2-cffi` (pin da versão estável corrente em `pyproject.toml` + `uv.lock`); `uv run python scripts/check_licenses.py` e `uv run pip-audit` verdes; registrar na `docs/compatibility-matrix.md` conforme ADR 0001.
- [x] **T3 — `app/auth/settings.py`** (`AuthSettings.from_environment`, fail-fast em produção) + envs novas em `infra/.env.example` (valores de dev) e no serviço `api` do `infra/docker-compose.yml` (`AUTH_SECRET`, `APP_ENV`, `PUBLIC_BASE_URL`, `ALLOWED_ORIGINS`, `SMTP_SENDER`) + testes unitários (default dev, produção sem segredo falha, segredo fraco rejeitado).
- [x] **T4 — `app/auth/passwords.py`** + `tests/test_passwords.py` (parâmetros v19 no hash, verify ok/falha, rehash detectado, limites 12–128 na borda do service).
- [x] **T5 — `app/auth/tokens.py`** + `tests/test_tokens.py` (256 bits, digest 32 bytes, comparação tempo constante).
- [x] **T6 — `app/platform/problems.py` + middleware `request_id` + handlers** (401/404/409/422/429/500 → RFC 9457 com `X-Request-Id`) + `tests/test_problems.py`.
- [x] **T7 — Wiring `create_app`**: engine + `session_factory` em `app.state`, lifespan com `dispose()`, injeção para testes; `GET /health` segue verde via `httpx ASGITransport`.
- [x] **T8 — `app/auth/emails.py`** (`EmailSender` Protocol, `SmtpEmailSender`, `EmailOutboxService` com deliver pós-commit e retry) + **`app/auth/audit.py`** (`AuthAuditService.record`) + testes unitários (fake sender; transições PENDING→SENT/FAILED com `attempt_count`/`next_attempt_at`).
- [x] **T9 — Docs + gate + relatório**: `docs/architecture.md` e `docs/security.md` (estado), quality gate completo. **Relatório ao usuário e AGUARDAR aprovação.**

### Incremento M1.3.2 — Sessões e login

- [x] **T1 — Migration `0005_auth_indexes`** (SQL acima) + `alembic check` limpo + ciclo downgrade/upgrade.
- [x] **T2 — Repositories globais** (`app/auth/repositories/session_repository.py`, `password_credential_repository.py`; `app/users/repositories/user_repository.py`) + testes de integração (padrão transacional rollback).
- [x] **T3 — `app/auth/authenticator.py`**: Protocol + `LocalPasswordAuthenticator` (busca por email, `verify_and_rehash` com persistência do rehash) + testes de contrato com provider local **e** fake.
- [x] **T4 — `app/auth/sessions.py`** + integração: criação, resolução válida → `Principal`, touch com throttle 5min deslizando idle, expiração idle/absoluta, reuso após revogação, revogar-todas.
- [x] **T5 — `app/auth/cookies.py`** + unit: nomes/flags por `APP_ENV` (dev sem `Secure`; produção `__Host-` + `Secure` + `Max-Age`).
- [x] **T6 — Dependência `get_principal` + routers** (`app/auth/routers.py`: endpoints 1, 3–7; registro em `application.py`) + fixtures `api_client` (env `DATABASE_URL` derivada de `TEST_APP_DATABASE_URL` asyncpg, `AUTH_SECRET` de teste, `ALLOWED_ORIGINS=http://testserver`) e `clean_auth_state` (limpa tabelas globais de auth **e buckets** entre testes via migrator; e-mails únicos por teste) + integração: round-trip de cookie, login cria sessão nova sem revogar outro dispositivo, revogação remota ⇒ 401, logout-all, lista de sessões sem tokens, 401 genérico sem cookie, eventos de auditoria.
- [x] **T7 — Docs + gate + relatório (AGUARDAR aprovação).**

### Incremento M1.3.3 — CSRF e rate limiting

- [x] **T1 — `app/auth/csrf.py`** (`CsrfService`: issue/verify com bindings `anonymous`/session; HMAC D3/D4) + unit.
- [x] **T2 — `GET /auth/csrf`**: cookie anônimo + token no corpo; reemissão vinculada à sessão pós-login; testes.
- [x] **T3 — Enforcement em mutações** (dependência nos routers; POST/PUT/PATCH/DELETE): header == cookie, assinatura válida para o binding atual, `Origin`/`Referer` na allowlist (ausência rejeita) + **matriz de rejeição** em integração (sem header, sem cookie, mismatch, assinatura inválida, origin estranha, sem origin/referer, GET isento).
- [x] **T4 — Migration `0006_rate_limit_function`** + `RateLimiter` + integração: **concorrência determinística** (10 falhas simultâneas ⇒ exatamente 5×401 e 5×429), backoff progressivo cresce entre bloqueios, janela expirada reseta contagem, bloqueio persiste na janela nova.
- [x] **T5 — Wiring login** (consume pré-autenticação conta+IP; sucesso limpa bucket da conta; 429 com `Retry-After`; audit `rate_limit_triggered`) + testes de lockout por conta e por IP. _Parcial: os limites de recuperação/reenvio (`RECOVERY_\*`prontos em`app/auth/ratelimit.py`) ficam para o M1.3.4, quando os endpoints 8–11 existirem.\_
- [x] **T6 — Resolução de IP do cliente** (`TRUSTED_PROXIES`; `X-Forwarded-For` aceito só de proxies confiáveis, senão endereço do socket) + unit.
- [x] **T7 — Docs + gate + relatório (AGUARDAR aprovação).**

### Incremento M1.3.4 — Verificação e recuperação

- [ ] **T1 — `app/auth/action_tokens.py`** (24h verificação / 30min reset; consumo single-use atômico) + integração (expirado, reusado, dois consumes concorrentes ⇒ 1 sucesso).
- [ ] **T2 — Endpoints 8–11** + testes de anti-enumeração (login com email inexistente vs senha errada indistinguíveis; forgot sempre 202; confirm/reset com mensagens genéricas).
- [ ] **T3 — Reset completo:** consome token, upsert de credencial, revoga **todas** as sessões, sem auto-login; rehash no login quando parâmetros mudarem; testes.
- [ ] **T4 — Templates pt-BR** (links `{PUBLIC_BASE_URL}/...#token=`) + outbox (`idempotency_key` semântico; deliver pós-commit; retry com backoff) + testes com fake sender.
- [ ] **T5 — Docs + gate + relatório (AGUARDAR aprovação).**

### Incremento M1.3.5 — Provisionamento e aceite

- [ ] **T1 — Migration `0007_invitation_functions`** (SQL acima; dona `easydentist_migrator`; `EXECUTE` só para app; reversível).
- [ ] **T2 — `ProvisionService` + CLI `python -m app.auth.provision`** (`--email`, `--name`, `--slug`, `--display-name` opcional, `--timezone` default `America/Bahia`; gera token 256-bit, chama `provision_clinic_owner`, enfileira e envia o convite; imprime **só metadados** — nunca o token) + integração: usuário (reutilizado se existir), clínica `PROVISIONING`, settings, membership OWNER `PENDING`, invitation 72h, audit `clinic.provisioned`; slug duplicado ⇒ `ConflictError`.
- [ ] **T3 — `POST /invitations/accept`** (token+senha no corpo) → `consume_invitation` + integração: feliz (membership `ACTIVE`, clínica `ACTIVE`, `email_verified_at` preenchido, credencial criada, token consumido, audit `invitation.accepted`), expirado/reusado ⇒ 400 genérico **com estado intacto**, senha fraca ⇒ 422, **dois accepts concorrentes ⇒ exatamente 1 sucesso**.
- [ ] **T4 — E-mail do convite** (72h, fragmento, nome da clínica no template) + testes.
- [ ] **T5 — Docs + gate + relatório (AGUARDAR aprovação).**

### Incremento M1.3.6 — Prova de segurança

- [ ] **T1 — Matriz §5** (`tests/integration/test_auth_security_matrix.py`): banco contém **só hashes** (`auth_sessions.token_hash` == sha256 do token emitido; `password_hash` é string Argon2; nada de token bruto em coluna); flags de cookie por ambiente; expiração idle/absoluta; token reusado/expirado/revogado ⇒ 401; sessões concorrentes de dois dispositivos OK; rotação no login; anti-enumeração login/forgot; matriz CSRF completa; rate limit atômico sob concorrência.
- [ ] **T2 — Redaction:** handler capturando logs + inspeção de `event_metadata` — nenhuma senha, token, cookie ou IP bruto em logs ou auditoria.
- [ ] **T3 — Contrato do `Authenticator`** passa igualmente com provider local e fake (conformidade do Protocol).
- [ ] **T4 — `./scripts/verify-migrations.sh`** (Compose descartável) + Compose completo + docs finais (`security.md` itens M1.3 implementados; `architecture.md` estado; `implementation-divergences.md` se necessário).
- [ ] **T5 — Relatório final do M1.3** com evidência dos testes do §5.

## Self-review

- **Cobertura da spec:** os 12 endpoints do §4 mapeados ✔; parâmetros exatos do §3 (Argon2id, sessões, cookies, CSRF, rate limiting, verificação/recuperação, provisionamento) ✔; itens do §5 aplicáveis distribuídos pelos incrementos e consolidados no M1.3.6 ✔; M1.4 (convites de equipe/papéis), M1.5 (frontend) e M1.6 (Playwright e2e) explicitamente fora do escopo ✔.
- **Coerência com o M1.2:** nenhuma escrita direta em `memberships`/`clinics` pela role runtime — D8 via funções `SECURITY DEFINER` contorna o bloqueio de RLS do aceite (`is_active_member()` é falso enquanto `PENDING`, então a função roda como dona com a policy permissiva do migrator); repositories globais não usam o guard de tenant (documentado).
- **Lição do M1.2 embutida:** Prettier/gitignore nas docs, migrations reversíveis por incremento, scripts não destrutivos, docs de estado por incremento, teste de concorrência determinístico.
