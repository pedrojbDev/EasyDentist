# Segurança

Este documento materializa a direção de segurança aprovada. Salvo os limites de
contêiner, segredos locais de desenvolvimento e health checks, as políticas abaixo
**ainda não estão implementadas no M1.1**. Elas são requisitos vinculantes dos
incrementos indicados.

## Autenticação (M1.3)

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

Rotas tenant-aware usarão `/api/v1/clinics/{clinic_id}/...`. O contexto obrigatório
valida a sessão, relê membership ativa, calcula permissões, abre transação e usa
`set_config(..., true)` para `app.current_user_id` e `app.current_clinic_id`.

Todas as tabelas de domínio terão `clinic_id NOT NULL`, FKs compostas e RLS com
`FORCE ROW LEVEL SECURITY`. A role da aplicação não será dona nem terá
`BYPASSRLS`; migrations usarão role distinta. Repositories exigirão
`TenantContext`, e updates/deletes combinarão `id` e `clinic_id`. Falhas
cross-tenant responderão 404.

RBAC será default-deny e terá OWNER, ADMIN, DENTIST, ASSISTANT e RECEPTIONIST;
somente OWNER promove OWNER e o último OWNER não pode ser removido/rebaixado.
Registros clínicos serão aditivos e terão autor profissional.

## Roles PostgreSQL (M1.2.1)

A role runtime `easydentist_app` não é dona do schema `app`, não executa DDL e
possui `NOBYPASSRLS`. Alembic usa exclusivamente `easydentist_migrator`, também
sem privilégios administrativos ou `BYPASSRLS`. A credencial de migration não é
injetada no processo normal da API. RLS e o contexto transacional de tenant ainda
não estão implementados; entram nos próximos incrementos de M1.2.

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
