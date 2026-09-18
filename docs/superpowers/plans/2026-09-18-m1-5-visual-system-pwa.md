# M1.5 Visual System and Lean PWA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the approved clinical-and-serene visual system to every M1.5 route, establish it as the project UI standard, and add a secure installable online-first PWA foundation.

**Architecture:** Add shared visual tokens and focused UI/layout primitives, then recompose existing public and authenticated routes without changing their API, authorization, validation, or server/client boundaries. Add a typed App Router manifest, brand icons, and a connectivity notice; do not add a service worker or cache authenticated data.

**Tech Stack:** Next.js 15 App Router, React 19, TypeScript 5.9, Tailwind CSS 4, CVA, Lucide React, Vitest, Testing Library.

**Spec:** `docs/superpowers/specs/2026-09-18-m1-5-visual-system-pwa-design.md`

## Global Constraints

- Preserve every M1.5 route, API call, CSRF behavior, permission rule, validation message, and 401 redirect.
- Reuse existing dependencies and lockfile; add no UI, PWA, state-management, or font package.
- Keep domain behavior in `src/features/*`; shared rule-free primitives live in `src/components/ui` or `src/components/layout`.
- The UI language remains pt-BR and the default provisioning timezone remains `America/Bahia`.
- Main text is at least 16 px and recurring labels are at least 14 px.
- Support 320 px width, keyboard and touch use, visible focus, 200% text enlargement, and no page-level horizontal overflow.
- PWA is installable and online-first: no service worker, offline mutation queue, background sync, or caching of pages, `/api/v1`, tokens, credentials, clinic data, or other authenticated content.
- Keep testing proportional: add only focused tests for new behavior, retain existing behavioral tests, and finish with lint, typecheck, frontend tests, build, and targeted visual checks.

---

## File Structure

### New files

- `apps/web/src/components/layout/auth-shell.tsx` — shared public-route shell.
- `apps/web/src/components/layout/app-shell.tsx` — authenticated desktop/mobile frame.
- `apps/web/src/components/layout/app-sidebar.tsx` — global Clinics/Sessions navigation.
- `apps/web/src/components/ui/brand.tsx` — reusable EasyDentist mark and wordmark.
- `apps/web/src/components/ui/page-header.tsx` — eyebrow, title, description, and action slot.
- `apps/web/src/components/ui/status-badge.tsx` — semantic status/role badge.
- `apps/web/src/components/ui/feedback.tsx` — consistent alert/status presentation.
- `apps/web/src/components/ui/connectivity-notice.tsx` — online/offline notice.
- `apps/web/src/components/ui/connectivity-notice.test.tsx` — one focused connectivity test file.
- `apps/web/src/features/clinics/components/ClinicNav.tsx` — local clinic navigation.
- `apps/web/src/app/manifest.ts` — typed PWA manifest.
- `apps/web/public/icons/easydentist-192.png` — install icon.
- `apps/web/public/icons/easydentist-512.png` — install/maskable icon.
- `apps/web/public/icons/apple-touch-icon.png` — iOS home-screen icon.
- `docs/ui-standards.md` — official UI standard.

### Main modified files

- `apps/web/src/app/styles.css` — tokens, base styles, and shared utility patterns.
- `apps/web/src/app/layout.tsx` — font, metadata, viewport, icons, connectivity notice.
- `apps/web/src/app/(app)/layout.tsx` — compose `AppShell` after the existing session guard.
- `apps/web/src/features/auth/components/AppHeader.tsx` — account actions in the new shell.
- `apps/web/src/components/ui/button.tsx` — approved variants and touch-safe sizing.
- `apps/web/src/components/ui/confirm-button.tsx` — render the shared `Button` primitive.
- All five public route pages — compose `AuthShell`.
- Existing auth form/panel components — shared field, feedback, link, and button styles.
- Clinic route pages and clinic components — `PageHeader`, cards, local navigation, sections.
- Member and session components — responsive data presentation and consistent actions.

---

### Task 1: Visual foundation and shared primitives

**Files:**

