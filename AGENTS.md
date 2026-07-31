# Dassein — Agent Notes

## What this is

A single-page 3D avatar site. An icosahedron wireframe morphs into a talking face on click, powered by Three.js. Voice chat is speech-to-speech via the OpenAI Realtime API (`gpt-realtime-mini`) over WebRTC, with native server-VAD turn-taking and barge-in. Dark cyan-blue terminal-noir aesthetic.

Live at https://www.dassein.io

## Structure

| File | Role |
|---|---|
| `index.html` | Entire app — HTML, inline CSS, inline Three.js module. Single page with landing → agent transition. Tier-1 shape system (spec model, modifiers, blend) |
| `voice-realtime.js` | S2S voice client — WebRTC peer connection + `oai-events` data channel to OpenAI Realtime, ephemeral-token auth, client-side tool execution (`spawn_object`, `web_search`, `get_time`, `get_weather`), output-audio RMS tap for visemes |
| `voice-conversation.js` | Thin event-wiring layer — maps realtime events to UI state (idle/listening/thinking/speaking) and chat messages |
| `blogs.html` | Standalone blog page ("Forest Paths") — philosophical essays |
| `wylan.html` | Personal portfolio/bio page |
| `data/robota_scan.json` | 5MB face mesh (478 landmarks, blendshapes, expressions). Fetched at runtime |
| `api/index.py` | Vercel serverless FastAPI backend — `/api/realtime/session`, `/api/health` |
| `server.py` | Local dev server (Python stdlib) with same API endpoints as `api/index.py` |
| `vercel.json` | Routes `/api/*` → serverless function |
| `requirements.txt` | Python deps for both local and Vercel |
| `tests/e2e/dassein.spec.js` | Playwright E2E tests — landing state, transformation, agent mode, procedural spawn (tier-0 S1–S7 + tier-1 S8–S16), performance |
| `playwright.config.js` | Playwright config — runs `python3 server.py` on port 3000 |
| `docs/PLAN.md` | Current plan — Tier 2 "Summoning": compound builder, curated spec library, DeepSeek spec synthesis, voice summoning |
| `docs/MISSING_FEATURES.md` | Gap analysis audit — all 23 features confirmed implemented |

## Quick Start

```bash
cp .env.example .env
# edit .env with your API keys
pip install -r requirements.txt
python3 server.py         # local dev on :3000
```

Or serve statically with `npx serve .`.

## API

| Method | Path | Body | Response |
|--------|------|------|----------|
| POST | `/api/realtime/session` | — | `{"token": "ek_...", "expires_at": ...}` — ephemeral Realtime token. Never returns the master API key |
| GET | `/api/health` | — | `{"status": "ok", "agent": "live"}` |

## Tier-1 shape system

- Unified spec: `{ type, size='medium', params={}, mods={}, blend={with, ratio}, union=[...], seed, url }`.
- Bases are welded + FPS'd once and cached by `(type, params)` only (bounded ~26 entries); unions are cached under a composite key. Mods, blend, size, and edges are cheap 478-point array ops recomputed per spawn. `force` clears a base key.
- Modifiers run pointwise on target arrays post-FPS in fixed order: squash → bend → twist → taper → bulge → spherize → jitter. All functions of normalized height/radius.
- Blend is a 478-point lerp over size-normalized cached bases; `ratio=0` ≈ A exactly, size applied last.
- **Union/merge:** `union: ['cube', 'gem']` fuses two+ base geometries before the weld → FPS step, so the net samples both shapes in one solid (same mechanism as the double-strand `helix`). Normalized to the 0.55r bulk; voice exposes it as `combine`.
- **G1:** each name lands at its current absolute size — native primitives (cube/cylinder/pyramid/cone/torus) keep their geometry scale; every other builder is normalized to the 0.55r bulk.
- **G2:** `object:'model'` without a `url` loads the Duck (default); with `url` it loads any `.glb` via `loadGLBFromURL` (CORS failures return a helpful error).
- Builder-conformance rule: every builder must produce ≥478 unique welded verts (FPS guard stays loud).
- Pills and voice route procedural names through the same spec path; `switchShape` keeps only face/sphere/model semantics. `window.__scene.spec` mirrors the active spec.

## Key conventions

- No build tool, no framework — single `index.html` with all JS/CSS inline
- Three.js loaded from CDN via import map (`three@0.152.0`)
- GSAP loaded from CDN for animations
- Fonts via Google Fonts (Space Grotesk + Caveat)
- Voice: browser ↔ OpenAI Realtime (`gpt-realtime-mini`) over WebRTC; server only mints ephemeral tokens. Turn-taking/interruption are native (`server_vad` + `interrupt_response`); tools (`spawn_object`, `web_search`, `get_time`, `get_weather`) execute client-side over the data channel. Visemes are driven by the real output-audio RMS, not text guesses
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

Env vars required in Vercel (or `.env` locally): `OPENAI_API_KEY` (required for voice).
