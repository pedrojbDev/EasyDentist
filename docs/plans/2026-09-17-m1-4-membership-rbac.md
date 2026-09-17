# M1.4 — Membership e RBAC: Plano de Implementação

> **Para o agente executor:** implemente tarefa por tarefa, um incremento por vez. Passos usam checkbox (`- [ ]`). **Regra do `plan.md` §4:** ao final de cada incremento, apresente ao usuário o relatório de conclusão (arquivos e comportamentos implementados, comandos executados, resultados, pendências) e **aguarde aprovação antes de iniciar o incremento seguinte** — não haverá avanço silencioso. Este plano incorpora os quatro ajustes da revisão de pré-aprovação: serialização do último OWNER, senha opcional sem sobrescrever credencial existente, separação entre `invalid_role` e `not_permitted`, e permissão dedicada para expor e-mail de membros.

**Goal:** Membership e RBAC do Marco 1 — matriz papel × permissão default-deny em código, contexto tenant por requisição com membership revalidada, gestão de equipe (convite, troca de papel, remoção) via funções `SECURITY DEFINER` com guardas de último OWNER serializadas e promoção exclusiva de OWNER, convites de equipe com aceite de senha opcional (sem sobrescrever credencial existente), e os endpoints tenant-aware de clínica/equipe do §4.

**Spec:** `plan.md` §3 (RBAC inicial, Isolamento multi-tenant — fluxo obrigatório, Provisionamento), §4 (API pública — Tenancy), §5 (testes obrigatórios) · `docs/security.md` (RBAC) · `docs/adr/0003-solid-and-modular-boundaries.md` · `docs/adr/0005-rls-policies-and-tenant-context.md` · `docs/adr/0006-authentication-design.md`

**Tech stack:** sem dependências novas — Python 3.12.14 · FastAPI 0.141.1 · SQLAlchemy 2.0.44 async · Alembic 1.16.5 · pytest 9.0.3 (+anyio, httpx ASGI) · PostgreSQL 17 · `zoneinfo` (stdlib) para validação de timezone IANA.

**Estado pré-existente (M1.3 mergeado, `35919be`, 301 testes verdes):** 11 endpoints de auth + `/invitations/accept` (senha obrigatória); migrations `0001`–`0007` com RLS fail-closed, `is_active_member()`, `consume_rate_limit`, `provision_clinic_owner`/`consume_invitation` (que já revoga sessões ao trocar senha); `Principal` + `get_principal`/`require_csrf`; `MembershipRepository`/`ClinicRepository`/`ClinicSettingsRepository` tenant-aware (M1.2) sem rotas; `enforce_recovery_rate_limit` em `app/auth/routers.py`; outbox de e-mail + templates pt-BR.

## Global Constraints

- ADR 0003: routers só HTTP; services orquestram; repositories persistem; regras de domínio (RBAC) não importam FastAPI/SQLAlchemy; sem `BaseService`/`BaseRepository`.
- ADR 0005: a role runtime **não escreve** `memberships`/`clinics` — toda transição passa por função `SECURITY DEFINER` (dona `easydentist_migrator`, `search_path` fixo, `EXECUTE` só para app); transações tenant-aware sempre com GUCs `app.current_user_id`/`app.current_clinic_id`.
- Fluxo obrigatório do §3 em toda rota tenant-aware: `Principal` → `clinic_id` só da rota → membership `ACTIVE` → permissão do papel → `tenant_transaction` → RLS revalida. `clinic_id` nunca vem do body; cross-tenant sempre **404 genérico**.
- RBAC default-deny: permissões são constantes em código; permissão não declarada falha; **apenas OWNER promove/convide/remove OWNER e ADMIN**; último OWNER `ACTIVE` não é removido nem rebaixado, com serialização que impede dois OWNERs de se auto-rebaixarem/removerem simultaneamente.
- Sem JWT; mutações exigem CSRF (router-level); tokens sempre no corpo; links com fragmento `#token=`.
- mypy strict (`app`, `scripts`), ruff 100 colunas, documentação pt-BR; todo `.md` novo precisa passar em `prettier --check .` a partir da raiz (lição M1.2/M1.3 — o CI `web` roda `pnpm format:check`).
- Migrations: `0008_membership_management` reversível (downgrade restaura a `consume_invitation` v1 da 0007); emendas só pré-merge; qualificar `public.citext` nos DDL; `CREATE OR REPLACE` não serve para a `consume_invitation` (a assinatura muda) — usar DROP + CREATE + re-grant.
- Quality gate por incremento: `ruff check`/`format --check`, `mypy app scripts`, `pytest`, `alembic check`, Compose; relatório e **aguardar aprovação**.

