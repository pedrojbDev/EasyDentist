# M1.5 — Frontend operacional: Plano de Implementação

> **Para o agente executor:** implemente tarefa por tarefa, um incremento por vez. Passos usam checkbox (`- [ ]`). **Regra do `plan.md` §4:** ao final de cada incremento, apresente ao usuário o relatório de conclusão (arquivos e comportamentos implementados, comandos executados, resultados, pendências) e **aguarde aprovação antes de iniciar o incremento seguinte**. Este plano incorpora as decisões da pré-aprovação: testes de componente com RTL/jsdom agora (Playwright no M1.6), OpenAPI commitado com verificação de drift no CI, Tailwind v4 + shadcn sob demanda (sem copiar OpenDentist) e gestão de sessões incluída — além dos quatro ajustes da revisão: separação entre cliente browser e server-side, logouts individual e global distintos, contrato de `ApiError` completo (com validação de campo no frontend e 422 genérico) e preservação do token em memória após limpar o fragmento.

**Goal:** Frontend operacional do Marco 1 — login, recuperação, verificação de e-mail e aceite de convite, seletor de clínica baseado em `GET /clinics`, gestão de clínica/settings/equipe/convites/sessões conforme a matriz de papéis, consumindo a API same-origin com tipos gerados do OpenAPI e erguido sobre a fundação Next 15 + Tailwind v4 + shadcn já existente.

**Spec:** `plan.md` §1 (topologia same-origin, OpenAPI como fonte do contrato), §3 (Sessões/CSRF/anti-enumeração, clínica ativa na rota, RBAC), §4 (API pública), §5 (testes) · `docs/architecture.md` · `docs/compatibility-matrix.md` · ADRs 0002 (monorepo/serviços), 0003 (fronteiras), 0006 (auth), 0007 (RBAC)

**Tech stack:** já existente — Node 24.19.0 · pnpm 11.10.0 · Next.js 15.5.25 (App Router, `typedRoutes`, rewrite `/api/v1/:path*` → `API_INTERNAL_BASE_URL`) · React 19.2.7 · Tailwind CSS 4.1.17 + shadcn (new-york/neutral, `components/ui`) · TypeScript 5.9.3 · Vitest 4.1.11 · Lucide. **Novas devDependencies (MIT, sujeitas ao gate de licenças/audit):** `jsdom`, `@testing-library/react`, `@testing-library/user-event`, `openapi-typescript`. Sem dependência de estado global, sem i18n framework, sem MSW.

**Estado pré-existente:** M1.3 e M1.4 mergeados apoiados em `4585184` (API com 11 endpoints de auth + 10 de tenancy, migrations até `0008`, 415 testes, matriz RBAC provada). `apps/web` tem layout/page mínimos, `/health` com teste, `Button` shadcn, `cn()` com teste, `vitest.config.ts` (environment `node`), `src/lib/api/generated/README.md` como placeholder do cliente, e o job `web` do CI roda lint, format:check, typecheck, test, build, licenses e audit.

## Global Constraints

- **Nenhum componente do OpenDentist será copiado** (§4/M1.5). Somente shadcn (base já licenciada) e código próprio; pt-BR em toda a interface.
- O contrato é o OpenAPI do FastAPI: nada de duplicar tipos à mão; `openapi.json` + `schema.d.ts` gerados e commitados, com verificação de drift no CI (job `api` exporta e compara; job `web` regenera e exige diff vazio).
- Topologia same-origin: o browser fala sempre `/api/v1/...` (rewrite do Next); nunca `NEXT_PUBLIC_*` de API; sessão em cookie `HttpOnly`, CSRF em cookie legível + header `X-CSRF-Token` obtido via `GET /auth/csrf` antes de cada mutação.
- **Dois clientes distintos:** `client.ts` (browser: URL relativa, cookies automáticos, CSRF) e `server-client.ts` (Server Components: `API_INTERNAL_BASE_URL`, encaminhamento **explícito e restrito** do header `Cookie` da requisição, `cache: "no-store"`, sem CSRF em GET). Nenhum outro header recebido é encaminhado indiscriminadamente.
- Clínica ativa **na rota** (`/clinics/{clinicId}/...`), nunca como autorização implícita; a UI esconde/desabilita ações sem permissão usando o `role` de `GET /clinics`, mas **o backend continua a autoridade** (403/404 tratados).
- Tokens de convite/verificação/reset **somente em fragmento de URL** (`#token=`): lidos para o estado do componente, fragmento limpo com `history.replaceState` **depois** de guardar o token em memória (para permitir nova tentativa após erro de rede) e estado limpo apenas após sucesso definitivo. Nunca em query string ou logs.
- **Validação de campo no frontend** (o backend remove detalhes de 422): formulários validam antes do submit; 422 da API vira mensagem genérica. `password_required` não tem `code` estável no Problem Details — a tela orienta genericamente sem afirmar a causa exata (adicionar `code` à API é mudança de backend, fora do M1.5).
- `pnpm build` não pode depender da API no ar: nenhuma página faz fetch em tempo de build (usar client components para dados, ou `dynamic = 'force-dynamic'` nos layouts autenticados que validam sessão).
- Testes: RTL + jsdom para componente/estado, fetch stubbado (sem MSW); **Playwright fica no M1.6**. Suíte web precisa continuar verde sem banco/API.
- Gate por incremento: `pnpm lint`, `pnpm format:check`, `pnpm build`, `pnpm typecheck`, `pnpm test`, `pnpm run licenses`, `pnpm run audit` (com `typedRoutes`, o build gera os tipos de rota exigidos pelo typecheck); relatório e **aguardar aprovação**.

