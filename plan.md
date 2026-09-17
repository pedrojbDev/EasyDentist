# Especificação técnica e plano incremental — EasyDentist SaaS

## 1. Direção arquitetural

Construiremos um monólito modular próprio, usando o OpenDentist apenas como referência funcional e fonte seletiva de código MIT.

Estrutura:

```text
apps/
  web/                         # Next.js estável compatível, React, TypeScript
    src/app/
    src/components/
    src/features/
    src/lib/api/generated/     # cliente/tipos derivados do OpenAPI
  api/                         # Python estável compatível, FastAPI
    app/
      core/
      auth/
      clinics/
      users/
      patients/
      appointments/
      clinical_records/
      anamnesis/
      odontogram/
      treatments/
      billing/
      documents/
      audit/
    migrations/
    tests/
infra/
  docker-compose.yml
docs/
  architecture.md
  security.md
  data-model.md
  open-dentist-audit.md
  third-party-licenses.md
```

Decisões principais:

- PostgreSQL 17 com schema compartilhado e isolamento por `clinic_id`.
- SQLAlchemy 2 async, Alembic, Pydantic e `asyncpg`.
- As versões de Python, Node.js, React e Next.js serão definidas no M1.1 por uma matriz de compatibilidade, usando apenas releases estáveis e suportadas; versões beta, RC e canary não serão usadas.
- A seleção priorizará compatibilidade comprovada entre framework, bibliotecas, ferramentas de teste e imagens Docker, em vez de forçar Python 3.13 ou Next.js 16.
- As versões escolhidas serão fixadas em arquivos de runtime, manifests, imagens Docker e lockfiles, com justificativa registrada em ADR.
- Next.js acessará o FastAPI pelo mesmo domínio, sob `/api/v1`.
- OpenAPI será a fonte do contrato; tipos TypeScript serão gerados.
- `pnpm` para o frontend e `uv` para Python.
- PostgreSQL, Mailpit e armazenamento S3 compatível via Docker Compose.
- Sem Redis, microservices ou filas externas no MVP.
- IDs UUID, datas em `timestamptz`, timezone configurável em `clinic_settings` e valores monetários em centavos.
- Interface em português brasileiro; moeda inicial BRL.
- O usuário pode pertencer a várias clínicas.
- A clínica ativa estará na rota, nunca será uma autorização implícita da sessão.

## 2. Política de reaproveitamento do OpenDentist

A auditoria fica vinculada ao commit `65885f0`.

| Classe | Conteúdo |
|---|---|
| A — reutilizar quase sem alteração | Primitivos visuais genéricos shadcn e utilitários puramente visuais, preferencialmente regenerados da fonte oficial |
| B — adaptar | Agenda, telas de pacientes, formulários, visual do plano de tratamento, timeline clínica e integração visual do odontograma |
| C — somente referência | Tipos de domínio, nomenclaturas, fluxos clínicos, financeiro, laboratório, seguros e relatórios |
| D — não utilizar | Backend Hono/D1, schema atual, roteamento próprio, estado global, seed em requisição, exclusão destrutiva de registros clínicos, branding e pacotes `@clawnify/*` sem licença clara |

Regras de licença:

- MIT, BSD, ISC e Apache-2.0 entram na allowlist.
- GPL, AGPL, SSPL e copyleft equivalente bloqueiam a integração até aprovação explícita.
- MPL/LGPL e licenças incomuns exigem revisão manual.
- Todo arquivo adaptado terá origem, commit, licença e alterações registradas.
- Avisos MIT serão preservados em `THIRD_PARTY_NOTICES`.
- Dependências `@clawnify/app`, `@clawnify/db` e `@clawnify/routes` não serão usadas.
- O backend Hono/D1 será descartado.
- O `react-odontogram`, atualmente MIT, ficará atrás de um adaptador próprio para permitir substituição.
- CI verificará licenças e vulnerabilidades em dependências Python e JavaScript.

## 3. Modelo de segurança, autenticação e tenancy

### Autenticação

A autenticação local ficará desacoplada da autorização:

```text
Credencial local ou provider externo
              ↓
Authenticator
              ↓
Principal(user_id, session_id, auth_method)
              ↓
Membership + RBAC + TenantContext
              ↓
Domínio
```

