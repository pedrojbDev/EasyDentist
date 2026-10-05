# M4 — Prontuário e odontograma: plano de implementação

> **Para agentes executores:** use `executing-plans` para executar
> um incremento por vez, ou `subagent-driven-development` quando
> houver autorização para delegação. Os checkboxes acompanham a execução.

**Objetivo:** entregar evoluções clínicas e odontograma com autoria profissional,
histórico imutável, RBAC e isolamento por clínica.

**Arquitetura:** dois módulos do monólito (`clinical_records` e `odontogram`),
PostgreSQL como autoridade, frontend sob contratos OpenAPI e adaptador gráfico
substituível. Reutilizar pacientes, perfil profissional e agenda de M2/M3.

**Stack:** Python 3.12.14, FastAPI/SQLAlchemy/Alembic existentes; PostgreSQL 17.6;
Node 24.19.0, pnpm 11.10.0, Next 15.5.25, React 19.2.7 e Tailwind 4.1.17.

**Especificação:**
`docs/superpowers/specs/2026-10-05-m4-prontuario-odontograma-design.md`.
**Estado:** planejamento proposto; implementação não iniciada.

## Restrições globais

- Interface e documentação pt-BR; código, tabelas e endpoints em inglês.
- UUID, clinic_id obrigatório, FKs compostas e RLS FORCE em cada tabela nova.
- Runtime sem BYPASSRLS, sem DELETE clínico e sem UPDATE em registros finais.
- Perfil profissional completo na autoria; não confiar em autor do payload.
- Finalização e retificação não alteram consulta M3 nem geram financeiro.
- Conteúdo clínico fora de logs/auditoria/erros, URLs e persistência do navegador.
- Preservar versões fixadas e licenças permitidas; contratos vêm do OpenAPI.
- Cada incremento termina com testes, relatório e revisão antes do seguinte.
- Não implementar M5/M6 junto com este marco.

## Estrutura e interfaces

Criar em `apps/api/app/clinical_records/`: `models.py`, `schemas.py`,
`repository.py`, `service.py`, `routers.py`. Separar persistência, contrato,
regras transacionais e HTTP. Criar a mesma estrutura em `app/odontogram/`,
com `projection.py` para o último evento e `tooth_catalog.py` para validação.
Registrar modelos em `app/models.py` e routers em `app/application.py`.

Frontend em `apps/web/src/features/clinical-records/` e
`apps/web/src/features/odontogram/`: `api.ts`, `server.ts`, componentes e testes.
Rotas em `src/app/(app)/clinics/[clinicId]/patients/[patientId]/records/page.tsx`
e `.../odontogram/page.tsx`, com params Promise e tratamento 403/404 existente.

Todos os endpoints têm prefixo
`/api/v1/clinics/{clinic_id}/patients/{patient_id}`:

| Endpoint                                           | Operação                                             |
| -------------------------------------------------- | ---------------------------------------------------- |
| GET `/clinical-entries`                            | Finais e retificações paginados, occurred_at/id desc |
| POST `/clinical-record-drafts`                     | Criar rascunho próprio, original ou retificação      |
| GET/PATCH `/clinical-record-drafts/{draft_id}`     | Ler/editar próprio rascunho, expected_version        |
| POST `/clinical-record-drafts/{draft_id}/finalize` | Finalizar uma vez, expected_version                  |
| GET `/odontogram`                                  | Projeção dos achados e versões atuais                |
| POST `/odontogram/findings`                        | Identidade e evento inicial na mesma transação       |
| POST `/odontogram/findings/{finding_id}/events`    | Corrigir/resolver, expected_sequence                 |
| GET `/odontogram/findings/{finding_id}/events`     | Histórico imutável paginado                          |

Listagens: `{items, total, limit, offset}`, limite padrão 20 e máximo 100.
POST de rascunho/evento retorna 201; PATCH e finalize 200. As referências a
appointment_id/clinical_entry_id devem ser do mesmo paciente e clínica.

