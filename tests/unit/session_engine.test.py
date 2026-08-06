#!/usr/bin/env python3
"""Unit tests for session_engine.SessionEngine against a real temp git repo and
a fake `pi --mode rpc` worker binary.

Covers: fork creates worktree + vault node + worker (inline flags), run logs as
ground truth (C7), sync-before-merge refusal and approve-gate (G2), clean
merge success, deterministic tree graph-walk (C6), abandon teardown.

Run:
    NLTK_DISABLE_IMPORT_SECURITY=1 .venv-voice/bin/python tests/unit/session_engine.test.py
"""
import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("NLTK_DISABLE_IMPORT_SECURITY", "1")
sys.path.insert(0, str(ROOT))

from obsidian_memory import ObsidianMemory  # noqa: E402
from vault_cli import VaultCLI  # noqa: E402
from session_engine import (  # noqa: E402
    SessionEngine,
    Session,
    RebaseResult,
    WORKER_TOOLS,
)


class RecordingWorker:
    """Stands in for a PiRpcSession worker fork. Records the inline flags it was
    given and returns canned answers; lets the test force a commit too."""
    def __init__(self, cwd, session_id, progress_cb=None, extra_args=None):
        self.cwd = cwd
        self.session_id = session_id
        self.extra_args = list(extra_args or [])
        self.started = False
        self.closed = False
        self.prompts = []

    async def start(self):
        self.started = True

    async def prompt(self, task):
        self.prompts.append(task)
        return "PI-STUB OK: did the work"

    async def steer(self, message):
        return f"Steered: {message}"

    async def abort(self):
        return "ABORTED"

    async def close(self):
        self.closed = True


def make_engine(root):
    mem = ObsidianMemory(root / "vault")
    mem.ensure_scaffold()
    cli = VaultCLI(mem)
    engine = SessionEngine(cli, rpc_factory=RecordingWorker)
    return engine


