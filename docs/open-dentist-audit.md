# Auditoria de reaproveitamento OpenDentist

Referência auditada: commit `65885f0`.

| Classe | Decisão                                                                                                                                                                   |
| ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A      | Primitivos visuais genéricos shadcn e utilitários puramente visuais podem ser regenerados da fonte oficial.                                                               |
| B      | Agenda, pacientes, formulários, plano de tratamento, timeline e odontograma poderão ser adaptados em marcos posteriores.                                                  |
| C      | Tipos, nomenclaturas, fluxos clínicos, financeiro, laboratório, seguros e relatórios são somente referência.                                                              |
| D      | Não usar backend Hono/D1, schema atual, roteamento/estado globais, seed por requisição, exclusão clínica destrutiva, branding ou pacotes `@clawnify/*` sem licença clara. |

No M1.1 nenhum arquivo do OpenDentist foi copiado ou adaptado. `@clawnify/app`,
`@clawnify/db` e `@clawnify/routes` permanecem proibidos. `react-odontogram`, se
usado no Marco 4, ficará atrás de adaptador próprio e terá a licença MIT revisada
na versão concreta escolhida.

Antes de cada adaptação: confirmar licença, registrar URL/origem/commit/licença e
alterações em `THIRD_PARTY_NOTICES`, preservar aviso MIT e passar a allowlist.
GPL, AGPL, SSPL e copyleft equivalente bloqueiam integração; MPL, LGPL e licenças
incomuns exigem revisão manual explícita.