### Comandos de referência

```sh
docker compose -f infra/docker-compose.yml up -d --wait db
docker compose -f infra/docker-compose.yml --profile tools run --rm migrate
export TEST_ADMIN_DATABASE_URL=postgresql://easydentist:easydentist-local-only@127.0.0.1:5433/easydentist
export TEST_APP_DATABASE_URL=postgresql://easydentist_app:easydentist-app-local-only@127.0.0.1:5433/easydentist
export TEST_MIGRATION_DATABASE_URL=postgresql://easydentist_migrator:easydentist-migrator-local-only@127.0.0.1:5433/easydentist
# gate (apps/api): ruff check/format --check · mypy app scripts · pytest (env acima) · alembic check
```

## Decisões travadas (viram ADR 0007)

| #   | Decisão                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| D1  | **Matriz em código, default-deny:** `app/clinics/rbac.py` com `Role`/`Permission` (`StrEnum`), `ROLE_PERMISSIONS: dict[Role, frozenset[Permission]]` e `role_allows(role, permission) -> bool`. No M1.4 declaram-se **apenas** as permissões dos endpoints existentes: `clinic:read`, `clinic:update-legal-name`, `settings:read`, `settings:update`, `memberships:read`, `memberships:read-contact`, `memberships:manage-role`, `memberships:remove`, `invitations:create`. Permissões clínicas (anamnese, prontuário, agenda…) são declaradas nos marcos que criarem os endpoints; nada fica liberado sem declaração.                                                                                             |
| D2  | **Leitura básica para todos os papéis ativos:** OWNER/ADMIN/DENTIST/ASSISTANT/RECEPTIONIST recebem `clinic:read`, `settings:read`, `memberships:read` (sem dados de contato). `memberships:read-contact` (e-mail completo dos membros), `settings:update`, `memberships:manage-role`, `memberships:remove` e `invitations:create` são OWNER/ADMIN. `clinic:update-legal-name` e tudo que tem OWNER ou ADMIN como **alvo** é exclusivo de OWNER.                                                                                                                                                                                                                                                                     |
| D3  | **Membership revalidada por requisição:** dependência `get_membership` (em `app/clinics/dependencies.py`) resolve `Principal` + `clinic_id` da rota, consulta a membership do usuário (via `user_transaction`, policy `memberships_user_select`) e devolve `ClinicMembership(context: TenantContext, role: Role)`; sem membership `ACTIVE` ⇒ **404 genérico** (anti-enumeração cross-tenant). Os repositories rodam em `tenant_transaction` com o contexto; RLS revalida.                                                                                                                                                                                                                                           |
| D4  | **Transições de equipe só em funções `SECURITY DEFINER`** (migration `0008`): `create_member_invitation`, `change_member_role`, `remove_membership` — cada uma valida internamente o papel do actor (fail-closed no banco, defesa em profundidade além do `role_allows`). Erros nomeados via `RAISE EXCEPTION`, mapeados no service: `not_permitted`→403, `last_owner`→409, `invalid_role`→422, `password_required`→422, `password_not_allowed`→422, `invitation_unusable`→400 genérico. `invalid_role` (papel desconhecido, erro do cliente) é sempre verificada e levantada **antes** das checagens de permissão do actor.                                                                                        |
| D5  | **Serialização do último OWNER:** `change_member_role` e `remove_membership` adquirem, **antes de qualquer lock de membership e antes da contagem**, `SELECT 1 FROM app.clinics c WHERE c.id = p_clinic_id FOR UPDATE` — um único ponto de lock por clínica, na mesma ordem para todos os concorrentes, eliminando deadlock e corrida de dois OWNERs se auto-rebaixando/removendo em paralelo (ambos contariam 2 owners e deixariam a clínica sem nenhum). Só então travam o alvo (`FOR UPDATE`), contam OWNERs `ACTIVE` e aplicam a guarda (`<= 1` ⇒ `last_owner`). `create_member_invitation` não precisa da guarda (só cria `PENDING`); corrida de convite duplicado cai no unique `(user_id, clinic_id)` ⇒ 409. |
| D6  | **Remoção de membership é DELETE físico**, com evento em `clinic_audit_events` (`membership.removed`): o unique `(user_id, clinic_id)` impede reconvite se a linha ficar `SUSPENDED`; o histórico vive na auditoria, não na constraint.                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| D7  | **Aceite com senha opcional, sem sobrescrever credencial existente:** `consume_invitation` v2 aceita `p_password_hash text` nullable com semântica exclusiva: (a) usuário **sem** credencial e **sem** senha ⇒ `password_required` (422); (b) usuário **sem** credencial e **com** senha ⇒ cria credencial, revoga todas as sessões e marca `email_verified_at` (semântica M1.3 preservada, regressão coberta); (c) usuário **com** credencial ⇒ ativa apenas a membership, **sem tocar em senha ou sessões** — e, se o cliente enviar senha mesmo assim, ⇒ `password_not_allowed` (422), rejeitando o campo explicitamente em vez de ignorar silenciosamente. Schema: `password: str                               | None = Field(default=None, min_length=12, max_length=128)`. |
| D8  | **Convite de equipe:** `POST /clinics/{id}/invitations` com rate limit compartilhado de recuperação (3/destinatário/h, 20/IP/h — `recovery_recipient`/`recovery_ip`, helper movido de `app/auth/routers.py` para `app/platform/rate_limit.py`), membership `PENDING` + invitation 72 h na mesma transação, e-mail outbox-first com template pt-BR `team-invitation` (nome da clínica, papel em pt-BR, fragmento `#token=`). Usuário já membro ⇒ 409 (`ConflictError` via unique).                                                                                                                                                                                                                                   |
| D9  | **PATCH /clinics/{id} só `legal_name`** (slug imutável no Marco 1); PATCH de settings aceita `display_name`/`timezone`/`locale`/`currency` opcionais; timezone validado contra `zoneinfo.available_timezones()` ⇒ 422.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| D10 | **Exposição de dados de contato:** `GET /clinics/{id}/memberships` devolve `id`, `user_id`, `role`, `status`, `created_at` para quem tem `memberships:read`; o campo `user.email` só é incluído quando o actor tem `memberships:read-contact` (OWNER/ADMIN). `GET /clinics` devolve clínica + `role` do próprio principal (seletor do M1.5) — e-mail do próprio usuário não é exposto aqui. Erros de autorização usam 403 (`PermissionDeniedError`, novo em `core/errors` + handler em `problems.py`).                                                                                                                                                                                                              |
| D11 | **Auditabilidade:** eventos de clínica em `clinic_audit_events` (`membership.invited`, `membership.role_changed`, `membership.removed`, `invitation.accepted`) com `actor_user_id` do principal; metadados **nunca** contêm token, senha, cookie ou IP bruto.                                                                                                                                                                                                                                                                                                                                                                                                                                                       |

