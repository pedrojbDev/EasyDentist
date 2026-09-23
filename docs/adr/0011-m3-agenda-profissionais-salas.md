# ADR 0011: agenda clínica, profissionais e salas do Marco 3

**Status:** Aceito — implementado no M3, 2026-09-22

## Contexto

O Marco 3 introduz agenda por clínica sem alterar o perfil profissional global
do Marco 2. A agenda precisa preservar isolamento tenant, disponibilidade
semanal, ocupação concorrente segura, histórico e a privacidade das notas
administrativas antes que endpoints ou telas sejam expostos.

## Decisão

`agenda_professionals` é um recurso de agenda da clínica: tem nome, CRO/UF
opcionais, estado `ACTIVE/ARCHIVED` e pode não ter conta. Seu vínculo opcional
`(clinic_id, membership_id)` para `memberships` é único por clínica; o service
valida papel e estado do vínculo antes de gravar. Ele não lê, grava nem
sincroniza `professional_profiles`, que continua sendo um perfil global do
usuário usado somente pelos fluxos de anamnese do M2. `agenda_rooms` representa
uma sala/cadeira individual com o mesmo ciclo ativo/arquivado. Profissionais e
salas não são apagados fisicamente.

`professional_availabilities` armazena intervalos locais semanais por
profissional (`weekday`, `starts_at`, `ends_at`), permitindo vários intervalos
no dia. A ausência de intervalo ativo significa indisponibilidade. Configurar
horário novo desativa as linhas anteriores sem apagá-las; consultas futuras
afetadas devem ser resolvidas antes da troca. Serviços resolvem a entrada local
pela timezone IANA de `clinic_settings`, rejeitando horários ambíguos ou
inexistentes; os instantes persistidos são `timestamptz` e nunca são deslocados.

`schedule_events` é a estrutura interna compartilhada entre consultas e
bloqueios. Um evento contém recursos da mesma clínica, início/fim e estado de
ocupação. Consultas requerem paciente e profissional; sala é opcional.
Exclusion constraints GiST em `(clinic_id, professional_id|patient_id|room_id,
tstzrange(starts_at, ends_at, '[)'))` impedem sobreposição e permitem intervalos
adjacentes. Apenas eventos `OCCUPYING` participam da exclusão: cancelar ou
marcar falta libera a agenda; consultas concluídas permanecem ocupando o
histórico. Bloqueios são liberados mudando o evento para `RELEASED`.

`appointments` referencia um único evento `APPOINTMENT`, mantém o status
`SCHEDULED`, `CONFIRMED`, `CHECKED_IN`, `IN_PROGRESS`, `COMPLETED`,
`CANCELLED` ou `NO_SHOW`, nota administrativa privada e contador `version` para
concorrência otimista. Um trigger sincroniza cancelamento/falta com a ocupação,
preservando a de consultas concluídas; outro trigger impede que uma escrita
direta libere ou reclassifique o evento já vinculado a uma consulta. Os
services validam paciente e profissional ativos, disponibilidade
integral, início/fim no mesmo dia local e duração positiva antes de gravar.

`schedule_blocks` guarda o ciclo de vida público dos bloqueios, separado de
`schedule_events`; seu cancelamento libera a ocupação sem apagar histórico.

`appointment_history` é append-only: registra ator, instante, versão, tipo de
evento (`CREATED`, `RESCHEDULED`, `STATUS_CHANGED`) e estados anterior/novo em
JSONB. Triggers rejeitam `UPDATE` e `DELETE`, e também rejeitam a chave
`administrative_note` em qualquer profundidade do histórico. Notas
administrativas não podem entrar em logs, erros, metadata de auditoria ou cache
persistente.

Todas as sete tabelas são tenant-aware, têm UUID, `clinic_id`, FKs compostas
para recursos da clínica, grants mínimos e `FORCE ROW LEVEL SECURITY`. Policies
da role runtime reutilizam `TenantContext` e `app.is_active_member()` em modo
fail-closed; não há grant `DELETE`. A role migrator tem apenas a policy
administrativa controlada necessária sob RLS forçada.

As mutações de agenda, disponibilidade e arquivamento travam a linha da
`clinic_settings` na transação. A alteração da timezone deve usar a mesma trava
no service. Isso ordena mudanças que poderiam invalidar uma decisão de agenda,
enquanto as exclusion constraints permanecem a autoridade para colisões.

## Provisionamento administrativo

`btree_gist` é necessário para igualdade de UUID nas exclusion constraints. O
bootstrap administrativo local o instala em
`infra/postgres/init/001-create-roles.sh`. Para banco já provisionado, um
administrador do banco deve executar, antes de `alembic upgrade head`:

```sh
psql "$ADMIN_DATABASE_URL" -v ON_ERROR_STOP=1 -c 'CREATE EXTENSION IF NOT EXISTS btree_gist;'
```

A role runtime não recebe `CREATE` em schema ou extensão, nem executa DDL. A
credencial de migration também não é entregue ao processo normal da API.

## Consequências

Rotas, RBAC, validação local, bloqueios e interface implementam esta fronteira.
As operações de criação, reagendamento e mudança de status registram histórico
na mesma transação que altera a consulta.
