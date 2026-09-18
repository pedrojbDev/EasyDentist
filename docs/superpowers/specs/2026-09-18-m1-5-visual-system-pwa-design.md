# Sistema visual e PWA enxuta do M1.5

**Data:** 2026-09-18  
**Status:** Aprovado  
**Branch de referência:** `feat/m1-5-frontend-operacional`

## Objetivo

Transformar todas as interfaces do M1.5 em uma experiência coesa, profissional e
responsiva, formalizando o resultado como padrão oficial do EasyDentist. A mudança
preserva integralmente os fluxos, contratos de API, validações, permissões e limites
entre Server e Client Components já entregues pelo M1.5.

O padrão visual aprovado é **clínico e sereno**: azul-petróleo como cor estrutural,
turquesa como destaque de ação, superfícies claras, hierarquia nítida e densidade
moderada. A interface deve transmitir confiança, organização e cuidado sem parecer
hospitalar.

## Escopo

O trabalho cobre todas as rotas existentes do M1.5:

- públicas: `/login`, `/forgot-password`, `/reset-password`, `/verify-email` e
  `/accept-invitation`;
- autenticadas: `/clinics`, `/clinics/{clinicId}`,
  `/clinics/{clinicId}/settings`, `/clinics/{clinicId}/members` e `/sessions`;
- estados de erro, sucesso, vazio, carregamento e confirmação dessas rotas;
- layout responsivo para desktop, tablet e celular;
- fundação instalável de PWA online-first;
- documentação do sistema visual como padrão do projeto.

Não fazem parte deste trabalho novas regras de negócio, novos endpoints, novos
papéis, notificações push, operação offline, sincronização em segundo plano, cache de
dados autenticados ou mudanças na matriz de permissões.

## Direção visual

### Personalidade

- segura e tranquila, sem aparência fria;
- funcional antes de decorativa;
- próxima do vocabulário de clínicas odontológicas, sem ilustrações genéricas;
- clara para usuários administrativos e clínicos com diferentes níveis de domínio
  técnico.

### Tokens

`apps/web/src/app/styles.css` será a fonte dos tokens visuais globais:

- cores semânticas para fundo, texto, marca, ação, borda, foco, sucesso, aviso e
  erro;
- família tipográfica legível e carregada pelo mecanismo de fontes do Next.js;
- escala consistente de espaços, raios e sombras;
- estados de hover, focus-visible, disabled e pending;
- largura e espaçamento responsivos dos shells.

Componentes devem consumir tokens sem repetir valores arbitrários. Cores de estado
nunca serão o único meio de transmitir significado.

## Arquitetura de interface

### Shell público

Um `AuthShell` compartilhado atenderá todas as rotas públicas. No desktop, ele terá
um painel de marca azul-petróleo e uma área clara focada no formulário ou na ação.
No celular, a marca vira um cabeçalho compacto e o conteúdo ocupa a largura útil.

O shell recebe título, descrição e conteúdo sem conhecer regras de autenticação.
Cada fluxo mantém sua lógica atual em seu componente específico.

### Shell autenticado

Um `AppShell` organizará as rotas protegidas:

- navegação lateral persistente no desktop;
- cabeçalho com contexto da rota, atalho para trocar de clínica nas rotas de uma
  clínica específica e ações de conta;
- navegação compacta no tablet;
- cabeçalho e menu acessível no celular, sem depender de hover;
- conteúdo central com largura adequada a formulários, cards ou tabelas.

A clínica ativa continua derivada da rota. A interface pode refletir o papel
retornado pela API, mas o backend permanece a autoridade de autorização.

### Primitivos compartilhados

O sistema terá componentes reutilizáveis para:

- marca, navegação, breadcrumbs e cabeçalho de página;
- botão primário, secundário, discreto e destrutivo;
- campo, select, ajuda e mensagem de validação;
- alertas de erro, feedback de sucesso e estado vazio;
- badge de situação e papel;
- superfície/card e seção de formulário;
- tabela responsiva e ações de linha;
- diálogo de confirmação para ações destrutivas.

As páginas devem compor esses elementos e evitar cadeias extensas de classes
visuais duplicadas. Os componentes de domínio continuam em `features/*`; apenas os
primitivos sem regra de negócio vivem em `components/ui`.

## Aplicação por fluxo

### Autenticação e ações por token

Login, recuperação, redefinição, verificação e convite usarão o mesmo shell e a
mesma linguagem de formulário. A prioridade é uma única ação principal por tela,
com links secundários claros. O token continua somente no fragmento da URL e na
memória do componente, conforme o ADR 0008.

### Clínicas e configurações

A lista de clínicas usará cards de seleção com nome, slug, papel e situação. A
página de clínica passa a ser uma visão de contexto com navegação local para dados
legais, configurações e equipe. Formulários serão agrupados por assunto e manterão
as restrições de edição por papel.

### Equipe

