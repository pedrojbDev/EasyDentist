# Modelo de dados planejado

> **Estado (M1.2.3):** as tabelas abaixo existem como models SQLAlchemy
> (`app/users/models.py`, `app/auth/models.py`, `app/clinics/models.py`) e
> migrations (`0002_global_identity`, `0003_tenant_structure`), com RLS ativo e
> contexto transacional de tenant implementados (`0004_rls_policies`, ADR 0005).

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

As entidades pacientes, profissionais, salas, catálogo, anamneses, consultas,
evoluções clínicas, odontograma, tratamentos, orçamentos, faturamento e documentos
são posteriores. Cada tabela de domínio terá UUID, `clinic_id NOT NULL`, relações
tenant-aware e RLS; temporalidade usará `timestamptz` e dinheiro será inteiro em
centavos. Objetos de documentos não ficam no banco.