- Modify: `apps/web/src/app/styles.css`
- Modify: `apps/web/src/app/layout.tsx`
- Modify: `apps/web/src/components/ui/button.tsx`
- Modify: `apps/web/src/components/ui/confirm-button.tsx`
- Create: `apps/web/src/components/ui/brand.tsx`
- Create: `apps/web/src/components/ui/page-header.tsx`
- Create: `apps/web/src/components/ui/status-badge.tsx`
- Create: `apps/web/src/components/ui/feedback.tsx`
- Test: `apps/web/src/components/ui/button.test.tsx`
- Test: `apps/web/src/components/ui/button.interaction.test.tsx`
- Test: `apps/web/src/components/ui/confirm-button.test.tsx`

**Interfaces:**

- Produces: `Brand({ compact?: boolean })`, `PageHeader({ eyebrow?, title, description?, actions? })`, `StatusBadge({ tone, children })`, and `Feedback({ tone, children })`.
- Produces: `Button` variants `default | secondary | outline | ghost | destructive | link` with existing public API preserved.
- Consumes: existing `cn`, CVA, Radix Slot, and Lucide React.

- [ ] **Step 1: Tighten the existing button assertions before restyling**

Add one assertion to the existing button tests that the default button retains a visible focus-ring class and one assertion that `ConfirmButton` forwards the destructive variant through `Button`. Keep existing interaction tests unchanged.

```tsx
expect(button.className).toContain('focus-visible:ring');
expect(screen.getByRole('button', { name: 'Remover' }).className).toContain('bg-destructive');
```

- [ ] **Step 2: Run the three focused primitive test files**

Run:

```bash
pnpm --filter @easydentist/web test -- src/components/ui/button.test.tsx src/components/ui/button.interaction.test.tsx src/components/ui/confirm-button.test.tsx
```

Expected: the new destructive forwarding assertion fails before `ConfirmButton` is migrated; all pre-existing assertions pass.

- [ ] **Step 3: Replace neutral defaults with approved global tokens**

Update `styles.css` with semantic OKLCH tokens for the approved palette and base document behavior. Keep Tailwind's current mappings and add success/warning/surface/sidebar tokens.

```css
:root {
  --background: oklch(0.98 0.006 205);
  --foreground: oklch(0.25 0.035 205);
  --primary: oklch(0.52 0.105 200);
  --primary-foreground: oklch(0.99 0.004 200);
  --secondary: oklch(0.94 0.018 200);
  --secondary-foreground: oklch(0.3 0.045 205);
  --muted: oklch(0.95 0.01 205);
  --muted-foreground: oklch(0.48 0.025 205);
  --accent: oklch(0.91 0.035 195);
  --accent-foreground: oklch(0.29 0.055 202);
  --destructive: oklch(0.56 0.19 27);
  --border: oklch(0.88 0.018 205);
  --input: oklch(0.84 0.024 205);
  --ring: oklch(0.57 0.12 199);
  --surface: oklch(1 0 0);
  --sidebar: oklch(0.31 0.055 207);
  --sidebar-foreground: oklch(0.92 0.025 195);
  --success: oklch(0.56 0.12 155);
  --warning: oklch(0.68 0.13 75);
  --radius: 0.75rem;
}
```

Set `body` to a 16 px minimum, improve smoothing/background, add `::selection`, and add reusable `app-field`, `app-label`, `app-panel`, and `app-link` component classes with `@layer components`. Do not hide browser focus outlines without a replacement.

- [ ] **Step 4: Use `next/font` and implement the shared primitives**

Use `Geist` from `next/font/google` in the root layout without adding a package. Implement small semantic components with no business logic. `Feedback` must map `error` to `role="alert"` and `success` to `role="status"`.

```tsx
export function Feedback({
  tone,
  children,
}: {
  tone: 'error' | 'success' | 'info';
  children: ReactNode;
}) {
  return (
    <div
      role={tone === 'error' ? 'alert' : 'status'}
      className={cn('feedback', `feedback-${tone}`)}
    >
      {children}
    </div>
  );
}
```

- [ ] **Step 5: Route confirmation styling through `Button`**

Extend `ConfirmButton` with optional `variant` and `size` props, render `<Button type="button">`, and preserve its current `window.confirm` behavior and `className` support. Existing callers must continue compiling before later visual cleanup.

- [ ] **Step 6: Run primitive tests and commit**

Run:

```bash
pnpm --filter @easydentist/web test -- src/components/ui/button.test.tsx src/components/ui/button.interaction.test.tsx src/components/ui/confirm-button.test.tsx
pnpm --filter @easydentist/web typecheck
```

