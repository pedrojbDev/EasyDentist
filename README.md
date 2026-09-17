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
docker compose -f infra/docker-compose.yml up --build
```

Endereços locais:

- Web: <http://localhost:3000>
- API: <http://localhost:8000/api/v1/health>
- Mailpit: <http://localhost:8025>
- Storage S3-compatible (SeaweedFS): <http://localhost:9000>

As credenciais locais são valores de desenvolvimento e vivem em `infra/.env.example`.
Copie-o para `infra/.env` antes de executar a composição fora da automação.

## Comandos de qualidade

```sh
pnpm lint && pnpm format:check && pnpm typecheck && pnpm test
(cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest)
pnpm run licenses && (cd apps/api && uv run python scripts/check_licenses.py)
pnpm run audit && (cd apps/api && uv run pip-audit)
docker compose -f infra/docker-compose.yml config --quiet && \
  docker compose -f infra/docker-compose.yml up --build --wait && \
  ./scripts/verify-compose-health.sh
```

Não há autenticação, tenancy, RLS, RBAC, migrations ou entidades de domínio neste
incremento. Migrations são deliberadamente não aplicáveis no M1.1; Alembic começa
no M1.2. Não há código copiado ou adaptado do OpenDentist neste marco.

SeaweedFS é infraestrutura exclusivamente local nesta fase. Antes de produção,
o armazenamento deverá ser gerenciado ou ter signing keys explícitas,
criptografia em repouso e plano de backup configurados.

`scripts/verify-compose-health.sh` lê credenciais e bucket efetivos do
container `storage`; para diagnósticos controlados, `S3_ACCESS_KEY` e
`S3_SECRET_KEY` podem ser sobrescritos apenas em conjunto. `S3_BUCKET` e
`S3_ENDPOINT_URL` também podem ser sobrescritos explicitamente.
