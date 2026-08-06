# Dassein — PLAN_AGENT_BACKEND.md: Obsidian CLI + git-worktree session engine

Current authoritative plan (Design Level: **L2** — concrete contracts, module boundaries
locked, no implementation yet). Companion to `PLAN.md` (the live Tier-3 "Summoning v2 / SDF"
plan, which this does not touch). This plan adds a second pillar: turning the voice agent
into a **planning + building partner** — a thin delegating front-end over an Obsidian
structure organiser (a tool) and a git-worktree session engine (fork/run/steer/merge).

Supersedes none. Ships alongside, behind the same local Pipecat server. Product surface
(shape system, summon flow, face) is untouched.

## Decisions locked (2026-08-04 review)

1. **Obsidian CLI is a TOOL, not a subagent.** Deterministic file-op layer called by the
   voice agent. Purpose: memory + structure organisation — the agent commands the vault as
   a working surface (create/organise folders; create/open/append/rename notes with YAML
   frontmatter; maintain the index). **Never overwrite or delete — create/append/move only.**
2. **Gates at merge ONLY.** Execution auto-runs within a phase; pauses for human approval at
   the merge gate. User may steer/abort by voice at any time.
3. **No multi-agent framework.** No MetaGPT/CrewAI/AutoGen. A single thin delegating voice
   agent + an orchestrator wall. Rationale: multi-agent costs 4–7× tokens (fatal for voice
   prefill latency); this need is "one good delegating agent," not a committee.
4. **Web research = the existing SearXNG-backed `web_search` tool.** The agent-browser is
   deliberately NOT exposed as a voice tool (the user intends to run agent-browser via pi).
5. **plan.md flow:** the working/iterated draft lives in the Obsidian vault
   (`projects/<proj>/plan.md`); the **approved** plan is promoted into the project folder
   where it belongs (target repo's `docs/PLAN.md`).
6. **Latency is a hard constraint.** The voice agent keeps a *small stable hot toolset*;
   heavy capability lives behind the orchestrator wall so the per-turn prefill stays small.
7. **Pacing reuses the existing narration system** (narrate-first acks, heartbeats, live
   tool-activity narration, barge-in steer/abort) so the agent "works in the background but
   keeps you updated."
8. **Model B — voice director, capable workers.** The voice agent (DeepSeek) owns the
   *goal*, the *plan.md contract*, and the *gates only*. It never writes code. Each fork is a
   **self-reasoning worker** (`PiRpcSession` with real pi agency) that decomposes its own
   subtask from the approved plan, small enough to complete in one session with an explicit
   **Definition of Done (DoD)**. The orchestrator is an execution **foreman**, not a
   decision-maker. Latency is preserved because workers burn tokens **off** the voice path.
9. **C3 — vault coordination state lives outside the worktrees.** All coordination state
   (the plan.md contract, session-tree notes, per-fork logs) lives **only** in the Obsidian
   vault (or a repo-external path), never inside a forked worktree's git object store.
   Workers *read* the approved plan and *append* to vault log sections; the vault is not part
   of the forked repo. This keeps the shared coordination artifacts off the merge-conflict
   surface (the "shared checklist becomes a conflict surface" failure); the merge gate touches
   only worker *code*, never coordination notes.
10. **Workers run inline — no subagent delegation.** A worker session executes with its own
    read/bash/edit/write tools only; it must **never** delegate to architect/manager/engineer
    subagents. Keeps each worker single-brained and deterministic, and stops multi-agent
    token/latency costs re-appearing at the worker layer. Mechanics in Phase 1 (`--no-session`
    + `--exclude-tools subagent*` + `--no-skills`, verified against `pi list`).

### Constraints (C) — referenced throughout, defined here

Inline references to `C1`/`C3`/`C5`/`C6`/`C7` below (e.g. on `sync_session`, `session_tree`,
`log()`, the merge gate, and G2/G5) refer to these constraints. `C3` is both a constraint here
and the numbered Decision 9 above; the rest are single-purpose design invariants, not numbered
decisions.
- **C1 — drift + conflict control.** Auto-merge agents must NOT rewrite shared code on main that a
  still-running worker is based on, and must NEVER auto-resolve LLM-generated conflicts (resolving
  creates new conflicts for still-working agents → feedback loop). An agent runs the merge
  *machinery* (rebase, ff, cleanup); a human *adjudicates* genuine conflicts. `sync_session`
  (rebase-to-main checkpoints) is the drift *prevention*; the merge gate is the conflict *stop*.
- **C3 — coordination state lives outside the worktrees.** (Per Decision 9.) All coordination
  state (plan.md contract, session-tree notes, per-fork logs) lives only in the Obsidian vault
  or a repo-external path, never inside a forked worktree's git object store — so coordination
  artifacts stay off the merge-conflict surface.
- **C5 — schema still fits the voice prefill.** The hot `plan_work`/`step_task` schemas (and any
  structure/session CLI schema surfaced) must keep the serialized voice prefill block under
  `VOICE_SCHEMA_TOKEN_BUDGET`; heavy parameter schemas never enter the prefill (see G5).
- **C6 — deterministic graph-walk.** `session_tree` walks the session tree by following `child:`
  frontmatter iteratively (depth ≤ 8, visited-set cycle guard) — an explicit, deterministic
  traversal, never fuzzy `memory_recall`.
- **C7 — the vault `log:` section is ground truth.** Progress is captured by appending to the
  `log:` section on every meaningful step (fork/finished/error/steered) via `SessionEngine.log()`;
  spoken narration is the ephemeral surface, `step_task` reads the *verbatim* latest `log:` entry
  + `.status`.

## Why this (the diagnosis)

The voice agent currently has **12 tools** all on one model (spawn/summon/edit, web/time/weather,
delegate/steer pi, 4 obsidian memory). Research and direct experience converge on a
**tool-selection accuracy cliff around 10–15 tools**: past it, wrong-tool calls rise. Adding
the user's desired capability (brainstorm → research → write `plan.md` → execute a feature on
a pi backend, in a git-worktree fork, in parallel) would push the voice toolset well past that
cliff and bloat every per-turn prefill — the exact thing that destroys voice response time.