## Contratos de código

```python
# app/clinics/rbac.py — domínio puro, sem FastAPI/SQLAlchemy
class Role(StrEnum):  # OWNER, ADMIN, DENTIST, ASSISTANT, RECEPTIONIST
    ...
class Permission(StrEnum):  # clinic:read, clinic:update-legal-name, settings:read,
    # settings:update, memberships:read, memberships:read-contact,
    # memberships:manage-role, memberships:remove, invitations:create
    ...
ROLE_PERMISSIONS: dict[Role, frozenset[Permission]]
def role_allows(role: Role, permission: Permission) -> bool: ...  # default deny

# app/clinics/dependencies.py
@dataclass(frozen=True, slots=True)
class ClinicMembership:
    context: TenantContext  # (user_id, clinic_id)
    role: Role

async def get_membership(
    clinic_id: UUID, principal: Principal, settings: AuthSettings,
    session_factory: async_sessionmaker[AsyncSession],
) -> ClinicMembership  # 404 genérico sem membership ACTIVE; cache em request.state

MembershipDep = Annotated[ClinicMembership, Depends(get_membership)]

# app/clinics/services.py — orquestra funções SECURITY DEFINER
class MembershipService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None: ...
    async def invite(self, context: TenantContext, *, email: str, role: str,
                     token: str) -> InvitedMember          # create_member_invitation
    async def change_role(self, context: TenantContext, *, membership_id: UUID,
                          new_role: str) -> None           # change_member_role
    async def remove(self, context: TenantContext, *, membership_id: UUID) -> None  # remove_membership

# app/auth/invitations.py — aceite estendido
class InvitationService:
    async def accept(self, *, token: str,
                     password: str | None = None) -> AcceptedInvitation | None

# app/platform/rate_limit.py — movido de app/auth/routers.py
async def enforce_recovery_rate_limit(
    request: Request, settings: AuthSettings,
    session_factory: async_sessionmaker[AsyncSession], identifier: str,
) -> None

# app/core/errors.py + app/platform/problems.py
class PermissionDeniedError(DomainError)  # → 403
```

