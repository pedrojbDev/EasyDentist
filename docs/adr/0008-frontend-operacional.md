# ADR 0008: frontend operacional

**Status:** Aceito — M1.5, 2026-09-17

## Contexto

O M1.3 e o M1.4 entregaram a API completa de autenticação (11 endpoints) e de
tenancy/RBAC (10 endpoints), com CSRF signed double-submit, sessões opacas por
cookie e Problem Details (RFC 9457). O `apps/web` tem a fundação do M1.1
(Next.js 15 App Router com `typedRoutes`, Tailwind v4, componentes shadcn
locais, rewrite same-origin de `/api/v1` e Vitest em ambiente Node). O M1.5
materializa o frontend operacional do Marco 1: login, recuperação, verificação
de e-mail, aceite de convite, seletor de clínica e gestão de
clínica/settings/equipe/convites/sessões. O contrato do OpenAPI é a fonte de
verdade dos tipos, e nenhum componente do OpenDentist pode ser copiado neste
marco.

## Decisão

### Rotas (D1)

`/login`, `/forgot-password`, `/reset-password`, `/verify-email` e
`/accept-invitation` são públicas; os três últimos coincidem com os links de
e-mail emitidos pelo backend, com o token apenas no fragmento de URL. As rotas
autenticadas são `/` (redirect para `/clinics`), `/clinics`,
`/clinics/{clinicId}`, `/clinics/{clinicId}/settings`,
`/clinics/{clinicId}/members` e `/sessions`. A clínica ativa vive na rota e
nunca é autorização implícita: a UI reflete o papel devolvido por
`GET /clinics`, mas o backend continua a autoridade.

### Cliente HTTP em duas superfícies (D2, D3)

O navegador usa `src/lib/api/client.ts`: URL relativa same-origin, cookies
automáticos, `Content-Type: application/json`, `X-CSRF-Token` obtido de
`GET /api/v1/auth/csrf` imediatamente antes de cada mutação e Problem Details
convertido em `ApiError { status, title, detail?, requestId?, retryAfter? }`
(com `Retry-After` lido do header). Server Components usam
`src/lib/api/server-client.ts`: base `API_INTERNAL_BASE_URL`, encaminhamento
explícito e restrito do header `Cookie` da requisição recebida, `cache:
'no-store'` e sem CSRF (somente GET). Nenhum outro header do usuário é
repassado, e nenhum token é persistido em JavaScript.

### Contrato gerado e verificado no CI (D4)

`apps/api/scripts/export_openapi.py` exporta o `openapi.json` do FastAPI sem
levantar o lifespan (não exige banco) e aceita `--check` para detectar drift; o
JSON é commitado em `apps/web/src/lib/api/generated/openapi.json` e o
`openapi-typescript` gera `schema.d.ts` (`pnpm gen:api`). O job `api` do CI
executa o `--check` e o job `web` regenera e exige `git diff --exit-code`, de
modo que o contrato não diverge silenciosamente.

### Guarda de sessão (D5)

O layout autenticado é um Server Component que consulta `GET /auth/me` pelo
cliente server-side e redireciona para `/login` em 401; as páginas
autenticadas declaram `dynamic = 'force-dynamic'` para que o build não dependa
da API. O cliente browser também reage a 401 encerrando o estado local e
voltando ao login.

### Papel, erros e validação (D6, D10)

A interface espelha a matriz de papéis: OWNER vê identidade legal, convites de
qualquer papel e gestão de qualquer vínculo; ADMIN vê settings, convites e
gestão de papéis não-OWNER/ADMIN; os demais papéis têm leitura. A validação de
campos (senha 12–128, e-mail, timezone) acontece no frontend antes do submit,
porque o backend remove detalhes dos erros 422; 422 da API vira mensagem
genérica. Como o Problem Details não expõe um `code` estável para
`password_required`, a tela orienta genericamente sem afirmar a causa exata —
adicionar `code` é mudança de backend, fora do escopo do M1.5. Mensagens de
anti-enumeração são preservadas (login e recuperação não distinguem contas).

### Fragmento de URL e token em memória (D7)

Nas páginas de verificação, reset e convite o token é lido do fragmento
**primeiro para o estado do componente**; só então o hash é limpo com
`history.replaceState`. O token permanece apenas em memória para permitir nova
tentativa após erro de rede e é descartado após sucesso definitivo. Envio
sempre no corpo da requisição, nunca em query string.

### Componentes e acessibilidade (D8)

Somente shadcn (base new-york/neutral já licenciada) e código próprio,
adicionando componentes sob demanda; nenhum componente do OpenDentist é
copiado. Todo campo tem `<label>` associado, erros usam `aria-invalid` e
`aria-live`, e o foco vai ao primeiro erro.

### Sessões e logout (D9)

"Sair" revoga apenas a sessão atual (`POST /auth/logout`); "Sair de todos os
dispositivos" revoga todas (`POST /auth/logout-all`) com diálogo de
confirmação. `/sessions` lista as sessões do usuário com a atual marcada,
permite revogar outro dispositivo (404 tratado) e também a sessão atual, com
confirmação e redirecionamento ao login.

### Estado e dados (D11)

Server Components buscam os dados iniciais pelo cliente server-side e as
interações usam client components com `useState`/`useTransition` e o cliente
browser, revalidando com `router.refresh()` após mutações. Sem TanStack
Query/Redux, sem i18n framework, sem service worker e sem dark mode; strings
em pt-BR e tema claro com as CSS variables existentes.

## Consequências

- O frontend compila e testa sem API no ar (build independente, fetch sempre
  em runtime), e o contrato tipado elimina divergência entre UI e API.
- CSRF e sessão seguem as decisões do ADR 0006 sem duplicação de regras de
  segurança no cliente, que apenas transporta cookie e header.
- Testes de componente com RTL/jsdom cobrem os fluxos de UI; os fluxos web
  completos em Playwright permanecem no M1.6 (hardening).
- Adicionar `code` estável aos Problem Details fica registrado como melhoria
  possível de backend caso a UX de erros de convite exija precisão maior.
