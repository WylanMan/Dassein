# Dassein — PLAN.md: Tier 3 "Summoning v2" (SDF shape grammar + quality system)

Current authoritative plan. Supersedes the Tier-2 "Summoning" plan (shipped 2026-07-31: compound builder, profiles, curated library, DeepSeek spec synthesis, voice summoning). Tier 3 replaces the *spec grammar and the net-building pipeline*, not the product surface: pills, voice, face/sphere/model semantics, the 478-point morph, and the summon flow all survive.

## Decisions locked (2026-07-31 review)

1. **Aesthetic identity: angular.** Hard booleans are the default idiom; faceted prims and crisp creases are the house look. Smooth ops exist only as an accent (`k ≤ 0.15`). Rationale: the 478-point k-NN wireframe reads best on angular, structural, silhouetted forms; SDFs left unchecked drift blobby, which is the exact "5-of-22-builders-are-displaced-icosahedrons" failure this plan exists to fix.
2. **No vision model.** Quality verification is **human-in-the-loop only**: a client-side "keep this" affordance feeds a promotion flywheel into the curated few-shot bank. No image critique anywhere.
3. **Screenshot gate.** Curated re-expressions cut over only after Playwright golden-image diffs against the current renders (settled ≥2.2s).
4. **Order-aligned FPS.** Shape targets are sampled along **478 canonical reference directions** (the existing `icoPoints` FPS set), so index *i* always means "the surface point along direction *d_i*." This makes shape↔shape morphs coherent — pointwise lerp no longer maps unrelated net positions. The current mush at mid-ratios was unrelated FPS orderings, not blend math.
5. **Extract `sdf-core.js`.** The pure SDF kernel is a separate ES module (import-mapped), breaking the "all JS inline" convention deliberately so the most bug-prone code in the project is unit-testable in isolation.

## Why the Tier-2 grammar is a 3/10 (the diagnosis)

Reading the shipped code end-to-end, the quality ceiling is structural, not the LLM:

- **Composition is crude.** `union` merges point clouds — buried/overlapping surfaces keep their points; `parts` is a flat primitive list (index.html:1537, 1434). Fused, structural shapes are impossible; everything reads as parts bolted on.
- **Modifiers run on the sampled 478 points** after geometry is destroyed (index.html:1590). `bend` is a parabolic shear (`x += r·h²`), `twist` tears the k-NN net. They distort a wireframe; they don't bend a shape.
- **Blend is an index-wise lerp of unrelated FPS orderings** (index.html:1666) → crumpled mush at mid-ratios.
- **The LLM is asked to author coordinates it can't.** Profile lathes require exact `[y,r]` arrays; DeepSeek guesses → lumpy silhouettes.
- **Few-shot dominance.** Outputs mimic the 16 curated examples (vase/hourglass-lite) instead of the concept.
- **5 of 22 builders are the same displaced icosahedron** (gem/rock/crystal/pebble/blob, index.html:1115) — one trick, five noise knobs.

## Why SDF

2026 research converged on **Signed Distance Fields as the LLM-native shape language**:

- **ALICE-SDF** (2026): text → LLM → SDF JSON tree (primitives, CSG ops, domain modifiers) → mesh; validates and fix-retries — the architecture Dassein already has.
- **Curv / atelier-mcp**: "the aesthetic lives in the tools, not the model" — a constrained SDF/CSG operation vocabulary produces consistent output.
- **Proc3D** (2026): LLM-generated *procedural compact graphs* are 4–10× more token-compact than code DSLs → fewer hallucination errors; constrained graph beats free code.

The operative insight: **LLMs can't author coordinates, but they're good at structure.** "A crown is a band hard-unioned with repeated spikes" maps to `union(revolve(profile), polar_repeat(cone))`; "symmetric" maps to `mirror`; "chain" maps to `repeat`. And SDF domain warps (twist/bend/taper) are applied *before* surface extraction → real bends, real twists.

Crucially, SDF evaluates pointwise — no meshing needed. We sample the **outer surface directly by radial probing along 478 canonical directions**, which (a) kills the buried-surface problem of the old `union`, (b) gives order-aligned morphs for free, (c) is <5ms per build.

---

## Phase 0 — Face-as-loading (ship first, ~30 min)

Replace the seeded-blob stand-in with a **contemplation state**:

