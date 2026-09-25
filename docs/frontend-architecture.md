# Frontend Architecture (Phase 3 — as implemented)

Modern health-tech frontend consuming the Phase 2 FastAPI backend
(**not** the legacy Flask app, which remains untouched for regression).

```text
Next.js 16 (App Router) → React 19 → TypeScript (strict, no `any`)
        ↓
app/ routes (server components by default; client components where interactive)
   /            Dashboard   — hero, honest scope notice, model cards
   /assessment  3-step form — 13 features, grouped, validated with Zod
   /results/[id] Result     — gauge, badge, model info, contributions
   /history     Dashboard   — table (desktop) / cards (mobile), paginated
        ↓
lib/api.ts — single typed API client (NEXT_PUBLIC_API_URL base; no scattered
fetch; timeouts; ApiError with status/code/requestId; cache: no-store)
        ↓
FastAPI /api/v1/assessments (+ /{id}/explanation), /health, /ready
```

## Stack

- **Next.js 16.3.6** (App Router, Turbopack) + **React 19.2** + **TypeScript 5**
- **Tailwind CSS v4** (CSS-first config in `globals.css`, shadcn design tokens)
- **shadcn/ui** (radix base): button, card, input, label, radio-group,
  badge, separator, sonner, progress, table, skeleton, collapsible
- **Zod** validation mirroring `backend/app/schemas/assessment.py` exactly
  (the backend stays the final authority)
- **Vitest 5 + React Testing Library** (jsdom) for behavior tests
- **lucide-react** icons, **next-themes** dark mode

## Design system

Restrained medical-product aesthetic: neutral palette + emerald (lower
probability) / amber (higher) semantics, one accent, consistent radii,
borders and shadows, `Geist` type. No AI gradients, no glassmorphism, no
fake medical imagery. Status colors carry meaning only.

## State handling

Local `useState` + effects with cancellation flags (no global state library
needed at this scale). Every async surface implements
initial / loading / success / empty / error / retry explicitly.

## API integration

`lib/api.ts` exposes `createAssessment`, `getAssessment`, `listAssessments`,
`getExplanation`, `getHealth`, `getReadiness`. `NEXT_PUBLIC_API_URL`
env var (default `http://localhost:8000`), documented in
`frontend/.env.example`. CORS: backend allows explicit origins only
(configured via `CORS_ORIGINS`).

## Validation

`lib/validation.ts`: Zod schema with ranges + categorical enums identical to
the backend contract; coerces form strings; returns per-field accessible
error messages (`role="alert"`, `aria-describedby`, `aria-invalid`).

## Results semantics (honest wording)

- Headline: "Model-estimated disease probability" with gauge — never
  "you have heart disease", never "diagnosis".
- Badge: "Lower / Higher model-estimated probability of disease".
- Contributions panel (lazy-loaded on expand):
  `GET /api/v1/assessments/{id}/explanation` → SHAP values rendered as
  amber (pushes estimate up) / green (down) bars, labeled
  **"Model feature contributions … not causes of disease"**.
- "About this prediction" collapsible: probabilistic output, small
  historical dataset, not a diagnosis, professional evaluation required.

## Accessibility

Semantic landmarks (`header/nav/main/footer`), labels tied to inputs,
`aria-current` navigation, `aria-live` status regions (backend indicator,
loading states), keyboard-operable everything with visible focus rings
(`focus-visible:outline-*`), `prefers-reduced-motion` respected on the
gauge animation, color contrast ≥ WCAG AA on text.

## Responsive behavior

Mobile-first: bottom icon nav < md, table → cards transformation for
history, stacked gauge/metric on small screens, grids collapse to single
column. Verified conceptually at 375 / 768 / 1440.

## Dark mode

`next-themes` with `attribute="class"`, system default + visible toggle
(aria-labeled). Colors use shadcn tokens so both themes stay readable.

## Privacy UX

Demo-environment notice on the assessment page; no medical inputs logged to
console; only assessment IDs appear in URLs; no compliance claims.

## Tests

`frontend/tests/`: validation (8), API client (7: success, backend error
mapping, network failure, timeout with fake timers, pagination query,
explanation route, ApiError shape), components (7: gauge incl. clamping,
contributions loading/error/labels, history cards). Run: `npm test`.

## Commands

```bash
cd frontend
npm install
npm run dev        # http://localhost:3000
npm run lint && npm run typecheck && npm test && npm run build
```

With backend: `uvicorn backend.app.main:app --port 8000` and
`NEXT_PUBLIC_API_URL=http://localhost:8000` in `frontend/.env.local`.

## Planned (not implemented)

Authentication-adjacent UX, conversational assistant, report upload,
wearable integration — all later phases per the roadmap.
