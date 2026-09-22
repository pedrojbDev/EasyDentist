# Modelo de dados planejado

> **Estado (M2.1):** as 14 tabelas do Marco 1 existem como models SQLAlchemy
> (`app/users/models.py`, `app/auth/models.py`, `app/clinics/models.py`) e
> migrations (`0002_global_identity`, `0003_tenant_structure`), com RLS ativo e
> contexto transacional de tenant implementados (`0004_rls_policies`, ADR 0005).
> As tabelas do Marco 2 estão **contratadas** na ADR 0010 (M2.1) e ainda não
> existem: nenhuma migration, model ou rota de pacientes, anamnese ou documentos
> foi criada. Esta referência fixa o modelo que o M2.2 a M2.5 devem implementar.

O M1.1 não cria banco, migration, role ou tabela. Esta referência fixa os
limites para M1.2 e posteriores, evitando que a fundação induza um modelo errado.

## Tabelas globais do Marco 1

| Tabela                    | Responsabilidade                                                  |
| ------------------------- | ----------------------------------------------------------------- |
| `users`                   | identidade canônica, e-mail único global, status e verificação    |
| `password_credentials`    | hash Argon2id e data de alteração                                 |
| `external_identities`     | provider e subject; inicialmente vazio                            |
| `auth_sessions`           | hash de token, expirações, revogação, rotação e metadados mínimos |
| `auth_action_tokens`      | verificação, reset e ações single-use                             |
| `auth_rate_limit_buckets` | janelas e bloqueios atômicos                                      |
| `auth_audit_events`       | eventos de segurança sem escopo clínico                           |
| `email_outbox`            | entrega SMTP idempotente com tentativas                           |

## Tabelas tenant-aware do Marco 1

| Tabela                   | Responsabilidade                                            |
| ------------------------ | ----------------------------------------------------------- |
| `clinics`                | identidade legal, slug e ciclo de vida                      |
| `clinic_settings`        | nome comercial, timezone IANA, locale, moeda e preferências |
| `clinic_feature_flags`   | chave tipada, estado, configuração opcional e auditoria     |
| `memberships`            | vínculo do usuário com clínica e papel                      |
| `membership_invitations` | convite de uso único e validade                             |
| `clinic_audit_events`    | trilha de auditoria clínica/administrativa                  |

## Tabelas globais do Marco 2 (propriedade do usuário)

| Tabela                  | Responsabilidade                                                    |
| ----------------------- | ------------------------------------------------------------------- |
| `professional_profiles` | nome profissional, CRO e UF do usuário, sem vínculo com uma clínica |

Tabelas desta classe **não** têm `clinic_id`. A RLS é por proprietário
(`user_id = app.current_user_id`, sem clínica) e também usa
`FORCE ROW LEVEL SECURITY`; como `user_transaction` e `tenant_transaction`
instalam `app.current_user_id`, o mesmo modelo funciona nas duas transações.

## Tabelas tenant-aware do Marco 2 (propriedade da clínica)

| Tabela              | Responsabilidade                                                        |
| ------------------- | ----------------------------------------------------------------------- |
| `patients`          | cadastro demográfico e administrativo do paciente                       |
| `patient_alerts`    | alergia, medicação, risco clínico ou outro alerta e sua resolução       |
| `anamneses`         | rascunho único e versões finais imutáveis do questionário `cfo_2026_v1` |
| `patient_documents` | metadados de arquivo privado, com checksum e chave opaca de storage     |

Todas usam UUID, `clinic_id NOT NULL`, FK composta `(clinic_id, parent_id)`,
`FORCE ROW LEVEL SECURITY` e grants mínimos por finalidade. A role runtime não
possui `DELETE` em nenhuma delas e não há expurgo neste marco.

## Modelo planejado do Marco 2

### `professional_profiles`

