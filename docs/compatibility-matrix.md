# Matriz de compatibilidade e versões — M1.1

Avaliada em 2026-09-16. Todas as versões abaixo são estáveis, sem beta, RC ou
canary. Dependências transitivas são resolvidas integralmente em `pnpm-lock.yaml`
e `apps/api/uv.lock`.

| Camada                              | Versão fixada                    | Motivo de compatibilidade                                                                                                   |
| ----------------------------------- | -------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| Node.js                             | 24.19.0 LTS                      | LTS atual, disponível no ambiente, suportado pelo ecossistema Next 15; imagem oficial `node:24.19.0-alpine3.23`.            |
| pnpm                                | 11.10.0                          | Gerenciador escolhido; fixado por `packageManager` e Corepack.                                                              |
| Next.js                             | 15.5.25                          | Última manutenção estável da linha 15, com correções de segurança transitivas; evita avanço desnecessário para Next 16.     |
| PostCSS                             | 8.5.23                           | Override transitivo: corrige CVEs ainda presentes na transitiva do Next 15.5.25 sem migrar de major.                        |
| React / React DOM                   | 19.2.7                           | Release estável maduro, compatível com a faixa React 19 do Next 15.                                                         |
| Tailwind CSS / plugin PostCSS       | 4.1.17                           | Tailwind v4 integrado pelo plugin oficial `@tailwindcss/postcss`; requer Chrome 111+, Safari 16.4+ e Firefox 128+.          |
| shadcn/ui base                      | new-york / neutral               | Componentes locais em React 19 sobre Radix, CSS variables e Lucide; a combinação é suportada com Next 15 e React 19.        |
| TypeScript / compatibilidade ESLint | 5.9.3 / `@eslint/eslintrc` 3.3.7 | TypeScript compatível com Next 15 e React 19; o adaptador suporta os presets legados do Next 15 no flat config do ESLint 9. |
| Vitest                              | 4.1.11                           | Runner de testes unitários do frontend; primeira versão sem CVEs conhecidas no audit atual.                                 |
| Python                              | 3.12.14                          | Último patch da linha 3.12, em suporte de segurança até 2028-10; ecossistema FastAPI/SQLAlchemy consolidado.                |
| uv                                  | 0.12.5                           | Release estável que reconhece CPython 3.12.14; fixado no CI e Docker.                                                       |
| FastAPI                             | 0.141.1                          | Release estável atual da linha compatível com Pydantic 2 e Starlette 1.x corrigido.                                         |
| Uvicorn                             | 0.40.0                           | Servidor ASGI estável compatível com FastAPI.                                                                               |
| Starlette                           | 1.6.0                            | Transitivo de FastAPI, atualizado no lockfile para as correções de segurança; permanece sob controle do framework.          |
| SQLAlchemy / Alembic / asyncpg      | 2.0.44 / 1.16.5 / 0.30.0         | Preparados e lockados para o M1.2 sem introduzir schema agora.                                                              |
| PostgreSQL                          | 17.6                             | Major definido no plano; imagem oficial Alpine com tag exata.                                                               |
| Mailpit                             | 1.27.5                           | SMTP e interface de inspeção local estáveis.                                                                                |
| SeaweedFS                           | 4.29                             | Endpoint S3 compatível local sob Apache-2.0, selecionado em lugar de MinIO (AGPLv3, bloqueada pela política).               |

Fontes de decisão: [ciclo do Node.js](https://nodejs.org/en/about/previous-releases),
[status de Python](https://devguide.python.org/versions/),
[Python 3.12.14](https://www.python.org/doc/versions/),
[Next 15.5](https://nextjs.org/blog/next-15-5),
[correções Next 15.5.25](https://nextjs.org/blog),
[React 19.2](https://react.dev/blog/2025/10/01/react-19-2) e
[FastAPI release notes](https://fastapi.tiangolo.com/release-notes/).

Atualizações são deliberadas: primeiro atualizar a documentação/ADR, depois os
manifests, lockfiles e imagens, e executar a suíte completa de M1.1.
