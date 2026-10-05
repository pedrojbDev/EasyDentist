# M4 — Prontuário e odontograma: proposta de desenho

**Estado:** proposta para revisão de produto; nenhuma funcionalidade M4 foi
implementada. Base: M2 e M3 integrados, `plan.md` e ADRs 0003, 0005, 0007,
0010 e 0011. O objetivo é registrar evoluções e achados odontológicos por
paciente, com autoria, histórico imutável e isolamento por clínica.

## Abordagem

Manter dois módulos no monólito: `clinical_records` para evoluções e
`odontogram` para achados. Usar tabelas e transações PostgreSQL; o frontend
apresenta uma projeção do histórico. Essa abordagem reaproveita TenantContext,
RBAC e o perfil profissional do M2 e permite verificar imutabilidade no banco.

Um histórico apenas mutável seria mais simples, mas perderia a prova de quais
informações foram registradas originalmente. Um sistema geral de event sourcing
adicionaria infraestrutura sem necessidade neste marco. A proposta usa eventos
somente no histórico de achados e registros finais append-only nas evoluções.

## Fluxos e limites

- A ficha ganha Prontuário e Odontograma para os papéis autorizados.
- OWNER com perfil profissional completo e DENTIST criam seu próprio rascunho
  e finalizam evoluções. A autoria sempre vem da sessão.
- Um rascunho por paciente e autor, com controle de versão. Salvar é explícito;
  não manter texto clínico em localStorage, cache PWA ou URL.
- Finalizar cria uma evolução imutável e encerra o rascunho na mesma transação.
  Repetir a finalização do mesmo rascunho retorna o mesmo registro.
- Corrigir uma evolução cria uma retificação vinculada ao original. O histórico
  exibe ambos, em ordem; nunca substitui ou oculta o conteúdo anterior.
- A consulta M3 pode ser referenciada se for do mesmo paciente e clínica.
  Finalizar evolução não conclui consulta nem gera cobrança automaticamente.
- Paciente arquivado permite leitura do histórico; bloqueia novos rascunhos originais,
  finalizações e achados. Retificação de registro existente continua permitida.
- A UI usa “Finalizar evolução”. Essa operação registra autoria autenticada;
  não implementa assinatura digital com certificado.
- Ficam fora: prescrição, atestados, assinatura do paciente/certificado,
  periodontal, diagnóstico automático, faturamento e planos de tratamento M5.

## Dados e integridade

`clinical_record_drafts`: UUID, clinic_id, patient_id, author_user_id,
appointment_id opcional, correction_of_id opcional, conteúdo e version.
Conteúdo: occurred_at com timezone, relato/evolução obrigatório (1–10.000
caracteres), procedimentos e orientação opcionais (até 5.000 cada).
Não aceitar datas de ocorrência futuras; ordenar por occurred_at e id.

`clinical_entries`: UUID, clinic_id, patient_id, draft_id único, author_user_id,
occurred_at, finalized_at, conteúdo e snapshot de nome/CRO/UF. Correção
referencia registro da mesma clínica e paciente e exige motivo até 1.000
caracteres. Triggers rejeitam UPDATE/DELETE; role runtime recebe SELECT/INSERT.
Rascunhos finalizados ficam identificados por finalized_entry_id e não podem
ser editados. Não oferecer endpoint DELETE.

Todas as referências a paciente usam FK composta com clinic_id. Adicionar
unique `(clinic_id, patient_id, id)` onde necessário para referências de
correção; usar a mesma integridade para referência à consulta. Timestamps UTC
em banco; exibição no fuso da clínica. Conteúdo em texto simples, renderizado
sem HTML arbitrário. Limites também validados no banco onde forem escalares.

`odontogram_findings`: identidade UUID, clinic_id e patient_id. Não manter
coluna mutável com diagnóstico definitivo nesta tabela.