## Migrations

**`0008_membership_management`** (reversível; downgrade recria a `consume_invitation` v1 da 0007):

```sql
-- v2: senha opcional, sem sobrescrever credencial existente (D7)
DROP FUNCTION app.consume_invitation(bytea, text);
CREATE FUNCTION app.consume_invitation(p_token_hash bytea, p_password_hash text)
RETURNS TABLE (user_id uuid, clinic_id uuid)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = app, pg_temp AS $$
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

  IF EXISTS (SELECT 1 FROM app.password_credentials pc
             WHERE pc.user_id = v_membership.user_id) THEN
    IF p_password_hash IS NOT NULL THEN
      RAISE EXCEPTION 'password_not_allowed';
    END IF;
  ELSE
    IF p_password_hash IS NULL THEN
      RAISE EXCEPTION 'password_required';
    END IF;
    INSERT INTO app.password_credentials (user_id, password_hash, changed_at)
      VALUES (v_membership.user_id, p_password_hash, v_now);
    UPDATE app.auth_sessions s SET revoked_at = v_now
      WHERE s.user_id = v_membership.user_id AND s.revoked_at IS NULL;
  END IF;

  UPDATE app.users u SET email_verified_at = v_now WHERE u.id = v_membership.user_id;
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

CREATE FUNCTION app.create_member_invitation(
  p_clinic_id uuid, p_actor_user_id uuid, p_email public.citext,
  p_role text, p_invitation_token_hash bytea
) RETURNS TABLE (membership_id uuid, invitation_id uuid, user_id uuid,
                 invitation_expires_at timestamptz)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = app, pg_temp AS $$
DECLARE
  v_actor_role text;
  v_user_id uuid;
  v_membership_id uuid;
  v_invitation_id uuid;
  v_expires_at timestamptz := now() + interval '72 hours';
BEGIN
  -- erro de cliente primeiro (ajuste 3 da revisão)
  IF p_role NOT IN ('OWNER','ADMIN','DENTIST','ASSISTANT','RECEPTIONIST') THEN
    RAISE EXCEPTION 'invalid_role';
  END IF;
  SELECT m.role INTO v_actor_role FROM app.memberships m
    WHERE m.clinic_id = p_clinic_id AND m.user_id = p_actor_user_id AND m.status = 'ACTIVE';
  IF v_actor_role IS NULL
     OR v_actor_role NOT IN ('OWNER','ADMIN')
     OR (p_role IN ('OWNER','ADMIN') AND v_actor_role <> 'OWNER') THEN
    RAISE EXCEPTION 'not_permitted';
  END IF;
  SELECT u.id INTO v_user_id FROM app.users u WHERE u.email = p_email;
  IF v_user_id IS NULL THEN
    INSERT INTO app.users (email) VALUES (p_email) RETURNING id INTO v_user_id;
  END IF;
  INSERT INTO app.memberships (clinic_id, user_id, role, status)
    VALUES (p_clinic_id, v_user_id, p_role, 'PENDING') RETURNING id INTO v_membership_id;
  INSERT INTO app.membership_invitations
    (clinic_id, membership_id, email, token_hash, expires_at)
    VALUES (p_clinic_id, v_membership_id, p_email, p_invitation_token_hash, v_expires_at)
    RETURNING id INTO v_invitation_id;
  INSERT INTO app.clinic_audit_events (clinic_id, actor_user_id, event_type, entity_type, entity_id)
    VALUES (p_clinic_id, p_actor_user_id, 'membership.invited', 'membership', v_membership_id);
  RETURN QUERY SELECT v_membership_id, v_invitation_id, v_user_id, v_expires_at;
END;
$$;

CREATE FUNCTION app.change_member_role(
  p_clinic_id uuid, p_actor_user_id uuid, p_membership_id uuid, p_new_role text
) RETURNS TABLE (membership_id uuid, old_role text, new_role text)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = app, pg_temp AS $$
DECLARE
  v_target app.memberships%ROWTYPE;
  v_actor_role text;
  v_owner_count int;
BEGIN
  IF p_new_role NOT IN ('OWNER','ADMIN','DENTIST','ASSISTANT','RECEPTIONIST') THEN
    RAISE EXCEPTION 'invalid_role';
  END IF;
  -- serialização por clínica ANTES de qualquer lock de membership (ajuste 1 da revisão)
  PERFORM 1 FROM app.clinics c WHERE c.id = p_clinic_id FOR UPDATE;
  SELECT * INTO v_target FROM app.memberships m
    WHERE m.id = p_membership_id AND m.clinic_id = p_clinic_id FOR UPDATE;
  SELECT m.role INTO v_actor_role FROM app.memberships m
    WHERE m.clinic_id = p_clinic_id AND m.user_id = p_actor_user_id AND m.status = 'ACTIVE';
  IF v_target.id IS NULL OR v_actor_role IS NULL OR v_target.status <> 'ACTIVE'
     OR v_actor_role NOT IN ('OWNER','ADMIN')
     OR ((v_target.role IN ('OWNER','ADMIN') OR p_new_role IN ('OWNER','ADMIN'))
         AND v_actor_role <> 'OWNER')
     OR (v_actor_role = 'ADMIN' AND v_target.role = 'ADMIN') THEN
    RAISE EXCEPTION 'not_permitted';
  END IF;
  IF v_target.role = 'OWNER' AND p_new_role <> 'OWNER' THEN
    SELECT count(*) INTO v_owner_count FROM app.memberships m
      WHERE m.clinic_id = p_clinic_id AND m.role = 'OWNER' AND m.status = 'ACTIVE';
    IF v_owner_count <= 1 THEN
      RAISE EXCEPTION 'last_owner';
    END IF;
  END IF;
  UPDATE app.memberships m SET role = p_new_role, updated_at = now() WHERE m.id = v_target.id;
  INSERT INTO app.clinic_audit_events (clinic_id, actor_user_id, event_type, entity_type, entity_id)
    VALUES (p_clinic_id, p_actor_user_id, 'membership.role_changed', 'membership', v_target.id);
  RETURN QUERY SELECT v_target.id, v_target.role, p_new_role;
END;
$$;

CREATE FUNCTION app.remove_membership(
  p_clinic_id uuid, p_actor_user_id uuid, p_membership_id uuid
) RETURNS TABLE (membership_id uuid)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = app, pg_temp AS $$
DECLARE
  v_target app.memberships%ROWTYPE;
  v_actor_role text;
  v_owner_count int;
BEGIN
  -- serialização por clínica ANTES de qualquer lock de membership (ajuste 1 da revisão)
  PERFORM 1 FROM app.clinics c WHERE c.id = p_clinic_id FOR UPDATE;
  SELECT * INTO v_target FROM app.memberships m
    WHERE m.id = p_membership_id AND m.clinic_id = p_clinic_id FOR UPDATE;
  SELECT m.role INTO v_actor_role FROM app.memberships m
    WHERE m.clinic_id = p_clinic_id AND m.user_id = p_actor_user_id AND m.status = 'ACTIVE';
  IF v_target.id IS NULL OR v_actor_role IS NULL
     OR v_actor_role NOT IN ('OWNER','ADMIN')
     OR (v_target.role IN ('OWNER','ADMIN') AND v_actor_role <> 'OWNER') THEN
    RAISE EXCEPTION 'not_permitted';
  END IF;
  IF v_target.role = 'OWNER' AND v_target.status = 'ACTIVE' THEN
    SELECT count(*) INTO v_owner_count FROM app.memberships m
      WHERE m.clinic_id = p_clinic_id AND m.role = 'OWNER' AND m.status = 'ACTIVE';
    IF v_owner_count <= 1 THEN
      RAISE EXCEPTION 'last_owner';
    END IF;
  END IF;
  DELETE FROM app.membership_invitations i WHERE i.membership_id = v_target.id;
  DELETE FROM app.memberships m WHERE m.id = v_target.id;
  INSERT INTO app.clinic_audit_events (clinic_id, actor_user_id, event_type, entity_type, entity_id)
    VALUES (p_clinic_id, p_actor_user_id, 'membership.removed', 'membership', v_target.id);
  RETURN QUERY SELECT v_target.id;
END;
$$;

REVOKE ALL ON FUNCTION app.consume_invitation(bytea, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.consume_invitation(bytea, text) TO easydentist_app;
REVOKE ALL ON FUNCTION app.create_member_invitation(uuid, uuid, public.citext, text, bytea) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.create_member_invitation(uuid, uuid, public.citext, text, bytea) TO easydentist_app;
REVOKE ALL ON FUNCTION app.change_member_role(uuid, uuid, uuid, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.change_member_role(uuid, uuid, uuid, text) TO easydentist_app;
REVOKE ALL ON FUNCTION app.remove_membership(uuid, uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.remove_membership(uuid, uuid, uuid) TO easydentist_app;
-- downgrade: DROP das quatro + recriação da consume_invitation v1 (cópia fiel da 0007)
```