RBAC e domínio conhecerão apenas o `Principal.user_id`, não senhas ou detalhes do provider. Um OIDC externo poderá futuramente autenticar o usuário e emitir a mesma sessão opaca da aplicação.

Configuração da senha:

- Argon2id, versão 19.
- Baseline: 64 MiB, três iterações e paralelismo 1.
- Salt aleatório de 16 bytes e saída de 32 bytes.
- Parâmetros serão recalibrados em produção e hashes antigos atualizados após login.
- Senhas entre 12 e 128 caracteres, permitindo passphrases e sem regras artificiais de composição.

Sessões:

- Token aleatório de 256 bits, codificado em base64url.
- Apenas `SHA-256(token)` será armazenado, pois o token possui alta entropia.
- Comparação em tempo constante.
- Cookie `HttpOnly`, `Path=/`, sem `Domain`, `SameSite=Lax`.
- Produção: cookie `__Host-easydent_session`, `Secure=true` e HTTPS obrigatório.
- Desenvolvimento local: nome separado e `Secure=false`.
- Expiração por inatividade de 12 horas e absoluta de 30 dias.
- `last_seen_at` atualizado no máximo a cada cinco minutos.
- Sem JWT como sessão principal.
- Login sempre cria uma sessão nova.
- Troca ou recuperação de senha revoga todas as sessões e, quando aplicável, emite uma nova sessão para o dispositivo atual.
- Logout individual, revogação de um dispositivo e logout global serão suportados.
- Tokens e cookies nunca aparecerão em logs.

CSRF:

- Todas as mutações exigirão validação de `Origin`/`Referer`.
- Será usado signed double-submit: cookie CSRF legível pelo frontend, header `X-CSRF-Token` e assinatura HMAC validada pelo backend.
- Após login será emitido um novo token CSRF vinculado à sessão.
- Login, logout, recuperação de senha e demais operações sensíveis também serão protegidos.
- CORS permanecerá desativado na topologia same-origin; uma futura separação de domínios exigirá allowlist explícita.

Verificação e recuperação:

- Tokens aleatórios de 256 bits, armazenados somente por hash.
- Links usarão fragmento de URL para evitar token em logs HTTP e `Referer`.
- Verificação de e-mail: validade de 24 horas.
- Recuperação de senha: validade de 30 minutos.
- Convites: validade de 72 horas.
- Tokens serão single-use e consumidos atomicamente.
- Solicitações retornarão respostas genéricas para impedir enumeração de contas.
- Reset não fará login automático e revogará todas as sessões existentes.
- SMTP será abstraído por uma interface; Mailpit será usado em desenvolvimento.

Rate limiting em PostgreSQL, com atualização atômica:

- Login: cinco falhas por conta em 15 minutos e vinte por IP em 15 minutos.
- Recuperação, reenvio e convites: três por destinatário/hora e vinte por IP/hora.
- Bloqueios terão `Retry-After` e backoff progressivo.
- Identificadores e IPs usados como chave serão protegidos com HMAC.
- Headers de proxy só serão aceitos de proxies explicitamente confiáveis.

### Provisionamento inicial

Não haverá cadastro público no Marco 1.

O comando operacional `provision-clinic-owner` receberá e-mail, nome, slug e timezone da clínica. Ele criará:

- usuário sem senha, se ainda não existir;
- clínica em estado de provisionamento;
- configurações iniciais da clínica, incluindo nome comercial e timezone;
- membership `OWNER` pendente;
- convite de uso único enviado por e-mail.

Ao aceitar o convite, o OWNER define a senha, verifica o e-mail e ativa a membership e a clínica. O mesmo mecanismo poderá provisionar tenants adicionais sem expor cadastro público.

### Isolamento multi-tenant

Rotas tenant-aware seguirão:

```text
/api/v1/clinics/{clinic_id}/...
```

`clinic_id` não existirá nos schemas de entrada quando puder ser derivado da rota. O backend sempre o sobrescreverá com o `TenantContext`.

Fluxo obrigatório:

1. Validar cookie e obter `Principal.user_id`.
2. Ler `clinic_id` da rota apenas como tenant solicitado.
3. consultar `Membership(user_id, clinic_id, status=ACTIVE)`;
4. calcular permissões do papel;
5. iniciar transação;
6. definir `app.current_user_id` e `app.current_clinic_id` com `set_config(..., true)`;
7. executar repository e service tenant-aware;
8. RLS validar novamente o tenant e a membership.

Defesas complementares:

- Toda tabela de domínio terá `clinic_id NOT NULL`.
- Repositories tenant-aware exigirão `TenantContext`; não haverá métodos unscoped.
- Updates e deletes usarão simultaneamente `id` e `clinic_id`.
- Relacionamentos usarão FK composta `(clinic_id, parent_id)`.
- PostgreSQL RLS ficará com `FORCE ROW LEVEL SECURITY`.
- A role da aplicação não será dona das tabelas e não terá `BYPASSRLS`.
- Migrations usarão uma role separada.
- Policies falharão quando o contexto estiver ausente ou inválido.
- Uma função `SECURITY DEFINER` mínima e auditada verificará membership ativa; terá `search_path` fixo e owner sem login.
- Tentativas cross-tenant retornarão `404`, evitando revelar a existência do recurso.
- Jobs futuros receberão `TenantContext` explícito.
- Mudanças de membership terão efeito imediato, pois ela será validada em cada requisição.

### RBAC inicial

Permissões serão constantes em código, não papéis customizáveis, e seguirão `default deny`.

- `OWNER`: controle integral do tenant.
- `ADMIN`: configurações, equipe, pacientes, agenda, documentos e financeiro; não assina registros clínicos.
- `DENTIST`: pacientes, agenda, anamnese, prontuário, odontograma, tratamentos, documentos e orçamentos.
- `ASSISTANT`: leitura clínica e apoio operacional; não assina evoluções nem altera diagnóstico definitivo.
- `RECEPTIONIST`: cadastro demográfico, contatos, agenda, documentos administrativos, orçamentos e recebimentos; sem acesso ao conteúdo clínico.
- Apenas OWNER poderá promover outro OWNER.
- O último OWNER não poderá ser removido ou rebaixado.
- Entradas clínicas terão autor profissional e não poderão ser apagadas; correções serão aditivas.
- A matriz completa papel × permissão terá testes unitários parametrizados e testes de integração nos endpoints sensíveis.
- Os testes cobrirão permissões positivas e negativas de `OWNER`, `ADMIN`, `DENTIST`, `ASSISTANT` e `RECEPTIONIST`, incluindo negação cross-tenant para todos os papéis.

### Configurações e feature flags por clínica

Configurações que não representam a identidade estrutural do tenant ficarão fora de `clinics`:

- `clinics` manterá apenas identidade e ciclo de vida, como `id`, nome legal, slug e status.
- `clinic_settings` será uma relação 1:1 tenant-aware com nome comercial, timezone IANA, locale, moeda e `preferences` JSONB para preferências não sensíveis e sem schema próprio.
- Configurações com impacto de segurança ou domínio ganharão colunas tipadas ou tabelas próprias; não serão armazenadas livremente em `preferences`.

Feature flags terão uma abstração única no backend:

- `clinic_feature_flags` armazenará `clinic_id`, chave, estado, configuração opcional, responsável e datas de alteração.
- As chaves e seus defaults serão declarados em um registro tipado central; flags desconhecidas serão rejeitadas e o default será desabilitado.
- O domínio consultará `FeatureFlagService.is_enabled(TenantContext, FeatureKey)`, sem SQL direto e sem condicionais baseadas em plano espalhadas pelos módulos.
- Flags serão tenant-aware, protegidas por RLS e auditadas.
- Não serão implementados planos, Stripe, billing SaaS ou regras comerciais de assinatura no Marco 1.

## 4. Banco, interfaces e execução do Marco 1

### Modelo inicial

Tabelas globais do Marco 1:

- `users`: identidade canônica, e-mail global único, status e verificação.
- `password_credentials`: hash Argon2id e data de alteração.
- `external_identities`: provider e subject, inicialmente vazio.
- `auth_sessions`: hash do token, expirações, revogação, rotação e metadados minimizados.
- `auth_action_tokens`: verificação, reset e ações de uso único.
- `auth_rate_limit_buckets`: janelas e bloqueios.
- `auth_audit_events`: eventos de segurança sem escopo clínico.
- `email_outbox`: entrega SMTP com tentativas idempotentes.