## M4.1 — Contrato e fundação verificável

**Arquivos:** criar `docs/adr/0012-m4-clinical-records-odontogram.md`,
`app/clinical_records/models.py`, `app/clinical_records/schemas.py`,
`app/odontogram/models.py`, `app/odontogram/schemas.py`,
`app/odontogram/tooth_catalog.py`, migrations após a revisão 0016;
testes em `tests/integration/test_m4_foundation.py` e
`tests/test_odontogram_catalog.py`. Modificar `app/models.py`,
`app/clinics/rbac.py`, `docs/{architecture,data-model,security}.md`.

**Consome:** Base, TenantContext, ProfessionalProfile e modelos M2/M3.
**Produz:** ClinicalRecordDraft, ClinicalEntry, OdontogramFinding,
OdontogramEvent e schemas DraftCreate/DraftUpdate/DraftFinalize,
ClinicalEntryResponse, FindingCreate/FindingEventCreate, OdontogramResponse.
Schemas aceitam extra=forbid. Definir expected_version/sequence positivos.

- [ ] Revisar a especificação com o usuário e registrar ADR 0012 como aceito.
- [ ] Criar testes de catálogo para 11, 18, 48, 51, 85; rejeitar 19/49/56,
      OCCLUSAL em 11 e INCISAL em 16. Achado inteiro aceita surfaces vazias.

```python
def test_surface_matches_tooth():
    validate_tooth(16, [ToothSurface.OCCLUSAL])
    with pytest.raises(InvalidInputError):
        validate_tooth(11, [ToothSurface.OCCLUSAL])
```

- [ ] Executar `.venv/bin/pytest tests/test_odontogram_catalog.py`; confirmar
      falha antes de criar `validate_tooth(tooth_code: int, surfaces: list[ToothSurface]) -> None`.
- [ ] Criar schema conforme desenho, índices `(clinic_id, patient_id, occurred_at, id)`,
      unique por draft_id e por `(finding_id, sequence)`, FKs compostas,
      version >= 1, triggers imutáveis e policies/grants mínimos.
- [ ] Testar SQL direto com runtime: sem contexto não lê; contexto A não lê
      B; UPDATE/DELETE de final/evento falha; retificação/consulta de outro
      paciente falha mesmo dentro da mesma clínica. Rascunho é owner-scoped.
- [ ] Testar trigger com migrator para provar que a imutabilidade não depende
      apenas da ausência de grant runtime.
- [ ] Rodar migrations em banco descartável: upgrade M3 populado, check,
      downgrade quando reversível e upgrade limpo. Preservar dados M3.
- [ ] Commit: `feat: add M4 clinical record and odontogram foundation`.

## M4.2 — Evoluções e retificações pela API

**Arquivos:** criar `app/clinical_records/{repository,service,routers}.py`,
`tests/integration/test_clinical_entries.py` e `test_clinical_entries_concurrency.py`.
Modificar `app/application.py`, testes RBAC e OpenAPI gerado.

**Consome:** schemas/modelos M4.1 e transactions/clock/profile existentes.
**Produz:** ClinicalRecordService.create_draft, update_draft, finalize_draft
e list_entries; métodos recebem TenantContext, role e IDs da rota. O repository
nunca inicia ou confirma transação por conta própria.

- [ ] Escrever teste HTTP criar → editar com version 1 → finalizar com
      version 2 → repetir finalize e obter o mesmo ID. Atualização obsoleta 409.
- [ ] Rodar `.venv/bin/pytest tests/integration/test_clinical_entries.py -x`
      com TEST\_\* URLs e confirmar falha antes das rotas.
- [ ] Implementar autorização e leitura do paciente antes de qualquer escrita.
      Validar perfil do ator; copiar nome/CRO/UF para o registro final.
- [ ] Usar trava do rascunho e transação única: validar versão, inserir final,
      atualizar finalized_entry_id/version e inserir auditoria sem conteúdo.
      Se já finalizado pelo mesmo autor, retornar o registro existente.
