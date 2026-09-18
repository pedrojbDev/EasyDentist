# Padrão visual do EasyDentist

Este documento é a referência para novas interfaces do produto. O padrão busca uma experiência clínica, serena, confiável e eficiente em desktop e celular.

## Princípios

- Priorize clareza, legibilidade e hierarquia antes de decoração.
- Use superfícies claras, azul-petróleo como cor principal e estados semânticos com contraste suficiente.
- Preserve alvos de toque com pelo menos 40 px; campos principais usam 44 px.
- Comece pelo layout mobile e acrescente densidade em telas maiores.
- Mantenha uma ação principal evidente e trate ações destrutivas como exceção.

## Fundação

Os tokens globais vivem em `apps/web/src/app/styles.css`. Use sempre nomes semânticos como `background`, `foreground`, `primary`, `muted`, `border`, `destructive`, `success` e `warning`; não replique cores literais nos componentes.

A tipografia padrão é Geist, carregada no layout raiz. Textos corridos usam no mínimo `text-sm`; campos usam `text-base` para evitar zoom automático no iOS. O raio-base é `0.75rem` e painéis usam sombra sutil.

## Componentes e padrões

- `Button`: use `default` para a ação principal, `outline` ou `secondary` para ações de apoio, `ghost` para ações discretas e `destructive` apenas quando há perda ou revogação.
- `Brand`: identidade compacta para autenticação, navegação e telas vazias.
- `PageHeader`: título, contexto e ações da página.
- `StatusBadge`: estados curtos com tons `neutral`, `info`, `success`, `warning` e `danger`.
- `Feedback`: mensagens persistentes de erro, sucesso ou informação com ícone e sem depender apenas de cor.
- `ConfirmButton`: confirmação explícita para ações destrutivas.
- `AuthShell`: composição única das telas públicas de autenticação.
- `AppShell`, `AppSidebar` e `AppHeader`: estrutura responsiva da área autenticada.
- `ClinicNav`: navegação local das seções de uma clínica.

Utilitários compartilhados:

- `app-panel`: agrupamento visual de conteúdo relacionado.
- `app-label` e `app-field`: rótulos e controles de formulário consistentes.
- `app-link`: link textual com foco visível.
- `feedback-*`: estilos semânticos usados por `Feedback`.

## Responsividade e acessibilidade

Garanta foco visível, rótulos associados aos campos, regiões `alert`/`status` para feedback e texto alternativo apenas quando o ícone acrescenta informação. Tabelas podem rolar horizontalmente dentro do próprio painel; o restante da página não deve criar rolagem lateral. A navegação principal vira barra inferior no celular e lateral em telas grandes.

## PWA

O aplicativo é instalável e online-first. O manifesto está em `apps/web/src/app/manifest.ts`, e os ícones ficam em `apps/web/public/icons`.

Não adicione cache offline de respostas autenticadas, dados clínicos, sessões ou dados pessoais sem uma revisão específica de segurança e privacidade. Quando não há conexão, a interface apenas informa que a reconexão é necessária.

## Checklist para novas telas

1. Reuse os componentes e tokens existentes antes de criar variações.
2. Verifique a tela em largura de celular e desktop.
3. Confirme foco por teclado, rótulos, estados de carregamento, vazio, erro e sucesso.
4. Use uma única ação principal por contexto e confirmação em operações destrutivas.
5. Não armazene dados sensíveis no cliente ou em cache offline.
