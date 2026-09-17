# EasyDentist

Fundação do monólito modular EasyDentist, conforme `plan.md`.

## Requisitos fixados

- Node.js 24.19.0 e pnpm 11.10.0
- Python 3.12.14 e uv 0.12.5
- Docker Engine com Docker Compose v2
- Navegadores modernos: Chrome 111+, Safari 16.4+ e Firefox 128+ (mínimos do
  Tailwind CSS v4)

## Desenvolvimento local

```sh
pnpm install --frozen-lockfile
(cd apps/api && uv sync --locked --all-groups)
docker compose -f infra/docker-compose.yml up -d --build --wait db
docker compose -f infra/docker-compose.yml --profile tools run --rm migrate
docker compose -f infra/docker-compose.yml up -d --build --wait
```

Na primeira execução com volume limpo, o PostgreSQL cria separadamente as roles
de runtime e migration; o segundo comando aplica a baseline antes da aplicação.

Endereços locais:

- Web: <http://localhost:3000>
- API: <http://localhost:8000/api/v1/health>
- Mailpit: <http://localhost:8025>
- Storage S3-compatible (SeaweedFS): <http://localhost:9000>

As credenciais locais são valores de desenvolvimento e vivem em `infra/.env.example`.
Copie-o para `infra/.env` antes de executar a composição fora da automação.
O container `migrate` é uma tarefa sob demanda, não um serviço permanente. Ele
usa as credenciais efetivas de `infra/.env`; a API continua recebendo somente a
URL runtime. Para senhas com caracteres reservados de URL, defina explicitamente
`APP_DATABASE_URL` e `MIGRATION_DATABASE_URL` com credenciais percent-encoded.

## Comandos de qualidade

```sh
pnpm lint && pnpm format:check && pnpm typecheck && pnpm test
(cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest)
pnpm run licenses && (cd apps/api && uv run python scripts/check_licenses.py)
pnpm run audit && (cd apps/api && uv run pip-audit)
docker compose -f infra/docker-compose.yml config --quiet && \
  docker compose -f infra/docker-compose.yml up -d --build --wait db && \
  docker compose -f infra/docker-compose.yml --profile tools run --rm migrate && \
  docker compose -f infra/docker-compose.yml up -d --build --wait && \
  ./scripts/verify-compose-health.sh
./scripts/verify-migrations.sh
```

`scripts/verify-migrations.sh` é destrutivo: remove os volumes locais do
Compose e reexecuta a cadeia completa (upgrade, `alembic check`, downgrade até
`base` e upgrade novamente) contra um banco recém-criado, provando que as
migrations são aplicáveis do zero e reversíveis.

O M1.2 entrega o schema do Marco 1 (oito tabelas globais e seis tenant-aware),
RLS fail-closed por tenant com `TenantContext`, repositories tenant-aware com
`FeatureFlagService` tipado e a suíte de isolamento entre duas clínicas. Ainda
não há autenticação, RBAC ou rotas de domínio; nenhuma rota da API expõe dados.
Não há código copiado ou adaptado do OpenDentist.

SeaweedFS é infraestrutura exclusivamente local nesta fase. Antes de produção,
o armazenamento deverá ser gerenciado ou ter signing keys explícitas,
criptografia em repouso e plano de backup configurados.

`scripts/verify-compose-health.sh` lê credenciais e bucket efetivos do
container `storage`; para diagnósticos controlados, `S3_ACCESS_KEY` e
`S3_SECRET_KEY` podem ser sobrescritos apenas em conjunto. `S3_BUCKET` e
`S3_ENDPOINT_URL` também podem ser sobrescritos explicitamente.
