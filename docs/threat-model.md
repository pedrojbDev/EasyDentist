# Threat model do Marco 1

Este documento mapeia ativos, fronteiras de confiança e ameaças do Marco 1. Cada
ameaça tem uma mitigação implementada ou planejada e uma evidência: um teste
automatizado ou uma limitação operacional explícita. O threat model cobre o
estado local e o desenho; ele **não aprova produção** — os requisitos
operacionais pendentes estão listados ao final.

Referências: `plan.md` §§3–5, `docs/security.md`, ADRs 0002–0009.

## Ativos protegidos

| Ativo                                  | Onde vive                                                             | Risco principal                                  |
| -------------------------------------- | --------------------------------------------------------------------- | ------------------------------------------------ |
| Sessões autenticadas                   | cookie `HttpOnly` + `auth_sessions` (somente SHA-256)                 | roubo, fixação, reuso                            |
| Tokens de verificação, reset e convite | e-mail com link em fragmento + `auth_action_tokens` (somente SHA-256) | interceptação, reuso, vazamento em logs/Referer  |
| Credenciais                            | `password_credentials` (Argon2id v19)                                 | extração, cracking, enumeração                   |
| Dados clínicos e cadastrais            | tabelas tenant-aware (futuros marcos)                                 | acesso cross-tenant                              |
| Memberships e convites                 | `memberships`, `membership_invitations`                               | escalada de privilégio, remoção do último OWNER  |
| Backups                                | arquivos `pg_dump -Fc` fora do Git                                    | restauração incompleta, exposição de dados       |
| Logs e auditoria                       | stdout JSONL + `auth_audit_events`/`clinic_audit_events`              | vazamento de segredos e dados pessoais           |
| Segredos de aplicação                  | `AUTH_SECRET`, credenciais de banco, S3, SMTP                         | commit acidental, reutilização local em produção |
| Dependências                           | lockfiles npm e uv                                                    | vulnerabilidades e licenças incompatíveis        |

## Fronteiras de confiança

```text
Browser (não confiável)
  │  same-origin /api/v1 (cookie HttpOnly + CSRF)
  ▼
Next.js (apps/web)  ── confia apenas no cookie encaminhado em SSR
  │  rewrite /api/v1
  ▼
FastAPI (apps/api)  ── autoridade de autenticação, RBAC e tenant
  │  conexão runtime sem DDL e sem BYPASSRLS
  ▼
PostgreSQL runtime (app.* com FORCE RLS)   PostgreSQL migrator (DDL/migrations)

FastAPI ─► SMTP/Mailpit (desenvolvimento)   FastAPI ─► storage S3 privado (desenvolvimento)
```

- O navegador nunca fala direto com a API interna: o rewrite mantém a origem.
- O SSR encaminha somente o header `Cookie`, com `cache: 'no-store'`; nenhum
  outro header do usuário é repassado.
- A role runtime não é dona do schema, não executa DDL e não tem `BYPASSRLS`;
  a role de migration não é injetada no processo normal da API.
- Mailpit e SeaweedFS são estritamente locais; produção exige SMTP e storage
  gerenciados.

## Ameaças e mitigação

