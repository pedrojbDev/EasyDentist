# M3 — Agenda, profissionais, salas e histórico de status

## Resumo

Entregar uma agenda operacional completa, integrada aos pacientes do M2: cadastrar profissionais e salas, configurar disponibilidade, bloquear horários, marcar e remarcar consultas e acompanhar o atendimento com histórico.

A base será o M2 incorporado em `origin/main`, merge `f94bf29`. Antes da implementação, atualizar a base de trabalho preservando os arquivos locais não rastreados. Manter FastAPI, PostgreSQL, Next.js e os padrões de segurança e interface existentes.

## Comportamento definido

**Profissionais e salas**

- Profissional pertence à clínica e pode existir sem conta. OWNER/ADMIN poderão vinculá-lo a um membro ativo DENTIST ou OWNER, com no máximo um cadastro por membro na clínica.
- O cadastro da agenda terá nome e CRO/UF opcionais, separados do perfil global usado na anamnese. Não haverá sincronização automática nem mudança nas permissões do M2.
- Salas/cadeiras serão recursos individuais, com nome e estado ativo/arquivado. A sala será opcional na consulta.
- Arquivar profissional ou sala exigirá resolver suas consultas pendentes. Os registros históricos permanecerão acessíveis.

**Disponibilidade e marcação**

- Cada profissional terá intervalos semanais de trabalho, permitindo períodos separados para almoço. Sem disponibilidade cadastrada, não poderá receber consultas.
- Bloqueios serão pontuais, vinculados a um profissional ou sala, inclusive por vários dias. Não poderão sobrepor reservas existentes; será necessário remarcá-las ou cancelá-las primeiro.
- Toda consulta terá paciente ativo, profissional ativo, início e duração; sala e observações administrativas serão opcionais.
- A consulta deverá caber integralmente na disponibilidade do profissional. Sobreposições de profissional, paciente ou sala serão rejeitadas; horários consecutivos serão permitidos.
- Reduzir disponibilidade exigirá resolver previamente as consultas futuras afetadas. Nenhuma alteração de configuração moverá consultas automaticamente.
- Horários serão interpretados no fuso da clínica e persistidos como instantes com timezone. Entradas locais inexistentes ou ambíguas por mudança de horário serão rejeitadas.
- Duração inicial do formulário: 30 minutos, editável. Consultas deverão começar e terminar no mesmo dia local.

**Atendimento e histórico**

- Estados: `SCHEDULED`, `CONFIRMED`, `CHECKED_IN`, `IN_PROGRESS`, `COMPLETED`, `CANCELLED` e `NO_SHOW`.
- Fluxo: agendado pode ser confirmado; ambos permitem registrar chegada; chegada permite iniciar; atendimento iniciado permite concluir.
- Agendado e confirmado poderão ser cancelados ou marcados como falta; falta somente após o início previsto. Uma consulta com chegada registrada também poderá ser cancelada.
- Remarcação será permitida antes da chegada, preservará o mesmo ID e retornará o estado para agendado.
- Concluído, cancelado e faltou serão terminais nesta versão. Um novo agendamento será criado quando necessário.
- Criação, remarcação e mudanças de status registrarão autor, horário e valores anteriores/novos. Cancelamentos exigirão motivo administrativo. O histórico não poderá ser alterado ou apagado.
- Concluir uma consulta será uma operação da agenda; não produzirá evolução clínica, assinatura ou cobrança.

**Permissões**

| Papel         | Operação                                                                                                           |
| ------------- | ------------------------------------------------------------------------------------------------------------------ |
| OWNER / ADMIN | Gerenciar cadastros, vínculos, disponibilidades, bloqueios e todas as consultas                                    |
| RECEPTIONIST  | Gerenciar consultas e bloqueios de toda a clínica; consultar cadastros e disponibilidades                          |
| DENTIST       | Consultar a agenda da clínica e gerenciar consultas, disponibilidade e bloqueios do próprio profissional vinculado |
| ASSISTANT     | Consultar a agenda, sem alterações                                                                                 |

O dentista não poderá transferir consultas para outro profissional. As consultas da agenda não incluirão alertas, respostas de anamnese ou documentos clínicos.

## Implementação e contratos

**Persistência e concorrência**

Criar cadastros tenant-aware de profissionais, salas e disponibilidade semanal. Consultas e bloqueios compartilharão uma tabela interna de eventos da agenda, distinguida por tipo, para aplicar as mesmas garantias de ocupação. Os contratos públicos continuarão separados.