The fix is not a framework; it's **moving capability off the voice model**. The front-end
agent keeps a small set of always-hot conversational tools and one trunk handle
(`run_task`-style) that hands heavy work to an orchestrator. The orchestrator owns the
heavy machinery: an Obsidian structure CLI (tool) and a git-worktree session engine.

## Hot toolset (the voice agent carries only these)

| Tool | Why hot | Notes |
|---|---|---|
| `web_search` | instant info, research | existing SearXNG tool |
| `get_time` / `get_weather` | instant info | existing |
| `spawn_object` / `summon_object` / `edit_object` | scene control | existing (client) |
| `memory_recall` / `memory_read` / `memory_write` | brain read/write | existing — **collapse** `memory_summarize` into `delegate_task("summarise vault …")` |
| `plan_work` | trunk handle | **new** — starts the brainstorm→research→plan→execute flow |
| `step_task` | progress/chatter | **new** — "what are you doing", steer a running session |

**Moved behind the wall (no longer hot tools):** raw `delegate_pi`, `steer_pi`,
`memory_summarize`. They become vocations the orchestrator calls internally, surfaced to the
voice agent only through `plan_work`/`step_task` progress.

**Resulting hot toolset is 11 tools** (the 6 scene/instant-info + 3 memory + `plan_work` +
`step_task`) — only one fewer than today's 12. The real latency win is **not** raw count but
G5: the heavy parameter schemas (worktree/session, structure CLI) are kept off the voice
prefill, and `plan_work`/`step_task` are lazy-injected only in plan/execute context.

**Model-B note:** `plan_work` does not execute work itself. It enters a **director loop** —
holds the goal + plan.md contract + gates, and issues task-grained forks to capable workers.
Workers decompose their own subtask from the approved plan and complete it (DoD); the voice
agent stays off the code path entirely.

**Latency guard:** G5 is a **token budget, not a tool count** — the serialized voice prefill
schema block must stay under `VOICE_SCHEMA_TOKEN_BUDGET` (~1800 tokens), and the *large*
parameter-heavy schemas (worktree/session, structure CLI) never enter the voice prefill. Add
an e2e guard asserting the live voice payload stays under budget (see G5).

## Phase 0 — `vault_cli.py` (the Obsidian structure tool)

New pure-Python module, deliberately sibling to `obsidian_memory.py` (same conventions,
same no-overwrite/append-only discipline). Extends `ObsidianMemory` with structure verbs.

### Interface (L2 contract)

