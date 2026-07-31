# Dassein — Agent Notes

## What this is

A single-page 3D avatar site. An icosahedron wireframe morphs into a talking face on click, powered by Three.js. Voice chat is speech-to-speech via the OpenAI Realtime API (`gpt-realtime-mini`) over WebRTC, with native server-VAD turn-taking and barge-in. Dark cyan-blue terminal-noir aesthetic.

Live at https://www.dassein.io

## Structure

| File | Role |
|---|---|
| `index.html` | Entire app — HTML, inline CSS, inline Three.js module. Single page with landing → agent transition |
| `voice-realtime.js` | S2S voice client — WebRTC peer connection + `oai-events` data channel to OpenAI Realtime, ephemeral-token auth, client-side tool execution, output-audio RMS tap for visemes |
| `voice-conversation.js` | Thin event-wiring layer — maps realtime events to UI state (idle/listening/thinking/speaking) and chat messages |
| `blogs.html` | Standalone blog page ("Forest Paths") — philosophical essays |
| `wylan.html` | Personal portfolio/bio page |
| `data/robota_scan.json` | 5MB face mesh (478 landmarks, blendshapes, expressions). Fetched at runtime |
| `api/index.py` | Vercel serverless FastAPI backend — `/api/chat`, `/api/realtime/session`, `/api/health`, `/api/save-scan`, `/api/load-scan` |
| `server.py` | Local dev server (Python stdlib) with same API endpoints as `api/index.py` |
| `vercel.json` | Routes `/api/*` → serverless function |
| `requirements.txt` | Python deps for both local and Vercel |
| `tests/e2e/dassein.spec.js` | Playwright E2E tests for landing state, transformation, agent mode, performance |
| `playwright.config.js` | Playwright config — runs `python3 server.py` on port 3000 |
| `PLAN.md` | Redesign plan v4 — the spec that produced the current `index.html` |
| `MISSING_FEATURES.md` | Gap analysis audit — all 23 features confirmed implemented |

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
| POST | `/api/chat` | `{"messages": [...], "stream": bool, "tools": bool}` | `{"response": "..."}` or SSE token stream |
| POST | `/api/realtime/session` | — | `{"token": "ek_...", "expires_at": ...}` — ephemeral Realtime token. Never returns the master API key |
| GET | `/api/health` | — | `{"status": "ok", "agent": "live"}` |
| POST | `/api/save-scan` | JSON scan data | `{"status": "saved"}` |
| GET | `/api/load-scan` | — | scan JSON or `{"error": "no saved scan"}` |

## Key conventions

- No build tool, no framework — single `index.html` with all JS/CSS inline
- Three.js loaded from CDN via import map (`three@0.152.0`)
- GSAP loaded from CDN for animations
- Fonts via Google Fonts (Space Grotesk + Caveat)
- Voice: browser ↔ OpenAI Realtime (`gpt-realtime-mini`) over WebRTC; server only mints ephemeral tokens. Turn-taking/interruption are native (`server_vad` + `interrupt_response`); tools (`switch_shape`, `web_search`, `get_time`, `get_weather`) execute client-side over the data channel. Visemes are driven by the real output-audio RMS, not text guesses
- Text LLM chain (`/api/chat` only): DeepSeek → OpenAI → Anthropic → hardcoded fallbacks
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

Env vars required in Vercel (or `.env` locally): `OPENAI_API_KEY` (required for voice), `DEEPSEEK_API_KEY`, `LLM_PROVIDER`, `DEEPSEEK_MODEL` (text chat).
