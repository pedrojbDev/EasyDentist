# ADR 0004: roles PostgreSQL e migrations

**Status:** Aceito — M1.2.1, 2026-09-16

## Decisão

O PostgreSQL usa três identidades separadas:

- a role administrativa existe somente para inicialização local;
- `easydentist_migrator` é dona do schema `app` e executa Alembic;
- `easydentist_app` é usada pela API, não é dona do schema e não pode executar DDL.

As duas roles da aplicação são `NOSUPERUSER`, `NOCREATEDB`, `NOCREATEROLE`,
`NOINHERIT` e `NOBYPASSRLS`. A API recebe apenas `DATABASE_URL`; a credencial
`MIGRATION_DATABASE_URL` é fornecida exclusivamente ao comando Alembic.
Os acessos públicos `CONNECT` e `TEMPORARY` ao banco são revogados; `CONNECT` é
concedido explicitamente apenas às roles necessárias.

No Compose, migrations rodam em um container de tarefa ativado pelo profile
`tools`; ele encerra após o comando e não integra o runtime da aplicação.

O schema `app` e as roles são criados idempotentemente pelo bootstrap local do
PostgreSQL. Alembic mantém sua tabela de versão nesse schema. A migration
`0001_database_foundation` é uma baseline vazia: tabelas de domínio começam nos
incrementos seguintes.

## Consequências

A role runtime não consegue criar ou alterar objetos, e nunca será dona das
tabelas protegidas por RLS. Migrations continuam com autoridade suficiente para
DDL sem exigir credenciais administrativas. Ambientes existentes anteriores ao
M1.2.1 precisam recriar apenas o volume local de desenvolvimento ou executar o
bootstrap idempotente antes da primeira migration.