```
# vault_cli.py
class VaultCLI:
    def __init__(self, mem: ObsidianMemory) -> None                     # wraps existing memory
    def ensure_project(self, name: str) -> Path                          # projects/<slug>/ + plan.md skeleton
    def note_create(self, path: str, title: str, body: str = "",
                    front: dict | None = None) -> Path                   # errors: AlreadyExists
    def note_append(self, path: str, section: str, body: str) -> int     # appends dated ## section
    def note_read(self, name: str, follow_links: bool = True) -> str     # reuse mem.read
    def note_rename_or_move(self, old: str, new: str) -> Path            # only path/file (move/rename) mutation; errors: Missing
    def plan_draft(self, project: str, content: str) -> Path             # upsert projects/<proj>/plan.md
    def plan_read(self, project: str) -> str                             # read the vault plan body (reuse mem.read)
    def plan_append(self, project: str, section: str, body: str) -> int  # append-only (rev) section via note_append
    def plan_set_status(self, project: str, status: str, phase: str) -> None  # frontmatter edit-only
    def rebuild_index(self) -> list[str]                                 # regenerate index.md links
def scaffold_cli_tool() -> dict          # OCI tool schema for pipecat
```

Every op returns a **capped** string (≤ MEMORY_RESULT_MAX_CHARS) fitting LLM context. Errors
are terse strings, never raised into the LLM handler (mirrors `delegate_pi`).

### Frontmatter-driven status (plans)

`projects/<proj>/plan.md` carries frontmatter state so the agent tracks a plan through
states, and phases carry status the narration can speak:

```
---
title: <proj>
type: plan
status: drafting | approved | in_progress | merged | abandoned
promoted_to: "<repo>/docs/PLAN.md"   # set at approve
tags: [plan, <proj>]
---
```

Only `status`, `promoted_to`, and phase markers are ever edited in place (the sole in-place
mutations alongside `note_rename_or_move` renames and `rebuild_index` regeneration); body
content changes are always append-only (a `## … (rev)` dated section) — never a destructive rewrite.
The G1 carve-outs are: `plan_set_status` (frontmatter edit-only), `plan_promote` (writes only the
target repo `docs/PLAN.md`), and `rebuild_index` (regenerates `index.md`).
The approved plan is written by `plan_promote` (below) but the vault copy keeps an append-only
record.

### Plan promote (approved → project folder)

```
def plan_promote(self, project: str, repo_root: Path) -> Path
    # reads vault projects/<proj>/plan.md body, writes repo_root/docs/PLAN.md
    # (atomic: write temp + os.replace), stamps promoted_to, sets status=approved
    # NOTE: repo_root is per-project, not assumed to be the Dassein root — the
    #   target repo may be a separate worktree/repo from the one hosting the voice server.
```

**Gate: G1** — `plan_promote` only ever writes the repo `docs/PLAN.md`; it never touches the
vault note body. Vault keeps append-only provenance.

## Phase 1 — `session_engine.py` (git worktree + fork sessions)

New module wrapping `PiRpcSession` + `git worktree`. One orchestrator owns a **session tree**.
Under **Model B**, forks are **task-grained** (not goal-grained): each fork is a single-session
subtask with an explicit DoD, decomposed by the worker from the approved plan. The voice agent
holds contract + gates only; workers reason within their own tree.

### Interface (L2 contract)

