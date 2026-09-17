# ADR 0002: monorepo e serviços locais

**Status:** Aceito — M1.1, 2026-09-16

## Decisão

Usar pnpm workspace para `apps/web` e um projeto uv isolado em `apps/api`.
Docker Compose em `infra/docker-compose.yml` orquestra web, API, PostgreSQL,
Mailpit e SeaweedFS (S3-compatible sob Apache-2.0). Next.js faz rewrite
same-origin de `/api/v1` para a API.

## Consequências

Não há Redis, fila, proxy reverso adicional ou microserviço. Isso reduz o custo
operacional sem impedir as fronteiras modulares e mantém o contrato OpenAPI como
ponto de integração. Serviços possuem health checks e dependências só sobem após
seus pré-requisitos ficarem saudáveis.
