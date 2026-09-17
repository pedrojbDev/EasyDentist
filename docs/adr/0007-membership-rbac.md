# ADR 0007: membership e RBAC

**Status:** Aceito — M1.4, 2026-09-17

## Contexto

O M1.3 entregou autenticação completa e a role runtime continua proibida de
escrever `memberships`/`clinics` (lockdown do ADR 0005): toda transição de
vínculo passa por funções `SECURITY DEFINER`. O M1.4 implementa o RBAC inicial
do §3 do plano — papéis fixos, permissões em código, default deny — e a gestão
de equipe (convite, troca de papel, remoção) com as garantias de que apenas
OWNER promove OWNER e o último OWNER não pode ser removido nem rebaixado,
inclusive sob concorrência.

## Decisão

### Matriz em código, default deny (D1)

`app/clinics/rbac.py` declara `Role` e `Permission` como `StrEnum`,
`ROLE_PERMISSIONS` como o mapa papel → permissões e `role_allows(role,
permission)` com default deny. No M1.4 existem apenas as permissões dos
endpoints implementados: `clinic:read`, `clinic:update-legal-name`,
`settings:read`, `settings:update`, `memberships:read`,
`memberships:read-contact`, `memberships:manage-role`, `memberships:remove` e
`invitations:create`. Permissões clínicas (anamnese, prontuário, agenda,
odontograma, financeiro) são declaradas no marco que criar cada endpoint;
qualquer permissão não declarada falha.

### Leitura e gestão (D2)

OWNER, ADMIN, DENTIST, ASSISTANT e RECEPTIONIST podem ler clínica, settings e a
lista de vínculos. `memberships:read-contact` (e-mail dos membros),
`settings:update`, `memberships:manage-role`, `memberships:remove` e
`invitations:create` pertencem a OWNER e ADMIN. `clinic:update-legal-name` e
qualquer operação cujo **alvo** seja OWNER ou ADMIN são exclusivas de OWNER.

### Contexto tenant por requisição (D3)

A dependência `get_membership` resolve `Principal` + `clinic_id` da rota,
consulta a membership do usuário pela policy `memberships_user_select` e devolve
`ClinicMembership(TenantContext, Role)`. Sem membership `ACTIVE` a resposta é
404 genérico — o mesmo de clínica inexistente — impedindo enumeração
cross-tenant. Os repositories rodam em `tenant_transaction` e a RLS revalida.

### Transições só em funções SECURITY DEFINER (D4)

A migration `0008_membership_management` cria `create_member_invitation`,
`change_member_role` e `remove_membership`, donas `easydentist_migrator`, com
`search_path` fixo e `EXECUTE` restrito à role runtime. Cada função valida
internamente o papel do actor (defesa em profundidade além do `role_allows`) e
levanta erros nomeados mapeados no service: `not_permitted` → 403,
`last_owner` → 409, `invalid_role` → 422, `password_required` → 422,
`password_not_allowed` → 422 e `invitation_unusable` → 400 genérico.
`invalid_role` (erro do cliente) é verificada e levantada sempre antes das
checagens de permissão do actor.

### Serialização do último OWNER (D5)

`change_member_role` e `remove_membership` adquirem, antes de qualquer lock de
membership e antes da contagem, `SELECT 1 FROM app.clinics WHERE id =
p_clinic_id FOR UPDATE` — um único ponto de lock por clínica, na mesma ordem
para todos os concorrentes. Sem isso, dois OWNERs poderiam se rebaixar ou
remover simultaneamente, ambos contando dois owners e deixando a clínica sem
nenhum. Só depois travam o alvo (`FOR UPDATE`), contam OWNERs `ACTIVE` e
aplicam a guarda (`<= 1` ⇒ `last_owner`). `create_member_invitation` não precisa
da guarda (cria `PENDING`); convite duplicado cai no unique
`(user_id, clinic_id)` ⇒ 409.

### Remoção e histórico (D6)

Remover um vínculo é `DELETE` físico com evento `membership.removed` em
`clinic_audit_events`. O unique `(user_id, clinic_id)` impediria um reconvite
caso a linha permanecesse `SUSPENDED`; o histórico fica na auditoria, não na
constraint.

### Aceite com senha opcional (D7)

`app.consume_invitation` v2 aceita `p_password_hash` nullable com semântica
exclusiva: usuário sem credencial exige senha (cria credencial, revoga todas as
sessões e verifica o e-mail — regra do ADR 0006 preservada); usuário com
credencial ativa apenas a membership, sem tocar em senha ou sessões, e rejeita
com `password_not_allowed` se o cliente enviar senha (nunca sobrescreve
credencial existente nem revoga sessões por engano).

### Convites de equipe (D8)

`POST /clinics/{clinic_id}/invitations` cria membership `PENDING` e invitation
de 72 h na mesma transação, com rate limit compartilhado de recuperação
(3/destinatário/h e 20/IP/h) e e-mail outbox-first (`team-invitation`, pt-BR,
nome da clínica, papel e fragmento `#token=`). Usuário já membro ⇒ 409.

### Dados de contato e identidade (D9, D10)

`PATCH /clinics/{id}` altera apenas `legal_name` (slug é imutável no Marco 1);
settings aceita `display_name`, `timezone`, `locale` e `currency`, com timezone
validada por `zoneinfo`. A lista de membros devolve `id`, `user_id`, `role`,
`status` e `created_at`; `user.email` aparece somente para quem tem
`memberships:read-contact` (OWNER/ADMIN). `GET /clinics` devolve a clínica e o
papel do próprio principal, para o seletor do M1.5. Erros de autorização usam
403 via `PermissionDeniedError`.

### Auditoria (D11)

`membership.invited`, `membership.role_changed`, `membership.removed` e
`invitation.accepted` vão para `clinic_audit_events` com `actor_user_id`;
metadados nunca contêm token, senha, cookie ou IP bruto.

## Consequências

- Nenhuma escrita de vínculo pela role runtime; o RBAC em código é testável sem
  banco e o default deny obriga cada marco a declarar suas permissões.
- A matriz do §5 passa a ser verificável por testes parametrizados (unitários e
  de integração) e o lock por clínica elimina a corrida do último OWNER.
- O aceite de convite de equipe não força troca de senha de quem já tem conta,
  preservando sessões existentes do usuário.
- Permissões clínicas e restrições de RECEPTIONIST/ASSISTANT/ADMIN sobre
  conteúdo clínico permanecem para os marcos que criarem esses endpoints.
