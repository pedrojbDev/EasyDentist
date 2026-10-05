# Fechamento M3 e preparação M4 — 2026-10-05

## Entrega

A navegação autenticada usa a clínica ativa como contexto, com Agenda,
Pacientes e Visão geral; Ajustes e Equipe ficam na administração. Uma única
clínica ativa abre diretamente a agenda. O menu móvel abre e fecha ao navegar,
e a troca explícita continua disponível para contas com várias clínicas.

O fechamento corrigiu os seguintes problemas encontrados nos gates:

- Dias com mudança de horário de verão à meia-noite agora têm limites válidos;
  apagar o campo de data não invalida a agenda.
- Respostas antigas não substituem o período atual. A resposta de uma mutation
  atualiza a consulta ou bloqueio antes da recarga; a versão salva continua
  disponível mesmo quando o GET falha. O diálogo aguarda a atualização.
- O expediente só pode ser editado após leitura bem-sucedida. Falhas permitem
  nova tentativa, e trocar de profissional invalida os dados anteriores.
- O vínculo de membro ao profissional usa um lock com função administrativa
  restrita ao tenant e a OWNER/ADMIN ativos. A migration 0016 não concede
  UPDATE de memberships à role runtime.
- O catálogo de policies inclui as sete tabelas M3. Os testes de navegador
  usam seletores de acessibilidade e pacientes da própria clínica.

## Verificação executada

| Gate                                            | Resultado                                                            |
| ----------------------------------------------- | -------------------------------------------------------------------- |
| API unitária                                    | 449 testes aprovados                                                 |
| API integração, PostgreSQL e S3 locais          | 418 testes aprovados, sem skips                                      |
| Web                                             | 257 testes aprovados em 60 arquivos                                  |
| Playwright Chromium                             | 29 cenários aprovados, incluindo desktop, celular e isolamento       |
| Scripts de licenças e mitigação braces          | 11 + 3 testes aprovados                                              |
| Ruff, formatação Python, mypy                   | Aprovados                                                            |
| ESLint, Prettier, TypeScript                    | Aprovados                                                            |
| OpenAPI e tipos gerados                         | Sem drift                                                            |
| Build Docker web                                | Aprovado com Node 24.19.0 e pnpm 11.10.0                             |
| Compose, health API/web/proxy e storage privado | Aprovados                                                            |
| Migrations                                      | Upgrade M2 com dados, check, downgrade base e novo upgrade aprovados |
| Backup/restauração                              | Aprovados em banco descartável                                       |
| Scanner de segredos e licenças API/web          | Aprovados                                                            |
| pip-audit                                       | Nenhuma vulnerabilidade conhecida encontrada                         |
| Auditoria JavaScript                            | Aprovada com a mitigação específica descrita abaixo                  |

As verificações usam dados sintéticos e bancos descartáveis para as operações
destrutivas. O teardown E2E remove dados e objetos do próprio run e restaura o
prefixo de storage. Os volumes de desenvolvimento são preservados. As capturas
desktop e mobile foram inspecionadas visualmente. A revisão final não deixou
achados críticos ou importantes pendentes.

O host usa Node 24.21.0; os comandos locais exibem o aviso de versão. A imagem
de produção foi compilada com a versão fixada 24.19.0.

## Dependência com mitigação temporária

`braces@3.0.3`, transitivo do ESLint, ainda recebe o aviso
[GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm).
O patch local limita a profundidade do parser e dos walkers; os testes cobrem
padrões profundos, ASTs externas e globs comuns. O script de auditoria verifica
o patch antes de excluir exclusivamente esse aviso. A auditoria direta
continua mostrando a versão upstream vulnerável. A manutenção e a condição
para remover a mitigação estão em `docs/security.md` e
`docs/third-party-licenses.md`.

## Próximo incremento

O M4 permanece em planejamento, com especificação em
`docs/superpowers/specs/2026-10-05-m4-prontuario-odontograma-design.md` e plano
em `docs/plans/2026-10-05-m4-prontuario-odontograma.md`.

O primeiro incremento, M4.1, revisa o contrato e registra ADR 0012, criando
schema, catálogo de dentes/superfícies, imutabilidade, RLS e testes de
fundação. M4.2/M4.3 entregam evoluções; M4.4/M4.5 entregam odontograma; M4.6
fecha os gates. Nenhuma implementação M4 está incluída neste fechamento.
