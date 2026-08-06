#!/usr/bin/env python3
"""Unit tests for vault_cli.VaultCLI against a temp vault.

Covers the G1 discipline (never overwrite body content), frontmatter status
stamps, plan draft/promote (writes only the target repo docs/PLAN.md), note
create/append/rename, and rebuild_index. Pure stdlib + temp dirs (repo style).

Run:
    NLTK_DISABLE_IMPORT_SECURITY=1 .venv-voice/bin/python tests/unit/vault_cli.test.py
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("NLTK_DISABLE_IMPORT_SECURITY", "1")
sys.path.insert(0, str(ROOT))

from obsidian_memory import ObsidianMemory  # noqa: E402
from vault_cli import (  # noqa: E402
    VaultCLI,
    AlreadyExistsError,
    MissingError,
    _slugify,
)


def _make_cli(root: Path) -> VaultCLI:
    mem = ObsidianMemory(root)
    mem.ensure_scaffold()
    return VaultCLI(mem)


class TestVaultCLI(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "vault"
        self.cli = _make_cli(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    # -- project / plan ------------------------------------------------

    def test_ensure_project_creates_skeleton(self):
        pdir = self.cli.ensure_project("Coffee Robot")
        self.assertEqual(pdir, self.root / "projects" / "coffee-robot")
        self.assertTrue((pdir / "plan.md").exists())
        self.assertTrue((pdir / "sessions").is_dir())
        text = (pdir / "plan.md").read_text(encoding="utf-8")
        self.assertIn("status: drafting", text)

    def test_ensure_project_is_idempotent(self):
        self.cli.ensure_project("Thing")
        self.cli.ensure_project("Thing")  # no error
        self.assertEqual(
            (self.root / "projects" / "thing" / "plan.md")
            .read_text(encoding="utf-8")
            .count("---"),
            2,
        )

    def test_plan_draft_upserts_skeleton(self):
        self.cli.plan_draft("Auth", "# Auth\n\nGoal.")
        plan = self.root / "projects" / "auth" / "plan.md"
        self.assertTrue(plan.exists())
        body = plan.read_text(encoding="utf-8")
        self.assertIn("# Auth", body)

    def test_plan_set_status_stamps_frontmatter(self):
        self.cli.plan_draft("Auth", "x")
        self.cli.plan_set_status("Auth", "approved")
        self.assertEqual(self.cli.plan_get_status("Auth"), "approved")
        body = (self.root / "projects" / "auth" / "plan.md").read_text(encoding="utf-8")
        # Frontmatter edited; body untouched (no revision section added).
        self.assertIn("status: approved", body.split("---")[1])

    def test_plan_set_status_rejects_garbage(self):
        self.cli.plan_draft("P", "")
        self.cli.plan_set_status("P", "not-a-real-status")
        self.assertEqual(self.cli.plan_get_status("P"), "drafting")

    # -- note verbs + G1 ------------------------------------------------

    def test_note_create_then_append_never_overwrites(self):
        path = self.cli.note_create("people/amy.md", title="Amy", body="loves coffee")
        self.assertTrue(path.exists())
        n = self.cli.note_append("people/amy.md", "preference", "also likes tea")
        self.assertGreater(n, 0)
        after = path.read_text(encoding="utf-8")
        self.assertIn("loves coffee", after)
        self.assertIn("also likes tea", after)
        # The original body is still present verbatim (never destroyed).
        self.assertIn("# Amy", after)
        self.assertIn("also likes tea", after)

    def test_note_create_conflict_raises(self):
        self.cli.note_create("memories/x.md", "X")
        with self.assertRaises(AlreadyExistsError):
            self.cli.note_create("memories/x.md", "X again")

    def test_note_append_missing_raises(self):
        with self.assertRaises(MissingError):
            self.cli.note_append("does-not-exist.md", "s", "body")

    def test_note_rename_or_move_retargets_links(self):
        self.cli.note_create("memories/a.md", "A", body="see [[b]]")
        self.cli.note_create("memories/b.md", "B")
        self.cli.note_rename_or_move("memories/b.md", "memories/beefs.md")
        # Downstream note should now point at the moved path.
        text = (self.root / "memories" / "a.md").read_text(encoding="utf-8")
        self.assertIn("[[memories/beefs.md]]", text)

    def test_note_read_follows_links(self):
        self.cli.note_create("memories/a.md", "A", body="see [[b]] ref")
        self.cli.note_create("memories/b.md", "B", body="linked content")
        out = self.cli.note_read("memories/a.md")
        self.assertIn("linked content", out)

    # -- plan promote (G1) ---------------------------------------------

    def test_plan_promote_writes_only_target_repo_plan(self):
        self.cli.plan_draft("Auth", "# Auth\n\nReal plan body content")
        # A fake separate target repo (not the vault).
        with tempfile.TemporaryDirectory() as repo:
            repo_root = Path(repo) / "auth-repo"
            out = self.cli.plan_promote("Auth", repo_root)
            self.assertEqual(out, repo_root / "docs" / "PLAN.md")
            self.assertTrue(out.exists())
            self.assertIn("# Auth", out.read_text(encoding="utf-8"))
            self.assertIn("Real plan body content", out.read_text(encoding="utf-8"))
            # Vault note body unchanged (append-only provenance preserved).
            plan = self.root / "projects" / "auth" / "plan.md"
            body = plan.read_text(encoding="utf-8")
            self.assertIn("# Auth", body)
            self.assertIn("Real plan body content", body)
            # Status + promoted_to stamped in vault frontmatter.
            self.assertEqual(self.cli.plan_get_status("Auth"), "approved")
            self.assertIn(str(out), body)

    # -- run_tool (string boundary) -----------------------------------

    def test_run_tool_errors_are_strings_not_raises(self):
        res = self.cli.run_tool("plan_read", {"project": "missing"})
        self.assertTrue(res.startswith("Error:"))
        res = self.cli.run_tool("nope", {})
        self.assertTrue(res.startswith("Error:"))

    def test_run_tool_ok_paths(self):
        res = self.cli.run_tool("ensure_project", {"name": "Blue Whale"})
        self.assertTrue(res.startswith("OK:"))
        res = self.cli.run_tool("plan_set_status", {"project": "blue-whale", "status": "approved"})
        self.assertTrue(res.startswith("OK:"))
        res = self.cli.run_tool("read_missing", {"project": "blue-whale"})
        self.assertTrue(res.startswith("Error:"))

    def test_rebuild_index(self):
        self.cli.note_create("memories/remember-this.md", "Remember This")
        notes = self.cli.rebuild_index()
        self.assertIn("memories/remember-this.md", notes)
        idx = (self.root / "index.md").read_text(encoding="utf-8")
        self.assertIn("[[memories/remember-this.md]]", idx)

    def test_slugify(self):
        self.assertEqual(_slugify("Coffee Preference"), "coffee-preference")
        self.assertEqual(_slugify("  Spiky   Object 1 "), "spiky-object-1")

    # -- project registry (known_projects / register / repo) ------------

    def test_register_project_creates_skeleton_and_repo(self):
        with tempfile.TemporaryDirectory() as repo:
            repo_root = Path(repo)  # pretend an external git repo
            res = self.cli.register_project("Dassein", repo=repo_root)
            self.assertTrue(res.startswith("OK: registered project"))
            known = self.cli.known_projects()
            self.assertTrue(any(k["slug"] == "dassein" for k in known))
            self.assertEqual(self.cli.project_repo("Dassein"), repo_root.resolve())

    def test_known_projects_includes_idle_registered(self):
        self.cli.plan_draft("Auth", "")
        known = self.cli.known_projects()
        self.assertTrue(any(k["slug"] == "auth" for k in known))
        auth = next(k for k in known if k["slug"] == "auth")
        self.assertEqual(auth["title"], "Auth")
        self.assertEqual(auth["status"], "drafting")

    def test_register_project_is_idempotent(self):
        self.cli.register_project("X")
        self.cli.register_project("X")
        self.assertEqual(len([k for k in self.cli.known_projects() if k["slug"] == "x"]), 1)

    def test_project_repo_returns_none_when_unset(self):
        self.cli.plan_draft("NoRepo", "")
        self.assertIsNone(self.cli.project_repo("NoRepo"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
