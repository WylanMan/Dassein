# dassein.io — an interface for thinking out loud in 3D

`dassein.io` is a **live, voice-driven human-computer interface** — not a chatbot with a face, but an interface to the one thing AI has always been worst at: **making and iterating on 3D form.**

The problem is an interface problem, not a model problem. LLMs are astonishing with words and clumsy with geometry. Ask a model to "model" something and you get a pile of coordinates you can't meaningfully edit, or a rendered image you can't touch. Neither is an *interface* — there's no loop. Dassein closes that loop: you converse with the machine **in the medium you're making**, and you shape the result together.

## The design principle: constrain the grammar, then compose

Everything rests on one idea: **the model never writes geometry — it writes a short, declarative shape-spec ("shape DNA").** primitives, modifiers, parts, blends, unions. A small deterministic kernel (`sdf-core.mjs`) compiles that spec into a live wireframe. You specify *what*; the kernel figures out *how*.

From a **fixed** vocabulary the system yields **practically unbounded** form:

- a finite set of primitives, welded and cached
- a fixed order of modifiers — `squash → bend → twist → taper → bulge → spherize → jitter`
- compounding of up to 12 attached parts
- `union` (fuse two forms) and `blend` (morph between two at a ratio)

Simplicity at the base, infinity at the surface. That's the whole insight: **constrain the vocabulary, compose the pieces, and a tiny rule set unlocks limitless representation.**

## The loop *is* the interface

Text generation is one-shot. Making things isn't — and that's exactly why this is an interface rather than an output. The loop is iterative by design:

- **Summon** — ask for a concept. A curated library of 16 hand-written summons answers instantly (zero latency); anything else calls `/api/summon`, where DeepSeek writes the spec and the kernel renders it.
- **Re-roll** — say "different"; the seed bumps and you get a new form.
- **Refine** — adjust the concept; it gets a new canonical identity and remorphs.
- **Combine / blend** — fuse two forms, or morph between them at any ratio.
- **Graceful by design** — every failure degrades to a seeded abstract form. **Never a crash.**

You steer, it drafts, you converge. That's a collaborator — not a finished image handed back once.

## Why wireframe?

The wireframe is the honest substrate. It doesn't hide the structure — it *shows* the math, the joints, the topology. It's geometry thinking out loud: the model proposes, the kernel resolves, and you watch the proposed form assemble. The aesthetic isn't decoration; it's the proof-of-work made visible.

## It's more than a face in a browser

The "talking face" is just the front. Behind it is a working agent:

- **Voice:** a local Pipecat server runs `Silero VAD → STT → DeepSeek → Kokoro TTS`, speech-to-speech with **real-time barge-in**. The browser only does audio I/O; everything else is server-side.
- **Memory:** durable, queryable memory in an Obsidian vault — the agent recalls and writes across sessions.
- **Tool execution:** live tools (`spawn_object`, `summon_object`, `web_search`, `get_time`, `get_weather`), plus server-side `delegate_pi` / `steer_pi` through a warm `pi --mode rpc` session — no per-call cold start.
- **Plan/execute backend:** a full `brainstorm → plan → git-worktree workers → human-gated merge` arc, so the agent isn't just chatty — it plans and does.

## Architecture

| Layer | What |
|---|---|
| **Interface** | Single `index.html` — inline CSS + Three.js (`three@0.152.0`, import map) + GSAP. No build tool, no framework. |
| **Shape engine** | `sdf-core.mjs` — pure SDF kernel; `compileSdf` / `targetsFromSDF`. No DOM/Three dependency; unit-tested in isolation. |
| **Spec synthesis** | `api/summon.py` — DeepSeek writes the spec (JSON), validator + fix-retry + cache. `422` → `abstractify`. Served by Vercel (`api/index.py`) and a local `server.py`. |
| **Voice server** | `pipecat_server.py` — local, WS `/api/voice/ws`; browser is audio I/O + client tool execution. |
| **Agent backend** | `pi_rpc.py` (warm session), `obsidian_memory.py` (memory brain), `vault_cli.py` (structure tool), `session_engine.py` (git-worktree fork/worker/merge). |

## Tested

Playwright E2E (landing → transform → agent mode → procedural spawn → summon → tier-2/tier-3 → voice + voice-sessions) and isolated Node/Python unit suites (`sdf-core`, `session_engine`, `vault_cli`, `obsidian_memory`, voice pacing, pi delegation).

## Quick start

```bash
cp .env.example .env          # add your DEEPSEEK_API_KEY
pip install -r requirements.txt
python3 server.py             # local dev on :3000
```

Voice additionally needs the local Pipecat server (`requirements-voice.txt` → `.venv-voice`, run `pipecat_server.py` — see `docs/voice-integration-spec.md`). Or serve statically with `npx serve .`

## Live

**https://www.dassein.io** — speak to it, ask it to make something, steer the form.

---

*Built and shipped by [Wylan Man](https://github.com/WylanMan) · Durham Mech Eng (2:1) + multidisciplinary AI/agentic systems.*
