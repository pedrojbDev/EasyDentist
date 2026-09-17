# Divergências encontradas antes do M1.1

| Estado observado                                                                                                      | Resolução compatível com o plano                                                                                                                                                                         |
| --------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A especificação foi solicitada como `PLAN.md`, mas o único arquivo presente é `plan.md`.                              | `plan.md` foi lido integralmente e é a fonte de verdade desta implementação. Nenhum conteúdo foi renomeado sem solicitação explícita.                                                                    |
| O diretório não continha `.git`, código, manifests ou CI.                                                             | A fundação foi criada no diretório atual; a publicação remota permanece pendente da inicialização, autenticação exclusiva em `github.com` como `pedrojbDev` e primeira execução verde do GitHub Actions. |
| A primeira opção de storage S3-compatible, MinIO, declara AGPLv3 e a tag escolhida não estava disponível no registro. | SeaweedFS 4.29, com licença Apache-2.0 e S3 local, substitui MinIO. O plano exige storage S3-compatible, não um produto específico.                                                                      |
| SeaweedFS poderia parecer um serviço pronto para produção.                                                            | É uma dependência exclusiva do Docker Compose local no M1.1. Produção exige storage gerenciado ou signing keys, criptografia e backup explicitamente configurados.                                       |

O M1.1 não inicia M1.2: migrations/Alembic são não aplicáveis neste marco. As
dependências MPL encontradas receberam exceções exatas por pacote, versão e
licença após aviso explícito; MPL continua fora da allowlist geral.

## Extensão `citext` (M1.2.2)

A extensão `citext`, usada por `users.email` e `clinics.slug`, é criada pelo
bootstrap local do PostgreSQL (`infra/postgres/init/001-create-roles.sh`), que
só executa na primeira inicialização de um volume novo. Volumes locais criados
antes do M1.2.2 precisam ser recriados (`docker compose -f
infra/docker-compose.yml down --volumes` antes de subir novamente), mesmo
precedente registrado na ADR 0004. A role de migration não tem privilégio para
criar extensões; por isso a criação pertence ao bootstrap administrativo.

## Ajustes de execução do M1.2

- O registry `FeatureKey` começa vazio, conforme o plano; para exercitar o
  `FeatureFlagService` nos testes foi usado um `StrEnum` local de amostra, sem
  declarar nenhuma chave real em produção.
- O teste de `WITH CHECK` sem contexto usa `clinic_audit_events` (tabela com
  `INSERT` concedido), em vez de `clinic_settings`, cuja negação ocorreria por
  privilégio e não por policy.
- O unitário do registry foi renomeado para `tests/test_feature_keys.py` para
  evitar colisão de basename com o teste de integração no modo prepend do
  pytest.

## Correções após revisão (pré-merge do M1.2)

- **Escrita de membership bloqueada no banco.** A policy `memberships_tenant_all`
  permitia a qualquer membro ativo `INSERT`/`UPDATE`/`DELETE` em `memberships`
  (autopromoção de papel, remoção de vínculos). A role runtime agora tem apenas
  `SELECT` (user-scoped e tenant-scoped) e nenhum grant de escrita; as
  transições ficam reservadas às funções `SECURITY DEFINER` do M1.3/M1.4.
- **Consistência de contexto nos repositories.** `tenant_transaction`/
  `user_transaction` gravam o contexto em `session.info` e cada método de
  repository valida que o contexto recebido coincide com o da transação
  (`ensure_context_matches`), fechando o cenário de usuário pertencente a duas
  clínicas.
- **`verify-migrations.sh` usa projeto Compose descartável**
  (`easydentist-migrations-verify`, porta 5434) e nunca toca nos volumes de
  desenvolvimento; o ciclo completo roda em banco novo e o projeto é removido
  ao final.
- As migrations `0003` e `0004` foram emendadas antes do merge (nunca
  publicadas fora do ambiente local) para incorporar o lockdown de
  `memberships`.

## Decisões de execução do M1.3

- **Sessão explícita nos serviços de token.** `ActionTokenService.issue/consume`
  e `InvitationService.accept` recebem a `AsyncSession` corrente para que a
  linha de outbox (D7) e o reset/aceite (token + credencial + revogação) sejam
  atômicos na mesma transação; o contrato esboçado do plano não fixava a
  assinatura com sessão.
- **`p_display_name` na `provision_clinic_owner`.** O SQL do plano derivava o
  nome comercial do `p_name`; a CLI tem `--display-name` opcional, então a
  função ganhou o parâmetro separado (emenda pré-merge da migration 0007).
- **`ON CONFLICT` em `consume_invitation`.** `ON CONFLICT (user_id)` do SQL do
  plano é ambíguo no plpgsql por causa do parâmetro OUT `user_id`
  (`AmbiguousColumnError`); a emenda pré-merge usa
  `ON CONFLICT ON CONSTRAINT pk_password_credentials`.
- **Rotas do frontend nos links de e-mail.** Escolhidas `/verify-email`,
  `/reset-password` e `/accept-invitation` com fragmento `#token=`; o M1.5 pode
  ajustá-las sem impacto na API (o token viaja no corpo).
- **Auditoria do aceite em duas tabelas.** Além do `invitation.accepted` em
  `clinic_audit_events` gravado pela função, o router registra
  `invitation_accepted` em `auth_audit_events`, conforme a lista do D12.

## Ajustes de execução do M1.4

- **`membership_not_found` separado de `not_permitted` (migration 0008).** O
  SQL esboçado no plano misturava alvo inexistente com falta de permissão
  (403); a tabela de endpoints exige 404 para membership desconhecida ou de
  outro tenant, então a função levanta `membership_not_found` antes das
  checagens de papel, mapeado para `NotFoundError`.
- **DROP e CREATE em `op.execute` separados.** O `asyncpg` não aceita múltiplos
  comandos em um prepared statement; a 0008 emite o `DROP FUNCTION` da
  `consume_invitation` v1 em um statement próprio antes do `CREATE` da v2.
- **Aceite com senha opcional antecipado para o M1.4.4.** A v2 da
  `consume_invitation` mudou a semântica no M1.4.4 (migration), então o schema
  do `POST /invitations/accept` e o `InvitationService` foram adaptados no mesmo
  incremento (`password_required`/`password_not_allowed` → 422) para manter a
  suíte coerente; o endpoint de convite de equipe e seus testes por papel
  permanecem no M1.4.5.
- **`InvalidInputError` (422) no domínio.** Necessário para os erros de valor
  dos guards (`invalid_role`, `password_*`), que não são conflito nem falta de
  permissão.

## Correção após revisão do M1.4 (pré-merge)

- **Funções `SECURITY DEFINER` vinculadas aos GUCs da transação.** As funções
  `create_member_invitation`, `change_member_role` e `remove_membership` agora
  verificam, antes de qualquer outra checagem, se `p_clinic_id` e
  `p_actor_user_id` coincidem com `app.current_clinic_id` e
  `app.current_user_id` (`RAISE EXCEPTION 'context_mismatch'` — mesmo princípio
  do `ensure_context_matches` dos repositories no M1.2). Sem isso, uma chamada
  SQL direta com a role runtime poderia informar o UUID de um OWNER e operar em
  outra clínica. Em consequência, `MembershipService._call` passou a abrir
  `tenant_transaction` (instala os GUCs) em vez de `transaction_scope`, e os
  testes SQL dedicados em `test_membership_function_guards.py` cobrem ausência
  de contexto, ator estrangeiro, clínica estrangeira e o ataque com UUID de
  OWNER. A migration `0008` foi emendada pré-merge para incorporar as guardas.