## Endpoints (prefixo `/api/v1`; todos exigem sessão; mutações exigem CSRF)

| #   | Rota                                                    | Permissão                  | Body                                             | Sucesso                                                       | Erros                   |
| --- | ------------------------------------------------------- | -------------------------- | ------------------------------------------------ | ------------------------------------------------------------- | ----------------------- |
| 1   | GET /clinics                                            | membership `ACTIVE`        | —                                                | 200 `[{id, slug, legal_name, status, role}]`                  | 401                     |
| 2   | GET /clinics/{clinic_id}                                | `clinic:read`              | —                                                | 200 clínica                                                   | 401; 404                |
| 3   | PATCH /clinics/{clinic_id}                              | `clinic:update-legal-name` | `{legal_name}`                                   | 200                                                           | 401; 403; 404; 422      |
| 4   | GET /clinics/{clinic_id}/settings                       | `settings:read`            | —                                                | 200 settings                                                  | 401; 404                |
| 5   | PATCH /clinics/{clinic_id}/settings                     | `settings:update`          | `{display_name?, timezone?, locale?, currency?}` | 200                                                           | 401; 403; 404; 422      |
| 6   | GET /clinics/{clinic_id}/memberships                    | `memberships:read`         | —                                                | 200 lista (com `user.email` só p/ `memberships:read-contact`) | 401; 404                |
| 7   | PATCH /clinics/{clinic_id}/memberships/{membership_id}  | `memberships:manage-role`  | `{role}`                                         | 200                                                           | 401; 403; 404; 409; 422 |
| 8   | DELETE /clinics/{clinic_id}/memberships/{membership_id} | `memberships:remove`       | —                                                | 204                                                           | 401; 403; 404; 409      |
| 9   | POST /clinics/{clinic_id}/invitations                   | `invitations:create`       | `{email, role}`                                  | 202 `{membership_id, invitation_expires_at}`                  | 401; 403; 404; 409; 429 |
| 10  | POST /invitations/accept (estendido)                    | —                          | `{token, password?}`                             | 204                                                           | 400; 422                |

