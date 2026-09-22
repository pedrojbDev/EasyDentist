# ADR 0009: hardening e operação do Marco 1

**Status:** Aceito — M1.6, 2026-09-18

## Contexto

O M1.2 entregou schema, roles, RLS e isolamento por tenant; o M1.3, autenticação,
sessões, CSRF, rate limiting, tokens de ação e provisionamento; o M1.4, RBAC,
convites e gestão de equipe; o M1.5, o frontend operacional. Cada marco possui
provas automatizadas próprias, mas elas exercitam o backend por httpx sob ASGI e
o frontend por componentes isolados. Não existe ainda: suíte end-to-end sobre o
Compose completo, headers de segurança, logging estruturado com redaction,
prova de restauração de backup, scanner reprodutível de secrets e o critério
final de isolamento cross-tenant de ponta a ponta.

O M1.6 fecha essas lacunas sem alterar domínio clínico nem produto. Storage,
SMTP, retenção de backups, criptografia e gestão externa de secrets permanecem
pré-requisitos operacionais de produção, fora do escopo deste marco.

## Decisão

### E2E contra o Compose com fixtures determinísticas (D1)

Playwright executa contra o Compose completo (web, api, db, Mailpit e storage),
com `workers: 1`, trace e screenshot em falha. O estado E2E é criado por um
seed próprio (`apps/api/scripts/seed_e2e.py`) que usa **exclusivamente** a
conexão de migration — a role runtime não escreve vínculos nem clínicas — e
grava um manifesto temporário com e-mails, IDs e senhas sintéticas. O manifesto
não é versionado e o teardown remove os dados criados. As fixtures são híbridas:
nascem direto no banco para garantir determinismo e são exercitadas pelos fluxos
reais do navegador. O seed cria:

- Clínica A e Clínica B, cada uma com identificador e texto sentinela exclusivos;
- um usuário multi-clínica com membership ativa nas duas clínicas;
- um usuário exclusivo da Clínica A e outro da Clínica B;
- um usuário não verificado, para o fluxo de confirmação;
- um usuário com senha, para o fluxo de recuperação.

O helper de Mailpit busca mensagens pelo destinatário e pelo timestamp do
manifesto, extrai o token do fragmento e **nunca imprime o corpo do e-mail**.
Nenhum token de convite, reset ou verificação permanece na URL após o
processamento, e o cookie de sessão nunca aparece em `document.cookie`.

### Headers de segurança (D2)

Toda resposta da API emite `X-Content-Type-Options: nosniff`,
`X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`,
`Permissions-Policy: camera=(), microphone=(), geolocation=()`,
`Cross-Origin-Opener-Policy: same-origin`,
`Cross-Origin-Resource-Policy: same-origin` e
`Content-Security-Policy: default-src 'none'; base-uri 'none'; frame-ancestors 'none'`.
Em produção, acrescenta `Strict-Transport-Security: max-age=31536000; includeSubDomains`;
desenvolvimento nunca emite HSTS.

O Next.js gera um nonce por resposta, propaga-o para os scripts e estilos que
emite e usa CSP bloqueante sem `unsafe-inline` para scripts, com recursos,
conexões e formulários restritos à mesma origem (`data:` apenas para ícones).
O middleware de CSP exclui o rewrite `/api/v1` para preservar os headers da API,
e o rewrite same-origin continua sendo o único caminho do navegador até a API.

### Logging estruturado com allowlist (D3)

Logs de API e web são JSONL com um formatter sobre a biblioteca padrão e campos
em `snake_case`. Cada evento usa allowlist: serviço, ambiente, timestamp, nível,
evento, request ID, método, rota sem query string, status, duração, tipo de erro
e UUIDs de usuário/clínica somente quando necessários ao diagnóstico. Nunca
entram corpo de requisição/resposta, cookies, `Set-Cookie`, tokens, senhas,
headers de autorização, e-mails, IPs brutos, query strings ou mensagens de
exceção com dados de entrada. A API emite a rota no formato de template e cobre
`status`, `duration` e `error_type`; a web emite `method` e rota normalizada
(UUIDs viram `{id}`) no início da requisição, pois o middleware do Next roda
antes da renderização e não observa status ou duração. O access log textual do
Uvicorn é desativado para não duplicar eventos. A auditoria de segurança passa a
sanitizar metadata por allowlist de evento e a ignorar campos desconhecidos. O
request ID correlaciona logs da web e da API quando há encaminhamento.

### Backup, restauração e operação (D4)

`scripts/verify-backup-restore.sh` cria um projeto Compose descartável separado
do ambiente local, aplica as migrations, insere duas clínicas com dados
sentinela, gera o backup com `pg_dump -Fc`, restaura com `pg_restore` em um
PostgreSQL descartável independente, recria as roles necessárias e confirma
schema, migrations, grants, policies e dados. Conectado como
`easydentist_app`, prova que cada contexto enxerga somente sua clínica e executa
`alembic check`. Containers, volumes e arquivos temporários são removidos com
`trap`, sem tocar no Compose local do usuário. `docs/operations.md` registra o
runbook: inicialização, variáveis e segredos, migrations, health checks, backup,
restauração, validação pós-restore, rotação de credenciais, limites do ambiente
local e requisitos pendentes de produção.

### Secrets, dependências e cookies (D5)

Um scanner reprodutível (`scripts/verify-secrets.sh`) varre apenas arquivos
versionados com padrões explícitos: chaves privadas, access keys, tokens
conhecidos, URLs com credenciais e segredos atribuídos fora de arquivos de
exemplo permitidos. `infra/.env.example` contém somente valores locais
documentados; produção rejeita explicitamente o segredo padrão de
desenvolvimento. `.env`, dumps, manifestos E2E e artefatos Playwright não são
versionados. `pnpm audit`, `pip-audit` e a verificação de licenças permanecem no
CI e passam a cobrir também as dependências de Playwright.

### Critério de isolamento cross-tenant (D6)

O M1.6 só termina quando, com duas clínicas e contextos intercalados no mesmo
pool, uma conta restrita à Clínica B não acessa nenhum dado da Clínica A por
API, SSR, rota web ou consulta direta sob a role runtime. A prova cobre:
`FORCE ROW LEVEL SECURITY` nas tabelas tenant-aware, `NOBYPASSRLS` para runtime
e migrator, contexto ausente falhando fechado, IDs válidos da clínica errada
retornando 404, membership revalidada por requisição com efeito imediato de
mudança/revogação e ausência dos sentinelas da outra clínica na resposta e no
DOM. A prova automatizada final vive em
`apps/api/tests/integration/test_m16_isolation_gate.py` e nos cenários
`apps/web/e2e/isolation.spec.ts`.

## Consequências

- O M1.6 passa a ter um gate executável de ponta a ponta
  (`scripts/verify-secrets.sh`, `scripts/verify-migrations.sh`,
  `scripts/verify-backup-restore.sh`, `pnpm e2e` e as suítes existentes),
  reproduzível no CI por um job de hardening que desmonta volumes mesmo em falha.
- CSP bloqueante pode quebrar scripts inline adicionados no futuro; qualquer
  exceção exige atualização explícita do middleware e do teste de headers.
- O scanner de secrets é deliberadamente conservador e não substitui um gestor
  externo de segredos.
- Produção continua bloqueada até que storage gerenciado, SMTP real, retenção
  de backups, criptografia, rotação externa de credenciais e monitoramento
  estejam definidos; este ADR os registra como pré-requisitos, não como
  entregas.