- `summonStandIn()` (index.html:1924) → morph to `face` instead of a blob spec.
- Add a subtle breathing pulse (slow scale oscillation on the 478-net) + iris glow shimmer while `/api/summon` is in flight; a "concentrating" beat in the narration.
- On spec arrival: standard face→shape morph (index.html:2063 handles it); timeout/narrate-and-continue keeps the face until the spec lands; failure still degrades to seeded abstract (unchanged guarantee).
- Gate: S23 e2e (summon shows face, then morphs to shape).

## Phase 1 — `sdf-core.js` kernel + order-aligned net (the renderer)

### Architecture
Pure ES module (import-mapped, no deps): **compile the spec `root` tree → `d(p) → Number` closure → radial-probe 478 directions → `{targets, edgeIndices}`.** No marching cubes, no weld, no FPS — the SDF path constructs exactly 478 ordered surface points.

```
compileSdf(root)            // recursive: prims | profile-prims | combinators | transforms | surface detail
referenceDirs               // the 478 icoPoints, normalized — fixed, cached (identical ordering to the sphere)
sphereTrace(d, d0)          // step outward to first sign change, binary-refine ~6 iters → radius
targetsFromSDF(root)        // pts[i] = refDir[i] * r_i  → nearestNeighborEdges(pts, 6)
```

- **Ray miss** (hole/concave direction, no sign change in volume): fill by seeded-FPS over the hit points (deterministic), reindex. Angular artifacts are near-star-shaped, so misses are rare; the curve-swept leaves below never take this path.
- **Point ordering is order-aligned by construction**: index *i* is always "surface along direction *d_i*" → shape↔shape morphs lerp coherently. Add a morph-sanity property test: for fixture pairs, per-index travel at t=0.5 stays bounded (no point crosses the volume center).
- Deterministic: `seed` touches only noise ops; the net is seed-free. Cache keyed by `v2:<root-hash>:<seed>` (bounded ~80, as today).

### Op catalog (angular-biased, ~30 ops)
| Family | Ops | Angular default |
|---|---|---|
| Primitives | sphere, box, rbox, cylinder, cone, pyramid(n), torus, capsule, ellipsoid, superellipsoid, gem, rock, crystal, pebble, blob | box/pyramid/crystal/gem are the house idiom; blob is the fallback |
| Profile-prims | revolve (lathe via 2D profile), extrude (2D profile), star, gear, polygon, cross, rect, rect_r | profiles smoothed via Catmull-Rom from 4–8 authored points (LLM-friendly) |
| Combinators | **union, intersect, subtract** (hard — default), smooth_union/intersect/subtract (**k ≤ 0.15**, accent only), blend(A,B,t) (field lerp), mirror(plane), repeat(axis, n, spacing), polar_repeat(n) | hard booleans are the default composition; creases become dense node clusters that read great in wireframe |
| Transforms (domain) | translate, rotate (presets+deg, keeping the orientation vocabulary), scale, twist, bend, taper, squash, bulge, spherize | applied to the coordinate before distance eval → real warps |
| Surface detail | displace (noise amp/freq/seed), facet(levels), ridged, worley, round(r) | facet() is the low-poly look; displace for rock/crystal |

Depth ≤ 5, ≤ 32 nodes (validated). Closed-form SDFs only:
- `revolve`/`lathe` → `sdRevolution` over a 2D profile SDF; `extrude` → `sdExtrude`; star/gear/polygon/cross → standard 2D polygon SDFs.
- **Curve-swept leaves (`helix`, `spiral`, `knot`) are NOT SDFs** — keep the existing `TubeGeometry` builders and merge them as point-cloud unions at the edge stage (never smooth-blended; documented). No mesh→field voxelization, ever — it was the riskiest code in the original plan and it's unnecessary.

### Integration
- New path in the build routing (sibling of `getBase`/`getCompoundBase`, index.html:1413/1537): `spec.schema === 2` → `targetsFromSDF(root)`; v1 specs keep the existing builders unchanged.
- `nearestNeighborEdges`, cache, `scaleTargets`, `morphTo`, `switchShape` are untouched; only the builder side gains a path.
- Gate: S18-style conformance (478 valid points), determinism test (same spec → identical arrays), perf guard (<25ms/build).

## Phase 2 — Grammar v2 server side (`api/summon.py`)