## Incrementos e tarefas

### Incremento M1.4.1 — Fundação RBAC

- [ ] **T1 — ADR 0007** `docs/adr/0007-membership-rbac.md` com D1–D11 (incluindo os quatro ajustes da revisão: serialização do último OWNER, senha opcional sem sobrescrever credencial, separação `invalid_role`/`not_permitted`, `memberships:read-contact`) e a matriz papel × permissão do M1.4.
- [ ] **T2 — `app/clinics/rbac.py`** (`Role`, `Permission`, `ROLE_PERMISSIONS`, `role_allows` default-deny) + `tests/test_rbac.py` **parametrizado** (§5: todos os papéis × todas as 9 permissões, positivo e negativo; papel desconhecido e permissão não declarada ⇒ `False`).
- [ ] **T3 — `PermissionDeniedError`** em `core/errors.py` + handler 403 em `platform/problems.py` + teste em `test_problems.py`.
- [ ] **T4 — Docs + gate + relatório (AGUARDAR aprovação).**

### Incremento M1.4.2 — Contexto tenant e leitura

- [ ] **T1 — `app/clinics/dependencies.py`** (`get_membership`: `user_transaction` + membership `ACTIVE` ⇒ `ClinicMembership`; 404 genérico; cache em `request.state`) + integração: membro ativo resolve; não-membro/membro de outra clínica/`PENDING`/`SUSPENDED` ⇒ 404 idêntico ao de clínica inexistente.
- [ ] **T2 — Router `app/clinics/routers.py`** (`/clinics` e `/clinics/{clinic_id}`, CSRF via `require_csrf`) + `GET /clinics` (lista com `role`, via `ClinicRepository.list_for_user`) + testes: duas clínicas/dois papéis; membership revogada entre chamadas ⇒ 404 imediato (membership revalidada por requisição — §3/§5).
- [ ] **T3 — Docs + gate + relatório (AGUARDAR aprovação).**