`user_id` (PK, FK `users.id`), `professional_name`, `cro_number`, `cro_state`
(UF de duas letras), `created_at` e `updated_at`. A conclusão de uma anamnese
grava um snapshot desses campos; alterar o perfil não modifica versões
anteriores. A aplicação não valida o CRO em base externa.

### `patients`

`id`, `clinic_id`, `full_name`, `social_name`, `birth_date`, `cpf`, `phone`,
`phone_secondary`, `email`, `postal_code`, `street`, `number`, `complement`,
`district`, `city`, `state`, `occupation`, `nationality`, `birthplace`,
`emergency_contact_name`, `emergency_contact_relationship`,
`emergency_contact_phone`, `guardian_name`, `guardian_relationship`,
`guardian_phone`, `administrative_notes`, `status` (`ACTIVE/ARCHIVED`),
`archived_at`, `created_at` e `updated_at`.

- Nome, nascimento e telefone principal são obrigatórios.
- O CPF é opcional, normalizado para 11 dígitos e validado; o índice único
  parcial `(clinic_id, cpf) WHERE cpf IS NOT NULL` permite o mesmo CPF em
  clínicas diferentes.
- Menores de idade exigem responsável com nome, vínculo e telefone; a regra é
  validada na aplicação, não por `CHECK` volátil sobre a idade.
- `state` é a UF de duas letras; demais formatos são validados na aplicação.
- Arquivar preserva a linha; não há `DELETE`.

### `patient_alerts`

`id`, `clinic_id`, `patient_id`, `kind` (`ALLERGY/MEDICATION/CLINICAL_RISK/OTHER`),
`description`, `status` (`ACTIVE/RESOLVED`), `resolved_at`, `created_by_user_id`,
`created_at` e `updated_at`. Resolver preserva o histórico; não há `DELETE`.

### `anamneses`

`id`, `clinic_id`, `patient_id`, `status` (`DRAFT/FINAL`), `version_number`
(nulo no rascunho, obrigatório na versão final), `template` (`cfo_2026_v1`),
`payload` JSONB, `base_version_id`, `author_user_id`,
`author_professional_name`, `author_cro_number`, `author_cro_state`,
`created_at`, `updated_at` e `finalized_at`.

- Apenas um rascunho por paciente: índice único parcial
  `(clinic_id, patient_id) WHERE status = 'DRAFT'`.
- Numeração sequencial por paciente (`MAX(version_number) + 1`) com
  `UNIQUE (clinic_id, patient_id, version_number)`, atribuída na conclusão sob
  lock do paciente.
- Versões finais bloqueiam `UPDATE` e `DELETE` por trigger; a nova revisão
  nasce de `base_version_id` de uma versão final do mesmo paciente e copia o
  payload como rascunho.
- Concluir exige payload completo validado contra o catálogo e perfil
  profissional do autor, e grava o snapshot de autoria.

### `patient_documents`

`id`, `clinic_id`, `patient_id`, `category` (`ADMINISTRATIVE/CLINICAL`),
`title`, `original_filename`, `detected_mime`, `size_bytes`, `sha256`,
`storage_key`, `uploaded_by_user_id`, `status` (`ACTIVE/ARCHIVED`),
`archived_at`, `created_at` e `updated_at`. O objeto não fica no banco: permanece
em storage privado, com chave opaca sem PII; nenhum endpoint exclui fisicamente
documentos ou objetos. Limite de 10 MB e tipos PDF, JPEG e PNG detectados por
magic bytes.

### Entidades ainda posteriores

Consultas, histórico de status, evoluções clínicas, achados de odontograma,
planos e itens de tratamento, orçamentos, faturamento, catálogo de
procedimentos e salas permanecem nos marcos seguintes. Cada tabela de domínio
terá UUID, `clinic_id NOT NULL`, relações tenant-aware e RLS; temporalidade
usará `timestamptz` e dinheiro será inteiro em centavos. Objetos de documentos
não ficam no banco.
