# Dassein — Agent Notes

## What this is

A single-page 3D avatar site. An icosahedron wireframe morphs into a talking face on click, powered by Three.js. Voice chat is speech-to-speech via a **local Pipecat voice server** (`pipecat_server.py`): the browser is audio I/O only over a WebSocket, while VAD/STT/TTS run server-side and the LLM brain is DeepSeek (`deepseek-chat`). Dark cyan-blue terminal-noir aesthetic.

Live at https://www.dassein.io

## Structure

| File | Role |
|---|---|
| `index.html` | Entire app — HTML, inline CSS, inline Three.js module. Single page with landing → agent transition. Tier-1/2 shape system (spec model, modifiers, blend, compound `parts`, profiles, curated spec library, summon flow) |
| `voice-pipecat.js` | S2S voice client for the **local Pipecat server** — `getUserMedia` mic → AudioWorklet resampler (`dassein-mic-processor.js`) → binary WS frames; server audio → jitter queue → WebAudio lookahead scheduler. Client-side tool execution (`spawn_object`, `summon_object`, `web_search`, `get_time`, `get_weather`), output-audio RMS tap for visemes |
| `dassein-mic-processor.js` | AudioWorklet module (48k → 16k int16, 20 ms frames) loaded at runtime by `voice-pipecat.js` |
| `voice-conversation.js` | Thin event-wiring layer — maps voice events to UI state (idle/listening/thinking/speaking) and chat messages |
| `sdf-core.mjs` | Pure SDF kernel — Tier-3 shape grammar (compileSdf / targetsFromSDF). No DOM/Three dependency; unit-tested in isolation with Node |
| `pipecat_server.py` | Local Pipecat voice server — Silero VAD → STT → DeepSeek LLM → Kokoro TTS over WS (`/api/voice/ws`). Server-side tool execution with narrate-first pacing. **Agent-backend (Phase 2):** always-hot toolset = 6 scene/instant-info + 3 memory (G5 prefill under `VOICE_SCHEMA_TOKEN_BUDGET`); `plan_work`/`step_task` + the heavy `structure_notes`/`session_engine` schemas are lazy-injected on plan intent and drive the orchestrator behind the wall (`delegate_pi`/`steer_pi`/`memory_summarize` moved behind it). Exposes `/api/voice/tools` (hot-prefill budget guard, G5). Wire protocol in `docs/voice-integration-spec.md`; agent-backend design in `docs/PLAN_AGENT_BACKEND.md` |
| `pi_rpc.py` | Warm per-connection `pi --mode rpc` session client (no per-call cold start; pi keeps in-process context). `extra_args` injects worker-launch flags. Pure stdlib, unit-testable |
| `obsidian_memory.py` | Obsidian vault memory brain — `memory_recall`/`memory_read`/`memory_write`/`memory_summarize` server tools. Pure stdlib, unit-testable |
| `vault_cli.py` | Obsidian structure tool (`VaultCLI`) — `ensure_project`, `note_create/append/read/rename`, `plan_draft/read/append/promote`, `plan_set_status`, `rebuild_index`. Append-only body discipline (G1); only frontmatter/status/promote/index are edited in place. Pure stdlib, unit-testable |
| `session_engine.py` | git-worktree + fork session engine — `fork_session`/`run_in_worktree`/`steer`/`abort`/`abandon`/`sync`/`approve_merge`/`merge_session`/`session_tree`/`log`. Model-B inline workers (read/bash/edit/write only, no subagent+no-skills); merge gate G2 (no merge without approve + clean sync). Pure stdlib, unit-testable |
| `blogs.html` | Standalone blog page ("Forest Paths") — philosophical essays |
| `wylan.html` | Personal portfolio/bio page |
| `data/robota_scan.json` | 5MB face mesh (478 landmarks, blendshapes, expressions). Fetched at runtime |
| `data/curated_specs.json` | Curated spec library (16 summons) — generated from `CURATED_SPECS` in `index.html`; doubles as the few-shot example bank for `/api/summon` |
| `api/index.py` | Vercel serverless FastAPI backend — `/api/health`, `/api/summon` |
| `api/summon.py` | Spec synthesis (B1) — DeepSeek prompt + validator + fix-retry + cache; shared by `server.py` and `api/index.py` |
| `server.py` | Local dev server (Python stdlib) with same API endpoints as `api/index.py` |
| `vercel.json` | Routes `/api/*` → serverless function |
| `requirements.txt` | Python deps for the site + API (both local and Vercel) |
| `requirements-voice.txt` | Python deps for the local Pipecat voice server (install into `.venv-voice` — see `docs/voice-integration-spec.md`) |
| `tests/e2e/dassein.spec.js` | Playwright E2E tests — landing state, transformation, agent mode, procedural spawn (tier-0 S1–S7 + tier-1 S8–S16), performance |
| `tests/e2e/summon.spec.js` | `/api/summon` tests (S17/S19/S21) against a stubbed DeepSeek |
| `tests/e2e/tier2.spec.js` | Tier-2 client tests (S18 compound/curated build, S20 `summon_object` voice tool) |
| `tests/e2e/tier3.spec.js` | Tier-3 SDF shape-grammar client tests (v2 spec, order-aligned morph) |
| `tests/e2e/voice-pipecat.spec.js` | Voice e2e — WS protocol against `tests/support/pipecat_mock.py` (WS :6001, control :6002) |
| `tests/e2e/voice-sessions.spec.js` | Agent-backend e2e — S30 speakable arc (plan intent, merge-gate turn, client tool surface) through the mock |
| `tests/support/dev_server.py` | Test web server — app on :3000 with `DEEPSEEK_BASE_URL` → stub on :3001 |
| `tests/support/summon_stub.py` | Local DeepSeek chat-completions stub (valid/bad/retry specs, call counter) |
| `tests/support/pipecat_mock.py` | Mock Pipecat voice server for headless e2e (no GPU/venv models needed) |
| `tests/support/fake_pi.py`, `fake_pi_rpc.py` | Stub `pi` / `pi --mode rpc` binaries for unit tests |
| `tests/unit/*.py`, `tests/unit/*.mjs` | Pure-Python/Node unit suites: obsidian memory (e2e + pure), pi rpc, pi delegation, voice pacing, vault_cli, session_engine, plan_backend, sdf-core |
| `playwright.config.js` | Playwright config — runs `tests/support/dev_server.py` on port 3000 |
| `docs/PLAN.md` | Current plan — Tier 3 "Summoning v2" (SDF shape grammar + quality system) |
| `docs/MISSING_FEATURES.md` | Gap analysis audit — all 23 features confirmed implemented |
| `docs/voice-integration-spec.md` | Authoritative Pipecat voice integration spec (protocol §A, env, deployment) |
| `docs/voice-pacing-plan.md` | Voice pacing (narrate-first acks, heartbeats; live tool-activity narration) |
| `docs/pi-delegation-plan.md` | Server-side `delegate_pi` / `steer_pi` tool execution via the warm `pi --mode rpc` session |
| `docs/PLAN_AGENT_BACKEND.md` | Agent-backend plan — `vault_cli.py` + `session_engine.py` (plan/execute partner: brainstorm → plan.md → git-worktree workers → human-gated merge). Companion to `PLAN.md`, ships alongside the voice server |