class TestSessionEngine(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        # Real temp git repo with an initial commit on main.
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self._git(self.repo, "init", "-q", "-b", "main")
        self._git(self.repo, "config", "user.email", "t@t.co")
        self._git(self.repo, "config", "user.name", "Test")
        (self.repo / "base.txt").write_text("base\n", encoding="utf-8")
        self._git(self.repo, "add", ".")
        self._git(self.repo, "commit", "-qm", "init")
        self.engine = None  # set per-test to allow teardown cleanup

    def tearDown(self):
        if self.engine is not None:
            # best-effort worktree cleanup so the tempdir can be removed
            try:
                for s in list(self.engine._sessions.values()):
                    if (s.wt_path / "README").exists() or s.wt_path.exists():
                        pass
            except Exception:
                pass
        self._tmp.cleanup()

    def _git(self, cwd: Path, *args):
        import subprocess
        r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True)
        return r.returncode, r.stdout.decode(), r.stderr.decode()

    async def test_fork_creates_worktree_and_vault_node(self):
        self.engine = make_engine(self.root)
        s = await self.engine.fork_session(
            goal="add a docs page", repo=self.repo, branch="docs-a",
            dod="docs/index.md exists", project="Docs",
        )
        self.assertEqual(s.status, "forked")
        self.assertTrue(s.wt_path.is_dir())
        # Vault node exists with frontmatter + log.
        node = self.engine._vault_node(s)
        self.assertTrue(node.exists())
        text = node.read_text(encoding="utf-8")
        self.assertIn("type: session", text)
        self.assertIn("dod: docs/index.md exists", text)
        self.assertIn("status: forked", text)
        # Worker spawned with inline flags (Decision 10).
        worker = s.rpc
        self.assertTrue(worker.started)
        self.assertIn("--no-skills", worker.extra_args)
        self.assertIn("--exclude-tools", worker.extra_args)
        self.assertIn(WORKER_TOOLS, worker.extra_args)
        # git branch created on the worktree.
        rc, out, _ = self._git(self.repo, "worktree", "list")
        self.assertEqual(rc, 0)
        self.assertIn("docs-a", out)

    async def test_run_logs_ground_truth(self):
        self.engine = make_engine(self.root)
        s = await self.engine.fork_session(goal="task", repo=self.repo, branch="run-a", project="P")
        res = await self.engine.run_in_worktree(s.vid, "do the thing", dod="tests pass")
        self.assertIn("PI-STUB OK", res)
        node = self.engine._vault_node(s).read_text(encoding="utf-8")
        self.assertIn("status: finished", node)
        self.assertIn("— log", node)
        self.assertIn("running", node)
        self.assertIn("PI-STUB OK", node)

    async def test_merge_refuses_without_approval(self):
        self.engine = make_engine(self.root)
        s = await self.engine.fork_session(goal="x", repo=self.repo, branch="no-approve-a", project="P")
        # Give the branch a commit so the only blocker is the missing approval.
        self._git(s.wt_path, "config", "user.email", "t@t.co")
        self._git(s.wt_path, "config", "user.name", "T")
        (s.wt_path / "f.txt").write_text("x\n", encoding="utf-8")
        self._git(s.wt_path, "add", ".")
        self._git(s.wt_path, "commit", "-qm", "work")
        r = await self.engine.merge_session(s.vid)
        self.assertIn("not been approved", r)

    async def test_merge_refuses_without_clean_sync(self):
        self.engine = make_engine(self.root)
        s = await self.engine.fork_session(goal="x", repo=self.repo, branch="no-sync-a", project="P")
        self._git(s.wt_path, "config", "user.email", "t@t.co")
        self._git(s.wt_path, "config", "user.name", "T")
        (s.wt_path / "f.txt").write_text("x\n", encoding="utf-8")
        self._git(s.wt_path, "add", ".")
        self._git(s.wt_path, "commit", "-qm", "work")
        # Approve BUT no clean sync recorded -> still refuse.
        await self.engine.approve_merge(s.vid)
        r = await self.engine.merge_session(s.vid)
        self.assertIn("clean sync", r)

    async def test_merge_succeeds_after_approve_and_clean_sync(self):
        self.engine = make_engine(self.root)
        s = await self.engine.fork_session(goal="x", repo=self.repo, branch="ok-a", project="P")
        self._git(s.wt_path, "config", "user.email", "t@t.co")
        self._git(s.wt_path, "config", "user.name", "T")
        (s.wt_path / "feature.txt").write_text("feature\n", encoding="utf-8")
        self._git(s.wt_path, "add", ".")
        self._git(s.wt_path, "commit", "-qm", "feature work")
        sync = await self.engine.sync_session(s.vid)
        self.assertTrue(sync.clean, sync.detail)
        await self.engine.approve_merge(s.vid)
        r = await self.engine.merge_session(s.vid)
        self.assertIn("merged", r)
        # Feature file is now on main.
        rc, out, _ = self._git(self.repo, "log", "--oneline", "--all")
        self.assertIn("feature work", out)
        self.assertTrue((self.repo / "feature.txt").exists())

    async def test_merge_conflict_prepares_and_stops(self):
        self.engine = make_engine(self.root)
        # Fork from the ORIGINAL main (base.txt == "base").
        s = await self.engine.fork_session(goal="x", repo=self.repo, branch="conflict-a", project="P")
        # Advance main AFTER the fork with a conflicting edit to the same file.
        (self.repo / "base.txt").write_text("main changed\n", encoding="utf-8")
        self._git(self.repo, "add", ".")
        self._git(self.repo, "commit", "-qm", "main move")
        # Worker edits the same file differently and commits.
        self._git(s.wt_path, "config", "user.email", "t@t.co")
        self._git(s.wt_path, "config", "user.name", "T")
        (s.wt_path / "base.txt").write_text("worker changed\n", encoding="utf-8")
        self._git(s.wt_path, "add", ".")
        self._git(s.wt_path, "commit", "-qm", "worker move")
        sync = await self.engine.sync_session(s.vid)
        self.assertFalse(sync.clean, sync.detail)
        self.assertTrue(sync.conflict_files)  # base.txt in conflict
        await self.engine.approve_merge(s.vid)
        r = await self.engine.merge_session(s.vid)
        # The G2 gate refuses to touch main at all because sync was not clean —
        # the human must adjudicate before any merge attempt.
        self.assertIn("merge rejected", r)
        self.assertIn("not had a clean sync_session", r)

    async def test_session_tree_deterministic_walk(self):
        self.engine = make_engine(self.root)
        a = await self.engine.fork_session(goal="x", repo=self.repo, branch="root-a", project="Proj")
        b = await self.engine.fork_session(goal="y", repo=self.repo, branch="child-a", project="Proj", parent=a.vid)
        self.engine.log(b.vid, "merged")
        tree = self.engine.session_tree("Proj", root=a.vid)
        self.assertIn("root-a (forked)", tree)
        self.assertIn("child-a (merged)", tree)
        self.assertIn("→", tree)

    async def test_abandon_tears_down(self):
        self.engine = make_engine(self.root)
        s = await self.engine.fork_session(goal="x", repo=self.repo, branch="gone-a", project="P")
        r = await self.engine.abandon_session(s.vid)
        self.assertIn("abandoned", r)
        rc, out, _ = self._git(self.repo, "worktree", "list")
        self.assertNotIn("gone-a", out)
        node = self.engine._vault_node(s)
        if node.exists():
            self.assertIn("abandoned", node.read_text(encoding="utf-8"))

    async def test_steer_abort(self):
        self.engine = make_engine(self.root)
        s = await self.engine.fork_session(goal="x", repo=self.repo, branch="steer-a", project="P")
        r = await self.engine.steer_session(s.vid, "do the CSS first")
        self.assertIn("Steered:", r)
        r = await self.engine.abort_session(s.vid)
        self.assertIn("ABORTED", r)

    # -- multi-project cursor ----------------------------------------------

    async def test_fork_sets_and_flips_current_project(self):
        self.engine = make_engine(self.root)
        a = await self.engine.fork_session(goal="x", repo=self.repo, branch="auth-a", project="Auth")
        self.assertEqual(self.engine.current_project, "Auth")
        b = await self.engine.fork_session(goal="y", repo=self.repo, branch="db-a", project="Database")
        # most-recent engagement wins
        self.assertEqual(self.engine.current_project, "Database")
        self.assertNotEqual(a.vid, b.vid)

    async def test_set_project_cursor(self):
        self.engine = make_engine(self.root)
        await self.engine.fork_session(goal="x", repo=self.repo, branch="auth-a", project="Auth")
        await self.engine.fork_session(goal="y", repo=self.repo, branch="db-a", project="Database")
        r = self.engine.set_project("Auth")
        self.assertIn("switched to 'Auth'", r)
        self.assertEqual(self.engine.current_project, "Auth")
        # unknown project -> terse error, cursor unchanged
        r2 = self.engine.set_project("Nope")
        self.assertTrue(r2.startswith("Error:"))
        self.assertEqual(self.engine.current_project, "Auth")

    async def test_vid_for_project_resolves(self):
        self.engine = make_engine(self.root)
        a = await self.engine.fork_session(goal="x", repo=self.repo, branch="auth-a", project="Auth")
        await self.engine.fork_session(goal="y", repo=self.repo, branch="db-a", project="Database")
        self.assertEqual(self.engine.vid_for_project("Auth"), a.vid)
        self.assertIsNone(self.engine.vid_for_project("Nope"))
        self.assertIsNone(self.engine.vid_for_project(None))

    async def test_project_state_and_list_projects(self):
        self.engine = make_engine(self.root)
        a = await self.engine.fork_session(goal="x", repo=self.repo, branch="auth-a", project="Auth")
        await self.engine.fork_session(goal="y", repo=self.repo, branch="db-a", project="Database")
        state = self.engine.project_state("Auth")
        self.assertIn("Auth", state)
        self.assertIn(a.vid, state)
        listing = self.engine.list_projects()
        self.assertIn("auth", listing)
        self.assertIn("database", listing)
        # cursor marker on the most-recently-engaged project
        self.assertIn("*database", listing)

    async def test_session_tree_scope_by_project(self):
        self.engine = make_engine(self.root)
        a = await self.engine.fork_session(goal="x", repo=self.repo, branch="auth-a", project="Auth")
        await self.engine.fork_session(goal="y", repo=self.repo, branch="auth-b", project="Auth", parent=a.vid)
        await self.engine.fork_session(goal="z", repo=self.repo, branch="db-a", project="Database")
        tree = self.engine.session_tree("Auth")
        self.assertIn("auth-a", tree)
        self.assertIn("auth-b", tree)
        self.assertNotIn("db-a", tree)


if __name__ == "__main__":
    unittest.main(verbosity=2)