Tabelas tenant-aware do Marco 1:

- `clinics`: identidade legal, slug e ciclo de vida do tenant.
- `clinic_settings`: nome comercial, timezone IANA, locale, moeda e preferências da clínica.
- `clinic_feature_flags`: flags tipadas e configurações opcionais por tenant.
- `memberships`
- `membership_invitations`
- `clinic_audit_events`

Entidades previstas para os marcos seguintes:

- pacientes e alertas;
- profissionais, salas e catálogo de procedimentos;
- anamneses versionadas;
- consultas e histórico de status;
- evoluções clínicas append-only;
- achados de odontograma com histórico de resolução;
- planos e itens de tratamento;
- orçamentos com snapshots;
- faturas, itens, pagamentos e alocações;
- documentos com checksum e objeto privado.

Documentos ficarão em storage privado; PostgreSQL guardará somente metadados, checksum, MIME type, tamanho e chave opaca.

### API pública do Marco 1

Autenticação:

- `GET /api/v1/auth/csrf`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `POST /api/v1/auth/logout-all`
- `GET /api/v1/auth/me`
- `GET /api/v1/auth/sessions`
- `DELETE /api/v1/auth/sessions/{session_id}`
- `POST /api/v1/auth/email-verification/resend`
- `POST /api/v1/auth/email-verification/confirm`
- `POST /api/v1/auth/password/forgot`
- `POST /api/v1/auth/password/reset`

Tenancy:

- `GET /api/v1/clinics`
- `GET /api/v1/clinics/{clinic_id}`
- `PATCH /api/v1/clinics/{clinic_id}`
- `GET /api/v1/clinics/{clinic_id}/settings`
- `PATCH /api/v1/clinics/{clinic_id}/settings`
- `GET /api/v1/clinics/{clinic_id}/memberships`
- `PATCH /api/v1/clinics/{clinic_id}/memberships/{membership_id}`
- `DELETE /api/v1/clinics/{clinic_id}/memberships/{membership_id}`
- `POST /api/v1/clinics/{clinic_id}/invitations`
- `POST /api/v1/invitations/accept`

Tokens de verificação, reset e convite serão enviados no corpo, nunca na rota. Erros usarão Problem Details e incluirão `request_id`, sem detalhes que permitam enumeração.

Feature flags não terão endpoints públicos no Marco 1. Serão administradas por configuração operacional e consumidas apenas pela interface interna tipada, até existir um caso de uso real para gestão por UI.

### Incrementos do Marco 1

Regra de execução incremental:

- Apenas um incremento será implementado por vez.
- Ao final de cada incremento serão executados os testes aplicáveis, lint, typecheck, validação das migrations e validação do Docker Compose.
- Migrations serão validadas com criação limpa do banco, upgrade até `head` e checagem de divergência entre metadata e Alembic; downgrade será testado quando a migration for reversível e qualquer exceção será documentada.
- Docker Compose será validado com `docker compose config`, build das imagens, inicialização dos serviços e health checks.
- Decisões e alterações de arquitetura serão registradas nos documentos ou ADRs correspondentes.
- O relatório de conclusão listará arquivos e comportamentos implementados, comandos executados, resultados e pendências.
- O incremento seguinte só começará após a apresentação do relatório do incremento atual ao usuário; não haverá avanço silencioso.

1. **M1.1 — Especificação e fundação**
   - Materializar auditoria, arquitetura, modelo, segurança e ADRs em `docs/`.
   - Avaliar a matriz de compatibilidade e registrar as versões estáveis escolhidas para Python, Node.js, React, Next.js, FastAPI e ferramentas associadas.
   - Criar monorepo, lockfiles, configurações de qualidade e Docker Compose.
   - Subir web, API, PostgreSQL, Mailpit e storage local com health checks.
   - Adicionar CI, verificação de licenças e varredura de dependências.

2. **M1.2 — Banco e tenancy**
   - Criar roles PostgreSQL, migrations globais e tenant-aware, incluindo `clinic_settings` e `clinic_feature_flags`.
   - Implementar contexto transacional, RLS e FKs compostas.
   - Criar repositories que exijam `TenantContext` e a interface tipada de feature flags.
   - Comprovar isolamento com duas clínicas em testes automatizados.