- **Recursive validator** per op: arity, children, param ranges (e.g. `k ∈ [0, 0.15]`, `n ∈ [2, 24]`, `spacing ∈ [0.1, 1.2]`), depth/count caps, orientation vocabulary, profile shape (strictly monotonic height, `r ≥ 0`). Fail → one fix-prompt retry (existing mechanism, index of errors) → 422 abstractify.
- **Single-pass generation.** No critique/refine pass — with no vision in the loop, self-critique of JSON is theater. One call + validator retry; the 6s client cap (index.html:1993) is respected. Quality comes from the grammar, the angular prompt, the curated bank, and the Phase-4 flywheel.
- **Prompt rebuilt around the angular identity**: an idiom cookbook (fused parts → hard `union`; spikes/teeth → `repeat`/`polar_repeat`; symmetric → `mirror`; vessels → `revolve`; slabs → `extrude`; crisp edges preferred), *negative* guidance (no thin/lacy, one dominant gesture, prefer facets and hard joins), and the v2 curated re-expressions as few-shot examples. Examples kept small (4–8 node trees) to protect DeepSeek's nested-JSON reliability.
- **Cache rekeyed** to `v2:<root-hash>:<seed>`; slug→id index preserved. Never break existing cached entries — v1 cache keys and specs remain valid for the v1 path.
- Gate: S17/S19/S21 updated to v2 fixtures (`tests/support/summon_stub.py` serves v2 specs: valid / invalid / retry).

## Phase 3 — Curated library v2 + screenshot gate

- Re-express the 16 curated shapes in grammar v2 (crown via `polar_repeat(cone)` instead of 5 hand-placed cones; gate via hard `union`; well via `subtract`-style hollow). Regenerate `data/curated_specs.json`.
- **Screenshot gate (mandatory cutover):** for each v2 re-expression, Playwright renders it **settled (≥2.2s — the D2 lesson)**, screenshots, and diffs against the current v1 golden (`tests/golden/`). Only entries that pass (pixel-diff tolerance + human identifiability check) ship. v1 builders stay in the tree until every entry passes.
- Gate: S25 golden-image regression over all 16.

## Phase 4 — Human flywheel + tests + docs

- **"Keep this" affordance:** after a summoned shape settles, a subtle save control (shape-row button + voice phrase "keep this") stores `{spec, id, concept, seed, ts}` in localStorage (bounded ~20) and writes a screenshot to `data/saved/`.
- **`tools/promote_saved.py`:** merges saved specs into `data/curated_specs.json` with dedupe/id-rename, then regenerates the `CURATED_SPECS` block in `index.html` (and thus the few-shot bank). Human-in-the-loop: every best summon becomes a permanent, zero-API, instant summon. This is the quality engine that replaces the vision-model idea.
- **Re-rolls get structured variation:** `variation` map keyed by seed — repeat counts, proportions, spike counts, noise amplitude. "Different" yields meaningfully different (still cacheable) forms instead of `jitter+1`.
- Tests: S22 (order-aligned morph property), S23 (face-as-loading), S24 (flywheel promote→curated), S26 (structured re-roll variation). Update `docs/AGENTS.md` (grammar v2, `sdf-core.js`, flywheel, angular identity).

## Hard guarantees (carried forward, restated for v3)

- **G1:** Every spawned form is exactly 478 ordered points; shape↔shape morphs are order-aligned.
- **G2:** Every failed summon degrades to a seeded abstract form + narration — never a crash.
- **G3:** Deterministic — same spec + seed → identical net; cacheable.
- **G4:** No new third-party runtime deps. `sdf-core.js` is our own pure module; all network calls stay server-side.

## Files

| File | Change |
|---|---|
| `docs/PLAN.md` | This plan |
| `index.html` | `sdf-core.js` import; `targetsFromSDF` route; CURATED_SPECS v2; summon flow (face-as-loading, keep-this save, structured variation) |
| `sdf-core.js` | **New** — pure SDF kernel (prims, ops, domain transforms, 2D profiles, noise, radial probe, `targetsFromSDF`) |
| `api/summon.py` | Grammar v2 validator + angular prompt + `v2:` cache keys |
| `data/curated_specs.json` | Regenerated from v2 CURATED_SPECS |
| `tests/support/summon_stub.py` | v2 fixtures |
| `tests/e2e/*.spec.js` | S17–S21 updated; S22–S26 added |
| `tests/golden/*.png` | Curated shape goldens (settled renders) |
| `tools/promote_saved.py` | **New** — flywheel merge script |
| `AGENTS.md` | Grammar v2, architecture, flywheel |

## Execution order (commit after each)

