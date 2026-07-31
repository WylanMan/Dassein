# Dassein — PLAN.md: Tier 2 "Summoning"

Current authoritative plan. Supersedes the v4 redesign plan, PLAN_TIER1.md, and VOICEPLAN.md. The Tier-1 shape system (spec model, modifiers, blend, cached bases, GLB loading) is implemented in the working tree; step 0 finishes and commits it.

## Status — all steps shipped (2026-07-31)

- **Step 0–5 ✅** — Tier-1 commit, compound builder + profiles (A1/A3), curated library (A4), DeepSeek spike (D2), `/api/summon` (B1/B2/B3 + S17/S19/S21), voice summoning (C1/C2/C3 + S18/S20).
- **D2 verdict ✅ PASS** — 10/10 concepts built (gate ≥7); identifiability confirmed cold on fully-settled renders. Initial 0/10 was a **capture artifact**: screenshots were taken 350ms into a 1.5s morph (mid-transition frames). Lesson: **summon screenshots must be captured after the morph settles (~2.2s)**, not on spawn.
- **F3 ✅** — full suite: 31 tests green (`tests/e2e/dassein.spec.js` S1–S16/T-series, `summon.spec.js` S17/S19/S21, `tier2.spec.js` S18/S20). DeepSeek mocked via `DEEPSEEK_BASE_URL` → `tests/support/summon_stub.py` (port 3001).
- **Deploy ⏸** — all code committed and tested; deployment deferred by choice. `vercel --prod` when ready; `DEEPSEEK_API_KEY` is already set in Vercel Production.

## Premise

The agent writes a shape's **DNA** (a spec); the client's Tier-1 pipeline synthesizes the form (build → weld → FPS → 478-point morph). Two sources, one data structure:

1. A **curated spec library** — hand-written specs, deterministic, guaranteed legible, zero API, zero latency.
2. **DeepSeek-flash spec synthesis** — the cache-miss handler for anything the library lacks.

Quality bar is **identifiability, not fidelity**. The 478-point wireframe net forgives crudeness; the silhouette must read. A boxy hourglass that reads as an hourglass is a success.

## Hard guarantees

- **G1:** Tier-1 behavior untouched — spec path, pills, face/sphere/model semantics, blends stay as-is. Compound is purely additive.
- **G2:** No new client-side runtime dependencies; all new deps (DeepSeek) live server-side.
- **G3:** Every spawned form satisfies the ≥478 unique welded-verts guard; any failed summon degrades to a seeded abstract form + agent narration — never a crash.

---

## Part A — Compound builder + curated library (ship first)

### A1. Compound builder (`index.html`)
Extend the spec grammar: `spec` gains optional `parts: [{type, pos, rot, scale, params, mods}]`.
- Each part builds via existing `PROCEDURAL_BUILDERS` + `getBase`-style caching (composite parts key).
- All part point sets merge **before** the weld → FPS step (same mechanism as `union`/`helix`), then FPS to 478 and `nearestNeighborEdges(6)` as today.
- Parts live in a bounded work volume (±1.4r) so edges never bridge distant islands.
- Route: `spec.parts` present → compound path; else existing single-type path. `window.__scene.spec` mirrors both.

### A2. Legibility grammar (LLM-positioning weakness mitigation)
- **Orientation vocabulary:** `rot: 'up'|'flat'|'side'` presets + optional degrees — never raw Euler angles.
- **Anchor-part pattern:** the first part is the anchor; others attach relative to it (Scenethesis pattern).
- **Cap ≤ 12 parts.** More parts = more ways to become unreadable.

### A3. Profile-parameterized builders
- `latheBuilder` gains explicit `profile: [[y, r]...]` (vase/goblet/rocket/bowl become presets).
- `extrudeBuilder` gains explicit `profile: [[x, y]...]` + depth (star/gear/cross/hexagon become presets).
- No new builder types for v1 — parts + profiles + mods cover the simple-object vocabulary.

### A4. Curated spec library (12–20 specs)
Hand-written storytelling specs: hourglass, throne, labyrinth, lantern, key, door, chain, monument, stone arch (bridge), chrysalis, threshold gate, well, sundial, crown, ship, altar. Perfect every time — this is the demo-day deliverable. The library's data structure is identical to the LLM-tier cache entries, and the library doubles as the few-shot example bank in the LLM system prompt.

---

## Part B — LLM synthesis tier (DeepSeek)

### B1. `POST /api/summon {concept, seed?}` (`server.py` + `api/index.py`)
Returns a **JSON spec** (never geometry — the client owns building):
1. Cache lookup by canonical `id` + seed (`.cache/specs/` dev / KV prod). Specs are a few KB — trivial to cache.
2. Miss → DeepSeek call (OpenAI-compatible; `DEEPSEEK_API_KEY` / `DEEPSEEK_MODEL` / `DEEPSEEK_BASE_URL` from env; `response_format: json_object`). System prompt = spec grammar + simple-forms contract + curated library as worked examples. Output includes a **canonical `id`** the LLM chooses ("hourglass_wide") — the cache key, so "a chair" and "chair" collapse to one entry.
3. Validation: schema, numeric ranges, ≤12 parts, orientation vocabulary, profile sanitization (winding order, no self-intersection, no negative radii). Fail → **one fix-prompt retry** ("your output failed: <error>. Correct it."); second fail → 422 with an abstractify directive.
4. Cache the spec, return `{spec, id, cached}`.