3. **M1.3 — Autenticação**
   - Implementar Argon2id, sessões opacas, cookies, CSRF e rate limiting.
   - Implementar verificação, recuperação, rotação e revogação.
   - Implementar adapters de identidade, e-mail e audit log.
   - Adicionar comando de provisionamento seguro.

4. **M1.4 — Membership e RBAC**
   - Implementar convites, aceitação, alteração de papel e revogação.
   - Aplicar matriz de permissões nos services e routers.
   - Implementar testes parametrizados de autorização para todos os papéis, com atenção explícita às restrições de `RECEPTIONIST`, `ASSISTANT` e `ADMIN`.
   - Proteger último OWNER e impedir elevação indevida de privilégios.

5. **M1.5 — Frontend operacional**
   - Login, recuperação, confirmação de e-mail e aceitação de convite.
   - Seletor de clínica baseado nas memberships retornadas pela API.
   - Gestão básica de clínica, usuários, convites e sessões.
   - Nenhum componente do OpenDentist será copiado neste marco.

6. **M1.6 — Hardening**
   - Testes end-to-end, headers de segurança, logs estruturados e redaction.
   - Teste de restauração do banco e documentação operacional.
   - Revisão de dependências, secrets, cookies, RLS e threat model.
   - Marco concluído somente quando uma segunda clínica não conseguir acessar nenhum dado da primeira.

## 5. Verificação, roadmap e critérios de aceite

Testes obrigatórios do Marco 1:

- Argon2id, rehash e rejeição segura de credenciais.
- Banco contém apenas hashes de tokens.
- Cookies apresentam flags corretas em cada ambiente.
- Expiração idle/absoluta, logout atual, revogação remota e logout global.
- Rotação após login e alteração sensível.
- Tokens expirados, reutilizados ou concorrentes falham.
- Respostas de login/reset não revelam existência de conta.
- Rate limiting é atômico sob concorrência.
- CSRF inválido, ausente ou vindo de origem indevida é rejeitado.
- Membership é consultada novamente em cada contexto clínico.
- Mudança ou revogação de papel tem efeito imediato.
- Requests, repositories, SQL direto e relacionamentos cross-tenant falham.
- RLS falha sem contexto e continua ativa contra consultas incorretas.
- ADMIN não promove OWNER; último OWNER não é removido.
- A matriz papel × permissão cobre todos os papéis e falha por padrão para permissões não declaradas.
- RECEPTIONIST não lê nem altera anamnese, prontuário, odontograma ou diagnóstico; ASSISTANT não assina evolução nem diagnóstico definitivo; ADMIN não assina registros clínicos.
- Nenhum papel acessa recursos de outra clínica, mesmo quando conhece IDs válidos do outro tenant.
- `clinic_settings` e `clinic_feature_flags` respeitam TenantContext, RLS e auditoria.
- Flags desconhecidas ou ausentes permanecem desabilitadas, e módulos consumidores usam somente `FeatureFlagService`.
- Logs e auditoria não contêm senha, cookie ou token.
- O contrato do `Authenticator` passa tanto com provider local quanto com um provider fake.
- Fluxos web completos passam em Playwright.

Roadmap posterior:

- **Marco 2:** pacientes, anamnese e documentos.
- **Marco 3:** agenda, profissionais, salas e histórico de status.
- **Marco 4:** prontuário append-only e odontograma adaptado.
- **Marco 5:** plano de tratamento e orçamentos.
- **Marco 6:** financeiro básico.
- **Marco 7:** piloto real, backup/restauração, exportação, observabilidade, revisão LGPD e segurança.

Premissas:

- Cadastro público e cobrança de assinatura SaaS ficam fora do Marco 1.
- A aplicação começa com uma clínica piloto, mas testes sempre usarão pelo menos dois tenants.
- `America/Bahia` será o timezone padrão de provisionamento, armazenado e editável em `clinic_settings`.
- Não haverá exclusão física de informações clínicas.
- A auditoria técnica de LGPD não substitui revisão jurídica antes da comercialização.
- Reutilização visual do OpenDentist começa somente após a fundação de segurança e tenancy estar validada.
