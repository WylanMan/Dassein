# SelfShip — Agent Notes

## What this is

A single-page web app that simulates an autonomous feature pipeline: type a natural-language feature request, and it animates through Parsing intent → Generating code → Creating PR → Running tests → Deploying preview → Done, mutating a live embedded to-do app as the "deployment". Fully client-side, mock data, fake async delays — no backend, no GitHub integration.

Live at https://selfship.vercel.app

## Structure

| File | Role |
|---|---|
| `index.html` | Both views (landing + pipeline dashboard) — no build step |
| `styles.css` | Terminal-noir design system, glassmorphism, preview app theming |
| `app.js` | Particles, pipeline state machine, feature engine, fake artifacts, confetti |
| `.vercelignore` | Keeps legacy/venv/log junk out of deployments |

## Key conventions

- **No build tool, no dependencies** — serve statically (`npx serve .` or `python3 -m http.server`)
- Fonts via Google Fonts (Space Grotesk display + JetBrains Mono)
- The preview to-do app is real DOM, scoped under `.todoapp` / `.pv-*` classes with its own CSS vars (light default, `.pv-dark` for dark mode) so dashboard styles never leak in

## App logic summary

`app.js` is organized in sections:

1. **Particles** — canvas constellation background; static frame if `prefers-reduced-motion`
2. **To-do app** (`mountTodoApp`, `renderTodos`, `syncChrome`) — interactive: add/toggle/delete/filter all work; feature flags in `todo.features` gate per-feature row controls
3. **Feature engine** (`FEATURES`) — regex intent match → `{ files, tests, apply() }`; up to 3 matches compose, `makeCustomFeature()` is the fallback for unmatched requests
4. **Pipeline runner** (`runPipeline`) — token-cancellable async sequence; streams timestamped logs to `#terminal`, drives step states, mounts preview + applies hot updates with scanline/toast at the deploy step
5. **PR card + merge** — diff renderer with add/del/hunk line types; merge fires canvas confetti and flips status pill to violet `merged`

## Adding a new simulated feature

Push an object onto `FEATURES` with: `id`, `match` (regex), `intent`, `title`, `hotLabel`, `branch`, `commit`, `files[]` (path + added/removed + diff lines `{t: "+|-| |h", x}`), `tests[]`, and `apply()` which mutates the mounted to-do app.

## Deploy

```bash
npx vercel deploy --prod --yes   # linked to project "selfship" (wylanmans-projects)
```
