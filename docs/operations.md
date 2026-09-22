# Operações

Runbook operacional do EasyDentist local e registro dos requisitos ainda
pendentes para produção. Complementa `docs/security.md` e a ADR 0009.

## Observabilidade (M1.6.4)

A API emite um evento JSON por linha em stdout (`service: "api"`) e o servidor
Next emite o mesmo formato (`service: "web"`). O access log textual do Uvicorn
é desativado (`--no-access-log`) para não duplicar eventos. Campos emitidos:
`timestamp`, `service`, `environment`, `level`, `event`, `request_id`, `method`,
`route` (template sem query string), `status_code`, `duration_ms` e, em falhas,
`error_type`. Nunca são emitidos corpo de requisição/resposta, cookies, tokens,
senhas, headers de autorização, e-mails, IPs brutos, query strings ou mensagens
de exceção.

O middleware da web gera `x-request-id` por requisição; o SSR encaminha esse
header ao FastAPI e a API reutiliza request IDs válidos. Assim os logs da web e
da API compartilham o mesmo `request_id` quando há encaminhamento.

Leitura local:

```sh
docker compose -f infra/docker-compose.yml logs -f api
docker compose -f infra/docker-compose.yml logs -f web
```

## Health checks

- API: `GET /api/v1/health` → `{"service":"api","status":"ok"}`
- Web: `GET /health` → `{"service":"web","status":"ok"}`
- Proxy same-origin: `GET /api/v1/health` pela porta 3000
- Compose completo e canário S3: `./scripts/verify-compose-health.sh`

## Limites do ambiente local

Mailpit e SeaweedFS são ferramentas locais, sem autenticação de produção.
Segredos vivem em `infra/.env.example` como valores de desenvolvimento; nenhum
deles pode ser reutilizado em produção.
