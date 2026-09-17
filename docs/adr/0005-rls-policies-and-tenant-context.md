# ADR 0005: RLS, contexto de tenant e classes de policy

**Status:** Aceito — M1.2.3, 2026-09-17

## Decisão

O isolamento multi-tenant é enforced pelo PostgreSQL, não apenas pela
aplicação. A role runtime (`easydentist_app`) não é dona das tabelas e não tem
`BYPASSRLS`; as seis tabelas tenant-aware usam `ENABLE` e `FORCE ROW LEVEL
SECURITY`, de modo que o próprio dono (`easydentist_migrator`) também está
sujeito às policies, com a exceção explícita e auditada descrita abaixo.

### Contexto transacional

O contexto é transportado por dois parâmetros de sessão, sempre definidos
dentro da transação com `set_config(..., is_local = true)`, nunca por `SET`
persistente:

- `app.current_user_id` — usuário autenticado;
- `app.current_clinic_id` — clínica ativa solicitada pela rota.

Toda policy lê os parâmetros via `NULLIF(current_setting(name, true), '')`.
Contexto ausente ou vazio produz `NULL`, a comparação não é verdadeira e o
resultado é default-deny (`fail-closed`): zero linhas em leitura e rejeição em
`WITH CHECK`. O mesmo mecanismo protege contra conexões reutilizadas do pool:
ao fim da transação o valor local é descartado e o parâmetro volta ao valor de
reset (string vazia), que o `NULLIF` normaliza para `NULL`.

### Duas classes de policy

`clinics` e `memberships` são **user-scoped**, porque respondem à pergunta
"quais clínicas e vínculos este usuário possui" (seletor de clínica e aceite de
convite), antes de existir uma clínica ativa:

- `clinics`: `SELECT` visível quando existe membership `ACTIVE` do usuário na
  clínica; `UPDATE` tenant-scoped.
- `memberships`: `SELECT` do próprio usuário (`user_id`) somado ao `SELECT`
  tenant-scoped. A role runtime não possui `INSERT`, `UPDATE` ou `DELETE` em
  `memberships`, nem grant nem policy: qualquer escrita direta é negada pelo
  banco, impedindo autopromoção de papel e remoção de vínculos por um membro
  ativo qualquer.

### Consistência de contexto

A transação grava o contexto usado em `session.info`; os repositories validam,
antes de qualquer SQL, que o contexto recebido é o mesmo da transação
(`ensure_context_matches`). Leituras user-scoped (seletor de clínica) valem
dentro de uma transação de tenant quando o usuário coincide; chamadas
tenant-scoped exigem clínica igual. Divergência falha com
`ContextMismatchError`. Sem esse guard, um usuário pertencente a duas clínicas
poderia ter dados da clínica B servidos numa transação aberta para A, caso um
`TenantContext` incorreto chegasse ao repository — as policies user-scoped de
`clinics`/`memberships` permitiriam a leitura.

`clinic_settings`, `clinic_feature_flags`, `membership_invitations` e
`clinic_audit_events` são **tenant-scoped**: exigem
`clinic_id = app.current_clinic_id` **e** a função `app.is_active_member()`.

### Função `app.is_active_member()`

Verificação mínima de membership ativa, `SECURITY DEFINER`, dona
`easydentist_migrator` (não-superuser; a contenção pelo `FORCE` permanece),
`search_path` fixo em `app, pg_temp`, `EXECUTE` revogado de `PUBLIC` e
concedido apenas a `easydentist_app`.

```sql
CREATE FUNCTION app.is_active_member() RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = app, pg_temp
AS $$
  SELECT EXISTS (
    SELECT 1 FROM app.memberships m
    WHERE m.clinic_id::text = NULLIF(current_setting('app.current_clinic_id', true), '')
      AND m.user_id::text   = NULLIF(current_setting('app.current_user_id', true), '')
      AND m.status = 'ACTIVE'
  );
$$;
```

Não há recursão de policies: `clinics` e `memberships` nunca chamam a função
(apenas comparam os parâmetros diretamente), e a função lê `memberships` como
sua dona, que possui a policy permissiva abaixo — que por sua vez não chama
função alguma.

### Exceção do migrator

Com `FORCE ROW LEVEL SECURITY`, o dono também está sujeito às policies. Sem uma
exceção, backfills futuros, o provisionamento operacional e a própria função
`is_active_member()` ficariam bloqueados pelo default-deny. Cada tabela
tenant-aware recebe portanto:

```sql
CREATE POLICY <tabela>_migrator_all ON app.<tabela>
  FOR ALL TO easydentist_migrator USING (true) WITH CHECK (true);
```

A exceção é aceita porque `easydentist_migrator` é uma role trusted, sem login
interativo, sem `BYPASSRLS` e cuja credencial nunca é injetada no processo
normal da API. Qualquer operação da aplicação continua limitada pelas policies
`TO easydentist_app`.

### Tabelas globais

As oito tabelas globais do Marco 1 não têm coluna `clinic_id` e permanecem sem
RLS. O controle é feito pelos grants mínimos por finalidade e pela camada de
aplicação.

### Transições sensíveis

Mudanças de estado de membership (aceite de convite `PENDING → ACTIVE`,
rebaixamento, remoção) não são feitas por escrita direta da role runtime: ela
não tem grant nem policy de escrita em `memberships`, e qualquer tentativa é
negada pelo banco. Essas operações usarão funções `SECURITY DEFINER` dedicadas
e auditadas, desenhadas no M1.3/M1.4, com validação de token e de último
`OWNER` dentro da função.

## Matriz de policies da role `easydentist_app`

| Tabela                   | Classe        | Comandos e escopo                                              |
| ------------------------ | ------------- | -------------------------------------------------------------- |
| `clinics`                | user-scoped   | `SELECT` via membership `ACTIVE`; `UPDATE` tenant-scoped       |
| `memberships`            | ambas         | `SELECT` próprio usuário; `SELECT` tenant-scoped (sem escrita) |
| `clinic_settings`        | tenant-scoped | `SELECT`; `UPDATE`                                             |
| `clinic_feature_flags`   | tenant-scoped | `SELECT`                                                       |
| `membership_invitations` | tenant-scoped | `SELECT`; `INSERT`                                             |
| `clinic_audit_events`    | tenant-scoped | `SELECT`; `INSERT` (append-only; sem `UPDATE`/`DELETE`)        |

Leituras cross-tenant retornam zero linhas e não revelam existência; a camada
HTTP responderá `404` quando os routers existirem (M1.3+).

## Consequências

- Consultas fora de `tenant_transaction`/`user_transaction` falham fechado, o
  que torna o contexto obrigatório por construção e detectável em testes.
- Updates e deletes dos repositories combinarão `id` e `clinic_id` (defesa em
  camadas), mesmo com RLS ativo.
- Qualquer nova tabela tenant-aware deve repetir o padrão: `clinic_id NOT NULL`,
  `UNIQUE (clinic_id, id)`, RLS com `FORCE`, policies das duas classes e a
  policy permissiva do migrator.
- A exceção do migrator precisa ser reavaliada se a credencial de migration
  deixar de ser exclusiva de operação.