| #   | Ameaça                                         | Vetor                                                                      | Mitigação                                                                                                                                                                                 | Evidência                                                                                                                                                                                                                              |
| --- | ---------------------------------------------- | -------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| T1  | XSS                                            | conteúdo refletido/armazenado, script inline, dependência comprometida     | CSP bloqueante com nonce por resposta, sem `unsafe-inline` para scripts, `default-src 'none'` na API, React sem HTML cru, `X-Content-Type-Options: nosniff`                               | `apps/api/tests/test_security_headers.py`, `apps/web/src/lib/security-headers.test.ts`, fluxos Playwright sem violação CSP                                                                                                             |
| T2  | CSRF                                           | formulário/requisição externa contra cookie de sessão                      | signed double-submit (cookie legível + `X-CSRF-Token` + HMAC), `Origin`/`Referer` em allowlist, reemissão do token no login, CORS desativado                                              | `apps/api/tests/integration/test_csrf_enforcement.py`, matriz CSRF de `test_auth_security_matrix.py`, `apps/web/e2e/auth.spec.ts`                                                                                                      |
| T3  | Session fixation                               | sessão pré-existente reaproveitada após login                              | login sempre cria sessão nova e reemite CSRF vinculado; tokens de 256 bits; apenas hash persistido; cookie `HttpOnly`                                                                     | `test_auth_security_matrix.py`, `apps/api/tests/integration/test_session_service.py`                                                                                                                                                   |
| T4  | Enumeração de contas                           | respostas distintas em login, recuperação e convite                        | respostas genéricas e indistinguíveis; rate limiting por conta e IP; verificação dummy no login                                                                                           | `test_auth_security_matrix.py`, `apps/api/tests/integration/test_recovery_endpoints.py`, `apps/api/tests/integration/test_login_rate_limit.py`                                                                                         |
| T5  | Acesso cross-tenant                            | IDs válidos da outra clínica via rota, API, SQL cru ou FK                  | `clinic_id` da rota só como tenant solicitado; membership revalidada por requisição; repos exigem contexto; FK composta; 404 genérico                                                     | `apps/api/tests/integration/test_tenant_isolation.py`, `test_raw_sql_isolation.py`, `test_cross_tenant_reference.py`, `test_rbac_matrix.py`, `apps/web/e2e/isolation.spec.ts`, `apps/api/tests/integration/test_m16_isolation_gate.py` |
| T6  | RLS ausente ou contornada                      | policy não forçada, role com `BYPASSRLS`, contexto vazio aceito            | `FORCE ROW LEVEL SECURITY` nas seis tabelas tenant-aware, policies fail-closed, runtime/migrator `NOBYPASSRLS`, `set_config(..., true)` transacional                                      | `apps/api/tests/integration/test_rls_policies.py`, `test_rls_fail_closed.py`, `test_pool_tenant_leak.py`, `test_m16_isolation_gate.py`                                                                                                 |
| T7  | Vazamento em logs                              | access log textual, metadata de auditoria, exceção com dados de entrada    | JSONL com allowlist de campos; sem corpo, cookies, tokens, senhas, headers de autorização, e-mails, IPs ou query strings; Uvicorn sem access log textual; auditoria sanitizada            | `apps/api/tests/test_structured_logging.py`, `apps/api/tests/integration/test_logging_redaction.py`, `apps/api/tests/integration/test_auth_redaction.py`, `apps/web/src/lib/server-logging.test.ts`                                    |
| T8  | Secrets no Git                                 | `.env`, dumps, manifestos E2E, credenciais em exemplos                     | `.env*` ignorado com exceção de `.env.example`; scanner reprodutível de padrões; produção rejeita o segredo padrão de desenvolvimento; `.gitignore` cobre dumps e artefatos               | `scripts/verify-secrets.sh`, `apps/api/tests/test_auth_settings.py`, `docs/operations.md`                                                                                                                                              |
| T9  | Dependência vulnerável ou licença incompatível | supply chain npm/uv                                                        | lockfiles congelados, `pnpm audit`, `pip-audit`, verificação de licenças com allowlist e exceções exatas                                                                                  | `pnpm run audit`, `pnpm run licenses`, `pip-audit`, `apps/api/scripts/check_licenses.py`, jobs do CI                                                                                                                                   |
| T10 | Restauração incompleta                         | backup sem roles, grants, policies ou migrations                           | `pg_dump -Fc` + `pg_restore` em PostgreSQL descartável; recriação de roles; conferência de schema, grants, policies e sentinelas; `alembic check`; prova de isolamento sob a role runtime | `scripts/verify-backup-restore.sh`                                                                                                                                                                                                     |
| T11 | Fixação de tenant via sessão                   | clínica ativa inferida da sessão                                           | a clínica ativa vive na rota e é validada contra membership ativa em cada requisição; mudança/revogação tem efeito imediato                                                               | `test_tenant_isolation.py`, `test_rbac_matrix.py`, `test_m16_isolation_gate.py`                                                                                                                                                        |
| T12 | Escalada de privilégio                         | papel forjado, promoção a OWNER por ADMIN, remoção do último OWNER         | RBAC default-deny; apenas OWNER promove OWNER; guarda de último OWNER com serialização por clínica; transições só em funções `SECURITY DEFINER` que conferem os GUCs                      | `apps/api/tests/integration/test_rbac_matrix.py`, `test_membership_function_guards.py`, `test_membership_management.py`, `apps/web/e2e/clinics.spec.ts`                                                                                |
| T13 | Token residual em URL ou JavaScript            | fragmento não limpo, token em query string, persistência em `localStorage` | token lido do fragmento para a memória, `history.replaceState` imediato, envio no corpo, descarte após sucesso, cookie de sessão inacessível a JS                                         | `apps/web/e2e/auth.spec.ts`, `apps/web/src/features/auth/use-fragment-token.test.tsx`, `test_auth_security_matrix.py`                                                                                                                  |
| T14 | Abuso de autenticação                          | força bruta, reenvio em massa                                              | rate limiting atômico em PostgreSQL com backoff e `Retry-After`; chaves HMAC sem IP bruto                                                                                                 | `test_login_rate_limit.py`, `test_rate_limiter.py`                                                                                                                                                                                     |
| T15 | Envio de e-mail perdido ou duplicado           | falha SMTP, retry cego                                                     | outbox transacional com `idempotency_key` e backoff exponencial; Mailpit apenas local                                                                                                     | `apps/api/tests/integration/test_email_outbox.py`, `test_auth_endpoints.py`                                                                                                                                                            |

## Limitações operacionais explícitas

Os itens abaixo são riscos aceitos no ambiente local e **bloqueiam produção**
até revisão: storage S3 local sem criptografia gerenciada, SMTP Mailpit sem
autenticação, backup sem retenção/expiração definida, segredos de
desenvolvimento versionados apenas em `.env.example`, ausência de monitoramento
externo e de rotação automática de credenciais. Eles estão registrados em
`docs/operations.md` e em `docs/security.md` e não são cobertos por teste porque
dependem de infraestrutura externa. O scanner de secrets é deliberadamente
conservador (padrões explícitos e poucas exceções locais documentadas) e não
substitui um gestor externo de segredos.
