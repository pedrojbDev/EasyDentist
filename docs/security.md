# Segurança

Este documento materializa a direção de segurança aprovada. Salvo os limites de
contêiner, segredos locais de desenvolvimento e health checks, as políticas abaixo
**ainda não estão implementadas no M1.1**. Elas são requisitos vinculantes dos
incrementos indicados.

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

## Operação local

`infra/.env.example` contém apenas credenciais de desenvolvimento. O arquivo
`infra/.env` é ignorado por Git. Produção deverá injetar segredos externamente e
nunca reutilizar esses valores. SeaweedFS não publica API fora do host; Mailpit é
estritamente uma ferramenta local e não deve estar em qualquer ambiente público.

SeaweedFS existe somente para integração local no M1.1. Antes de uma implantação
de produção, deve haver storage gerenciado ou uma configuração revisada que
defina signing keys, criptografia em repouso e backup/restauração. O check local
exercita AWS Signature v4 e confirma que um objeto privado não é legível sem
credenciais; ele não é uma aprovação de segurança para produção.