- [ ] Retificação cria novo draft com correction_of_id e correction_reason;
      permitir retificação de paciente arquivado e exigir referência final
      do mesmo paciente. Original permanece legível.
- [ ] Testar duas finalizações concorrentes: um registro final e um ID
      retornado pelas duas requisições, sem duplicate audit/evento.
- [ ] Testar todos os papéis, autoria falsificada, perda de membership,
      XSS como texto, perfil incompleto, datas futuras e referências cruzadas.
- [ ] Regenerar OpenAPI/tipos, rodar drift e suíte API. Commit:
      `feat: deliver immutable clinical entries API`.

## M4.3 — Prontuário na ficha do paciente

**Arquivos:** criar `features/clinical-records/{api,server}.ts`, componentes
`ClinicalTimeline.tsx`, `ClinicalDraftForm.tsx`, `ClinicalEntryDetails.tsx`
e seus `.test.tsx`; rota `.../records/page.tsx`; E2E
`apps/web/e2e/clinical-records.spec.ts`. Modificar a ficha do paciente.

**Consome:** OpenAPI M4.2, API clients, feedback/confirm UI existentes.
**Produz:** fluxo desktop/celular de histórico final e rascunho próprio.

- [ ] Testar formulário: salvar mantém rascunho editável; finalizar pede
      confirmação; falha 409 preserva o texto e oferece recarregar a versão.
- [ ] Implementar texto simples, campos e limites do desenho; distinguir
      “Salvo como rascunho” de “Evolução finalizada”. Não usar autosave.
- [ ] Mostrar original/retificações com autor, CRO/UF, occurred_at/finalized_at
      e motivos. Rascunho de outro autor nunca vem para o browser.
- [ ] Ocultar ações conforme papel e perfil; backend continua responsável.
- [ ] E2E com OWNER profissional e ASSISTANT: criar, finalizar, retificar,
      consultar histórico e comprovar que o leitor não consegue alterar.
- [ ] Validar 390px, teclado, foco, estado vazio/erro e ausência de overflow.
- [ ] Commit: `feat: add patient clinical record workflow`.

## M4.4 — Achados e histórico do odontograma

**Arquivos:** criar `app/odontogram/{repository,projection,service,routers}.py`,
testes `tests/integration/test_odontogram_events.py` e
`test_odontogram_concurrency.py`; modificar application/OpenAPI/tipos.

**Consome:** catálogo/modelos M4.1 e ClinicalEntry M4.2.
**Produz:** OdontogramService.record_finding, append_event, get_projection,
list_events. Projection retorna último evento de cada finding_id com sequence.

- [ ] Escrever teste registrar → corrigir (sequence 1) → resolver (sequence 2):
      3 eventos preservados, projeção resolvida, payload anterior legível.
- [ ] Rodar teste e confirmar falha antes de implementar os endpoints.
- [ ] Implementar criação de identidade/evento atômica e trava da identidade
      na adição de evento. Bloquear alterações após RESOLVED, exigir motivo
      para CORRECTED/RESOLVED, validar perfil/FDI/superfícies e referência final.
- [ ] Projeção não atualiza eventos passados. Usar latest-by-sequence por
      finding_id, filtrado por TenantContext/paciente.
- [ ] Testar duas alterações com expected_sequence igual: uma 201 e uma 409,
      sem perda de histórico; SQL direto não altera/apaga evento.
- [ ] Testar paciente arquivado, IDs A/B e referências de outro paciente.
- [ ] Regenerar tipos e commit: `feat: add versioned odontogram findings API`.

## M4.5 — Odontograma visual com alternativa acessível

**Arquivos:** criar `features/odontogram/{api,server,types}.ts`, componentes
`OdontogramAdapter.tsx`, `ToothFindingList.tsx`, `FindingForm.tsx`,
`FindingHistory.tsx` e testes; rota `.../odontogram/page.tsx`; E2E
`apps/web/e2e/odontogram.spec.ts`. Atualizar auditoria/licenças se houver reúso.

