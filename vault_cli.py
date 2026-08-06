"""Obsidian vault structure CLI — the voice agent's structure-organiser tool.

Part of the Dassein plan/execution backend (docs/PLAN_AGENT_BACKEND.md, Phase 0).
A deterministic, pure-stdlib file-op layer over `ObsidianMemory` that lets the
voice agent command the vault as a *working surface*: create/organise project
folders, create/open/append/rename notes (with YAML frontmatter), draft/promote
plan.md, and regenerate the vault index.

Conventions (shared with observation_memory.py and the plan's guarantees):

- **Never overwrite or delete body content.** `note_append` and `plan_append`
  add dated `## (rev)` sections; `note_create` errors if the note exists. The
  *only* in-place mutations are frontmatter fields (`plan_set_status` stamps
  `status`/`promoted_to`), renames/moves (`note_rename_or_move`), and `rebuild_index`
  regenerating the generated index.md.
- **G1** — `plan_promote` writes ONLY the target repo `docs/PLAN.md` (atomically);
  it never touches the vault note body.
- Every public op returns a **capped** string (<= MEMORY_RESULT_MAX_CHARS) so it
  fits LLM context. Errors are terse strings, never raised into the LLM handler
  (mirrors `delegate_pi`).
- Deliberately independent of pipecat so it is unit-testable with a temp vault
  (see tests/unit/vault_cli.test.py).

Plans live at `projects/<slug>/plan.md` and carry frontmatter state:

    ---
    title: <proj>
    type: plan
    status: drafting | approved | in_progress | merged | abandoned
    promoted_to: "<repo>/docs/PLAN.md"   # set at approve
    tags: [plan, <proj>]
    ---
"""

import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from obsidian_memory import (
    ObsidianMemory,
    MEMORY_RESULT_MAX_CHARS,
    _slugify,
    _split_frontmatter,
    _extract_links,
)

PLAN_TEMPLATE = """---
title: {title}
type: plan
status: drafting
promoted_to: ""
tags: [plan, {slug}]
---

# {title}

## goal

## approach

## definition of done

"""


class AlreadyExistsError(Exception):
    """note_create hit an existing note — refuse (never overwrite)."""


class MissingError(Exception):
    """note_rename_or_move referenced a note that does not exist."""


