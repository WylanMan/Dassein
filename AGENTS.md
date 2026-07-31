# Dassein — Agent Notes

## What this is

A single-page 3D avatar site. An icosahedron wireframe morphs into a talking face on click, powered by Three.js. Voice chat is speech-to-speech via the OpenAI Realtime API (`gpt-realtime-mini`) over WebRTC, with native server-VAD turn-taking and barge-in. Dark cyan-blue terminal-noir aesthetic.

Live at https://www.dassein.io

## Structure

| File | Role |
|---|---|
| `index.html` | Entire app — HTML, inline CSS, inline Three.js module. Single page with landing → agent transition. Tier-1/2 shape system (spec model, modifiers, blend, compound `parts`, profiles, curated spec library, summon flow) |
| `voice-realtime.js` | S2S voice client — WebRTC peer connection + `oai-events` data channel to OpenAI Realtime, ephemeral-token auth, client-side tool execution (`spawn_object`, `summon_object`, `web_search`, `get_time`, `get_weather`), output-audio RMS tap for visemes |
| `voice-conversation.js` | Thin event-wiring layer — maps realtime events to UI state (idle/listening/thinking/speaking) and chat messages |
| `blogs.html` | Standalone blog page ("Forest Paths") — philosophical essays |
| `wylan.html` | Personal portfolio/bio page |
| `data/robota_scan.json` | 5MB face mesh (478 landmarks, blendshapes, expressions). Fetched at runtime |
| `data/curated_specs.json` | Curated spec library (16 summons) — generated from `CURATED_SPECS` in `index.html`; doubles as the few-shot example bank for `/api/summon` |
| `api/index.py` | Vercel serverless FastAPI backend — `/api/realtime/session`, `/api/summon`, `/api/health` |
| `api/summon.py` | Spec synthesis (B1) — DeepSeek prompt + validator + fix-retry + cache; shared by `server.py` and `api/index.py` |
| `server.py` | Local dev server (Python stdlib) with same API endpoints as `api/index.py` |
| `vercel.json` | Routes `/api/*` → serverless function |
| `requirements.txt` | Python deps for both local and Vercel |
| `tests/e2e/dassein.spec.js` | Playwright E2E tests — landing state, transformation, agent mode, procedural spawn (tier-0 S1–S7 + tier-1 S8–S16), performance |
| `tests/e2e/summon.spec.js` | `/api/summon` tests (S17/S19/S21) against a stubbed DeepSeek |
| `tests/e2e/tier2.spec.js` | Tier-2 client tests (S18 compound/curated build, S20 `summon_object` voice tool) |
| `tests/support/dev_server.py` | Test web server — app on :3000 with `DEEPSEEK_BASE_URL` → stub on :3001 |
| `tests/support/summon_stub.py` | Local DeepSeek chat-completions stub (valid/bad/retry specs, call counter) |
| `playwright.config.js` | Playwright config — runs `tests/support/dev_server.py` on port 3000 |
| `docs/PLAN.md` | Current plan — Tier 2 "Summoning": compound builder, curated spec library, DeepSeek spec synthesis, voice summoning |
| `docs/MISSING_FEATURES.md` | Gap analysis audit — all 23 features confirmed implemented |

## Quick Start

```bash
cp .env.example .env
# edit .env with your API keys
pip install -r requirements.txt
python3 server.py         # local dev on :3000
```

`OPENAI_API_KEY` is required for voice; `DEEPSEEK_API_KEY` enables `/api/summon`
spec synthesis (falls back to curated-library-only summons without it).

Or serve statically with `npx serve .`.

## API

| Method | Path | Body | Response |
|--------|------|------|----------|
| POST | `/api/realtime/session` | — | `{"token": "ek_...", "expires_at": ...}` — ephemeral Realtime token. Never returns the master API key |
| POST | `/api/summon` | `{"concept": "a wide hourglass", "seed": 1234?}` | `{"spec": {...}, "id": "hourglass_wide", "seed": ..., "cached": bool}` — a JSON spec (never geometry). `422` → `{"abstractify": true}` on unrecoverable synthesis failure; `503` without `DEEPSEEK_API_KEY` |
| GET | `/api/health` | — | `{"status": "ok", "agent": "live"}` |

## Shape system (Tier 1 + Tier 2)