### Comandos de referência

```sh
# API local para desenvolvimento manual
docker compose -f infra/docker-compose.yml up -d --wait db
docker compose -f infra/docker-compose.yml --profile tools run --rm migrate
docker compose -f infra/docker-compose.yml up -d --wait api web
# frontend
pnpm --filter @easydentist/web dev        # http://localhost:3000
pnpm lint && pnpm format:check && pnpm build && pnpm typecheck && pnpm test
# contrato
uv run --project apps/api python -m scripts.export_openapi            # escreve o JSON
uv run --project apps/api python -m scripts.export_openapi --check    # verifica drift
pnpm gen:api                                                          # regenera schema.d.ts
```

## Decisões travadas (viram ADR 0008)

| #   | Decisão                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| D1  | **Rotas (App Router, `typedRoutes`):** públicas `/login`, `/forgot-password`, `/reset-password`, `/verify-email`, `/accept-invitation` (os quatro últimos compatíveis com os links de e-mail do M1.3/4, token só no fragmento); autenticadas `/` → redirect `/clinics`, `/clinics`, `/clinics/{clinicId}`, `/clinics/{clinicId}/settings`, `/clinics/{clinicId}/members`, `/sessions`. Inglês nas rotas, pt-BR na interface.                                                |
| D2  | **Cliente browser** `src/lib/api/client.ts`: `fetch` com URL relativa same-origin e cookies automáticos, `Content-Type: application/json`, parse de Problem Details (RFC 9457) em `ApiError` tipada, `X-CSRF-Token` obtido de `GET /api/v1/auth/csrf` imediatamente antes de cada mutação, `retryAfter` lido do header `Retry-After` quando presente. Nenhum token persistido em JS.                                                                                        |
| D3  | **Cliente server-side** `src/lib/api/server-client.ts` (Server Components/layouts): base `API_INTERNAL_BASE_URL`, encaminha **somente** o header `Cookie` da requisição recebida (via `cookies()` do Next, montando a string explicitamente), `cache: 'no-store'`, sem CSRF (usa apenas GET), `ApiError` compartilhada com o cliente browser. Não repassa nenhum outro header do usuário.                                                                                   |
| D4  | **Contrato gerado:** `apps/api/scripts/export_openapi.py` (novo; `create_app().openapi()`, sem lifespan/DB; `--check` compara com o arquivo) grava `apps/web/src/lib/api/generated/openapi.json`; `openapi-typescript` gera `schema.d.ts` via script `pnpm gen:api`. Ambos commitados; CI falha por drift.                                                                                                                                                                  |
| D5  | **Guarda de sessão no servidor:** layout do grupo autenticado é server component que chama `GET /auth/me` pelo `server-client` e faz `redirect('/login')` em 401; páginas autenticadas usam `export const dynamic = 'force-dynamic'`. O cliente browser também trata 401 globalmente (limpa estado e volta ao login).                                                                                                                                                       |
| D6  | **Papel da UI espelha a matriz** (`GET /clinics` → `role`): OWNER vê `legal_name`, convite de OWNER/ADMIN, troca/remoção de qualquer papel; ADMIN vê settings, convites e gestão de não-OWNER/ADMIN; demais papéis só leitura. Estados 403/404/409/422/429 sempre tratados com mensagem pt-BR, incluindo o tempo de espera no 429.                                                                                                                                          |
| D7  | **Fragmento de URL:** `/verify-email`, `/reset-password` e `/accept-invitation` leem o token do fragmento **primeiro para o estado**, limpam o hash com `history.replaceState` em seguida e mantêm o token apenas em memória para reenvio após erro de rede; o estado é limpo após sucesso definitivo. Envio do token sempre no corpo.                                                                                                                                      |
| D8  | **Componentes shadcn sob demanda** (locais em `components/ui`, MIT/ISC): `input`, `label`, `card`, `alert`, `badge`, `table`, `dialog`, `select`, `separator`, `dropdown-menu` conforme necessidade real de cada incremento; `Button` existente reutilizado. Acessibilidade mínima obrigatória: `<label>` associado, `aria-invalid`/mensagens de erro, foco no primeiro erro, `aria-live` para feedbacks.                                                                   |
| D9  | **Sessões e logout com semânticas distintas:** header tem **"Sair"** (`POST /auth/logout`, revoga somente a sessão atual) e **"Sair de todos os dispositivos"** (`POST /auth/logout-all`, com diálogo de confirmação). `/sessions` lista as sessões (`id`, `created_at`, `last_seen_at`, `expires_at`, `current`), permite revogar outro dispositivo (404 tratado) **e também a sessão atual** (com confirmação, redirecionando ao login); `logout-all` também aparece ali. |
| D10 | **Erros e validação:** `ApiError { status, title, detail?, requestId?, retryAfter? }`; validações de campo (senha 12–128, e-mail, timezone) são do frontend antes do submit; 422 da API → mensagem genérica ("Verifique os dados e tente novamente"), pois o backend não devolve detalhes por campo; anti-enumeração mantida (forgot/login com mensagens genéricas); sem alegar causa exata de `password_required` (sem `code` estável na API).                             |
| D11 | **Estado e dados:** server components buscam dados iniciais pelo `server-client`; interações usam client components com `useState`/`useTransition` e o cliente browser; revalidação por `router.refresh()` após mutações. Sem TanStack Query/Redux, sem i18n framework, sem service worker e sem dark mode (tema claro com as CSS variables existentes); strings pt-BR no código.                                                                                           |

