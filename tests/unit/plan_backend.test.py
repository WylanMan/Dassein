#!/usr/bin/env python3
"""Unit tests for the Phase 2 wire-up in pipecat_server: G5 schema-token budget,
lazy-injection of plan tools, and the plan_work/step_task/session_engine/structure_notes
server-tool handlers behind the orchestrator wall.

Run:
    NLTK_DISABLE_IMPORT_SECURITY=1 .venv-voice/bin/python tests/unit/plan_backend.test.py
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ["PI_BIN"] = str(ROOT / "tests" / "support" / "fake_pi_rpc.py")
os.environ.setdefault("NLTK_DISABLE_IMPORT_SECURITY", "1")
sys.path.insert(0, str(ROOT))

import pipecat_server as server  # noqa: E402
from obsidian_memory import ObsidianMemory  # noqa: E402
from vault_cli import VaultCLI  # noqa: E402
from session_engine import SessionEngine  # noqa: E402
from pipecat.processors.aggregators.llm_context import LLMContext  # noqa: E402
from pipecat.frames.frames import (  # noqa: E402
    FunctionCallInProgressFrame,
    TranscriptionFrame,
)


class RecordingWorker:
    def __init__(self, cwd, session_id, progress_cb=None, extra_args=None):
        self.cwd = cwd
        self.extra_args = list(extra_args or [])
        self.started = False
        self.closed = False

    async def start(self):
        self.started = True

    async def prompt(self, task):
        return "PI-STUB OK: did the work"

    async def steer(self, message):
        return f"Steered: {message}"

    async def abort(self):
        return "ABORTED"

    async def close(self):
        self.closed = True


def make_relay():
    ctx = LLMContext(messages=[{"role": "system", "content": server.INSTRUCTIONS}],
                     tools=server.TOOL_SCHEMAS)
    relay = server.ToolRelayProcessor(ctx, "plan-test")
    return ctx, relay


class TestSchemaBudget(unittest.TestCase):
    def test_hot_prefill_within_budget(self):
        est = server.estimate_schema_tokens(server.TOOL_SCHEMAS)
        self.assertLessEqual(est, server.VOICE_SCHEMA_TOKEN_BUDGET)
        self.assertEqual(server.assert_schema_budget(), est)

    def test_hot_prefill_has_expected_toolset(self):
        names = {t.name for t in server.TOOL_SCHEMAS}
        # G5: 9 always-hot tools. behind-the-wall tools are NOT prefilled.
        for hot in {"web_search", "get_time", "memory_recall", "spawn_object"}:
            self.assertIn(hot, names)
        for wall in {"delegate_pi", "steer_pi", "memory_summarize"}:
            self.assertNotIn(wall, names)
        # plan tools are lazy, not plain hot.
        for lazy in {"plan_work", "step_task", "structure_notes", "session_engine"}:
            self.assertNotIn(lazy, names)
        self.assertIn("plan_work", {t.name for t in server.LAZY_PLAN_SCHEMAS})

    def test_budget_raises_when_lowered(self):
        with self.assertRaises(RuntimeError):
            server.assert_schema_budget(budget=10)

    def test_behind_wall_tools_still_in_server_tools(self):
        for wall in {"delegate_pi", "steer_pi", "memory_summarize",
                     "plan_work", "step_task"}:
            self.assertIn(wall, server.SERVER_TOOLS)


class TestLazyInjection(unittest.TestCase):
    def test_apply_plan_intent_expands_tools(self):
        ctx, relay = make_relay()
        self.assertFalse(relay._plan_tools_injected)
        # no plan tools yet
        self.assertEqual(len(server.TOOL_SCHEMAS), 9)
        relay._apply_plan_intent("build me a new feature please")
        self.assertTrue(relay._plan_tools_injected)
        # The context's tools now include the lazy plan toolset.
        ts = ctx.tools
        names = {
            getattr(t, "name", None)
            for t in list(getattr(ts, "standard_tools", []) or [])
            + list(getattr(ts, "custom_tools", []) or [])
            if hasattr(t, "name")
        }
        self.assertIn("plan_work", names)
        self.assertIn("structure_notes", names)
        self.assertIn("session_engine", names)

    def test_apply_plan_intent_idempotent(self):
        ctx, relay = make_relay()
        relay._apply_plan_intent("let's plan the migration")
        relay._apply_plan_intent("more")
        self.assertTrue(relay._plan_tools_injected)


class TestPlanHandlers(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self._git("init", "-q", "-b", "main")
        self._git("config", "user.email", "t@t.co")
        self._git("config", "user.name", "T")
        (self.repo / "a.txt").write_text("a\n", encoding="utf-8")
        self._git("add", ".")
        self._git("commit", "-qm", "init")
        self._make_orchestrator()

    def tearDown(self):
        self._tmp.cleanup()

    def _git(self, *args):
        import subprocess
        return subprocess.run(["git", *args], cwd=str(self.repo), capture_output=True)

    def _make_orchestrator(self):
        mem = ObsidianMemory(self.root / "vault")
        mem.ensure_scaffold()
        self.cli = VaultCLI(mem)
        self.engine = SessionEngine(self.cli, rpc_factory=RecordingWorker)
        self.ctx, self.relay = make_relay()
        self.relay._orchestrator = self.engine

    async def test_plan_work_start(self):
        res = await self.relay._run_plan_work(
            {"goal": "add a docs page", "project": "Docs", "repo": str(self.repo)}
        )
        self.assertIn("Plan started", res)
        self.assertIn("forked", res)
        # Plan + session nodes created in the temp vault.
        plan = self.cli.vault / "projects" / "docs" / "plan.md"
        self.assertTrue(plan.exists())
        self.assertEqual(self.cli.plan_get_status("Docs"), "in_progress")

    async def test_step_task_reports_progress(self):
        await self.relay._run_plan_work(
            {"goal": "task", "project": "P", "repo": str(self.repo)}
        )
        res = await self.relay._run_step_task({"project": "P"})
        self.assertIn("(", res)  # tree annotation
        vid = next(iter(self.relay._orchestrator._sessions))
        tree = self.relay._orchestrator.session_tree("P", root=vid)
        self.assertIn(vid, tree)

    async def test_session_engine_dispatch(self):
        s = await self.engine.fork_session(goal="x", repo=self.repo, branch="op-a", project="P")
        res = await self.relay._run_session_engine_tool({"op": "steer", "args": {"vid": s.vid, "message": "go left"}})
        self.assertIn("Steered:", res)
        res = await self.relay._run_session_engine_tool({"op": "tree", "args": {"project": "P"}})
        self.assertIn("op-a", res)
        res = await self.relay._run_session_engine_tool({"op": "bogus", "args": {}})
        self.assertTrue(res.startswith("Error:"))

    async def test_structure_notes_via_run_tool(self):
        res = self.cli.run_tool("ensure_project", {"name": "Blue"})
        self.assertTrue(res.startswith("OK:"))
        res = self.cli.run_tool("note_create", {"path": "memories/note-1", "title": "Note 1", "body": "hi"})
        self.assertTrue(res.startswith("OK:"))

    # -- multi-project voice disambiguation --------------------------------

    async def _fork_two_projects(self):
        a = await self.engine.fork_session(goal="x", repo=self.repo, branch="auth-a", project="Auth")
        b = await self.engine.fork_session(goal="y", repo=self.repo, branch="db-a", project="Database")
        return a, b

    async def test_set_project_and_list_ops(self):
        await self._fork_two_projects()
        res = await self.relay._run_session_engine_tool({"op": "list", "args": {}})
        self.assertIn("auth", res)
        self.assertIn("database", res)
        res = await self.relay._run_session_engine_tool({"op": "set_project", "args": {"project": "Auth"}})
        self.assertIn("switched to 'Auth'", res)
        self.assertEqual(self.engine.current_project, "Auth")

    async def test_step_task_steers_by_project_not_dict_order(self):
        await self._fork_two_projects()
        # current cursor is Database (most recent fork). Explicit project wins:
        res = await self.relay._run_step_task({"project": "Auth", "steer": "do the CSS first"})
        self.assertIn("Steered:", res)
        # default steers the CURRENT project when no explicit one given.
        res2 = await self.relay._run_step_task({"steer": "go left"})
        self.assertIn("Steered:", res2)

    async def test_project_state_narration(self):
        await self._fork_two_projects()
        res = await self.relay._run_step_task({"project": "Auth"})
        self.assertIn("Auth", res)
        self.assertIn("auth-a", res)
        # current-project fallback when no project supplied.
        res2 = await self.relay._run_step_task({})
        self.assertIn("Database", res2)
        self.assertIn("db-a", res2)

    async def test_register_op_lists_registered_project(self):
        # register a known external project through the session_engine dispatch.
        res = await self.relay._run_session_engine_tool({
            "op": "register", "args": {"project": "Ironman", "repo": str(self.repo)}
        })
        self.assertTrue(res.startswith("OK: registered project"))
        lst = await self.relay._run_session_engine_tool({"op": "list", "args": {}})
        self.assertIn("ironman (registered", lst)


if __name__ == "__main__":
    unittest.main(verbosity=2)