- Unified spec: `{ type, size='medium', params={}, mods={}, blend={with, ratio}, union=[...], parts=[...], seed, url }`.
- **Parts (compound, Tier 2):** `parts: [{ type, pos, rot, scale, params, mods, seed }]` assembles a form from multiple builders. The first part is the anchor at the origin; others attach relative to it. `rot` uses the orientation vocabulary `'up'|'flat'|'side'` or `{preset, deg}` — never raw Euler angles. ≤12 parts; pos is clamped into the ±0.8 work volume so edges never bridge distant islands. Part point sets merge **before** the weld → FPS step (same mechanism as `union`/`helix`).
- **Profiles (Tier 2):** `latheBuilder` accepts `params.profile: [[y, r]...]` (height first, radius second); `extrudeBuilder` accepts `params.profile: [[x, y]...]` + `params.depth`. Presets (vase/goblet/rocket/bowl, star/gear/cross/polygon) remain.
- Bases are welded + FPS'd once and cached by `(type, params)` only; unions/compounds cache under composite keys. Cache is bounded (~80 entries, oldest evicted). Mods, blend, size, and edges are cheap 478-point array ops recomputed per spawn. `force` clears a base key.
- Modifiers run pointwise on target arrays post-FPS in fixed order: squash → bend → twist → taper → bulge → spherize → jitter. All functions of normalized height/radius. **Jitter is the only seed-sensitive modifier** — pinned seeds make re-rolls cacheable.
- Blend is a 478-point lerp over size-normalized cached bases; `ratio=0` ≈ A exactly, size applied last.
- **Union/merge:** `union: ['cube', 'gem']` fuses two+ base geometries before the weld → FPS step; voice exposes it as `combine`.
- **Curated library (Tier 2):** `CURATED_SPECS` in `index.html` — 16 hand-written summons (hourglass, throne, labyrinth, lantern, key, door, chain, monument, arch, chrysalis, gate, well, sundial, crown, ship, altar). Same data structure as LLM cache entries; also the few-shot example bank in the DeepSeek prompt (`data/curated_specs.json`, regenerated from `index.html`). Voice routes concepts through aliases + substring matching.
- **Summon flow:** curated concepts hit the library instantly (zero API, zero latency). Anything else shows a seeded stand-in blob, calls `/api/summon` (≤6s hard cap, then narrate-and-continue), and morphs on arrival. Re-rolls ("different") bump the seed +1 with a light jitter; refined concepts get a new canonical id. **Every failure degrades to a seeded abstract form — never a crash.**
- **G1:** each name lands at its current absolute size — native primitives keep their geometry scale; every other builder (incl. compounds/unions) normalizes to the 0.55r bulk.
- **G2:** `object:'model'` without a `url` loads the Duck (default); with `url` it loads any `.glb` via `loadGLBFromURL`.
- Builder-conformance rule: every builder must produce ≥478 unique welded verts (FPS guard stays loud).
- Pills and voice route procedural names through the same spec path; `switchShape` keeps only face/sphere/model semantics. `window.__scene.spec` mirrors the active spec.

## Key conventions

- No build tool, no framework — single `index.html` with all JS/CSS inline
- Three.js loaded from CDN via import map (`three@0.152.0`)
- GSAP loaded from CDN for animations
- Fonts via Google Fonts (Space Grotesk + Caveat)
- Voice: browser ↔ OpenAI Realtime (`gpt-realtime-mini`) over WebRTC; server only mints ephemeral tokens. Turn-taking/interruption are native (`server_vad` + `interrupt_response`); tools (`spawn_object`, `summon_object`, `web_search`, `get_time`, `get_weather`) execute client-side over the data channel. Visemes are driven by the real output-audio RMS, not text guesses
- Tests mock DeepSeek by pointing `DEEPSEEK_BASE_URL` at `tests/support/summon_stub.py` (port 3001) via `tests/support/dev_server.py`
- Face scan data at `data/robota_scan.json` (478-vertex mesh from real 3D scan)

## Design system

- Primary: `#00d4ff` (cyan) — wireframes, glows, highlights
- Background: `radial-gradient` deep blue-black (`#0c0c14` → `#06060a`)
- Text: `#b9b6c2` (primary), `#9a97a3` (dim)
- Accent: `#ff4466` (mic active, red)

## Deploy

```bash
vercel --prod
```

Env vars required in Vercel (or `.env` locally): `OPENAI_API_KEY` (required for voice),
`DEEPSEEK_API_KEY` (enables `/api/summon` spec synthesis; without it summons fall back
to the curated library). Optional: `DEEPSEEK_MODEL` (default `deepseek-chat`),
`DEEPSEEK_BASE_URL`, `KV_REST_API_URL` + `KV_REST_API_TOKEN` (Vercel KV cache in prod;
dev uses `.cache/specs/`, gitignored).