### B2. Seed policy
- Default: `seed = hash(canonical_id)` → stable, cacheable, deterministic.
- "Different" / "surprise me" → seed+1 (jitter is the only seed-sensitive mod).
- This is what makes the cache actually hit: pinned seeds, not random ones.

### B3. Client-side build + validation gate
Build the spec through the existing pipeline; post-build sanity: all-finite, spread within volume, non-degenerate. Fail → seeded abstract form + "it resisted capture; here is its abstract form." The fallback is the quality system, not an error.

---

## Part C — Voice + UX

### C1. New tool `summon_object {concept}` (`voice-realtime.js` + `index.html`)
- `INSTRUCTIONS` decision rule: known `OBJECT_TYPES` → `spawn_object`; anything specific, novel, or metaphorical → `summon_object`.
- **Simple-forms contract:** prefer solid, simple, stylized forms; avoid thin/lacy/hollow/mechanically complex requests; if the request is fragile, narrate and summon its essence (bridge → stone arch).
- Concept is treated as **data** in the prompt, not instructions (injection hygiene).

### C2. Summon flow
- t=0: stand-in morph (procedural blob, `seed = hash(concept)`) — the gathering-magic moment.
- Agent narrates during the wait; voice keeps flowing.
- On spec arrival: `interruptMorph()` → morph into built targets.
- Latency budget: ~1–2s build, 2–5s DeepSeek, worst case +5s retry; hard cap ~8s then narrate-and-continue (leave stand-in, absorb miss later).

### C3. Re-roll loop (fixes misreads, not polish)
- "Different" → seed+1 re-summon.
- "Like that but X" → refined concept re-summon (new canonical id, new entry).

---

## Part D — Quality contract (identifiability)

- **D1.** Bar: shown a screenshot cold, a stranger can say what it is. Not beauty, not fidelity.
- **D2. Spike gate** (dev-time, before endpoint work): 10 concepts → ≥7 build → ≥4 identifiable cold. Fail → **kill switch**: curated library + Tier-1 vocabulary only; LLM tier demoted to an experiment.
- **D3.** The abstractify fallback absorbs every miss — a miss becomes a narrated abstract form, never a broken render.

---

## Part E — Deferred

- **E1.** Organic tier (Tripo text-to-3D + Vercel Blob GLB cache) for real-world/organic asks ("a fox", "an oak tree"). Documented, not built. `/api/summon` schema leaves room for `mode: 'organic'` so nothing needs rework.

---

## Part F — Infra & tests

- **F1.** `.env.example` += `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL` (default `deepseek-chat`, confirmed by spike), `DEEPSEEK_BASE_URL`. `requirements.txt` unchanged (httpx suffices). Dev cache dir `.cache/` gitignored.
- **F2.** Verify `BufferGeometryUtils.mergeGeometries` is reachable via the import-map addons path; else hand-roll a Float32Array concat (~10 lines).
- **F3.** Tests (`tests/e2e/dassein.spec.js`), DeepSeek mocked by pointing `DEEPSEEK_BASE_URL` at a local stub:
  - **S17** `/api/summon` returns a valid spec
  - **S18** compound spec builds ≥478 verts and morphs clean (fixture specs, no API)
  - **S19** invalid spec → fix-retry → abstract fallback path
  - **S20** `summon_object` voice tool end-to-end (stub)
  - **S21** cache hit returns canonical spec with no API call
  - Plus `python3 server.py` smoke.

---

## Execution order (commit after each)

0. **Ship Tier 1** ✅ — A4 voice schema (speakable params), A5 (`blob`/`helix` + family params), C (S8–S13), B5 (AGENTS.md).
1. **A1 + A3** ✅ — compound builder + profile params (client-side, `__testHooks`-verifiable).
2. **A4** ✅ — curated spec library → demo day: voice summons 16 curated objects.
3. **D2** ✅ — DeepSeek spike against the gate: 10/10 built, ≥4 identifiable cold (settled renders). Verdict: **proceed**.
4. **B1 + B2 + B3** ✅ — `/api/summon` + cache + validator + fix-retry + S17/S19/S21.
5. **C1 + C2 + C3** ✅ — voice tool, stand-in morph, narration, re-roll + S18/S20.
6. **F3 full suite** ✅ — AGENTS.md + docs update, deploy.

**Risks:** DeepSeek format drift (pinned prompt, strict validator, one retry, tier-0 fallback); compound edge-bridging (bounded volume + gate); coordinate misalignment (orientation vocab + anchor + caps). Kill switch: D2.
