"""git-worktree + fork session engine — the Dassein execution backend.

Phase 1 of docs/PLAN_AGENT_BACKEND.md. Turns a plan into parallel, isolated,
self-reasoning worker forks on a `pi --mode rpc` session, each running *inline*
(read/bash/edit/write only — never delegating to subagents), with a human-gated
merge at the end.

Model B: the voice agent holds the goal + plan.md contract + gates ONLY. Each
fork is a **task-grained** worker that decomposes its own subtask from the
approved plan and completes it to a Definition of Done (DoD). This engine is
the execution *foreman*: it drives git worktrees, worker sessions, drift
prevention (sync/rebase checkpoints), and the merge gate.

Hard guarantees implemented here:

- G2 — no auto-merge and no auto-resolve. `merge_session` refuses unless
  `approve_merge(vid)` was called in this engine's lifetime AND a prior
  `sync_session(vid)` returned `clean == True`. Rebase conflicts `prepare`
  the conflict report and STOP — a human adjudicates.
- C1 — `sync_session` (rebase-to-main checkpoints) is drift *prevention*; the
  merge gate is the conflict *stop*. Coordination files stay out of the fork
  via C3.
- C3 — coordination state (plan contract, session-tree notes, per-fork logs)
  lives ONLY in the Obsidian vault, never inside a forked worktree's git object
  store. The vault is not part of the forked repo.
- C6 — `session_tree` walks by following `child:` frontmatter iteratively
  (depth <= 8, visited-set cycle guard), never fuzzy recall.
- C7 — the vault `log:` section is ground truth. Every meaningful step
  (fork/finished/error/steered) appends via `log()`; spoken narration is the
  ephemeral surface.
- Decision 10 — workers run inline: each `PiRpcSession` is spawned with
  worker-launch flags (`--no-session`, an inline-tool allowlist, `--exclude-tools
  subagent*` glob, `--no-skills`) so it NEVER delegates to architect/manager/
  engineer subagents and loads no skill bundles.

Pure stdlib + subprocess (git). Vault ops go through `VaultCLI`. Deterministic,
unit-testable with a fake `pi` binary and temp git repos (tests/unit/session_engine.test.py).
"""

import asyncio
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from vault_cli import VaultCLI, _slugify, MissingError

WORKER_TOOLS = os.environ.get("VOICE_WORKER_TOOLS", "read,bash,edit,write").strip()
# Defensive glob: disable any subagent-delegation tools (Decision 10). The exact
# tool name is verified live in Phase 1; the glob is deliberately conservative.
WORKER_EXCLUDE_TOOLS = os.environ.get("VOICE_WORKER_EXCLUDE_TOOLS", "subagent*").strip()
SESSION_TREE_MAX_DEPTH = int(os.environ.get("SESSION_TREE_MAX_DEPTH", "8"))
SESSION_RESULT_MAX_CHARS = 1500  # cap for what enters LLM context


class MergeGateError(Exception):
    """merge_session refused: no approval or no prior clean sync."""


@dataclass
class Session:
    """One forked worker session (Model B, task-grained)."""
    vid: str                      # vault node id — the branch name (space-safe key)
    branch: str
    repo: Path
    wt_path: Path
    project: str
    status: str = "forked"
    dod: str = ""
    parent: str | None = None

    def describe(self, status: str | None = None) -> str:
        s = status or self.status
        return f"{self.branch} ({s})"


@dataclass
class RebaseResult:
    clean: bool
    conflict_files: list[str]
    detail: str = ""

    def __bool__(self):
        return self.clean


