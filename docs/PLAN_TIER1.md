# Dassein Tier-1 Shape System + Repo Cleanup — Plan

Supersedes all prior discussion this session. Two hard guarantees: **(G1)** existing shapes render at their current absolute sizes; **(G2)** the Duck model stays reachable with zero config. Everything in Tier 1 is additive.

---

## Part A — Tier 1: spec, modifiers, blends, speakable params

### A1. Unified spec model (`index.html`)
Replace `spawnObject(name, size)` with:
```
spec = { type, size='medium', params={}, mods={}, blend={with, ratio}, seed, url }
```
- Every `PROCEDURAL_BUILDERS[type](params)` accepts params; defaults = current constants.
- **Cache key = (type, params) only.** Base builds are welded + FPS'd once and cached (small, bounded ~26 entries). Mods, blend, size, and edges are cheap 478-point array ops recomputed per spawn (~1ms). `force` clears a base key.
- Pills route procedural names through the spec path; `switchShape` keeps only face/sphere/model semantics. Voice "cube" and pill "cube" are the same path by construction.
- **G1:** carry a per-builder `BASE_SCALE` so each name lands at its current absolute size (cube ~0.43r, normalized shapes 0.55r). Size scale applied as a uniform factor on targets, last.
- `window.__scene.spec` mirrors the active spec.

### A2. Modifiers on target arrays (not geometry)
`applyMods(targets, mods)` — pointwise, topology-independent, applied **post-FPS** in fixed order (squash → bend → twist → taper → bulge → spherize → jitter):
- `twist(deg)`, `taper(k)`, `bulge(k)`, `bend(r)`, `squash(kx,ky,kz)`, `spherize(k)`, `jitter(seed, amp)` — all functions of normalized height/radius; jitter reuses `mulberry32`/`hashString`.
- Deletes `normalizeGeometry`, `NATIVE_SIZE_NAMES`, the size special-casing, and any need to re-weld (eliminates the 492-vert guard hazard entirely).
- Add a builder-conformance rule to the tier-1 comment block: **every builder must produce ≥478 unique welded verts** (FPS guard at index.html:964 stays loud).

### A3. Blend morphing
- `targets = lerp(cache[A].targets, cache[B].targets, ratio)` — bases cached, so it's pure array math.
- **Size-normalize both bases to a common reference before lerp**, apply size after (matches G1 so `ratio=0` ≈ A exactly).
- Edges recomputed once via `nearestNeighborEdges(final, 6)` — reused by existing `morphToTarget`. No new tween machinery; barge-in works via `interruptMorph`.
- Restricted to procedural types. Visual note: index-correspondence lerp is a "reassembly" morph (same as the landing transform) — on-brand, not a clean topology morph.

### A4. Voice schema + speakable params (`voice-realtime.js` + index.html:2033)
- Flatten `spawn_object` to semantic fields: `object, size, seed, twist, stretch, sharpness, blend_with, blend_ratio, url` + optional `params` bag (sides, teeth, turns, inner) for family-specifics.
- `INSTRUCTIONS` vocabulary stays tiny: *"twisted, stretched, spikier, blend X into Y, surprise me"*.
- **G2:** `object:'model'` without `url` loads the Duck (kept as default URL, so the model pill stays functional). With `url`, calls new `loadGLBFromURL(url)`. CORS failures return a helpful error.
- Validation at index.html:2033 becomes spec-aware: valid types + hint at params/mods/blend/model-url.

### A5. Two new archetypes + family parameterization
- Parameterize existing families: star(`sides`,`inner`), gear(`teeth`), polygon(`sides`), pyramid(`sides`), spiral(`turns`,`thickness`), lathe(`bulge`,`waist`). Presets stay as defaults.
- Add only genuinely distinct bases: **`blob`** (new smooth noise profile) and **`helix`** (double-strand coil). Everything else is mod-reachable — the modifier chain *is* the archetype expansion.

---

## Part B — Repo cleanup

### B1. Backend residue (`server.py`, `api/index.py`, `requirements.txt`, `.env.example`)
- Remove `/api/chat`, `_handle_chat`, `_handle_stream`, `_sse_*`, `TOOLS`, `SYSTEM_PROMPT`, `CHAT_RESPONSES`, `_llm_call`, `/api/save-scan`, `/api/load-scan` from both files (verified: no page calls any of them).
- `requirements.txt` → `fastapi`, `httpx`, `requests`, `python-dotenv`. Drop `anthropic`, `openai`. Remove `random` import where orphaned.
- `.env.example` → drop `DEEPSEEK_API_KEY`, `ANTHROPIC_API_KEY`, `DEEPSEEK_MODEL`, `LLM_PROVIDER`; keep `OPENAI_API_KEY`.

### B2. GLB path refactor (keeps online-GLB capability)
- `loadGLBModel` → `loadGLBFromURL(url)`, reusing `targetsFromGeometry` (dedupes the current re-implemented weld/FPS/edge code). `GLTFLoader` stays.
- **G2:** Duck URL becomes the model default, not deleted. No `model` pill removal — it stays, routed through the default.

### B3. Delete dead files
`data/shapes/*.glb` (5 files), `scripts/build_glb_shapes.js`, `docs/GLB_REMESH_SPIKE.md`, `docs/PLAN_VOICE_AGENT.md`, `docs/NEWPLAN.md`. Keep `PLAN.md`, `MISSING_FEATURES.md`, `VOICEPLAN.md`. Remove `!data/shapes/` from `.gitignore`.

### B4. index.html micro-residue
- Remove unused `delaunator` importmap entry (index.html:155).
- **Keep** `agentAvatar.lookAt/loadProfile/_setBlink` (4 no-op lines — preserve public API surface).
- Refresh stale F-key comments; fix the pill-vs-voice `isAnimating` inconsistency (pills now call `interruptMorph()` too — new behavior, tested).

### B5. AGENTS.md updates
- **Repo:** API table (drop /api/chat, save/load-scan), tools list → `spawn_object` + client-side web_search/get_time/get_weather, drop "Text LLM chain" line, STRUCTURE table reflects deletions, add Tier-1 spec section.
- **~/.config/opencode/AGENTS.md:** still describes the old LangGraph support-agent — replace with a pointer to the repo AGENTS.md.

---

## Part C — Tests & verification

Extend the tier-0 describe (S1–S7 stay green via string→spec compat):
- **S8** spec determinism with params+mods
- **S9** modifier changes geometry (twist vs none differ)
- **S10** blend: `ratio=0` ≈ A, `1` ≈ B (approx, `< ε` per G1), midpoint differs from both
- **S11** voice tool accepts spec, rejects bad spec gracefully
- **S12** blend barge-in mid-animation lands clean
- **S13** pills interrupt an in-flight morph (new behavior from B4)
- Amend **S6** assertion to the spec-aware error text

Run: `npx playwright test` (full suite) + `python3 server.py` smoke (static, `/api/health`, `/api/realtime/session`).

---

## Execution order (commit after each)
1. **B1 + B3** — backend trim, file/doc deletions, gitignore (independent, zero index.html)
2. **A1 + B2 + B4** — one pass over the shape path: spec model, pill unification, `loadGLBFromURL`, Duck default, interrupt fix, micro-residue
3. **A2 + A3** — target-array mods, cached bases, blend
4. **A4** — voice schema + instructions + validation
5. **A5** — family params + `blob` + `helix`
6. **C + B5** — tests, both AGENTS.md files, full verification
