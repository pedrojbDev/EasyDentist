# Arquitetura

## Decisão materializada

EasyDentist será um monólito modular próprio. O frontend Next.js e a API FastAPI
são aplicações independentes no monorepo, executadas junto de PostgreSQL, Mailpit
e armazenamento S3 compatível no Docker Compose local. Não há Redis,
microserviços ou filas externas no MVP.

```text
Browser
  │ same origin /api/v1
  ▼
Next.js (apps/web) ─────► FastAPI (apps/api)
                                  │
                                  ├── PostgreSQL 17
                                  ├── SMTP (Mailpit no desenvolvimento)
                                  └── S3 privado (SeaweedFS no desenvolvimento)
```

O rewrite de Next.js preserva a topologia same-origin em `/api/v1`; o destino
interno é configurado por `API_INTERNAL_BASE_URL`. O serviço FastAPI expõe seu
contrato OpenAPI, que será a fonte do cliente TypeScript em
`apps/web/src/lib/api/generated/` quando os endpoints de domínio existirem.

## Limites de módulos previstos

O backend terá `core`, `auth`, `clinics`, `users`, `patients`, `appointments`,
`clinical_records`, `anamnesis`, `odontogram`, `treatments`, `billing`,
`documents` e `audit`. Esta estrutura é uma reserva de fronteiras: no M1.1 só
existem `core` e a rota técnica de saúde. Não foram criados módulos vazios de
domínio para evitar aparentar implementação antecipada.

As regras de segurança e isolamento pertencem a `auth`, `clinics`, repositories
tenant-aware e PostgreSQL; seu desenho está em `security.md` e sua implementação
começa no M1.2/M1.3, não nesta fundação.

## Convenções duráveis

- O contrato público usa OpenAPI e URLs `/api/v1`.
- IDs de domínio serão UUID; instantes serão `timestamptz`; moeda será armazenada
  em centavos e a configuração inicial será BRL.
- O idioma de interface é pt-BR. `America/Bahia` será o timezone padrão de
  provisionamento no marco correspondente.
- Objetos de documentos serão privados; PostgreSQL guardará apenas metadados,
  checksum, MIME type, tamanho e chave opaca.
- Não se copia OpenDentist no M1.1. A política de auditoria está em
  `open-dentist-audit.md`.
- SeaweedFS é exclusivamente infraestrutura local. Produção exige storage
  gerenciado ou configuração explícita de signing keys, criptografia em repouso
  e backup.

## Fronteiras de código

A ADR 0003 fixa a separação pragmática: routers cuidam só de HTTP; services/use
cases orquestram; repositories persistem; e regras de domínio não dependem de
FastAPI ou SQLAlchemy. `app/main.py` é somente o composition root e a application
factory centraliza a criação de FastAPI e o registro de routers. Ports/`Protocol`
só aparecem em fronteiras externas substituíveis; não existem `BaseService` nem
`BaseRepository` genéricos.

## Estado do M1.2.1

A fundação fornece somente `GET /health` na web e `GET /api/v1/health` na API.
São endpoints operacionais sem dados, credenciais ou autorização. Eles não são a
API pública do Marco 1 e não introduzem autenticação, tenancy ou domínio. O
backend agora possui engine e sessões SQLAlchemy assíncronas, metadata no schema
`app` e Alembic com uma baseline vazia. A ADR 0004 define a separação entre as
roles administrativa, de migration e de runtime.

Ainda não existem tabelas de domínio, RLS, `TenantContext`, repositories,
autenticação ou RBAC. Esses limites permanecem nos incrementos seguintes.