```
# session_engine.py
class SessionEngine:
    def __init__(self, vault: VaultCLI, rpc_factory: Callable)
    async def fork_session(self, goal: str, repo: Path, branch: str | None = None) -> Session
        # Model B: task-grained fork; decompose a single-session subtask + DoD from the plan.
        # git worktree add <tmp>/dassein-<branch> -b <branch>
        # PiRpcSession(cwd=tmp, session_id=branch, flags=["--no-session",
        #   "--exclude-tools", "subagent*", "--no-skills"])  # Decision 10: inline worker
        # start(); record vault node (incl. dod:); auto-run sync_session() baseline;
        #   log(vid, "forked", goal)
        # Session{vid, branch, repo, wt_path, rpc, status, dod, parent=None}
    async def run_in_worktree(self, vid: str, task: str, dod: str) -> str
        # await session.rpc.prompt(task); narrate via progress_cb
        # on meaningful step: self.log(vid, status, truncated note)   # C7 ground truth
    async def steer_session(self, vid: str, message: str) -> str   # rpc.steer
    async def abort_session(self, vid: str) -> str                 # rpc.abort (session stays alive)
    async def abandon_session(self, vid: str) -> str               # close rpc + worktree remove -f; vault -> abandoned
    async def sync_session(self, vid: str) -> RebaseResult          # C1 drift prevention
        # git -C wt fetch origin; git -C wt rebase origin/main
        # RebaseResult{clean: bool, conflict_files: list[str]}
        # clean=False -> MERGE FORBIDDEN; surface structured conflict report to user
    async def approve_merge(self, vid: str) -> str                  # Decision 2: explicit human gate
        # no auto-merge and NO auto-resolve ever without this
    async def merge_session(self, vid: str, strategy: str = "ff") -> str  # THE GATE
        # REQUIRES approve_merge() AND a prior sync_session(vid).clean == True
        #   git -C wt add . && git -C wt commit
        #   git -C repo merge --ff <branch>  (default; --no-ff on explicit user request)
        #   worktree remove -f; vault -> merged; delete branch
    def session_tree(self, project: str, root: str | None = None) -> str  # C6 deterministic graph-walk
    def log(self, vid: str, status: str, note: str) -> None         # C7 ground-truth progress
    def _vault_node(self, s: Session, status: str) -> Path          # projects/<proj>/sessions/<branch>.md
def scaffold_session_tool() -> dict        # tool schema(s) exposed behind plan_work
```

**Merge gate (Decisions 2 + C1):** a capable agent auto-runs the merge *machinery* (rebase,
ff, cleanup); **only genuine conflict *adjudication* stops for the human.**

```
async def approve_merge(self, vid: str) -> str
    # Requires a prior gate prompt + explicit user approval.
    # No auto-merge and NO auto-resolve ever happen without approve_merge().
```

`merge_session` refuses unless `approve_merge` has been called for that `vid` in the current
orchestration run ("bump" = one engine `SessionEngine` lifetime, i.e. between consecutive
voice-session re-runs; rebooting the engine clears all pending approvals), AND unless a prior
`sync_session(vid)` returned `clean == True`. On a rebase conflict,
the engine **prepares** (gathers both sides, diffs, hunks) and presents a structured report via
narration, then **stops** — the user adjudicates (verdict, or directs `-X ours`/`-X theirs`
explicitly; never by default).