Expected: all focused tests and typecheck pass.

Commit:

```bash
git add apps/web/src/app/styles.css apps/web/src/app/layout.tsx apps/web/src/components/ui
git commit -m "feat(web): establish EasyDentist visual foundation"
```

---

### Task 2: Public authentication experience

**Files:**

- Create: `apps/web/src/components/layout/auth-shell.tsx`
- Modify: `apps/web/src/app/login/page.tsx`
- Modify: `apps/web/src/app/forgot-password/page.tsx`
- Modify: `apps/web/src/app/reset-password/page.tsx`
- Modify: `apps/web/src/app/verify-email/page.tsx`
- Modify: `apps/web/src/app/accept-invitation/page.tsx`
- Modify: `apps/web/src/features/auth/components/LoginForm.tsx`
- Modify: `apps/web/src/features/auth/components/ForgotPasswordForm.tsx`
- Modify: `apps/web/src/features/auth/components/ResetPasswordForm.tsx`
- Modify: `apps/web/src/features/auth/components/VerifyEmailPanel.tsx`
- Modify: `apps/web/src/features/auth/components/AcceptInvitationForm.tsx`
- Test: existing tests under `apps/web/src/features/auth/components/*.test.tsx`

**Interfaces:**

- Consumes: `Brand`, `Button`, `Feedback`, and global form classes from Task 1.
- Produces: `AuthShell({ eyebrow, title, description, children, footer? })`.
- Preserves: every existing form state, API call, redirect, validation rule, fragment-token flow, and accessible field identifier.

- [ ] **Step 1: Add the public shell**

Implement the approved two-column desktop composition and stacked mobile composition. The brand panel contains product copy only; route-specific forms remain children.

```tsx
type AuthShellProps = {
  eyebrow: string;
  title: string;
  description: string;
  children: ReactNode;
  footer?: ReactNode;
};

export function AuthShell(props: AuthShellProps) {
  return (
    <main className="auth-shell">
      <aside className="auth-brand-panel">
        <Brand />
      </aside>
      <section className="auth-content-panel" aria-labelledby="auth-title">
        <div className="auth-content-card">
          <p className="auth-eyebrow">{props.eyebrow}</p>
          <h1 id="auth-title">{props.title}</h1>
          <p>{props.description}</p>
          {props.children}
          {props.footer}
        </div>
      </section>
    </main>
  );
}
```

- [ ] **Step 2: Recompose all five public pages**

Replace repeated `<main>`/heading blocks with `AuthShell`. Keep the login session check and redirect exactly where they are. Add the existing recovery link below `LoginForm`; add a return-to-login link to recovery/reset/verification completion states where it does not change behavior.

- [ ] **Step 3: Apply shared form and feedback primitives**

Replace repeated visual class strings with `app-label`, `app-field`, `Button`, and `Feedback`. Do not change validation functions, state names, API functions, `aria-*`, `autoComplete`, or token cleanup.

- [ ] **Step 4: Run the existing auth component suite**

Run:

```bash
pnpm --filter @easydentist/web test -- src/features/auth/components
pnpm --filter @easydentist/web typecheck
```