class VaultCLI:
    """Thin structure orchestrator over an ObsidianMemory vault."""

    def __init__(self, mem: ObsidianMemory):
        self.mem = mem
        self.vault = mem.vault

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _cap(text: str, max_chars: int = MEMORY_RESULT_MAX_CHARS) -> str:
        if len(text) <= max_chars:
            return text
        return text[: max_chars] + "…"

    def _vault_rel(self, path: Path) -> str:
        return path.relative_to(self.vault).as_posix()

    def _resolve(self, name: str) -> Path | None:
        """Resolve a path inside the vault (absolute or vault-relative), reusing
        ObsidianMemory's fuzzy resolution for names."""
        return self.mem._resolve(name)

    def _heading(self, title: str) -> str:
        return f"## {datetime.now():%Y-%m-%d %H:%M} — {title}"

    # -- project scaffold ---------------------------------------------------

    def ensure_project(self, name: str) -> Path:
        """Create `projects/<slug>/` with a plan.md skeleton. Returns the project dir.

        Also creates `projects/<slug>/sessions/` so fork nodes have a home.
        Idempotent: re-calling returns the same dir without erroring.
        """
        name = (name or "").strip()
        if not name:
            return self.vault / "projects" / "_untitled"
        slug = _slugify(name) or f"proj-{datetime.now():%Y%m%d%H%M%S}"
        pdir = self.vault / "projects" / slug
        pdir.mkdir(parents=True, exist_ok=True)
        (pdir / "sessions").mkdir(parents=True, exist_ok=True)
        plan = self._plan_path(slug)
        if not plan.exists():
            plan.write_text(
                PLAN_TEMPLATE.format(title=name, slug=slug), encoding="utf-8"
            )
        return pdir

    def _plan_path(self, project: str) -> Path:
        return self.vault / "projects" / _slugify(project) / "plan.md"

    def _project_of(self, rel: str) -> str:
        parts = Path(rel).parts
        if len(parts) >= 2 and parts[0] == "projects":
            return parts[1]
        return ""

    # -- note verbs ---------------------------------------------------------

    def note_create(
        self,
        path: str,
        title: str,
        body: str = "",
        front: dict | None = None,
    ) -> Path:
        """Create a new note at `path` (vault-relative or absolute). Never overwrites.

        `front` is merged under the standard title/date/type/tags frontmatter.
        Raises AlreadyExistsError if the note already exists (caller converts to an
        error string); otherwise returns the created Path.
        """
        path = (path or "").strip().lstrip("/")
        if not path.endswith(".md"):
            path += ".md"
        note: Path = self.mem._resolve(path) if not Path(path).is_absolute() else None
        target = note if note is not None else (self.vault / path)
        if target.exists():
            raise AlreadyExistsError(f"Note already exists: {self._vault_rel(target)}")
        target.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now()
        lines = ["---"]
        lines.append(f"title: {str(title).strip() or target.stem}")
        lines.append(f"date: {now:%Y-%m-%d}")
        lines.append("type: note")
        front = front or {}
        for k in ["tags"]:
            v = front.get(k)
            if v is not None:
                lines.append(f"tags: [{', '.join(str(x).strip() for x in v)}]")
        extra = {k: v for k, v in front.items() if k != "tags"}
        for k in ["status", "branch", "repo", "parent", "child", "dod", "created"]:
            if k in extra:
                v = extra.pop(k)
                lines.append(f"{k}: {v}")
        for k, v in extra.items():
            lines.append(f"{k}: {v}")
        lines.append("---")
        lines.append("")
        lines.append(f"# {str(title).strip() or target.stem}")
        if body.strip():
            lines.append("")
            lines.append(body.strip())
        lines.append("")
        target.write_text("\n".join(lines), encoding="utf-8")
        return target

    def note_append(self, path: str, section: str, body: str) -> int:
        """Append a dated `## <now> — <section>` section to a note.

        Returns number of chars appended. Errors (missing note / empty body) return
        a terse string via the string-returning wrapper — the inner op raises.
        """
        target = self.mem._resolve(path)
        if target is None:
            raise MissingError(f"Note not found: {path}")
        body = (body or "").strip()
        if not body:
            raise ValueError("note_append requires a body.")
        note = f"\n\n---\n\n{self._heading(section)}\n\n{body}\n"
        with target.open("a", encoding="utf-8") as f:
            f.write(note)
        return len(note)

    def note_read(self, name: str, follow_links: bool = True) -> str:
        """Read a note, reusing mem.read (which caps + follows wiki-links)."""
        return self.mem.read(name, follow_links=follow_links)

    def note_rename_or_move(self, old: str, new: str) -> Path:
        """Rename or move a note *within the vault*. The only path/file mutation
        allowed by G1. Returns the new Path. Raises MissingError if old is absent."""
        src = self.mem._resolve(old)
        if src is None:
            raise MissingError(f"Note not found: {old}")
        old_key = self._vault_rel(src)  # pre-rename identity for link retargeting
        new = (new or "").strip().lstrip("/")
        if not new.endswith(".md"):
            new += ".md"
        dst = self.vault / new
        if dst.exists():
            raise AlreadyExistsError(f"Destination exists: {new}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
        # Update wiki-links pointing at the moved note across the vault.
        self._retarget_links(self._vault_rel(dst), old_key)
        return dst

    def _retarget_links(self, new_rel: str, old_key: str):
        """After a rename/move, rewrite any `[[...]]` link across the vault whose
        target resolves to the moved note so it points at the new path.

        `old_key` is the moved note's pre-rename vault-relative path (computed by
        the caller before renaming, since the note no longer resolves afterwards).
        Walks every note's wiki-links, resolves each target through
        ObsidianMemory._resolve (handles bare `[[b]]` and `[[path/to/b]]` both),
        and rewrites links that resolve to the moved note. Deterministic; only
        touches text, never removes content."""
        old_norm = old_key.replace("\\", "/") if old_key else ""
        for p in self.mem._iter_notes():
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if "[[" not in text:
                continue
            changed = text
            for m in re.finditer(r"\[\[([^\]]+)\]\]", text):
                token = m.group(1).strip()
                label = token.split("|")[0].split("#")[0].strip()
                resolved = self.mem._resolve(label)
                # Resolve runs AFTER the move so the old note won't resolve by
                # filename anymore; match the pre-rename identity by stem too.
                rrel = None
                if resolved is not None:
                    try:
                        rrel = resolved.relative_to(self.vault).as_posix()
                    except ValueError:
                        rrel = None
                label_norm = label.replace("\\", "/")
                old_stem = old_norm.strip(".md").split("/")[-1]
                label_stem = label_norm.strip(".md").split("/")[-1]
                # A link matches the moved note if it resolves directly to it, OR
                # (the note is now gone and) the link's bare stem equals the moved
                # note's stem — the moved note was the only holder of that stem.
                matched = rrel == old_norm or (
                    resolved is None and label_stem == old_stem
                )
                if not matched:
                    continue
                # Target moved -> rewrite the token (preserve alias/heading suffix).
                suffix = token[len(label):] if token.startswith(label) else ""
                new_token = new_rel + suffix
                changed = changed.replace(f"[[{token}]]", f"[[{new_token}]]")
            if changed != text:
                p.write_text(changed, encoding="utf-8")

    def run_tool(self, op: str, args: dict) -> str:
        """Dispatch a structure op to the matching verb and return a capped string.

        This is the boundary the voice server calls (through the `structure_notes`
        schema). Errors are converted to terse strings, never raised — mirroring
        delegate_pi and the plan's "errors are strings, not exceptions" rule.
        """
        args = dict(args or {})
        try:
            if op == "ensure_project":
                out = self.ensure_project(str(args.get("name") or ""))
                return f"OK: {self._vault_rel(out)}"
            if op == "note_create":
                out = self.note_create(
                    str(args.get("path") or ""),
                    str(args.get("title") or ""),
                    str(args.get("body") or ""),
                    args.get("front") or None,
                )
                return f"OK: {self._vault_rel(out)}"
            if op == "note_append":
                n = self.note_append(
                    str(args.get("path") or ""),
                    str(args.get("section") or "log"),
                    str(args.get("body") or ""),
                )
                return f"OK: appended {n} chars"
            if op == "note_read":
                return self.note_read(str(args.get("name") or ""))
            if op == "note_rename_or_move":
                out = self.note_rename_or_move(
                    str(args.get("old") or ""), str(args.get("new") or "")
                )
                return f"OK: renamed to {self._vault_rel(out)}"
            if op == "plan_draft":
                out = self.plan_draft(
                    str(args.get("project") or ""), str(args.get("content") or "")
                )
                return f"OK: plan at {self._vault_rel(out)}"
            if op == "plan_read":
                return self.plan_read(str(args.get("project") or ""))
            if op == "plan_append":
                n = self.plan_append(
                    str(args.get("project") or ""),
                    str(args.get("section") or "plan"),
                    str(args.get("body") or ""),
                )
                return f"OK: plan appended {n} chars"
            if op == "plan_set_status":
                out = self.plan_set_status(
                    str(args.get("project") or ""),
                    str(args.get("status") or ""),
                    str(args.get("phase") or "") or None,
                )
                return f"OK: status set on {self._vault_rel(out)}"
            if op == "plan_promote":
                out = self.plan_promote(
                    str(args.get("project") or ""), Path(str(args.get("repo_root") or ""))
                )
                return f"OK: promoted to {out}"
            if op == "rebuild_index":
                notes = self.rebuild_index()
                return f"OK: rebuilt index with {len(notes)} notes"
            return f"Error: unknown structure op {op}"
        except AlreadyExistsError as e:
            return self._cap(f"Error: {e}")
        except MissingError as e:
            return self._cap(f"Error: {e}")
        except ValueError as e:
            return self._cap(f"Error: {e}")
        except OSError as e:
            return self._cap(f"Error: vault op {op}: {e}")

    # -- plan verbs ---------------------------------------------------------

    def _plan_path_for(self, project: str) -> Path:
        p = self._plan_path(project)
        if not p.exists():
            raise MissingError(f"No plan for project: {project}")
        return p

    def plan_draft(self, project: str, content: str) -> Path:
        """Upsert `projects/<proj>/plan.md` body. If it doesn't exist, create a
        skeleton; if it does, treat the new content as a revision appended to the
        `plan:` section (append-only, G1). Returns the plan Path."""
        content = (content or "").strip()
        project = (project or "").strip()
        slug = _slugify(project) or "untitled"
        pdir = self.vault / "projects" / slug
        pdir.mkdir(parents=True, exist_ok=True)
        (pdir / "sessions").mkdir(parents=True, exist_ok=True)
        plan = pdir / "plan.md"
        if not plan.exists():
            plan.write_text(
                PLAN_TEMPLATE.format(title=project or slug, slug=slug), encoding="utf-8"
            )
        if content:
            self.note_append(self._vault_rel(plan), "plan", content)
        return plan

    def plan_read(self, project: str) -> str:
        """Read the vault plan body (reuse mem.read)."""
        plan = self._plan_path_for(project)
        return self.mem.read(self._vault_rel(plan), follow_links=True)

    def plan_append(self, project: str, section: str, body: str) -> int:
        """Append-only revision section via note_append."""
        plan = self._plan_path_for(project)
        return self.note_append(self._vault_rel(plan), section, body)

    def plan_get_status(self, project: str) -> str:
        """Read the plan's `status` frontmatter (for step_task narration)."""
        plan = self._plan_path_for(project)
        text = plan.read_text(encoding="utf-8", errors="replace")
        front, _ = _split_frontmatter(text)
        m = re.search(r"^status:\s*(.+?)\s*$", front, re.MULTILINE)
        return (m.group(1).strip() if m else "unknown").strip('"')

    def plan_set_status(self, project: str, status: str, phase: str | None = None) -> Path:
        """Frontmatter edit-only G1 carve-out: stamp `status` (and optional phase)
        on the plan. Phase is written as a `phase:` frontmatter line, not body."""
        plan = self._plan_path_for(project)
        text = plan.read_text(encoding="utf-8", errors="replace")
        front, body = _split_frontmatter(text)
        allowed = {"drafting", "approved", "in_progress", "merged", "abandoned"}
        status = (status or "").strip()
        if status not in allowed:
            status = "drafting"
        def _stamp(block: str, key: str, val: str, quote: bool = False) -> str:
            val = val.strip()
            if quote and val:
                val = f'"{val}"'
            lines = block.split("\n")
            found = False
            for i, ln in enumerate(lines):
                if re.match(rf"^{re.escape(key)}:\s*", ln):
                    lines[i] = f"{key}: {val}"
                    found = True
                    break
            if not found:
                # insert after `type:` if present else at top after `---`
                ins = 0
                for i, ln in enumerate(lines):
                    if ln.startswith("type:"):
                        ins = i + 1
                        break
                lines.insert(ins, f"{key}: {val}")
            return "\n".join(lines)
        front = _stamp(front, "status", status)
        if phase:
            front = _stamp(front, "phase", phase)
        plan.write_text(f"---\n{front}\n---\n{body}", encoding="utf-8")
        return plan

    def plan_promote(self, project: str, repo_root: Path) -> Path:
        """G1 carve-out: write ONLY the target repo `docs/PLAN.md`.

        Reads the vault plan body, writes `<repo_root>/docs/PLAN.md` atomically
        (temp + os.replace), stamps `promoted_to` and `status=approved`.
        Never touches the vault note body.
        """
        plan = self._plan_path_for(project)
        vault_text = plan.read_text(encoding="utf-8", errors="replace")
        repo_root = Path(repo_root).expanduser().resolve()
        out = repo_root / "docs" / "PLAN.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        # atomic write
        tmp = out.with_name(f".{out.name}.{os.getpid()}.tmp")
        tmp.write_text(vault_text + "\n", encoding="utf-8")
        os.replace(tmp, out)
        # record promotion in the vault's frontmatter only (G1: frontmatter edit-only)
        self.plan_set_status(project, "approved")
        self._stamp_promoted(project, str(out))
        return out

    def _stamp_promoted(self, project: str, target: str):
        plan = self._plan_path_for(project)
        text = plan.read_text(encoding="utf-8", errors="replace")
        front, body = _split_frontmatter(text)
        lines = front.split("\n")
        replaced = False
        for i, ln in enumerate(lines):
            if ln.startswith("promoted_to:"):
                lines[i] = f'promoted_to: "{target}"'
                replaced = True
                break
        if not replaced:
            insert = 0
            for i, ln in enumerate(lines):
                if ln.startswith("status:"):
                    insert = i + 1
                    break
            lines.insert(insert, f'promoted_to: "{target}"')
        plan.write_text(f"---\n{'\n'.join(lines)}\n---\n{body}", encoding="utf-8")

    # -- index --------------------------------------------------------------

    def rebuild_index(self) -> list[str]:
        """Regenerate the vault index.md (the one G1 carve-out that rewrites a file).
        Returns the list of note paths indexed."""
        idx = self.vault / "index.md"
        notes = [p.relative_to(self.vault).as_posix() for p in self.mem._iter_notes()]
        parts = ["# Vault Index", "", "Map of the agent's memory. Folders:"]
        by_dir: dict[str, list[str]] = {}
        for rel in notes:
            d = rel.split("/")[0]
            by_dir.setdefault(d, []).append(rel)
        for d in sorted(by_dir):
            parts.append(f"\n## {d}")
            for rel in sorted(by_dir[d]):
                parts.append(f"- [[{rel}]]")
        parts.append(f"\n{len(notes)} notes total.")
        idx.write_text("\n".join(parts) + "\n", encoding="utf-8")
        return notes


def scaffold_cli_tool(
    name: str = "structure_notes",
    description: str = (
        "Organise the Obsidian vault: create a project, create/open/append/rename notes "
        "with YAML frontmatter, draft/promote a plan.md, or rebuild the index. Never "
        "deletes or overwrites body content. Call with a single `op` + its arguments."
    ),
) -> dict:
    """OCI/pipecat tool schema for the structure CLI (surfaced behind plan_work).

    Kept intentionally small (one `op` enum + a generic `args` object) so the
    heavy per-op parameter schemas never enter the voice prefill (G5/C5).
    """
    return {
        "type": "function",
        "runsOn": "server",
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": {
                "op": {
                    "type": "string",
                    "enum": [
                        "ensure_project",
                        "note_create",
                        "note_append",
                        "note_read",
                        "note_rename_or_move",
                        "plan_draft",
                        "plan_read",
                        "plan_append",
                        "plan_set_status",
                        "plan_promote",
                        "rebuild_index",
                    ],
                    "description": "The vault structure operation to run",
                },
                "args": {
                    "type": "object",
                    "description": "Op-specific arguments (project, path, title, content, section, body, front, status, phase, repo_root)",
                },
            },
            "required": ["op"],
        },
    }