No desktop, a lista de membros e o convite podem ocupar duas colunas. Em telas
estreitas, a lista de membros aparece primeiro e o formulário de convite em seguida,
sem ocultar ações. A tabela terá alternativa responsiva legível e manterá confirmação
para remoção e proteção visual das ações destrutivas.

### Sessões

Sessões serão apresentadas com identificação clara da sessão atual, datas legíveis
e hierarquia entre revogar uma sessão e encerrar todas. Ações que removem o acesso
continuam exigindo confirmação.

## Estados e acessibilidade

- Todo campo mantém `label`, `aria-invalid`, descrição de erro e foco no primeiro
  campo inválido.
- Mensagens de erro ficam próximas da ação que falhou e usam `role="alert"` quando
  exigem atenção imediata.
- Sucessos usam feedback discreto com região de status.
- Botões pending preservam o rótulo contextual, ficam desabilitados e não causam
  mudança brusca de layout.
- Estados vazios explicam a situação e oferecem ação somente quando ela já existe
  no produto.
- Navegação, menus, diálogos e ações de tabela funcionam por teclado e toque.
- Texto principal usa no mínimo 16 px; rótulos recorrentes usam no mínimo 14 px.
- A interface deve permanecer utilizável com ampliação de texto em 200% e em
  larguras a partir de 320 px, sem rolagem horizontal da página.

## PWA online-first

A primeira etapa de PWA será instalável e deliberadamente enxuta:

- `app/manifest.ts` tipado com nome, nome curto, descrição, `start_url`,
  `display: "standalone"`, cores do tema e ícones;
- favicon, ícone Apple e PNGs 192×192 e 512×512 coerentes com a marca;
- metadados de viewport e cor do tema integrados ao App Router;
- experiência responsiva e segura em modo standalone;
- detecção de conectividade para informar que o aplicativo precisa de internet;
- HTTPS como requisito de implantação para instalação.

Não haverá cache de páginas autenticadas, respostas de `/api/v1`, credenciais,
tokens, dados de clínica ou conteúdo sensível. Também não haverá background sync ou
fila de mutações. Como manifest válido e HTTPS atendem ao escopo instalável atual,
esta etapa não adicionará service worker. Uma etapa posterior poderá introduzi-lo
somente após definir uma estratégia explícita de segurança, atualização e cache.

Essa decisão segue a orientação atual do Next.js App Router: manifest nativo e HTTPS
são a base da instalação; suporte offline e service worker são extensões separadas.
Referência: <https://nextjs.org/docs/app/guides/progressive-web-apps>.

## Padrão oficial do projeto

`docs/ui-standards.md` será a referência operacional para novas interfaces. O
documento registrará:

- princípios e personalidade visual;
- tokens e regras de contraste;
- shells e responsividade;
- catálogo dos primitivos compartilhados e quando usar cada um;
- padrões de formulário, tabela, feedback, estado vazio e confirmação;
- requisitos de acessibilidade;
- exemplos mínimos e anti-padrões.

Novas telas devem reutilizar os shells, tokens e primitivos existentes antes de
criar variações. Um novo componente compartilhado deve representar uma necessidade
recorrente, não apenas reduzir algumas classes de uma única tela.

## Fluxo de dados e segurança

O redesenho não muda o fluxo de dados do ADR 0008:

- Server Components continuam buscando dados iniciais pelo cliente server-side;
- Client Components continuam executando mutações pelo cliente browser com CSRF;
- cookies, tokens e headers não ganham armazenamento adicional;
- 401 continua redirecionando globalmente para login;
- 403, 404, 409, 422 e 429 preservam a semântica e as mensagens já testadas;
- permissões continuam sendo verificadas no backend, mesmo quando uma ação não é
  exibida na interface.

## Estratégia de verificação

1. Preservar os testes dos fluxos e mensagens existentes.
2. Adicionar testes focados aos novos shells e primitivos interativos.
3. Atualizar testes de componentes apenas quando a estrutura acessível mudar, sem
   reduzir a cobertura comportamental.
4. Verificar lint, formatação, tipos, testes e build do frontend.
5. Validar visualmente todas as rotas em desktop e celular, incluindo estados de
   erro, sucesso, vazio e pending.
6. Verificar navegação por teclado, foco visível, nomes acessíveis e ausência de
   overflow horizontal.
7. Validar manifest, ícones, modo standalone, comportamento offline informativo e
   ausência de cache de respostas autenticadas.

## Critérios de aceite

- Todas as telas do M1.5 seguem a direção clínica e serena aprovada.
- Shells público e autenticado são consistentes e responsivos.
- Nenhum fluxo, contrato, permissão ou garantia de segurança existente regride.
- Formulários e tabelas mantêm a cobertura comportamental e a acessibilidade.
- O aplicativo pode ser instalado em navegadores compatíveis usando o manifest e
  HTTPS.
- Ficar offline não expõe dados anteriores nem permite mutações; a interface
  comunica a necessidade de conexão.
- `docs/ui-standards.md` documenta o padrão para as próximas telas.
- Testes, lint, typecheck e build passam.