Expected: all existing auth tests and typecheck pass without loosening assertions.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/layout/auth-shell.tsx apps/web/src/app/login apps/web/src/app/forgot-password apps/web/src/app/reset-password apps/web/src/app/verify-email apps/web/src/app/accept-invitation apps/web/src/features/auth/components
git commit -m "feat(web): redesign public authentication flows"
```

---

### Task 3: Authenticated shell and clinic flows

**Files:**

- Create: `apps/web/src/components/layout/app-shell.tsx`
- Create: `apps/web/src/components/layout/app-sidebar.tsx`
- Create: `apps/web/src/features/clinics/components/ClinicNav.tsx`
- Modify: `apps/web/src/app/(app)/layout.tsx`
- Modify: `apps/web/src/features/auth/components/AppHeader.tsx`
- Modify: `apps/web/src/app/(app)/clinics/page.tsx`
- Modify: `apps/web/src/app/(app)/clinics/[clinicId]/page.tsx`
- Modify: `apps/web/src/app/(app)/clinics/[clinicId]/settings/page.tsx`
- Modify: `apps/web/src/features/clinics/components/ClinicList.tsx`
- Modify: `apps/web/src/features/clinics/components/LegalNameForm.tsx`
- Modify: `apps/web/src/features/clinics/components/ClinicSettingsForm.tsx`
- Test: `apps/web/src/features/auth/components/AppHeader.test.tsx`
- Test: existing clinic component tests.

**Interfaces:**

- Consumes: Task 1 primitives.
- Produces: `AppShell({ user, children })`, `AppSidebar()`, and `ClinicNav({ clinicId, active })` where `active` is `'overview' | 'settings' | 'members'`.
- Preserves: authenticated layout's server-side `getCurrentUser()` guard and global 401 redirect.

- [ ] **Step 1: Implement the authenticated shell without moving the session guard**

Keep `getCurrentUser()` and `redirect('/login')` in `app/(app)/layout.tsx`; replace only the returned markup:

```tsx
return <AppShell user={user}>{children}</AppShell>;
```

`AppShell` composes `AppSidebar`, `AppHeader`, and `<main id="main-content">`. Include a skip link. Desktop uses the sidebar; mobile exposes the same destinations in a compact header/nav without hover. Task 5 adds `ConnectivityNotice` after its component exists.

- [ ] **Step 2: Restyle `AppHeader` while preserving logout behavior**

Keep `run`, `logout`, `logoutAll`, router replacement, error handling, and exact accessible button names. Use `Button`/`ConfirmButton`, move the e-mail into account context, and keep “Sair de todos os dispositivos” visually secondary to “Sair”.

- [ ] **Step 3: Convert the clinic selector into approved cards**

Use `StatusBadge` for role/status and a clinic monogram derived from `legal_name`. Keep each whole card as the existing link and preserve empty-state text. Do not invent clinic metrics.

- [ ] **Step 4: Add local clinic navigation and page composition**

Use `PageHeader` and `ClinicNav` on overview/settings/members routes. The overview keeps legal identity, role, status, and `LegalNameForm`; settings retains role-based read/edit behavior. Global navigation remains Clinics/Sessions, while `ClinicNav` provides Visão geral/Ajustes/Equipe.

- [ ] **Step 5: Standardize clinic forms**

Wrap each logical form in `app-panel`, use shared fields and `Feedback`, and keep all validation/error logic intact. Read-only settings use a responsive `<dl>` with semantic labels.

- [ ] **Step 6: Run existing shell and clinic tests**

Run:

```bash
pnpm --filter @easydentist/web test -- src/features/auth/components/AppHeader.test.tsx src/features/clinics/components
pnpm --filter @easydentist/web typecheck
```

Expected: existing behavioral tests and typecheck pass.

- [ ] **Step 7: Commit**

```bash
git add apps/web/src/components/layout apps/web/src/app/'(app)' apps/web/src/features/auth/components/AppHeader.tsx apps/web/src/features/clinics
git commit -m "feat(web): add responsive clinical workspace shell"
```

---

### Task 4: Team and session management surfaces

**Files:**

- Modify: `apps/web/src/app/(app)/clinics/[clinicId]/members/page.tsx`
- Modify: `apps/web/src/features/members/components/InviteMemberForm.tsx`
- Modify: `apps/web/src/features/members/components/MembersTable.tsx`
- Modify: `apps/web/src/app/(app)/sessions/page.tsx`
- Modify: `apps/web/src/features/sessions/components/SessionsTable.tsx`
- Test: existing member and session component tests.

**Interfaces:**

- Consumes: `PageHeader`, `ClinicNav`, `Button`, `ConfirmButton`, `StatusBadge`, `Feedback`, and shared panel/field classes.
- Preserves: role assignment restrictions, owner safeguards, current-session redirect, 404 idempotency, confirmations, API calls, and feedback text.

- [ ] **Step 1: Build the responsive team composition**

Desktop: member list is the primary column and invite form is a bounded side panel. Mobile: member list appears first and invite form second. Keep `InviteMemberForm` hidden for roles without permission.

- [ ] **Step 2: Make member actions responsive without changing behavior**

Keep the semantic table at wide widths. At narrow widths, allow each row's content/actions to wrap or render a CSS-driven card layout while preserving `<table>` semantics where practical. Use `StatusBadge` for role/status, `Button` for change-role, and destructive `ConfirmButton` for removal.

- [ ] **Step 3: Redesign sessions with clear action hierarchy**

Mark the current session with a success/info badge, keep dates visible, and render “Revogar” as a secondary/destructive action. “Sair de todos os dispositivos” remains a separate destructive action after the list.

- [ ] **Step 4: Run existing behavioral tests**

Run:

```bash
pnpm --filter @easydentist/web test -- src/features/members/components src/features/sessions/components
pnpm --filter @easydentist/web typecheck
```

Expected: all existing behavior remains green.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/app/'(app)'/clinics/'[clinicId]'/members apps/web/src/app/'(app)'/sessions apps/web/src/features/members apps/web/src/features/sessions
git commit -m "feat(web): polish team and session management"
```

