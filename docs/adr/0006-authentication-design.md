# ADR 0006: autenticação, sessões e proteção de mutações

**Status:** Aceito — M1.3, 2026-09-17

## Contexto

O M1.2 entregou as oito tabelas globais de autenticação, RLS fail-closed para o
escopo clínico e o bloqueio de escrita direta em `memberships`/`clinics` pela
role runtime. O M1.3 implementa o comportamento: credenciais, sessões, CSRF,
rate limiting, verificação de e-mail, recuperação de senha e provisionamento.

## Decisão

### Authenticator desacoplado (D1)

A autenticação é um port (`Protocol`) separado da autorização. Um provider
local verifica Argon2id e um provider fake exercita o mesmo contrato nos testes.
O resultado é `Principal(user_id, session_id, auth_method)`; RBAC e domínio
conhecem apenas `user_id` (ou o `Principal`), nunca senhas ou detalhes do
provider. Um OIDC futuro emite a mesma sessão opaca.

### Sessões e cookies (D2, D13)

- `APP_ENV` (`development`/`production`) decide nomes e flags:
  desenvolvimento usa `easydent_session`/`easydent_csrf` sem `Secure`;
  produção usa `__Host-easydent_session`/`__Host-easydent_csrf` com `Secure`.
- Cookie de sessão é `HttpOnly`, `Path=/`, sem `Domain`, `SameSite=Lax`,
  `Max-Age` igual ao TTL absoluto (30 dias). O cookie de CSRF é legível pelo
  frontend.
- O token de sessão tem 256 bits em base64url; apenas `SHA-256(token)` é
  persistido; comparações usam tempo constante.
- Expiração por inatividade de 12 horas (deslizante a cada `touch`) e absoluta
  de 30 dias. `last_seen_at` é atualizado no máximo a cada cinco minutos.
- Login sempre cria uma sessão nova; sessões de outros dispositivos permanecem.
  Recuperação de senha revoga todas as sessões e não faz login automático.
  Expiradas são resolvidas de forma lazy, sem jobs.

### CSRF e origem (D3, D4)

Todas as mutações exigem double-submit assinado: o valor é
`token ‧ HMAC-SHA256(AUTH_SECRET, "csrf:" ‖ binding)`, com binding igual ao
`session_id` (autenticado) ou `anonymous` (pré-login). O header `X-CSRF-Token`
deve ser idêntico ao cookie e a assinatura deve validar para o binding atual.
`Origin` (ou `Referer` na ausência) precisa constar na allowlist; a ausência de
ambos rejeita. `AUTH_SECRET` (≥ 32 bytes) é obrigatório em produção e nunca
aparece em logs.

### Rate limiting atômico (D5)

`app.consume_rate_limit` faz o upsert com janela e bloqueio em uma única
statement (serializa por chave). O login consome **antes** de autenticar, de
modo que o bloqueio vale mesmo sob concorrência; um login bem-sucedido limpa o
bucket da conta (senha correta zera falhas). O bloqueio tem backoff progressivo
de `30·2^(excedentes)` segundos com teto de 15 minutos e `Retry-After`.
Limites: login 5/conta/15min e 20/IP/15min; recuperação e reenvio
3/destinatário/h e 20/IP/h. As chaves são `HMAC(AUTH_SECRET, kind ‖
identificador)`; IPs brutos não são persistidos.

### Anti-enumeração (D6)

Login, recuperação, reenvio, confirmação e aceite de convite retornam respostas
genéricas e indistinguíveis para existência de conta, token inválido ou expirado.

### E-mail outbox-first (D7)

A linha em `email_outbox` é gravada na mesma transação da ação; a tentativa de
envio ocorre após o commit, via `EmailSender` (SMTP com `smtplib` e
`asyncio.to_thread`, sem dependência nova; Mailpit no desenvolvimento). Falhas
registram `attempt_count` e `next_attempt_at` e são retentadas no próximo
enqueue. Links usam fragmento de URL.

### Provisionamento e aceite (D8, D9)

`provision_clinic_owner` e `consume_invitation` são funções `SECURITY DEFINER`
com dona `easydentist_migrator`, `search_path` fixo e `EXECUTE` restrito à role
runtime. Elas contornam o lockdown do ADR 0005 (a role runtime não escreve
`memberships`/`clinics`) e tornam o aceite atômico: lock da invitation por
`SELECT … FOR UPDATE`, guarda `accepted_at IS NULL`, credencial, verificação de
e-mail, `PENDING → ACTIVE` e `PROVISIONING → ACTIVE` na mesma transação. O
aceite não faz login automático. Slug duplicado é erro; usuário existente é
reutilizado.

### Senhas (D10)

Argon2id versão 19, 64 MiB, três iterações, paralelismo 1, salt de 16 bytes e
saída de 32 bytes. Comprimento entre 12 e 128 caracteres, sem regras de
composição. Rehash transparente no login quando os parâmetros evoluírem.

### Erros (D11)

Todas as respostas de erro usam Problem Details (RFC 9457,
`application/problem+json`) com `request_id` ecoado no header `X-Request-Id` e
no corpo; títulos em pt-BR.

### Auditoria (D12)

Eventos mínimos: `login_succeeded`, `login_failed`, `logout`, `session_revoked`,
`password_reset_completed`, `email_verified`, `invitation_accepted`,
`rate_limit_triggered`. Metadados nunca contêm senha, token, cookie ou IP bruto.

### Identidade do usuário (D14)

`GET /auth/me` retorna apenas identidade (`id`, `email`, `email_verified_at`,
`status`). Memberships são servidas por `GET /clinics` no M1.4.

## Consequências

- A role runtime permanece incapaz de escrever vínculos e clínicas; toda
  transição sensível passa por função auditada.
- A superfície de autenticação é testável sem navegador (httpx + ASGI) e o
  contrato do `Authenticator` aceita providers futuros sem tocar a autorização.
- O rate limiting depende do PostgreSQL, coerente com a decisão de não usar
  Redis no MVP; a atomicidade é verificada sob concorrência.
- Segredos de desenvolvimento vivem em `infra/.env.example`; produção injeta
  externamente e o boot falha sem `AUTH_SECRET` válido.