### Incremento M1.4.3 — Clínica e settings

- [ ] **T1 — `GET/PATCH /clinics/{clinic_id}`** (PATCH só `legal_name`, permissão OWNER; `ClinicRepository.update_legal_name`) + `GET /clinics/{clinic_id}/settings` (`settings:read`).
- [ ] **T2 — `PATCH settings`** com validação `zoneinfo` (timezone inválido ⇒ 422; `currency` com 3 letras) + **matriz de integração por papel** (positivo/negativo dos 5 papéis em cada endpoint; cross-tenant 404 com IDs válidos do outro tenant).
- [ ] **T3 — Docs + gate + relatório (AGUARDAR aprovação).**

### Incremento M1.4.4 — Migration 0008 e gestão de equipe

- [ ] **T1 — Migration `0008`** (SQL acima) + `alembic check` + ciclo downgrade/upgrade (downgrade restaura a `consume_invitation` v1 e derruba as três novas).
- [ ] **T2 — `MembershipService`** (invite/change_role/remove chamando as funções; mapeamento `not_permitted`→403, `last_owner`→409, `invalid_role`→422) + `GET /clinics/{id}/memberships` (com `user.email` condicional a `memberships:read-contact` — DENTIST/ASSISTANT/RECEPTIONIST recebem só `id`, `user_id`, `role`, `status`, `created_at`) + `PATCH`/`DELETE` membership + integração: OWNER promove/demove; **ADMIN não promove OWNER nem toca ADMIN (403)**; último OWNER não rebaixado/removido (409); remoção com efeito imediato (próxima requisição 404); reconvite após remoção funciona; dois DELETE concorrentes do mesmo vínculo ⇒ 1×204 + 1×404; auditoria `membership.role_changed`/`membership.removed`.
- [ ] **T3 — Testes concorrentes do último OWNER (ajuste 1 da revisão):** dois OWNERs se auto-rebaixando simultaneamente ⇒ **exatamente 1×200 + 1×409** (nunca 500/deadlock, nunca clínica sem OWNER); duas remoções concorrentes dos dois OWNERs ⇒ 1×204 + 1×409; ao final, a clínica sempre conserva ≥ 1 OWNER `ACTIVE`.
- [ ] **T4 — Docs + gate + relatório (AGUARDAR aprovação).**

### Incremento M1.4.5 — Convites de equipe e aceite