## Quick Start

```bash
cp .env.example .env
# edit .env with your API keys
pip install -r requirements.txt        # site + API
python3 server.py                      # local dev on :3000
```

`DEEPSEEK_API_KEY` is required for `/api/summon` spec synthesis and the voice
brain (falls back to curated-library-only summons without it). Voice also needs
the local Pipecat server running — install `requirements-voice.txt` into
`.venv-voice` and launch `pipecat_server.py` (see `docs/voice-integration-spec.md`).
`OPENAI_API_KEY` is no longer used (the Realtime voice leg was removed).

Or serve statically with `npx serve .`.

## API

| Method | Path | Body | Response |
|--------|------|------|----------|
| POST | `/api/summon` | `{"concept": "a wide hourglass", "seed": 1234?}` | `{"spec": {...}, "id": "hourglass_wide", "seed": ..., "cached": bool}` — a JSON spec (never geometry). `422` → `{"abstractify": true}` on unrecoverable synthesis failure; `503` without `DEEPSEEK_API_KEY` |
| GET | `/api/health` | — | `{"status": "ok", "agent": "live"}` |

`/api/realtime/session` was removed — the Realtime voice leg is gone. The local Pipecat server owns voice (WS `/api/voice/ws` on `pipecat_server.py`, not `api/index.py`).

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
- Voice: browser ↔ local Pipecat server (`pipecat_server.py`) over WebSocket; the browser only does audio I/O (mic in, speakers out) plus client tool execution (`spawn_object`, `summon_object`, `web_search`, `get_time`, `get_weather`). VAD/STT/TTS run server-side (Silero VAD → STT → DeepSeek LLM → Kokoro TTS). Turn-taking/barge-in is server-VAD driven (`user_started_speaking` flushes the playout queue). Visemes are driven by the real output-audio RMS, not text guesses.
- Voice server tool execution: tools declare `runsOn: 'client' | 'server'`; `delegate_pi` runs headless on the machine and returns a capped result (~1500 chars) into the LLM context. Tier 2: `delegate_pi` runs through a warm per-connection `pi --mode rpc` session (`pi_rpc.py`) — no per-call cold start, pi keeps in-process context across calls; `steer_pi` redirects a running task; barge-in aborts the run but keeps the session alive. Falls back to one-shot `pi -p` (`execute_delegate_pi`) if the RPC session fails.
- Obsidian memory brain: the voice agent has durable, queryable memory in an Obsidian vault (default `~/Documents/Obsidian Vault`, env `OBSIDIAN_VAULT_PATH`). Server tools `memory_recall` / `memory_read` / `memory_write` are fast in-process vault file ops (`obsidian_memory.py` — pure stdlib, unit-testable); `memory_summarize` delegates cognition to pi via the warm RPC session (cwd=vault). Notes carry YAML frontmatter + tags; `[[wiki-links]]` are traversed on recall (1 hop). Writes never overwrite — they create or append a dated section. Results capped ~1500 chars.
- **Plan/execute backend (docs/PLAN_AGENT_BACKEND.md):** the voice agent is a planning + building partner. `plan_work` starts a brainstorm → research → draft `plan.md` → promote → fork → execute → human-gated-merge arc that runs **behind an orchestrator wall**: the always-hot voice prefill is a stable small set (G5), and `plan_work`/`step_task` + the heavy `structure_notes`/`session_engine` schemas are lazy-injected only on plan intent (`PLAN_INTENT_RE`). `vault_cli.VaultCLI` is the structure tool (append-only discipline; frontmatter status/promote/index are the only in-place edits); `session_engine.SessionEngine` drives git-worktree Model-B workers that run **inline** (`read/bash/edit/write` only, `--no-skills`, `--exclude-tools subagent*` — never delegate to subagents), with merge-gate G2 (no auto-merge and no auto-resolve: `approve_merge` + a prior clean `sync_session` are required). Coordination state (plan.md contract, session-tree notes, logs) lives only in the vault, never inside forked worktrees (C3). `session_tree` walks via `child:` frontmatter deterministically (C6); the vault `log:` section is ground truth (C7).
- Tool-activity filler speech is OFF by default (`VOICE_ANNOUNCE_TOOLS=0`): the agent stays silent while tools run, so you never hear a tool call announced. This gates all three pacing mechanisms at once — the Tier-1 narrate-first ack (VOICE_ACK_TEXT, default "On it — running that now."), the one-shot heartbeat (VOICE_HEARTBEAT_TEXT after VOICE_HEARTBEAT_S, default 8s), and Tier-2 live pi narration (PI_NARRATE_MIN_GAP_S=2.5s; PI_TOOL_PHRASES). Set `VOICE_ANNOUNCE_TOOLS=1` to re-enable. Acks are filler: never enter LLM context or the assistant buffer. The RPC session streams text deltas for the final answer and tool events for narration.
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

Env vars required in Vercel (or `.env` locally): `DEEPSEEK_API_KEY` (required for
`/api/summon` spec synthesis and the voice brain; without it summons fall back to
the curated library). Optional: `DEEPSEEK_MODEL` (default `deepseek-chat`),
`DEEPSEEK_BASE_URL`, `KV_REST_API_URL` + `KV_REST_API_TOKEN` (Vercel KV cache in prod;
dev uses `.cache/specs/`, gitignored). `OPENAI_API_KEY` is no longer used. Voice
additionally needs the local Pipecat server env vars in `.env.example` and a running
`pipecat_server.py` — see `docs/voice-integration-spec.md`.