1. **Phase 0** — face-as-loading (independent, ships immediately). ✅ *done — commit `a371381`*
2. **Phase 1** — `sdf-core.mjs` + `targetsFromSDF` + order-aligned morph, behind the v2 route; benchmarks; S22. ✅ *done — commit `70052c5`*
3. **Phase 2** — server grammar v2 (validator, prompt, cache rekey, stub fixtures); S17/S19/S21. ✅ *done — commit `08d07bb`*
4. **Phase 3** — curated v2 re-expression **behind the screenshot gate**; S25. ⬜
5. **Phase 4** — flywheel (keep-this + promote script), structured variation, S23/S24/S26, AGENTS.md + docs. ⬜

## Progress

| Phase | Status | Notes |
|---|---|---|
| 0 — Face-as-loading | ✅ Shipped | `summonStandIn` → contemplation face (breathing + iris shimmer); `summonAbstract` fallback preserved; timeout narration "I'm concentrating…"; **S23 e2e added** (stub gains `slow_reliquary`). |
| 1 — SDF kernel + order-aligned net | ✅ Shipped | `sdf-core.mjs` (pure ES module), ~30-op catalog, Catmull-Rom profiles, radial probing along the 478 canonical directions, ray-miss fill, hard booleans + `k ≤ 0.15` smooth accents; `spec.schema === 2` route + `v2:` cache keys in `index.html`; **S18v2 / S18v2b / S22 / perf-gate** e2e + isolated Node unit tests (`tests/unit/sdf-core.test.mjs`). |
| 2 — Server grammar v2 | ✅ Shipped | `build_prompt` rebuilt around the angular identity (idiom cookbook: fused→`union`, spikes/teeth→`repeat`/`polar_repeat`, symmetric→`mirror`, vessels→`revolve`, slabs→`extrude`; negative guidance; `V2_EXAMPLES` few-shot bank); `validate_v2_spec` = top-level id/size/root checks over the recursive `validate_v2_root`; `SpecCache` rekeyed to `v2:<root-hash>:<seed>` with a slug→`{id, root}` index (legacy string index entries treated as a miss); `summon()` = single-pass v2 generation + one fix-retry + 422 abstractify; `summon_stub.py` serves v2 fixtures; **S17/S19/S21 updated** and S20/S23 re-pointed at v2 specs (see deviations). |
| 3 — Curated v2 + screenshot gate | ⬜ | |
| 4 — Flywheel + structured variation + docs | ⬜ | S23 shipped early under Phase 0's gate. |

**Deliberate deviations from the plan text (recorded as they happened):**

- `sdf-core.js` is named **`sdf-core.mjs`** — the repo's `package.json` is `"type": "commonjs"`, so a `.js` module is not Node-importable and could not be unit-tested in isolation as the plan demands. Browsers load it fine either way.
- **Ray-miss fill** uses all sign changes along a ray (`probeSurfaces`), deduped into a surface cloud, then seeded-FPS to exactly 478 — an implementation of "seeded-FPS over the hit points, reindex" that also captures far/cavity walls, so hollow and ring forms (torus/crown/vault) keep their full silhouette instead of collapsing to the near wall only.
- Two kernel bugs found and fixed in Phase 1: (1) `traceRay` must clamp its final probe to `maxR` or the exponential step overshoots and every ray misses; (2) `revolve` must mirror its profile across the axis — closing the polygon through the axis put the origin *on* the boundary (`d(0)=0`), so every ray reported a surface at `r ≈ 0`.
- **S23** (listed under Phase-4 tests) was implemented in Phase 0 because Phase 0's own gate names it.
- **S20/S23 updated in Phase 2, not Phase 3:** the stub now serves v2 fixtures by default, and those two tests consume the stub's output directly (assertions on `spec.type === 'goblet'`), so they had to move to `schema: 2` + `root` assertions when the fixture flipped. No production client change was needed — the v2 route already existed from Phase 1.

## Risks

- **Radial probing limits:** concave back-surfaces (e.g., the inner U of a horseshoe) are unrepresentable by first-hit rays. Accepted: the angular-artifact aesthetic is near-star-shaped; k-NN fill and curve-swept leaves cover the gaps. Note: interior/buried surfaces vanish — the old `union` buried-surface problem is *fixed* by design.
- **DeepSeek nested-JSON drift:** mitigated by small examples, `json_object`, one fix-retry, tier-0 abstract fallback, and the v1 path remaining live until Phase 3 cutover.
- **Curated regression:** the screenshot gate is mandatory; v1 builders stay until all 16 pass.
- **Morph psychology:** order-aligned FPS fixes shape↔shape coherence. The sphere↔face and face↔shape transitions are semantic nets and are deliberately left as-is.
- **Convention break:** `sdf-core.js` leaves the single-file pattern deliberately — it's the purest, most testable code in the project and the unit tests depend on it.