---

### Task 5: Lean installable PWA and connectivity state

**Files:**

- Create: `apps/web/src/app/manifest.ts`
- Create: `apps/web/src/components/ui/connectivity-notice.tsx`
- Create: `apps/web/src/components/ui/connectivity-notice.test.tsx`
- Create: `apps/web/public/icons/easydentist-192.png`
- Create: `apps/web/public/icons/easydentist-512.png`
- Create: `apps/web/public/icons/apple-touch-icon.png`
- Modify: `apps/web/src/app/layout.tsx`
- Modify: `apps/web/src/components/layout/app-shell.tsx`

**Interfaces:**

- Produces: `ConnectivityNotice()` with no props; it listens to browser `online`/`offline` events and renders only when offline.
- Produces: App Router `MetadataRoute.Manifest` with standalone display and icon metadata.
- Explicitly does not produce: `sw.js`, service-worker registration, caches, background sync, push, or offline writes.

- [ ] **Step 1: Write the focused connectivity test**

```tsx
// @vitest-environment jsdom
it('shows and clears the offline notice as connectivity changes', () => {
  vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(false);
  render(<ConnectivityNotice />);
  expect(screen.getByRole('status').textContent).toContain('Sem conexão');

  vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(true);
  window.dispatchEvent(new Event('online'));
  expect(screen.queryByRole('status')).toBeNull();
});
```

- [ ] **Step 2: Run the new test to verify it fails**

Run:

```bash
pnpm --filter @easydentist/web test -- src/components/ui/connectivity-notice.test.tsx
```

Expected: FAIL because `ConnectivityNotice` does not exist.

- [ ] **Step 3: Implement the online-first notice**

```tsx
'use client';

export function ConnectivityNotice() {
  const [online, setOnline] = useState(true);

  useEffect(() => {
    const sync = () => setOnline(navigator.onLine);
    sync();
    window.addEventListener('online', sync);
    window.addEventListener('offline', sync);
    return () => {
      window.removeEventListener('online', sync);
      window.removeEventListener('offline', sync);
    };
  }, []);

  if (online) return null;
  return (
    <div role="status" className="connectivity-notice">
      Sem conexão. Reconecte-se para continuar.
    </div>
  );
}
```

Mount it once in `AppShell`, above the page content. Do not retain or replay failed mutations.

- [ ] **Step 4: Add the typed manifest and root metadata**

```ts
import type { MetadataRoute } from 'next';

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: 'EasyDentist',
    short_name: 'EasyDentist',
    description: 'Gestão segura de clínicas odontológicas',
    start_url: '/clinics',
    display: 'standalone',
    background_color: '#f4f8f9',
    theme_color: '#0d3b47',
    lang: 'pt-BR',
    icons: [
      { src: '/icons/easydentist-192.png', sizes: '192x192', type: 'image/png' },
      { src: '/icons/easydentist-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
      {
        src: '/icons/easydentist-512.png',
        sizes: '512x512',
        type: 'image/png',
        purpose: 'maskable',
      },
    ],
  };
}
```

Set `metadata.icons.apple` to `/icons/apple-touch-icon.png` and export a `Viewport` with the approved `themeColor`. Keep existing title and description.

- [ ] **Step 5: Generate deterministic brand icons**

Use Pillow already available in the workspace to generate three opaque PNGs with the approved `#0d3b47` background, centered `ED` monogram in `#ffffff`, and safe padding. Create the files directly under `apps/web/public/icons`; do not commit the temporary generator.