## Contratos de código

```ts
// src/lib/api/problem.ts
export class ApiError extends Error {
  status: number;
  title: string;
  detail?: string;
  requestId?: string;
  retryAfter?: number;
}
export function apiErrorFrom(response: Response, body: unknown): ApiError;

// src/lib/api/client.ts  (browser: relative URL, cookies, CSRF)
export async function apiFetch<T>(
  path: string,
  init?: RequestInit & { json?: unknown },
): Promise<T>;
export async function apiFetchVoid(
  path: string,
  init?: RequestInit & { json?: unknown },
): Promise<void>;
export async function csrfHeaders(): Promise<Record<string, string>>; // GET /auth/csrf → X-CSRF-Token

// src/lib/api/server-client.ts  (Server Components: internal base URL, Cookie forwarding, no-store, GET only)
export async function serverFetch<T>(path: string): Promise<T>; // encaminha somente Cookie; 401 → ApiError

// src/lib/api/generated/schema.d.ts  (gerado; não editar à mão)

// src/features/auth/api.ts        login, logout, logoutAll, me, forgot, reset, verifyEmail, resendVerification
// src/features/clinics/api.ts     listClinics, getClinic, updateClinic, getSettings, updateSettings
// src/features/members/api.ts     listMembers, changeRole, removeMember, inviteMember
// src/features/sessions/api.ts    listSessions, revokeSession

// src/features/auth/components/LoginForm.tsx / ForgotPasswordForm.tsx / ResetPasswordForm.tsx
// src/features/auth/components/VerifyEmailPanel.tsx / AcceptInvitationForm.tsx
// src/features/clinics/components/ClinicSwitcher.tsx / ClinicSettingsForm.tsx / LegalNameForm.tsx
// src/features/members/components/MembersTable.tsx / InviteMemberForm.tsx
// src/features/sessions/components/SessionsTable.tsx
```

