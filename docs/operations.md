# Operações

Runbook operacional do EasyDentist local e registro dos requisitos ainda
pendentes para produção. Complementa `docs/security.md` e a ADR 0009.

## Pré-requisitos

- Docker com Compose v2.
- Node.js 24.19.0 e pnpm 11.10.0.
- Python 3.12.14 e uv 0.12.5 (via `apps/api`).
- `curl` com suporte a AWS Signature v4 para o canário de storage.

## Inicialização do Compose

```sh
docker compose -f infra/docker-compose.yml config --quiet
docker compose -f infra/docker-compose.yml build
docker compose -f infra/docker-compose.yml up -d --wait db
docker compose -f infra/docker-compose.yml --profile tools run --rm migrate
docker compose -f infra/docker-compose.yml up -d --wait --wait-timeout 180
```

Serviços publicados em `127.0.0.1`: web `:3000`, api `:8000`, PostgreSQL `:5433`,
Mailpit SMTP `:1025`/UI `:8025` e storage S3 `:9000`.

## Variáveis e segredos

Os defaults do Compose são exclusivos de desenvolvimento. Em produção, injetar
externamente no mínimo:

- `APP_ENV=production` (ativa HSTS, cookies `__Host-` e `Secure`);
- `AUTH_SECRET` aleatório com pelo menos 32 bytes — o valor padrão de
  desenvolvimento é rejeitado em produção;
- `POSTGRES_PASSWORD`, `APP_DB_PASSWORD` e `MIGRATION_DB_PASSWORD` próprios;
- `ALLOWED_ORIGINS` e `PUBLIC_BASE_URL` do domínio real;
- credenciais SMTP e S3 reais (`SMTP_HOST`, `SMTP_PORT`, `SMTP_SENDER`,
  `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`).

`S3_KEY_PREFIX` é opcional e vazio por padrão: quando definido, a API prefixa
toda chave de documento com o valor normalizado (sem barras nas pontas) e o
adapter continua expondo a mesma chave lógica nos metadados. O harness E2E usa
esse isolamento para apontar a API a `e2e/{run_id}/` e remover o run sem tocar
nos demais objetos do bucket (ver "E2E e storage efêmero"). Em produção, deixe o
valor vazio ou use um prefixo fixo do ambiente; a variável nunca aceita dados do
cliente.

`infra/.env` é ignorado por Git e é a única fonte local aceita. Nenhum valor de
`infra/.env.example` pode ser reutilizado fora do desenvolvimento.

## Migrations

Aplicar com a role de migration (a API nunca usa essa credencial):

```sh
docker compose -f infra/docker-compose.yml --profile tools run --rm migrate
docker compose -f infra/docker-compose.yml --profile tools run --rm migrate alembic check
```

A cadeia completa em banco descartável é validada por
`./scripts/verify-migrations.sh` (0001→0012, downgrade e upgrade novamente).

## Health checks

- API: `GET http://127.0.0.1:8000/api/v1/health`
- Web: `GET http://127.0.0.1:3000/health`
- Proxy same-origin: `GET http://127.0.0.1:3000/api/v1/health`
- Banco: `docker compose -f infra/docker-compose.yml exec db pg_isready`
- Mailpit: `GET http://127.0.0.1:8025/livez`
- Storage: `./scripts/verify-compose-health.sh` (cobre health, proxy e um
  round-trip S3 assinado com negação de leitura anônima).

## E2E e storage efêmero

`pnpm e2e` roda o Playwright contra o Compose (`workers: 1`). O `global-setup`
executa as migrations, roda o seed determinístico (`scripts.seed_e2e`) e cria
uma sessão por usuário sintético, gravada em `artifacts/e2e/sessions/` e
removida no teardown. O seed cria duas clínicas, usuários de todos os papéis,
um paciente por clínica e o perfil profissional do usuário multi-clínica, todos
com o namespace `e2e-{run_id}`.

Depois do seed, o `global-setup` recria o serviço `api` com
`S3_KEY_PREFIX=e2e/{run_id}/` e espera o healthcheck; todo objeto enviado pelos
specs fica sob esse prefixo. No `global-teardown`, o `e2e-seed --cleanup`:

1. lista e remove exclusivamente os objetos sob `e2e/{run_id}/` e confirma que
   nenhum objeto daquele run permaneceu;
2. remove `patient_documents`, `patient_alerts`, `anamneses` (desabilitando os
   triggers de usuário apenas para a manutenção, porque versões finais são
   imutáveis), `patients`, `professional_profiles` e as demais linhas do run;
3. restaura `S3_KEY_PREFIX` vazio no serviço `api`.

O teardown roda mesmo com specs falhando e falha de forma explícita se a
remoção do prefixo não puder ser concluída. `E2E_KEEP_FIXTURES=1` preserva as
linhas para depuração (sessões e prefixo continuam sendo restaurados). Para
conferir manualmente, `SELECT count(*) FROM app.clinics` deve voltar a 0 e a
listagem do bucket com prefixo `e2e/` deve estar vazia.

## Observabilidade (M1.6.4)

Os dois serviços emitem JSON por linha em stdout com campos em `snake_case`.
O access log textual do Uvicorn é desativado (`--no-access-log`) para não
duplicar eventos. Campos comuns: `timestamp`, `service`, `environment`, `level`,
`event`, `request_id`. Nunca são emitidos corpo de requisição/resposta, cookies,
tokens, senhas, headers de autorização, e-mails, IPs brutos, query strings ou
mensagens de exceção.

- **API (`service: "api"`)**: `method`, `route` no formato de template (ex.:
  `/api/v1/clinics/{clinic_id}`, sem query string), `status_code`, `duration_ms`
  e, em falhas, `error_type`. Exceções não tratadas viram Problem Details 500 e
  continuam recebendo headers de segurança, `x-request-id` e evento de acesso.
