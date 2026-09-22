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

## Marco 2

O M2.1 não reutiliza nenhum arquivo do OpenDentist. O catálogo de anamnese
`cfo_2026_v1` (`apps/api/app/anamnesis/templates/cfo_2026_v1.py`) é **redação
própria em pt-BR**, estruturada a partir do Anexo 1 do
[Manual do Prontuário do CFO de 2026](https://website.cfo.org.br/wp-content/uploads/2026/03/CFO_Manual_do_Prontuario_Ebook.pdf),
usado somente como referência normativa de tópicos clínicos: nenhum trecho do
PDF ou do OpenDentist foi copiado ou adaptado. O documento do CFO não é
dependência de software; o material continua fora do repositório e não é
mencionado como código de terceiros. Pacientes, anamnese e documentos do M2
serão implementados do zero, sem backend Hono/D1, schema, nomenclatura ou
componentes do OpenDentist.