`odontogram_events`: UUID, clinic_id, patient_id, finding_id, sequence,
event_type `RECORDED/RESOLVED/CORRECTED`, tooth_code, surfaces, description,
clinical_entry_id opcional, author_user_id, snapshot profissional e recorded_at.
O evento inicial registra o achado. RESOLVED preserva o achado anterior e exige
justificativa; CORRECTED registra o novo conteúdo e motivo, mantendo os eventos
originais. Uma resolução é terminal; um novo achado cria outra identidade.

A projeção atual é o último evento por finding_id. Atualizações enviam
expected_sequence; travar a identidade durante a transação e retornar 409 se
a versão divergir. Eventos são append-only, protegidos também no banco.

Usar códigos FDI permanentes 11–18, 21–28, 31–38 e 41–48; decíduos 51–55,
61–65, 71–75 e 81–85. A UI oferece dentição permanente, decídua ou mista.
Superfícies: MESIAL, DISTAL, VESTIBULAR, LINGUAL e OCCLUSAL/INCISAL;
validar OCCLUSAL para posteriores e INCISAL para anteriores. Achado do dente
inteiro usa surfaces vazias. O catálogo inicial é um registro descritivo;
não interpreta o achado como recomendação de tratamento.

## Autorização e privacidade

| Papel        | Ler evoluções/achados | Criar/finalizar/retificar             | Registrar/corrigir/resolver achado    |
| ------------ | --------------------- | ------------------------------------- | ------------------------------------- |
| OWNER        | Sim                   | Com perfil profissional completo      | Com perfil profissional completo      |
| DENTIST      | Sim                   | Sim, com perfil profissional completo | Sim, com perfil profissional completo |
| ASSISTANT    | Sim                   | Não                                   | Não                                   |
| ADMIN        | Não                   | Não                                   | Não                                   |
| RECEPTIONIST | Não                   | Não                                   | Não                                   |

OWNER é um papel administrativo que já possui acesso clínico na matriz atual;
a exigência de perfil completo acrescenta a verificação de autoria profissional.
ADMIN não adquire acesso clínico por gerir a equipe. O backend é a autoridade;
membership revogada impede a requisição seguinte. Rascunhos são visíveis apenas
ao autor; leitores clínicos veem somente registros finais.

RLS forçada, default deny, contexto transacional e grants mínimos seguem M2.
Retornar 403 para falta de papel, 404 para IDs fora do escopo, 409 para versão
ou finalização conflitante e 422 para payload inválido. Logs, Problem Details
e auditoria não incluem conteúdo, achado, motivo ou dados clínicos. Auditoria
operacional usa IDs, tipo de evento e ator. Respostas private, no-store.

## Interface e adaptador do odontograma

O componente visual recebe somente o contrato próprio ToothCode/ToothSurface e
achados projetados; módulos de API não importam tipos de biblioteca visual.
Uma lista por dente, utilizável com teclado e leitor de tela, é a interface
obrigatória e a alternativa no celular. A representação gráfica fica atrás
de `OdontogramAdapter`. Selecionar dente/superfície abre formulário descritivo.

Antes de incorporar `react-odontogram` ou código MIT do OpenDentist, M4.5 terá
um experimento de compatibilidade React 19, SSR, teclado, dentição mista e
licenças transitivas. Registrar versão e origem reais. Se falhar, usar SVG
próprio sob o mesmo contrato, sem bloquear a lista acessível. Não copiar
componentes sem atualizar auditoria e THIRD_PARTY_NOTICES.

## Aceite

Fluxo completo: abrir ficha, salvar rascunho, finalizar, retificar, consultar
histórico, registrar/corrigir/resolver achado e revisar histórico do dente.
Testes cobrem dois tenants, todos os papéis, autoria, perda de membership,
SQL direto, referências de outro paciente, finalização concorrente, versão
obsoleta e tentativa de alterar/apagar registros finais. Backup restaurado
mantém snapshots, triggers e eventos. Desktop e celular sem rolagem lateral,
foco visível, estado vazio, erro recuperável e indicação de gravação.

O primeiro incremento é M4.1 (contrato, permissões e integridade); os módulos
novos só serão implementados após revisão desta proposta e do plano vinculado.