- **Web (`service: "web"`)**: `method` e `route` normalizada — UUIDs viram
  `{id}` —, registrados no início da requisição. O middleware do Next roda antes
  da renderização, então `status_code`, `duration_ms` e `error_type` não são
  observáveis nele; para respostas SSR, use o `request_id` e consulte os eventos
  da API gerados pelos `serverFetch`.

O middleware da web gera `x-request-id` por requisição; o SSR encaminha esse
header ao FastAPI e a API reutiliza request IDs válidos. Assim os logs da web e
da API compartilham o mesmo `request_id` quando há encaminhamento.

Leitura local:

```sh
docker compose -f infra/docker-compose.yml logs -f api
docker compose -f infra/docker-compose.yml logs -f web
```

## Secrets

```sh
./scripts/verify-secrets.sh   # ou pnpm run secrets
```

O scanner varre apenas arquivos versionados e imprime `arquivo:linha` (nunca o
valor). `infra/.env.example` é o único arquivo de exemplo permitido e contém
somente valores locais documentados. `.env`, dumps (`*.dump`) e artefatos de
teste são ignorados pelo Git e verificados pelo scanner. Em produção,
`APP_ENV=production` rejeita o `AUTH_SECRET` padrão de desenvolvimento na
inicialização.

## Backup

O formato suportado é o customizado do PostgreSQL:

```sh
docker compose -f infra/docker-compose.yml --profile tools run --rm -T \
  --entrypoint pg_dump pg-client \
  -h db -U easydentist -d easydentist -Fc > easydentist-$(date +%Y%m%d).dump
```

Armazenar o arquivo fora do repositório, com retenção e criptografia definidas
pelo ambiente (ver requisitos de produção). O dump contém dados clínicos: tratá-lo
como material sensível.

## Restauração em banco descartável

Nunca restaurar sobre o banco em uso. O fluxo automatizado completo é
`./scripts/verify-backup-restore.sh`: ele cria dois projetos Compose
descartáveis (origem e destino), aplica migrations, insere duas clínicas com
sentinelas, gera o dump `pg_dump -Fc`, recria o banco de destino mantendo as
roles, restaura com `pg_restore --exit-on-error`, confere schema, revisão
Alembic, grants, policies, `FORCE ROW LEVEL SECURITY`, `NOBYPASSRLS`,
sentinelas e isolamento sob a role `easydentist_app`, executa `alembic check` e
remove containers, volumes e arquivos temporários com `trap`. O Compose local
não é tocado.

Passos manuais equivalentes, para um banco descartável `restored`:

```sh
docker compose -p easydentist-restore -f infra/docker-compose.yml up -d --wait db
docker compose -p easydentist-restore -f infra/docker-compose.yml exec db \
  psql -U easydentist -d postgres -c 'CREATE DATABASE restored OWNER easydentist'
docker compose -p easydentist-restore -f infra/docker-compose.yml --profile tools \
  run --rm -T --entrypoint pg_restore pg-client \
  -h db -U easydentist -d restored --exit-on-error < easydentist.dump
```

## Validação pós-restore

- `SELECT version_num FROM app.alembic_version` igual ao ambiente de origem.
- Contagem de clinicas, memberships e clinic_settings igual à origem.
- `pg_policies` com a mesma contagem; `relforcerowsecurity` verdadeiro nas seis
  tabelas tenant-aware.
- `rolbypassrls` falso para `easydentist_app` e `easydentist_migrator`.
- Teste funcional como `easydentist_app`: cada contexto de usuário/clínica vê
  somente a própria clínica; contexto ausente ou membership divergente falha
  fechado.
- `alembic check` sem divergências.

## Rotação de credenciais

1. Gerar novos valores para `AUTH_SECRET` e para as senhas de banco/S3/SMTP.
2. Atualizar o segredo no cofre do ambiente e recriar a API e a web.
3. Para senhas de banco: `ALTER ROLE` na role correspondente e atualizar o
   segredo; a API lê a credencial na inicialização.
4. A rotação de `AUTH_SECRET` invalida CSRF emitidos e exige novo login.
5. Registrar data, responsável e motivo da rotação.

## Limites do ambiente local

Mailpit e SeaweedFS são ferramentas locais, sem autenticação de produção. Os
segredos vivem em `infra/.env.example` como valores de desenvolvimento. O
storage local não publica API fora do host; o Mailpit não pode ser exposto.

## Requisitos ainda necessários para produção

- storage gerenciado com criptografia em repouso, controle de acesso e backup;
- verificação antimalware dos uploads antes de disponibilizá-los ao download
  (o M2 valida vazio, tamanho, MIME por magic bytes e SHA-256, mas não inspeciona
  o conteúdo malicioso);
- SMTP autenticado com TLS e domínio verificado;
- retenção, expiração e criptografia dos backups (e teste periódico de restore);
- gestão externa de segredos com rotação automatizada;
- HTTPS terminado em proxy confiável e `TRUSTED_PROXIES` configurado;
- limite de corpo no proxy/ingress em produção: a aplicação rejeita com `413`
  requisições cujo `Content-Length` exceda 11 MiB antes de ler o corpo, mas
  uploads `Transfer-Encoding: chunked` não declaram tamanho e dependem do limite
  imposto pelo proxy/ingress;
- monitoramento e alertas sobre os logs JSON, com retenção definida;
- processo de ciência/assinatura do paciente: concluir a anamnese registra
  autoria e snapshot profissional, mas **não** é assinatura ICP-Brasil nem
  substitui a ciência ou a assinatura do paciente (fora do M2);
- revisão LGPD e jurídica antes da comercialização.