## Endpoints consumidos (21)

| Tela                                  | Endpoints                                                                                        |
| ------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `/login`, logout individual e global  | `POST /auth/login`, `POST /auth/logout`, `POST /auth/logout-all`, `GET /auth/me`                 |
| `/forgot-password`, `/reset-password` | `POST /auth/password/forgot`, `POST /auth/password/reset`                                        |
| `/verify-email`                       | `POST /auth/email-verification/confirm`, `GET /auth/me`                                          |
| `/accept-invitation`                  | `POST /invitations/accept`, `GET /auth/me`                                                       |
| `/clinics` (seletor)                  | `GET /clinics`                                                                                   |
| `/clinics/{id}`, settings             | `GET /clinics/{id}`, `PATCH /clinics/{id}`, `GET/PATCH /clinics/{id}/settings`                   |
| `/clinics/{id}/members`               | `GET/PATCH/DELETE /clinics/{id}/memberships[...]`, `POST /clinics/{id}/invitations`              |
| `/sessions`                           | `GET /auth/sessions`, `DELETE /auth/sessions/{id}`, `POST /auth/logout`, `POST /auth/logout-all` |
| Mutações (todas)                      | `GET /auth/csrf`                                                                                 |

**Migrations:** não aplicável (marco de frontend); o artefato versionado é o contrato (`openapi.json` + `schema.d.ts`).

## Incrementos e tarefas

### Incremento M1.5.1 — Fundação do cliente e contrato

- [ ] **T1 — ADR 0008** `docs/adr/0008-frontend-operacional.md` com D1–D11 (incluindo os quatro ajustes da revisão: dois clientes, logouts distintos, `ApiError` completo com validação no frontend, token em memória após limpar o fragmento).
- [ ] **T2 — Export e tipos:** `apps/api/scripts/export_openapi.py` (+ teste; `create_app().openapi()` sem DB; `--check` para drift), `openapi-typescript` no `apps/web` + script `gen:api`; `openapi.json` e `schema.d.ts` commitados substituindo o README placeholder; passos de CI (job `api`: `--check`; job `web`: `pnpm gen:api && git diff --exit-code apps/web/src/lib/api/generated`).
- [ ] **T3 — Clientes HTTP (TDD com fetch stubado):** `problem.ts` (`ApiError` com `status/title/detail?/requestId?/retryAfter?`, `retryAfter` do header), `client.ts` (sucesso JSON, 204, Problem Details, `csrfHeaders()`, erro de rede) e `server-client.ts` (base `API_INTERNAL_BASE_URL`, encaminha só o `Cookie`, `no-store`, 401 → `ApiError`).
- [ ] **T4 — Setup de testes de componente:** `jsdom` + `@testing-library/react` + `@testing-library/user-event`; ambiente jsdom por arquivo (mantendo os testes `node` existentes); smoke com `Button` (clique + `vi.fn`). Licenças/audit verdes.
- [ ] **T5 — Docs + gate + relatório (AGUARDAR aprovação).**

### Incremento M1.5.2 — Login, guarda de sessão e seletor de clínica

- [ ] **T1 — `/login`** (form e-mail/senha com validação de campo, estado de carregando, 401 genérico, 429 com tempo de espera) + redirect pós-login para `/clinics`; layout autenticado `(app)` com guarda server-side (`GET /auth/me` pelo `server-client` + `redirect`), header com usuário, **"Sair"** (`POST /auth/logout`) e **"Sair de todos os dispositivos"** (`POST /auth/logout-all`, com confirmação).
- [ ] **T2 — `/clinics`**: cards/tabela com `legal_name`, `slug`, `status` e `role`; clique navega para `/clinics/{id}`; estado vazio. Testes RTL (fetch stubado) e de build.
- [ ] **T3 — Docs + gate + relatório (AGUARDAR aprovação).**

### Incremento M1.5.3 — Recuperação, verificação e convite

- [ ] **T1 — `/forgot-password`** (validação de e-mail, 202 sempre, confirmação idêntica para qualquer e-mail) e **`/reset-password`** (token do fragmento para o estado → limpa hash → mantém em memória para retry; senha 12–128 validada no cliente; 400 genérico; sucesso → login).
- [ ] **T2 — `/verify-email`** (mesmo padrão de fragmento; 204 → sucesso; reuso/expirado → mensagem genérica) e **`/accept-invitation`** (senha opcional: usuário existente só ativa; sem senha para usuário novo → orientação genérica; 409/400 tratados; sucesso → login).
- [ ] **T3 — Docs + gate + relatório (AGUARDAR aprovação).**