> **C1 anti-feedback-loop rule.** An auto-merge agent must NOT rewrite shared code on main that
> a *still-running* worker is based on, and must NOT auto-resolve LLM-generated conflicts
> (research-verified: "resolutions create new conflicts for still-working agents → feedback
> loop"). An agent runs the merge *machinery*; a human *adjudicates* true conflicts. Prefer
> `sync_session` (rebase-to-main checkpoints) to *prevent* drift; C3 keeps coordination files
> off the conflict surface.

**Worker launch (Decision 10):** each `PiRpcSession` is created with `--no-session` (already
present) **plus** an allowlist that disables subagent delegation and skill bundles, e.g.
`--exclude-tools subagent*` (defensive glob) and `--no-skills` — so a worker runs inline with
read/bash/edit/write only, never delegating to architect/manager/engineer subagents. Exact
tool names to be verified against `pi list` during Phase 1.

### Vault session-tree schema (voice-navigable)

Each fork is a note; the tree is explicit via `[[wiki-links]]`:

```
# projects/<proj>/sessions/<branch>.md
---
type: session
branch: <branch>
repo: <abs path>
status: forked | running | steered | aborted | merged | abandoned
parent: "[[projects/<parent>/sessions/<parent_branch>]]"
child: "[[projects/<child>/sessions/<child_branch>]]"
dod: "<definition of done — one-session task, from the approved plan>"
created: <ts>
---
## goal
<user goal>
## log
- <ts> forked
- <ts> task: <truncated task>
- <ts> status: <status> note: <truncated note>
- <ts> merged
```

**Worker log protocol (C7):** the `log:` section is the **ground truth for progress**, appended
to on every meaningful step (fork / finished / error / steered) via `SessionEngine.log()`. The
spoken **narration** (VOICE_*) is the ephemeral surface; `step_task("what are you doing")`
reads the most recent `log:` entry + `.status` **verbatim (capped)** — a deterministic answer
to "what are you doing now?", and an auditable per-fork history in the vault.

`session_tree` performs a **deterministic graph-walk** (C6), not fuzzy recall: start at
`projects/<proj>/sessions/<root|first>`, follow `child:` frontmatter iteratively (depth ≤ 8,
visited-set cycle guard), read `.status` from each node, return a compact speakable tree
(e.g. "main → feature-a (running) → fix-b (merged)"). `memory_recall` is retained only as a
fallback when no project/root node resolves.

### Pacing integration (the "works in background but narrates" UX)

Reuses the existing hooks — no new pacing primitives:
- `fork_session` → narrate-first ack (existing VOICE_ACK) then the worktree add + session
  start happen; heartbeat (existing VOICE_HEARTBEAT_S) covers the wait.
- `run_in_worktree` → `_pi_progress` live tool-activity narration (existing PI_NARRATE_MIN_GAP_S)
  streams text deltas as speech.
- Merge gate → a deliberate spoken prompt ("changes are staged on auth-next — say merge to
  continue"). This is a real conversational turn, not filler; it *should* enter context.
- `abort_session` on barge-in → existing `_abort_quiet` fire-and-forget.

**Speech handle for the arc** (what the agent says, mapping to tools):
1. brainstorm → "I'll pull context from the vault and we'll shape this together." (`memory_recall`)
2. research → "Let me look into how that's been done." (`web_search`)
3. draft plan.md → "I've drafted a plan in the vault — here's the shape of it." (`plan_draft` + `plan_read`)
4. iterate to sign-off → conversational, `plan_append` for each revision
5. promote → "Plan's locked — I'm dropping it into the project as `docs/PLAN.md`." (`plan_promote`)
6. fork+execute → "Forking a session… working through phase 1 now." (`fork_session`, `run_in_worktree`)
7. gate at merge → "Ready to merge auth-next — say merge to continue, or tell me what to change." (`approve_merge` / `steer_session`)
8. report → "Phase 1 across, tests pass; that branch is merged." (`merge_session`, `memory_recall`)

## Hard guarantees (specific to this work)

- **G1** Vault body is never destructively rewritten — only create/append/move; `plan_promote`
  writes only the target repo `docs/PLAN.md`, not the vault note.
- **G2** No auto-merge and **no auto-resolve**: every merge path requires an explicit
  `approve_merge` gate AND a prior `sync_session(vid).clean == True`. Conflicts surface to the
  human, never auto-resolved. (C1.)
- **G3** No multi-agent framework and no new third-party runtime deps — `vault_cli.py` and
  `session_engine.py` are our own pure modules; all network calls stay server-side or in pi.
- **G4** Determinism: `vault_cli` ops are pure file ops (idempotent where sensible, deterministic
  ordering); the structure CLI is unit-tested in isolation.
- **G5** Latency guard = **token budget, not tool count.** The serialized voice prefill schema
  block (the real `TOOL_SCHEMAS`) must stay under `VOICE_SCHEMA_TOKEN_BUDGET` (default
  ~1800 tokens). `plan_work`/`step_task` schemas are **lazy-injected** only when the user is in a
  plan/execute context, so ordinary conversation stays near-minimal. e2e asserts the live payload
  size. (C5.)

  > **Lazy-injection = real engine work.** Today `TOOL_SCHEMAS` is a static module-level list
  > baked into `LLMContext(tools=TOOL_SCHEMAS)` at build time (`build_pipeline`). Conditional
  > per-context tool injection is not currently supported by the Pipecat wiring — Phase 2 must
  > build `LLMContext.tools` (and set `VOICE_SCHEMA_TOKEN_BUDGET` as its gate) dynamically per
  > phase/state, not merely add a schema flag.
- **G6** Every failure degrades to narration, never a crash or a stuck merge (mirrors the tier-0
  abstract-fallback guarantee).

## Files

| File | Change |
|---|---|
| `docs/PLAN_AGENT_BACKEND.md` | This plan |
| `vault_cli.py` | **New** — Obsidian structure tool (`VaultCLI`), plan draft/promote/status, scaffold tool schema |
| `session_engine.py` | **New** — git worktree + inline `PiRpcSession` fork/run/sync/steer/abort/merge engine, log(), session-tree graph-walk, worker-launch flags (Decision 10) |
| `pipecat_server.py` | Register `plan_work` / `step_task` (lazy-injected); move `delegate_pi`/`steer_pi`/`memory_summarize` behind the orchestrator; enforce `VOICE_SCHEMA_TOKEN_BUDGET`; wire `scaffold_cli_tool()` + `scaffold_session_tool()` |
| `pi_rpc.py` | (extension) if needed: a cwd-bound open helper + worker-launch flag injection; otherwise unchanged |
| `obsidian_memory.py` | (used as-is) VaultCLI composes it; no edits forced |
| `.env.example` | `VOICE_SCHEMA_TOKEN_BUDGET` (and any worker-launch overrides) |
| `tests/unit/vault_cli.test.py` | **New** — pure-stdlib temp-vault tests (no-overwrite, frontmatter status, plan promote) |
| `tests/unit/session_engine.test.py` | **New** — fake `pi` binary + worktree lifecycle, sync-before-merge refusal, merge-gate/conflict-stop, tree graph-walk, log protocol |
| `tests/e2e/voice-sessions.spec.js` | **New** — S30-speakable arc through the mock pipecat server + schema-token budget assertion |
| `AGENTS.md` | New tools, vault_cli, session_engine, plan flow |

## Execution order (commit after each)

1. **Phase 0** — `vault_cli.py` + unit tests (G1/G4). ✅ (commit c0a9db7)
2. **Phase 1** — `session_engine.py` + worker-launch flags (Decision 10) + sync-before-merge
   refusal, merge-gate/conflict-stop, tree graph-walk, log protocol unit tests (G2). ✅ (commit ea26390 — `pi_rpc` gained `extra_args` for worker flags; flags verified against `pi --help`)
3. **Phase 2** — wire `plan_work`/`step_task` + behind-the-wall migration in `pipecat_server.py`; hot-toolset trim; pacing narration over the full arc (G5). ✅ (commit f242a60 — 9-tool hot prefill under `VOICE_SCHEMA_TOKEN_BUDGET`, plan/step + orchestrator schemas lazy-injected on `PLAN_INTENT_RE`)
4. **Phase 3** — e2e speakable arc (S30) + latency guard + AGENTS.md + docs. ✅ (voice-sessions.spec.js; `/api/voice/tools` G5 guard; AGENTS.md; this doc updated)

> **Phase 3 note:** the voice e2e spec (`tests/e2e/voice-sessions.spec.js`) could not be executed here because the real `pipecat_server.py` occupies WS :6001 (the live voice server). It is gated identically to the existing `voice-pipecat.spec.js` and validated structurally; the G5 latency guard itself is enforced and unit-tested in Python (`assert_schema_budget`). Run `npx playwright test tests/e2e/voice-sessions.spec.js` when :6001 is free.

## Progress

| Phase | Status | Notes |
|---|---|---|
| 0 — vault_cli | ✅ | VaultCLI + G1 discipline; unit-tested (15) |
| 1 — session_engine | ✅ | git-worktree engine + merge gate (G2) + inline workers (D10); unit-tested (9) |
| 2 — wire into voice | ✅ | lazy-injected plan/step + orchestrator behind wall; G5 budget; unit-tested (10) |
| 3 — e2e + docs | ✅ | voice-sessions.spec.js (structure), /api/voice/tools guard, AGENTS.md, plan docs |

## Risks

- **Subagent artifact reliability:** the delegated document-writer returned status stubs
  instead of the file; the plan is authored directly by the manager as a mitigation. During
  implementation, hand the Engineer self-contained tasks with explicit "write the file" ground
  rules.
- **Merge-gate UX:** a forced pause is the right safety but must not feel like a stuck agent.
  Mitigate with the narrate-first gate prompt ("Ready to merge — say merge or tell me what to
  change") so it's a natural turn, not silence.
- **Vault drift vs repo:** the vault draft and promoted `docs/PLAN.md` can diverge. Mitigate:
  promotion is one-way, the vault keeps append-only provenance, and `status`/`promoted_to`
  frontmatter makes divergence visible.
- **Warm-session limit:** the engine opens one `PiRpcSession` per worktree; ensure teardown
  on `abandon`/`merge` so the capacity cap is not hit across many forks (reconnect/eviction
  logic already exists in the voice client; mirror for sessions).
- **Linear-vs-merge history (needs sign-off):** default is rebase-to-linear + `--ff`; a
  `--no-ff` preserve option exists only on explicit user request. Confirm this matches
  preference.
- **Subagent-delegation exclusion depends on pi's tool naming:** the `--exclude-tools subagent*`
  glob must be validated against `pi list`; if pi exposes delegation under a different name,
  adjust the allowlist in Phase 1.
- **Conflict resolution is human-in-the-loop by design:** genuine code conflicts block the
  merge until the user adjudicates. This is built-in (C1) — a deliberate, not accidental, brake.
