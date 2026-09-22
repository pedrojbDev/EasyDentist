# Política de licenças de terceiros

## Política

A allowlist é MIT, BSD-2-Clause, BSD-3-Clause, ISC e Apache-2.0. GPL, AGPL,
SSPL ou copyleft equivalente são reprovados. MPL, LGPL, licenças proprietárias,
desconhecidas ou ambíguas exigem revisão humana antes de serem aceitas.

## Verificação automatizada

- JavaScript: `pnpm run licenses` percorre o grafo efetivo de dependências
  diretas e transitivas, incluindo ferramentas de desenvolvimento, informado
  pelo `pnpm`, e falha fora da allowlist.
- Python: `uv run python scripts/check_licenses.py`, a partir de `apps/api`,
  percorre todas as distribuições instaladas por `uv sync --locked --all-groups`,
  incluindo ferramentas de desenvolvimento e dependências transitivas, e falha
  para licenças fora da allowlist ou sem classificação permitida.
- Vulnerabilidades: `pnpm run audit` e `uv run pip-audit`.

Os comandos fazem parte de `.github/workflows/ci.yml`. Qualquer exceção precisa
ser documentada neste arquivo com pacote, versão, licença, motivo, responsável e
data de reavaliação.

## Marco 2

O M2.1 não introduz nenhuma dependência de terceiros: o catálogo
`cfo_2026_v1` é redação própria e o contrato vive em documentação e código do
projeto. Dependências previstas para os próximos incrementos — o cliente S3
(`boto3`) e `python-multipart` no M2.5 — só entram acompanhadas de lockfile
atualizado, verificação de licenças, `pip-audit` e registro neste arquivo no
mesmo incremento. O Manual do Prontuário do CFO de 2026 é referência clínica
externa, não um pacote ou dependência de software.

## Revisões manuais registradas

| Pacote                       | Versão       | Licença         | Motivo                                                                                                                       | Responsável             | Revisão                                   |
| ---------------------------- | ------------ | --------------- | ---------------------------------------------------------------------------------------------------------------------------- | ----------------------- | ----------------------------------------- |
| `certifi`                    | 2026.7.22    | MPL-2.0         | Transitiva de HTTP/auditoria; exceção restrita à versão, sem modificação de seus arquivos.                                   | EasyDentist maintainers | 2026-09-16; reavaliar em cada atualização |
| `defusedxml`                 | 0.7.1        | PSF-2.0         | Transitiva de auditoria; licença permissiva, sem copyleft.                                                                   | EasyDentist maintainers | 2026-09-16; reavaliar em cada atualização |
| `greenlet`                   | 3.5.6        | MIT AND PSF-2.0 | Transitiva de SQLAlchemy/Alembic; ambas as licenças são permissivas.                                                         | EasyDentist maintainers | 2026-09-16; reavaliar em cada atualização |
| `pathspec`                   | 1.1.1        | MPL-2.0         | Transitiva de mypy; exceção restrita à versão de ferramenta de desenvolvimento.                                              | EasyDentist maintainers | 2026-09-16; reavaliar em cada atualização |
| `typing-extensions`          | 4.16.0       | PSF-2.0         | Dependência transitiva de FastAPI/Pydantic; licença permissiva, sem copyleft.                                                | EasyDentist maintainers | 2026-09-16; reavaliar em cada atualização |
| `argparse`                   | 2.0.1        | Python-2.0      | Transitiva de ferramenta de desenvolvimento; licença Python permissiva, sem copyleft.                                        | EasyDentist maintainers | 2026-09-16; reavaliar em cada atualização |
| `axe-core`                   | 4.13.0       | MPL-2.0         | Transitiva de lint; exceção restrita à versão de ferramenta.                                                                 | EasyDentist maintainers | 2026-09-16; reavaliar em cada atualização |
| `caniuse-lite`               | 1.0.30001810 | CC-BY-4.0       | Base de compatibilidade transitiva do Next.js; manter atribuição e reavaliar antes de qualquer redistribuição de seus dados. | EasyDentist maintainers | 2026-09-16; reavaliar em cada atualização |
| `language-subtag-registry`   | 0.3.23       | CC0-1.0         | Registro de subtags transitivo de ferramenta; dedicação de domínio público.                                                  | EasyDentist maintainers | 2026-09-16; reavaliar em cada atualização |
| `lightningcss`               | 1.30.2       | MPL-2.0         | Transformador CSS transitivo de build; exceção restrita à versão.                                                            | EasyDentist maintainers | 2026-09-16; reavaliar em cada atualização |
| `lightningcss-linux-x64-gnu` | 1.30.2       | MPL-2.0         | Binário Linux transitivo de lightningcss; exceção restrita à versão.                                                         | EasyDentist maintainers | 2026-09-16; reavaliar em cada atualização |
| `minimatch`                  | 10.2.6       | BlueOak-1.0.0   | Transitiva de ferramenta; licença permissiva, sem copyleft.                                                                  | EasyDentist maintainers | 2026-09-16; reavaliar em cada atualização |
| `tslib`                      | 2.8.1        | 0BSD            | Runtime transitivo; licença permissiva equivalente a domínio público.                                                        | EasyDentist maintainers | 2026-09-16; reavaliar em cada atualização |

Os registros executáveis das exceções ficam em
`apps/api/scripts/license-exceptions.json` e `scripts/js-license-exceptions.json`.

As exceções MPL acima foram registradas após aviso explícito e autorização para
prosseguir. Elas não ampliam a allowlist: qualquer outro pacote, versão ou texto
de licença MPL permanece bloqueado para revisão humana.

## Infraestrutura local

SeaweedFS 4.29 é usado como storage S3-compatible local. Seu repositório oficial
declara Apache-2.0, que pertence à allowlist. MinIO foi descartado porque sua
imagem oficial declara AGPLv3, bloqueada pela política do projeto.

O pacote opcional `sharp` do Next.js é explicitamente ignorado pelo pnpm: ele não
é necessário nesta fundação e sua cadeia inclui `libvips` sob LGPL. A otimização
de imagens deverá ser avaliada por revisão de licença quando houver um caso de
uso no produto.