### Incremento M1.5.4 — Clínica e settings

- [ ] **T1 — `/clinics/{id}`**: identidade (nome legal, slug, status) + papel do usuário; formulário de `legal_name` visível/habilitado só para OWNER (PATCH), com confirmação de sucesso.
- [ ] **T2 — `/clinics/{id}/settings`**: `display_name`, `timezone` (validação local + sugestões IANA), `locale`, `currency`; leitura para todos, edição OWNER/ADMIN; 422 genérico com validação prévia no formulário.
- [ ] **T3 — Docs + gate + relatório (AGUARDAR aprovação).**

### Incremento M1.5.5 — Equipe, papéis e convites

- [ ] **T1 — `/clinics/{id}/members`**: tabela com `role`/`status`/`created_at` (e `email` só quando a API devolver), troca de papel e remoção com diálogo de confirmação; ações ausentes para papéis sem permissão; 403/409/404 tratados.
- [ ] **T2 — Convite**: formulário (e-mail + papel), opções de papel filtradas pelo papel do ator (OWNER: todos; ADMIN: sem OWNER/ADMIN); 202 → confirmação; 409 → "já é membro"; 429 → aguarde o tempo informado.
- [ ] **T3 — Docs + gate + relatório (AGUARDAR aprovação).**

### Incremento M1.5.6 — Sessões e fechamento do marco

- [ ] **T1 — `/sessions`**: listar com marcação da sessão atual, revogar outro dispositivo (404 tratado), revogar a sessão atual (com confirmação, redireciona ao login) e `logout-all` com confirmação.
- [ ] **T2 — Polimento**: estados de carregamento/vazio/erro padronizados, acessibilidade (foco/labels/aria-live), responsividade mínima; revisão de textos pt-BR; sem dark mode.
- [ ] **T3 — Docs finais** (`architecture.md` estado M1.5 concluído; `security.md` superfície do frontend; `implementation-divergences.md` se aplicável) + gate completo (`pnpm` web + `docker compose up -d --build --wait` + `verify-compose-health.sh`).
- [ ] **T4 — Relatório final do M1.5** (Playwright explicitamente no M1.6) **e AGUARDAR aprovação.**

## Self-review

- **Cobertura da spec:** §1 topologia same-origin e OpenAPI como contrato (D2–D4, M1.5.1); §3 sessões/CSRF/anti-enumeração (D2/D9/D10), clínica na rota (D1/D6), RBAC refletido com backend como autoridade (D6); §4/M1.5 — login, recuperação, verificação, convite, seletor, gestão de clínica/usuários/convites/sessões (M1.5.2–M1.5.6); §4 "nenhum componente do OpenDentist" (D8); §5 — testes web; Playwright explicitamente no M1.6.
- **Ajustes da revisão incorporados:** (1) `client.ts` browser + `server-client.ts` server-side com encaminhamento restrito do `Cookie`, `no-store` e sem CSRF em GET (D2/D3, M1.5.1/T3); (2) "Sair" = logout individual e "Sair de todos os dispositivos" = logout-all com confirmação, e `/sessions` revoga a sessão atual com redirect (D9, M1.5.2/T1 e M1.5.6/T1); (3) `ApiError` com `detail` e `retryAfter` do header, validação de campo no frontend, 422 genérico e nenhuma alegação sobre `password_required` sem `code` estável (D10, M1.5.1/T3); (4) token lido para o estado → fragmento limpo → mantido em memória para retry → limpo no sucesso (D7, M1.5.3).
- **Fora do escopo (explícito):** Playwright e2e, headers de segurança, logs estruturados/redaction, backup/restauração (M1.6); adicionar `code` estável ao Problem Details é mudança de backend (avaliar em M1.6 se a UX exigir); RBAC clínico (marcos de domínio); i18n, dark mode, feature flags por UI.
- **Riscos mapeados:** build sem API (D5/`force-dynamic`); CSRF em mutações (D2 + testes); tokens nunca em query/logs (D7); drift do contrato (D4 + CI); dependências novas passam por licenças/audit (MIT).