class SessionEngine:
    """One orchestrator committing a session tree. One engine lifetime == one
    voice-session re-run; rebooting the engine clears all pending approvals."""

    def __init__(self, vault: VaultCLI, rpc_factory) -> None:
        # `rpc_factory(cwd, session_id, progress_cb, extra_args) -> PiRpcSession`.
        self.vault = vault
        self._rpc_factory = rpc_factory
        self._sessions: dict[str, Session] = {}
        self._approved: set[str] = set()          # vids approved for merge this lifetime (G2)
        self._last_sync: dict[str, RebaseResult] = {}  # last sync result per vid
        # Multi-project cursor: whichever project the user most recently engaged
        # with. Defaults to None until the first fork / explicit set_project.
        self.current_project: str | None = None
        self.progress_cb = None                    # async callable(ev) for live narration

    # -- shell helper --------------------------------------------------------

    async def _run_git(self, args, cwd: Path) -> tuple[int, str, str]:
        """Run git in cwd; returns (returncode, stdout, stderr)."""
        proc = await asyncio.create_subprocess_exec(
            "git", *args,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        return proc.returncode or 0, out.decode(errors="replace"), err.decode(errors="replace")

    # -- vault node helpers (C3) ---------------------------------------------

    def _vault_node(self, s: Session, status: str | None = None) -> Path:
        """locate `projects/<proj>/sessions/<branch>.md` (may not exist yet)."""
        proj = _slugify(s.project or s.branch or s.vid) or "main"
        pdir = self.vault.vault / "projects" / proj
        pdir.mkdir(parents=True, exist_ok=True)
        (pdir / "sessions").mkdir(parents=True, exist_ok=True)
        return pdir / "sessions" / f"{_slugify(s.branch)}.md"

    def _ensure_node(self, s: Session) -> Path:
        """Create the vault session-tree node note if missing. Returns its path."""
        node = self._vault_node(s)
        if not node.exists():
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            body = (
                f"## goal\n{s.project or s.vid}\n\n## log\n"
                f"- {now} {s.status}"
            )
            self.vault.note_create(
                self.vault._vault_rel(node),
                title=s.branch,
                front={
                    "type": "session",
                    "branch": s.branch,
                    "repo": str(s.repo),
                    "status": s.status,
                    "parent": f"[[projects/{_slugify(s.project)}/sessions/{_slugify(s.parent)}]]" if s.parent else "",
                    "child": "",
                    "dod": s.dod,
                    "created": now,
                },
            )
        return node

    def log(self, vid: str, status: str, note: str = "") -> str:
        """C7 ground-truth: append a dated line to the session node's `## log`
        section and update its `status:` frontmatter. Returns a terse capped
        result string (never raises into the LLM handler)."""
        s = self._sessions.get(vid)
        if s is not None:
            s.status = status
            node = self._ensure_node(s)
            self._stamp_status(node, status)
        else:
            # Unknown vid: still allow logging to a best-effort node path.
            return f"Error: unknown session {vid}"
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"- {now} status: {status}" + (f" note: {note}" if note else "")
        try:
            self.vault.note_append(
                self.vault._vault_rel(node), "log", entry
            )
        except (MissingError, OSError) as e:
            return f"Error: {e}"
        return f"OK: [{vid}] {status}"

    def _stamp_status(self, node: Path, status: str):
        """Frontmatter edit-only (G1 carve-out): set status on a session node."""
        try:
            text = node.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        if not text.startswith("---"):
            return
        m = re.match(r"^(---\n)(.*?)(\n---\n)(.*)$", text, re.DOTALL)
        if not m:
            return
        frame = m.group(2)
        lines = frame.split("\n")
        replaced = False
        for i, ln in enumerate(lines):
            if re.match(r"^status:\s*", ln):
                lines[i] = f"status: {status}"
                replaced = True
                break
        if not replaced:
            lines.append(f"status: {status}")
        node.write_text("---\n" + "\n".join(lines) + "\n---\n" + m.group(4), encoding="utf-8")

    def _set_child_link(self, parent_vid: str, child_vid: str):
        """Stamp a `child:` frontmatter link on the parent's node so the tree is
        traversable deterministically (C6). Frontmatter edit-only."""
        s = self._sessions.get(parent_vid)
        if s is None:
            return
        node = self._vault_node(s)
        if not node.exists():
            node = self._ensure_node(s)
        text = node.read_text(encoding="utf-8", errors="replace")
        if not text.startswith("---"):
            return
        m = re.match(r"^(---\n)(.*?)(\n---\n)(.*)$", text, re.DOTALL)
        if not m:
            return
        frame = m.group(2)
        child = None
        cs = self._sessions.get(child_vid)
        if cs is not None:
            child = f"[[projects/{_slugify(cs.project)}/sessions/{_slugify(cs.branch)}]]"
        lines = frame.split("\n")
        replaced = False
        for i, ln in enumerate(lines):
            if re.match(r"^child:\s*", ln):
                lines[i] = f"child: {child or ''}"
                replaced = True
                break
        if not replaced:
            lines.insert(0, f"child: {child or ''}")
        node.write_text("---\n" + "\n".join(lines) + "\n---\n" + m.group(4), encoding="utf-8")

    # -- lifecycle -----------------------------------------------------------

    async def fork_session(
        self,
        goal: str,
        repo: Path,
        branch: str | None = None,
        dod: str = "",
        project: str | None = None,
        parent: str | None = None,
    ) -> Session:
        """Model B task-grained fork: worktree add, spawn inline worker, record
        vault node, auto-run baseline sync_session(), log "forked"."""
        branch = (branch or (_slugify(goal) or f"wk-{datetime.now():%Y%m%d%H%M%S}"))
        project = project or branch
        # Default the target repo to the project's registered repo when none is given,
        # so forks of a registered project happen in ITS repo (not the voice host's).
        repo = Path(repo).expanduser().resolve()
        if not repo.is_dir():
            known_repo = self.vault.project_repo(project)
            if known_repo is not None and known_repo.is_dir():
                repo = known_repo
            else:
                raise ValueError(f"repo not found: {repo}")
        # git worktree add <tmp>/dassein-<branch> -b <branch>
        tmp = repo / f".dassein-worktrees"
        tmp.mkdir(parents=True, exist_ok=True)
        wt_path = tmp / f"dassein-{_slugify(branch)}"
        rc, out, err = await self._run_git(
            ["worktree", "add", "-b", branch, str(wt_path)], repo
        )
        if rc != 0:
            raise RuntimeError(f"worktree add failed: {err.strip() or out.strip()}")
        # Spawn the inline worker session in the worktree.
        extra = ["--no-skills", "--exclude-tools", WORKER_EXCLUDE_TOOLS, "--tools", WORKER_TOOLS]
        rpc = self._rpc_factory(
            cwd=str(wt_path),
            session_id=f"{branch}-{datetime.now():%Y%m%d%H%M%S}",
            progress_cb=self.progress_cb,
            extra_args=extra,
        )
        await rpc.start()
        vid = _slugify(branch)
        s = Session(
            vid=vid, branch=branch, repo=repo, wt_path=wt_path,
            project=project, status="forked", dod=dod, parent=parent,
        )
        self._sessions[vid] = s
        s.rpc = rpc
        self._ensure_node(s)
        if parent is not None:
            self._set_child_link(parent, vid)
            ps = self._sessions.get(parent)
            if ps is not None:
                self._set_child_link(ps.vid, vid)
        # Baseline drift-prevention sync (C1). Does NOT authorize a merge by
        # itself — an explicit sync_session() before merge is required (G2).
        try:
            await self._do_sync(s)
        except Exception as e:
            self.log(vid, "forked", f"baseline sync failed: {e}")
        self.log(vid, "forked", goal)
        # Most-recent engagement wins: forking flips the project cursor.
        self.current_project = s.project
        return s

    async def run_in_worktree(self, vid: str, task: str, dod: str = "") -> str:
        """Send a task to a worker fork, narrate via progress_cb, log the
        finished/error state (C7 ground truth)."""
        s = self._sessions.get(vid)
        if s is None:
            return f"Error: unknown session {vid}"
        rpc = getattr(s, "rpc", None)
        if rpc is None:
            return f"Error: no rpc for {vid}"
        if dod:
            # Worker is task-grained + DoD explicit: prefix the prompt so the
            # worker knows its Definition of Done.
            task = f"{task}\n\nDefinition of Done: {dod}"
        self.log(vid, "running", task[:200])
        try:
            result = await rpc.prompt(task)
        except asyncio.CancelledError:
            self.log(vid, "aborted", "barge-in during task")
            raise
        status = "finished" if "Error" not in (result or "") else "error"
        self.log(vid, status, (result or "")[:200])
        return self._cap(result or "COMPLETED")

    async def steer_session(self, vid: str, message: str) -> str:
        s = self._sessions.get(vid)
        if s is None:
            return f"Error: unknown session {vid}"
        if getattr(s, "rpc", None) is None:
            return f"Error: no active session {vid}"
        self.log(vid, "steered", (message or "")[:200])
        return await s.rpc.steer(message)

    async def abort_session(self, vid: str) -> str:
        s = self._sessions.get(vid)
        if s is None:
            return f"Error: unknown session {vid}"
        if getattr(s, "rpc", None) is None:
            return f"Error: no active session {vid}"
        self.log(vid, "aborted", "user cancelled current run")
        return await s.rpc.abort()

    async def abandon_session(self, vid: str) -> str:
        """Close rpc, `worktree remove -f`, vault -> abandoned. (C3 teardown.)"""
        s = self._sessions.get(vid)
        if s is None:
            return f"Error: unknown session {vid}"
        rpc = getattr(s, "rpc", None)
        if rpc is not None:
            try:
                await rpc.close()
            except Exception:
                pass
            s.rpc = None
        # worktree remove -f from the main repo
        try:
            await self._run_git(["worktree", "remove", "-f", str(s.wt_path)], s.repo)
            await self._run_git(["branch", "-D", s.branch], s.repo)
        except Exception:
            pass
        s.status = "abandoned"
        self.log(vid, "abandoned")
        self._sessions.pop(vid, None)
        return f"OK: abandoned {vid}"

    async def _do_sync(self, s: Session) -> RebaseResult:
        """Perform the git drift-prevention rebase for a session without recording
        a merge-authorizing result. Baseline forks use this so a pre-work sync does
        NOT satisfy the G2 gate (an explicit sync_session right before merge does)."""
        # Bring the worker up to date with current main. Use origin/main when an
        # origin remote exists, else the local main branch (local dev worktrees).
        rc, out, err = await self._run_git(["remote"], s.wt_path)
        has_origin = any(l.strip() == "origin" for l in out.splitlines())
        upstream = "origin/main" if has_origin else "main"
        if has_origin:
            await self._run_git(["fetch", "origin"], s.wt_path)
        rc2, out2, err2 = await self._run_git(["rebase", upstream], s.wt_path)
        resume = RebaseResult(clean=(rc2 == 0), conflict_files=[], detail=(err2 or out2).strip())
        if not resume.clean:
            _, uout, _ = await self._run_git(["status", "--porcelain"], s.wt_path)
            resume.conflict_files = [
                l[3:] for l in uout.splitlines()
                if l.startswith("UU ") or l.startswith("AA ") or l.startswith("DD ")
            ]
            # Leave the repo in a rebase-merge state for the human to adjudicate.
            resume.detail += "\n" + "\n".join(resume.conflict_files[:20])
        return resume

    async def sync_session(self, vid: str) -> RebaseResult:
        """C1 drift prevention: rebase the worker onto current main and RECORD the
        result so a clean sync here authorizes a subsequent merge (G2).

        Returns RebaseResult. clean=False -> MERGE FORBIDDEN; the caller surfaces
        a structured conflict report and stops.
        """
        s = self._sessions.get(vid)
        if s is None:
            return RebaseResult(False, [], f"unknown session {vid}")
        resume = await self._do_sync(s)
        self._last_sync[vid] = resume
        return resume

    async def approve_merge(self, vid: str) -> str:
        """Decision 2 explicit human gate. Requires a prior gate prompt + explicit
        user approval. No auto-merge ever without this."""
        s = self._sessions.get(vid)
        if s is None:
            return f"Error: unknown session {vid}"
        self._approved.add(vid)
        self.log(vid, "merge_pending", "user approved merge")
        return f"OK: merge approved for {vid}. Ready when you say the word."

    def _merge_forbidden_reason(self, s: Session) -> str | None:
        if s.vid not in self._approved:
            return f"merge rejected: {s.vid} has not been approved (call approve_merge first)."
        last = self._last_sync.get(s.vid)
        if last is None or not last.clean:
            files = last.conflict_files if last else []
            return (
                f"merge rejected: {s.vid} has not had a clean sync_session. "
                + (f"Conflicts: {', '.join(files[:5])}." if files else "Last sync was not clean.")
            )
        return None

    async def merge_session(self, vid: str, strategy: str = "ff") -> str:
        """THE GATE. Requires approve_merge() AND a prior clean sync_session (G2/C1).

        Default `--ff` (linear history); `--no-ff` only on explicit user request.
        On refusal, returns a terse error (never raises into the LLM handler).
        """
        s = self._sessions.get(vid)
        if s is None:
            return f"Error: unknown session {vid}"
        reason = self._merge_forbidden_reason(s)
        if reason:
            if reason.startswith("merge rejected") and (s.vid not in self._approved):
                self.log(vid, "merge_blocked", reason)
            return reason
        # git add + commit on the worktree
        rc, out, err = await self._run_git(["add", "-A"], s.wt_path)
        if rc == 0:
            await self._run_git(
                ["commit", "-m", f"dassein worker {s.branch}: {s.dod[:60] or 'task'}"], s.wt_path
            )
        # merge --ff / --no-ff
        fl = "--no-ff" if strategy == "noff" else "--ff"
        rc, out, err = await self._run_git(["merge", fl, s.branch], s.repo)
        if rc != 0:
            self.log(vid, "merge_conflict", (err or out).strip()[:200])
            return (
                "Merge conflict — cannot auto-resolve (G2). "
                "Please adjudicate the conflict in the worktree, then say continue."
            )
        # cleanup: remove worktree, delete branch, log merged.
        await self._run_git(["worktree", "remove", "-f", str(s.wt_path)], s.repo)
        await self._run_git(["branch", "-D", s.branch], s.repo)
        s.status = "merged"
        rpc = getattr(s, "rpc", None)
        if rpc is not None:
            try:
                await rpc.close()
            except Exception:
                pass
            s.rpc = None
        self.log(vid, "merged")
        return f"OK: merged {vid} ({strategy})"

    # -- tree / progress -----------------------------------------------------

    def session_tree(self, project: str, root: str | None = None) -> str:
        """C6 deterministic graph-walk: follow `child:` frontmatter iteratively
        (depth <= 8, visited-set cycle guard). Returns a compact speakable tree."""
        proj = _slugify(project)
        start = root or self.vid_for_project(project)
        if not start:
            return f"No sessions for project {project}."
        visited: set[str] = set()
        nodes: list[tuple[str, str]] = []  # (branch, status)
        cur: str | None = start
        depth = 0
        while cur is not None and depth <= SESSION_TREE_MAX_DEPTH:
            if cur in visited:
                break
            visited.add(cur)
            s = self._sessions.get(cur)
            status = s.status if s else self._node_status(proj, cur)
            nodes.append((cur, status))
            child = self._node_child(proj, cur)
            cur = child
            depth += 1
        return " → ".join(f"{b} ({st})" for b, st in nodes)

    def _node_status(self, proj: str, vid: str) -> str:
        node = self.vault.vault / "projects" / proj / "sessions" / f"{_slugify(vid)}.md"
        try:
            text = node.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return "unknown"
        m = re.search(r"^status:[ \t]*(.+?)[ \t]*$", text, re.MULTILINE)
        return m.group(1).strip() if m else "unknown"

    def _node_child(self, proj: str, vid: str) -> str | None:
        node = self.vault.vault / "projects" / proj / "sessions" / f"{_slugify(vid)}.md"
        try:
            text = node.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        m = re.search(r"^child:[ \t]*(.+?)[ \t]*$", text, re.MULTILINE)
        if not m:
            return None
        val = m.group(1).strip().strip('"')
        if not val:
            return None
        # [[projects/<proj>/sessions/<branch>]] -> branch
        inner = val.strip("[]")
        tails = inner.split("/")[-1] if "/" in inner else inner
        return tails

    @staticmethod
    def _cap(text: str, max_chars: int = SESSION_RESULT_MAX_CHARS) -> str:
        text = str(text or "")
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "…"

    # -- multi-project cursor (voice disambiguation) ------------------------

    def set_project(self, name: str | None) -> str:
        """Flip the current-project cursor. Accepts any registered/known project
        (idle or active). Returns a narratable ack."""
        slug = _slugify(name or "") if name else ""
        held = {_slugify(s.project) for s in self._sessions.values()}
        known = {k["slug"] for k in self.vault.known_projects()}
        if slug and slug not in held and slug not in known:
            return f"Error: unknown project '{name}'."
        self.current_project = name or None
        return f"OK: switched to '{name or 'no active project'}'."

    def vid_for_project(self, name: str | None) -> str | None:
        """Resolve the active worker `vid` for a project (stable first fork).
        Returns None if the project has no held session or the name is empty."""
        if not name:
            return None
        slug = _slugify(name)
        for vid, s in self._sessions.items():
            if _slugify(s.project) == slug:
                return vid
        return None

    def project_state(self, name: str | None) -> str:
        """A speakable snapshot of one project (its session tree + plan status). Falls
        back to the current-project cursor when name is None."""
        proj = name or self.current_project
        if not proj:
            return "No active project yet — start one with plan_work."
        vid = self.vid_for_project(proj)
        tree = self.session_tree(proj, root=vid)
        status = ""
        try:
            status = self.vault.plan_get_status(proj)
        except Exception:
            status = "unknown"
        return f"{proj} ({status}): {tree}"

    def list_projects(self) -> str:
        """Deterministic overview of every project known to the vault or with active
        sessions, marking the current cursor. Voice-navigable for switching context.
        Known-but-idle registered projects show as `<slug> (registered, status)`."""
        active: list[str] = []
        session_slugs = {_slugify(s.project) for s in self._sessions.values()}
        for known in self.vault.known_projects():
            slug = known["slug"]
            marker = "*" if (
                self.current_project and _slugify(self.current_project) == slug
            ) else ""
            if slug in session_slugs:
                vids = [v for v, s in self._sessions.items() if _slugify(s.project) == slug]
                statuses = ", ".join(
                    f"{self._sessions[v].branch}({self._sessions[v].status})" for v in vids
                )
                active.append(f"{marker}{slug}: {statuses}")
            else:
                active.append(f"{marker}{slug} (registered, {known['status']})")
        # Any active session whose project isn't (yet) a vault project gets listed too.
        known_slugs = {k["slug"] for k in self.vault.known_projects()}
        for slug in sorted(session_slugs - known_slugs):
            vids = [v for v, s in self._sessions.items() if _slugify(s.project) == slug]
            statuses = ", ".join(
                f"{self._sessions[v].branch}({self._sessions[v].status})" for v in vids
            )
            active.append(f"{slug}: {statuses}")
        if not active:
            return "No projects yet — register one or start plan_work."
        return "; ".join(active)


def scaffold_session_tool() -> dict:
    """Tool schema(s) exposed BEHIND plan_work (heavy schema, never in the voice
    prefill). One session verb + generic args, mirroring scaffold_cli_tool."""
    return {
        "type": "function",
        "runsOn": "server",
        "name": "session_engine",
        "description": (
            "Fork or drive a git-worktree worker session: fork a task, run it, "
            "steer/abort/abandon it, sync to main (rebase), approve a merge, or "
            "merge. Register a project by name+repo, or switch/list active projects "
            "with register / set_project / list / state. "
            "Each fork is an inline self-reasoning worker; merges require "
            "explicit approval and a clean sync first."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "op": {
                    "type": "string",
                    "enum": [
                        "fork", "run", "steer", "abort", "abandon",
                        "sync", "approve", "merge", "tree",
                        "set_project", "list", "state", "register",
                    ],
                    "description": "The session operation to run",
                },
                "args": {
                    "type": "object",
                    "description": (
                        "Op-specific args: goal, repo, branch, project, dod, task, "
                        "message, strategy, root (for tree), parent (vid)"
                    ),
                },
            },
            "required": ["op"],
        },
    }