```python
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

out = Path('apps/web/public/icons')
out.mkdir(parents=True, exist_ok=True)
font_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
for filename, size in [('apple-touch-icon.png', 180), ('easydentist-192.png', 192), ('easydentist-512.png', 512)]:
    image = Image.new('RGB', (size, size), '#0d3b47')
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(font_path, round(size * 0.34))
    box = draw.textbbox((0, 0), 'ED', font=font)
    draw.text(((size - (box[2] - box[0])) / 2, (size - (box[3] - box[1])) / 2 - box[1]), 'ED', fill='#ffffff', font=font)
    image.save(out / filename, optimize=True)
```

- [ ] **Step 6: Run the focused PWA checks and commit**

Run:

```bash
pnpm --filter @easydentist/web test -- src/components/ui/connectivity-notice.test.tsx
pnpm --filter @easydentist/web typecheck
pnpm --filter @easydentist/web build
```

Then inspect the build output for `/manifest.webmanifest` and confirm the icon files are present. Expected: test, typecheck, and build pass; no `sw.js` exists.

Commit:

```bash
git add apps/web/src/app/manifest.ts apps/web/src/app/layout.tsx apps/web/src/components/ui/connectivity-notice.tsx apps/web/src/components/ui/connectivity-notice.test.tsx apps/web/src/components/layout/app-shell.tsx apps/web/public/icons
git commit -m "feat(web): add lean installable PWA foundation"
```

---

### Task 6: Project UI standard and final verification

**Files:**

- Create: `docs/ui-standards.md`

**Interfaces:**

- Consumes: the implemented tokens, shells, primitives, responsive behavior, and PWA policy.
- Produces: the official project guidance for all future UI work.

- [ ] **Step 1: Document the implemented standard**

Write `docs/ui-standards.md` with these concrete sections:

```markdown
# Padrão de interface do EasyDentist

## Princípios

Clínico e sereno; funcional antes de decorativo; segurança visível sem alarmismo.

## Tokens

Documentar cada token de `styles.css` por função, nunca por aparência isolada.

## Shells

Quando usar `AuthShell`, `AppShell` e `ClinicNav`.

## Componentes

Assinaturas, variantes e exemplos de `Button`, `Feedback`, `StatusBadge` e `PageHeader`.

## Formulários e dados

Labels, validação, pending, sucesso, erro, estados vazios, tabelas e ações destrutivas.

## Responsividade e acessibilidade

320 px, toque, teclado, foco, 200% de texto e contraste.

## PWA e segurança

Online-first; proibido cachear conteúdo autenticado ou registrar service worker sem ADR.

## Anti-padrões

Valores visuais arbitrários, novos shells locais, cor como único sinal e ações sem confirmação.
```

Use examples copied from the implemented component APIs, not hypothetical APIs.

- [ ] **Step 2: Run the proportional final quality gate**

Run exactly:

```bash
pnpm --filter @easydentist/web lint
pnpm --filter @easydentist/web typecheck
pnpm --filter @easydentist/web test
pnpm --filter @easydentist/web build
pnpm exec prettier --check apps/web/src docs/ui-standards.md
```

Expected: all commands exit 0. Do not add more automated tests unless one of these commands exposes an uncovered regression.

- [ ] **Step 3: Perform one targeted visual pass**

Check at 390×844 and 1440×900:

- `/login` and one token-action route;
- `/clinics` and one clinic overview;
- settings, members, and sessions;
- keyboard focus order and visible focus;
- offline notice by toggling browser connectivity;
- no page-level horizontal overflow;
- no hidden primary or destructive action.

Fix only concrete regressions found in this pass. Do not add unrelated polish or new features.

- [ ] **Step 4: Commit documentation and final corrections**

```bash
git add docs/ui-standards.md apps/web
git commit -m "docs: establish EasyDentist UI standard"
```

- [ ] **Step 5: Review final diff**

Run:

```bash
git status --short
git diff --stat origin/feat/m1-5-frontend-operacional...HEAD
git log --oneline origin/feat/m1-5-frontend-operacional..HEAD
```

Expected: only the approved visual-system, PWA, documentation, and implementation-plan changes are present; `.superpowers/brainstorm/` remains untracked and is not committed.