- Usar UUID, `clinic_id`, FKs compostas, RLS forçada, `TenantContext` e permissões explícitas.
- Aplicar restrições de exclusão por clínica e recurso com `tstzrange`, intervalo `[início,fim)` e `btree_gist`. Essa combinação permite impedir sobreposições no banco. [Documentação PostgreSQL 17](https://www.postgresql.org/docs/17/rangetypes.html#RANGETYPES-CONSTRAINT)
- Cancelamentos, faltas e bloqueios cancelados liberarão ocupação; consultas concluídas preservarão a reserva histórica.
- Serializar mutações da agenda e alterações de disponibilidade por clínica, usando lock transacional em `clinic_settings`. Arquivamento dos recursos e mudança de timezone participarão da mesma coordenação.
- Consultas carregarão `version`; edições enviarão a versão esperada. Alteração concorrente ou conflito de reserva retornará `409`, sem sobrescrever silenciosamente.
- Gravar evento de histórico e alteração da consulta na mesma transação, com proteção contra `UPDATE/DELETE` do histórico no banco.
- Instalar `btree_gist` pelo provisionamento administrativo, incluindo procedimento para bancos existentes. Não ampliar privilégios da role runtime.

**API**

Todas as rotas abaixo terão prefixo `/api/v1/clinics/{clinic_id}`:

| Recurso                             | Contrato                                                                    |
| ----------------------------------- | --------------------------------------------------------------------------- |
| `/professionals` e `/rooms`         | Listar, cadastrar, consultar, editar, arquivar e restaurar                  |
| `/professionals/{id}/working-hours` | Consultar e substituir disponibilidade semanal                              |
| `/schedule-blocks`                  | Listar, criar, editar e cancelar bloqueios                                  |
| `/appointments`                     | Listar, criar, consultar e editar consultas                                 |
| `/appointments/{id}/reschedule`     | Remarcar com controle de versão                                             |
| `/appointments/{id}/status`         | Aplicar transição de status                                                 |
| `/appointments/{id}/history`        | Consultar histórico paginado                                                |
| `/availability`                     | Buscar horários livres para profissional, paciente, duração e sala opcional |

- Listagens seguirão `{items, total, limit, offset}`. A agenda aceitará período e filtros por profissional, sala, paciente e status.
- Consultas por período serão limitadas a 31 dias por requisição; o frontend carregará todas as páginas necessárias.
- Formulários enviarão data/hora locais e duração; o backend resolverá o fuso da clínica e retornará timestamps com offset.
- Horários livres serão sugestões: salvar sempre repetirá as validações dentro da transação.
- Manter `403` para permissão insuficiente, `404` para referências de outra clínica, `409` para conflito e `422` para entrada inválida.
- Regenerar OpenAPI e tipos TypeScript em cada incremento com alteração de contrato.

**Entrega incremental**

| Incremento                             | Entrega verificável                                                                                                                   |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| **M3.1 — Contrato e fundação**         | Registrar ADR 0011, atualizar arquitetura/modelo/segurança e criar migrations, RLS, restrições de ocupação, versionamento e histórico |
| **M3.2 — Profissionais e salas**       | API e telas de cadastro, vínculo opcional com membro, edição, arquivamento e restauração                                              |
| **M3.3 — Disponibilidade e bloqueios** | Configuração semanal, bloqueios pontuais e busca de horários livres, com proteção contra alterações concorrentes                      |
| **M3.4 — Consultas e atendimento**     | Criação, edição, remarcação, estados, histórico e autorização por profissional, com testes de concorrência                            |
| **M3.5 — Agenda visual**               | Visões diária/semanal no desktop, lista diária no celular, filtros, criação ao clicar em horário e remarcação por formulário          |
| **M3.6 — Fechamento**                  | E2E completo, matriz RBAC, isolamento, redaction, migrations, backup/restauração e documentação operacional                           |

A interface reutilizará os componentes e tokens existentes, com calendário próprio sem arrastar/redimensionar. Incluirá acesso à ficha do paciente, histórico de consultas na ficha, estados de carregamento/erro/vazio e atualização após mutações, ao recuperar foco e a cada 60 segundos enquanto visível.

Cada incremento terminará com verificações e relatório antes de avançar.

## Testes e critérios de aceite

- **Concorrência:** duas marcações conflitantes produzem um sucesso e um `409`; testar profissional, paciente, sala, bloqueio e remarcação.
- **Disponibilidade:** respeitar almoço, dias sem expediente, limites consecutivos, bloqueios de vários dias e redução de horário com consultas existentes.
- **Fusos:** navegador em timezone diferente, virada de dia e horários locais ambíguos/inexistentes. Mudar o fuso da clínica será bloqueado enquanto houver consultas pendentes ou bloqueios futuros ativos.
- **Histórico:** toda mudança gera exatamente um evento; falhas não deixam eventos órfãos; histórico rejeita alteração e exclusão.
- **RBAC e tenancy:** cobrir todos os papéis, dentista tentando alterar agenda alheia, perda de membership, profissional sem conta e IDs de outra clínica em API, repositories e SQL.
- **Integração M2:** paciente arquivado não recebe nova consulta; consultas existentes permanecem disponíveis para acompanhamento e cancelamento; permissões clínicas permanecem preservadas.
- **E2E:** cadastrar profissional/sala, configurar expediente, bloquear horário, agendar paciente, remarcar, registrar chegada/início/conclusão, cancelar e registrar falta.
- **Qualidade:** lint, formatação, typecheck, testes API/web, build, drift OpenAPI, scanner de secrets e verificações de dependências. Validar migrations limpas e upgrade do M2 em banco descartável, além de restauração com dados do M3.

O marco estará concluído quando o fluxo completo funcionar no desktop e celular, sem dupla reserva sob concorrência e sem acesso entre clínicas.

## Premissas e limites

- Liberação para todas as clínicas, sem feature flag, após os testes; configuração inicial de profissionais e disponibilidade será explícita.
- Bloqueios e conflitos serão locais à clínica, sem consultar agendas de outros tenants.
- Não haverá exclusão física de consultas, histórico, profissionais ou salas.
- Observações serão administrativas e ficarão fora de logs, erros e metadata de auditoria; respostas autenticadas continuarão sem cache persistente.
- Ficam fora: recorrência de consultas, encaixes com sobreposição, lista de espera, lembretes, WhatsApp/SMS/e-mail, agendamento público, calendários externos, prontuário, procedimentos, tratamentos e financeiro.