**Consome:** projeção M4.4. **Produz:** contrato visual independente:

```typescript
type ToothSelection = { toothCode: number; surfaces: ToothSurface[] };
type ToothSurface = 'MESIAL' | 'DISTAL' | 'VESTIBULAR' | 'LINGUAL' | 'OCCLUSAL' | 'INCISAL';
type ToothFinding = {
  id: string;
  toothCode: number;
  surfaces: ToothSurface[];
  description: string;
  sequence: number;
  status: 'ACTIVE' | 'RESOLVED';
};
type OdontogramAdapterProps = {
  findings: ToothFinding[];
  readOnly: boolean;
  dentition: 'PERMANENT' | 'DECIDUOUS' | 'MIXED';
  onSelect: (value: ToothSelection) => void;
};
```

- [ ] Executar experimento de `react-odontogram`: consultar versão/licença
      reais, renderizar React 19/Next SSR e exercitar teclado, FDI decíduo e
      misto. Registrar resultado em `docs/open-dentist-audit.md`.
- [ ] Se aprovado, pin exato e imports somente no adapter. Se não aprovado,
      implementar grade SVG própria e botões acessíveis sob o mesmo contrato;
      esta alternativa deve funcionar sem dependência nova.
- [ ] Testar seleção de 11 e 51, teclado Enter/Espaço, readOnly, legenda
      textual e nenhuma alteração da API quando trocar o renderizador.
- [ ] Implementar lista por dente e histórico, com estados vazio/erro/loading.
      CORRECTED/RESOLVED sempre enviam expected_sequence e motivo explícito.
- [ ] E2E registrar, corrigir, resolver e revisar o evento original; ASSISTANT
      só lê; desktop e 390px sem depender apenas de cores.
- [ ] Verificar licenças/audit/build/tipos e commit:
      `feat: add accessible patient odontogram`.

## M4.6 — Gate e fechamento

**Arquivos:** `tests/integration/test_m4_isolation_gate.py`,
`apps/web/e2e/m4-isolation.spec.ts`, `scripts/verify-migrations.sh`,
`scripts/verify-backup-restore.sh`, README, security/operations/threat-model e
relatório `docs/reports/2026-10-05-m4-completion.md` (data ajustada à entrega).

- [ ] Provar matriz RBAC em API, SSR e SQL runtime para duas clínicas,
      membership revogada, ID adulterado e usuário multi-clínica.
- [ ] Sentinel clínico não aparece em logs/erros/auditoria; private/no-store
      presente; service worker e browser storage não armazenam conteúdo.
- [ ] Backup/restore com evolução, retificação e eventos de achado; confirmar
      autoria, dados originais, RLS e triggers após restauração.
- [ ] Executar gates abaixo e anexar resultados reais ao relatório.

```sh
pnpm lint && pnpm format:check && pnpm test && pnpm build && pnpm typecheck
pnpm gen:api && git diff --exit-code apps/web/src/lib/api/generated
pnpm licenses && pnpm run audit && ./scripts/verify-secrets.sh
pnpm e2e
./scripts/verify-migrations.sh
./scripts/verify-backup-restore.sh
```

Na pasta `apps/api`, com TEST\_\* URLs de banco descartável e S3 de teste:

```sh
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/mypy app scripts && .venv/bin/pytest
.venv/bin/python -m scripts.export_openapi --check
.venv/bin/alembic check
.venv/bin/python scripts/check_licenses.py && .venv/bin/pip-audit
```

- [ ] Revisão antes de merge; corrigir achados críticos/importantes, registrar
      limitações reais. Commit: `test: close M4 clinical isolation gate`.

## Primeiro passo executável

Revisar e aceitar o desenho, criar worktree M4 sobre a main validada e executar
somente M4.1. Apresentar seu relatório antes de avançar para M4.2.