- [ ] **T1 — `POST /clinics/{id}/invitations`** (rate limit 3/destinatário/h + 20/IP/h — helper movido para `app/platform/rate_limit.py`; usuário já membro ⇒ 409; papel inválido ⇒ 422; e-mail `team-invitation` outbox-first com papel pt-BR e fragmento) + testes por papel e de rate limit.
- [ ] **T2 — `POST /invitations/accept` com `password` opcional** (`consume_invitation` v2; `InvitationService.accept(token, password=None)`) + integração: novo usuário define senha (verifica e-mail, revoga sessões — semântica M1.3 preservada); usuário existente ativa **sem trocar senha e mantendo sessões**; usuário existente que envia senha ⇒ 422 (`password_not_allowed` — ajuste 2 da revisão); usuário novo sem senha ⇒ 422 (`password_required`); expirado/reuso ⇒ 400 genérico; dois accepts concorrentes ⇒ 1 sucesso; regressão: fluxo OWNER do M1.3 segue verde.
- [ ] **T3 — Docs + gate + relatório (AGUARDAR aprovação).**

### Incremento M1.4.6 — Prova de autorização

- [ ] **T1 — Matriz §5 consolidada** (`tests/integration/test_rbac_matrix.py`): todos os papéis × endpoints 1–9 (positivo/negativo); cross-tenant 404 para todos os papéis com IDs válidos; efeito imediato de troca de papel/revogação; `memberships:read-contact` negado a DENTIST/ASSISTANT/RECEPTIONIST (e-mail ausente na resposta); redaction (audit de clínica sem token/senha/cookie/IP); último OWNER e "ADMIN não promove OWNER" reexecutados na matriz.
- [ ] **T2 — `./scripts/verify-migrations.sh`** (0001→0008 em banco descartável) + Compose completo + `verify-compose-health.sh`.
- [ ] **T3 — Docs finais** (`security.md` RBAC implementado; `architecture.md` estado M1.4; `implementation-divergences.md` se aplicável) + gate completo.
- [ ] **T4 — Relatório final do M1.4** com evidência dos testes do §5.

## Self-review

- **Cobertura da spec:** §3 fluxo obrigatório 1–8 (M1.4.2 + RLS existente); default-deny + matriz parametrizada (M1.4.1); apenas OWNER promove OWNER e último OWNER protegido com serialização à prova de corrida (M1.4.4, guardas no banco e no service); `clinic_id` só da rota e 404 cross-tenant (M1.4.2/3/6); §4 — 10 rotas de Tenancy mapeadas (accept estendido); §5 — matriz unitária e de integração, permissões negativas por papel, cross-tenant para todos os papéis, efeito imediato de papel/revogação, redaction.
- **Ajustes da revisão incorporados:** (1) lock da linha da clínica antes de qualquer lock de membership nos dois pontos de transição de OWNER + testes concorrentes dedicados em M1.4.4/T3; (2) `consume_invitation` v2 rejeita senha quando já existe credencial (`password_not_allowed`→422) em vez de sobrescrever; (3) `invalid_role` verificada antes das checagens de permissão e mapeada a 422 em todas as funções que recebem papel; (4) `memberships:read-contact` (OWNER/ADMIN) como única fonte de `user.email` na lista de membros.
- **Fora do escopo (explícito):** restrições clínicas de RECEPTIONIST/ASSISTANT/ADMIN (anamnese/prontuário/assinaturas) — dependem dos endpoints clínicos dos marcos seguintes e serão testadas lá; campo `name` de usuário ainda não existe no modelo; Playwright (M1.6); feature flags continuam sem endpoints.
- **Coerência:** nenhuma escrita direta em `memberships` pela role runtime (D4/D5); `consume_invitation` v2 preserva a semântica M1.3 para novos usuários (regressão coberta em M1.4.5/T2); `membership_invitations`/`clinic_audit_events` seguem com INSERT permitido à role via policy, mas transições de vínculo só nas funções.
- **Riscos mapeados:** `CREATE OR REPLACE` não serve (assinatura muda) ⇒ DROP+CREATE com re-grant; downgrade da 0008 precisa da cópia fiel da v1; lock clínica→alvo em ordem fixa elimina deadlock; a política `clinics_tenant_update` (RLS) não interfere porque as funções rodam como `easydentist_migrator` (policy permissiva).
