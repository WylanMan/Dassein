"""Persistent `pi --mode rpc` session client — Tier 2 voice pacing.

Replaces the one-shot `pi -p` delegate_pi execution with a warm, long-lived
RPC session per voice connection:

- spawn `pi --mode rpc --no-session` once (lazily), reuse across tool calls —
  no per-call cold start, pi keeps in-process conversation context
- stream live progress: `tool_execution_start` events → narration callback
  (the relay speaks short "Running a command." lines while pi works)
- `steer(message)` — redirect a running job between tool calls (RPC steer)
- `abort()` — cancel the current run WITHOUT killing the session (barge-in)

Wire protocol: strict JSONL over stdin/stdout (pi docs/rpc.md). Commands carry
an optional `id` for response correlation; `agent_settled` marks prompt
completion. This module is deliberately independent of pipecat so it is
unit-testable with a stub `pi` binary (see tests/support/fake_pi_rpc.py).
"""

import asyncio
import json
import os
from pathlib import Path

PI_BIN = os.environ.get(
    "PI_BIN",
    "/home/cman/.local/share/pi-node/node-v22.23.1-linux-x64/bin/pi",
)
PI_RESULT_MAX_CHARS = 1500    # cap for what enters LLM context


def _timeout_s() -> float:
    """Per-call timeout, env-overridable so tests (and ops) can tune it."""
    try:
        return max(0.1, float(os.environ.get("PI_TIMEOUT_S", "120")))
    except (TypeError, ValueError):
        return 120.0


def _env_for_pi():
    """Subprocess env: prepend pi's bin dir so the `#!/usr/bin/env node`
    shebang resolves regardless of caller PATH. Use UNRESOLVED parent — `pi`
    is a symlink; `.resolve()` follows it into dist/ which has no `node`."""
    env = os.environ.copy()
    env["PATH"] = str(Path(PI_BIN).parent) + os.pathsep + env.get("PATH", "")
    env.setdefault("NO_COLOR", "1")
    return env


class PiRpcSession:
    """One long-lived `pi --mode rpc` subprocess with JSONL framing.

    Usage:
        sess = PiRpcSession(cwd="/home/cman/Dassein", session_id="abc", progress_cb=cb)
        await sess.start()
        result = await sess.prompt("list the files")   # str, capped
        await sess.steer("actually do the CSS first")  # mid-run redirect
        await sess.abort()                              # barge-in cancel
        await sess.close()
    """

    def __init__(self, cwd: str, session_id: str, progress_cb=None, extra_args=None):
        self._cwd = str(cwd)
        self._session_id = session_id
        self._progress_cb = progress_cb          # async callable(ev: dict) or None
        self._extra_args = list(extra_args or [])  # worker-launch flags, e.g. --no-skills
        self._proc = None
        self._reader_task = None
        self._pending: dict[str, asyncio.Future] = {}
        self._accepted: set[str] = set()
        self._current_req: str | None = None
        self._started_rid: str | None = None  # request whose agent_start we saw
        self._final_text: dict[str, str] = {}
        self._req_id = 0
        self._write_lock = asyncio.Lock()
        self._dead = False

    # -- lifecycle ---------------------------------------------------------

    async def start(self):
        if self._proc is not None and self._proc.returncode is None and not self._dead:
            return
        args = [PI_BIN, "--mode", "rpc", "--no-session"] + self._extra_args
        try:
            self._proc = await asyncio.create_subprocess_exec(
                *args,
                cwd=self._cwd,
                env=_env_for_pi(),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            raise RuntimeError(f"pi binary not found at {PI_BIN}")
        except OSError as e:
            raise RuntimeError(f"failed to start pi: {e}")
        self._dead = False
        self._reader_task = asyncio.create_task(self._reader())

    async def close(self):
        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except (asyncio.CancelledError, Exception):
                pass
            self._reader_task = None
        if self._proc is not None and self._proc.returncode is None:
            self._proc.kill()
            try:
                await self._proc.wait()
            except Exception:
                pass
        self._proc = None
        self._dead = True
        # Fail any stragglers so awaiting prompt() never hangs forever.
        for fut in list(self._pending.values()):
            if not fut.done():
                fut.set_result("Error: pi session closed.")
        self._pending.clear()
        self._accepted.clear()

    # -- reader / dispatcher -----------------------------------------------

    async def _reader(self):
        try:
            while True:
                line = await self._proc.stdout.readline()
                if not line:
                    break
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                await self._dispatch(ev)
        except (asyncio.CancelledError, RuntimeError):
            pass
        finally:
            self._dead = True
            for fut in list(self._pending.values()):
                if not fut.done():
                    fut.set_result("Error: pi session ended.")
            self._pending.clear()
            self._accepted.clear()

    async def _dispatch(self, ev: dict):
        t = ev.get("type")
        rid = ev.get("id")

        if t == "response":
            # A command was accepted (NOT completion for prompt; that's
            # agent_settled). Resolve steer/abort futures here; prompt futures
            # wait for agent_settled.
            if rid in self._accepted:
                fut = self._pending.pop(rid, None)
                if fut and not fut.done():
                    fut.set_result("OK")
            return

        if t == "message_update":
            ae = ev.get("assistantMessageEvent") or {}
            if ae.get("type") == "text_delta" and rid is None:
                # Live narration feed: accumulate the forming answer.
                if self._current_req is not None:
                    self._final_text[self._current_req] = (
                        self._final_text.get(self._current_req, "") + ae.get("delta", "")
                    )
                if self._progress_cb:
                    try:
                        await self._progress_cb({"type": "text_delta", "delta": ae.get("delta", "")})
                    except Exception:
                        pass
            return

        if t == "tool_execution_start" and self._progress_cb:
            try:
                await self._progress_cb(
                    {
                        "type": "tool_execution_start",
                        "toolName": ev.get("toolName"),
                        "args": ev.get("args", {}),
                    }
                )
            except Exception:
                pass
            return

        if t == "agent_start":
            # Remember which request's turn actually started. agent_settled has no
            # id, so we only resolve the current request if its own agent_start was
            # seen — otherwise an aborted run's trailing agent_settled would be
            # misattributed to the NEXT prompt (resolving it with empty text).
            self._started_rid = self._current_req
            return

        if t == "agent_settled" and self._current_req is not None:
            if self._started_rid != self._current_req:
                return
            rid = self._current_req
            self._current_req = None
            self._started_rid = None
            fut = self._pending.pop(rid, None)
            if fut and not fut.done():
                fut.set_result(self._final_text.pop(rid, "") or "COMPLETED")
            return

    # -- commands ----------------------------------------------------------

    async def _send(self, obj: dict) -> str:
        """Write one JSONL command, await its response ack (or timeout)."""
        if self._dead or self._proc is None or self._proc.stdin is None:
            raise RuntimeError("pi session not running")
        rid = obj.get("id")
        fut = asyncio.get_running_loop().create_future()
        self._pending[rid] = fut
        self._accepted.add(rid)
        async with self._write_lock:
            self._proc.stdin.write((json.dumps(obj) + "\n").encode())
            await self._proc.stdin.drain()
        try:
            return await asyncio.wait_for(fut, timeout=_timeout_s())
        except asyncio.TimeoutError:
            self._pending.pop(rid, None)
            self._accepted.discard(rid)
            raise RuntimeError(f"pi {obj.get('type')} timed out after {int(_timeout_s())}s")

    async def prompt(self, task: str) -> str:
        """Send a prompt, stream progress, return the final assistant text (capped).

        Barge-in: if the awaiting LLM tool call is cancelled, abort pi's current
        run (keeps the session alive) and re-raise so pipecat owns the cancel.
        """
        timeout = _timeout_s()
        self._req_id += 1
        rid = f"req-{self._req_id}"
        # Crash / EOF respawn: if the session died, start() re-spawns it.
        if self._dead or self._proc is None:
            try:
                await self.start()
            except Exception as e:
                return f"Error: could not (re)start pi session: {e}"
        self._current_req = rid
        self._final_text[rid] = ""
        fut = asyncio.get_running_loop().create_future()
        self._pending[rid] = fut
        try:
            async with self._write_lock:
                self._proc.stdin.write(
                    (json.dumps({"id": rid, "type": "prompt", "message": task}) + "\n").encode()
                )
                await self._proc.stdin.drain()
        except (ConnectionResetError, BrokenPipeError, RuntimeError):
            # pi died between the check and the write (crash / EOF race).
            self._pending.pop(rid, None)
            self._final_text.pop(rid, None)
            self._current_req = None
            self._dead = True
            return "Error: pi session ended."
        try:
            result = await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.CancelledError:
            # Barge-in: cancel the run, keep the session for the next turn.
            # Clean up THIS request's bookkeeping so the aborted run's trailing
            # agent_settled is not attributed to the next prompt (which would
            # resolve it with empty text).
            self._pending.pop(rid, None)
            self._final_text.pop(rid, None)
            self._current_req = None
            await self._abort_quiet()
            raise
        except asyncio.TimeoutError:
            self._pending.pop(rid, None)
            self._current_req = None
            await self._abort_quiet()
            return f"Error: delegate_pi timed out after {int(timeout)}s."
        finally:
            self._final_text.pop(rid, None)
        result = str(result or "").strip()
        if not result:
            return "COMPLETED (no output)"
        if len(result) > PI_RESULT_MAX_CHARS:
            result = result[:PI_RESULT_MAX_CHARS] + "…"
        return result

    async def steer(self, message: str) -> str:
        """Queue a redirect to the running agent (RPC steer)."""
        if self._dead or self._proc is None:
            return "Error: no active pi session to steer."
        try:
            await self._send({"id": f"steer-{self._req_id + 1}", "type": "steer", "message": message})
            return f"Steered: {message}"
        except RuntimeError as e:
            return f"Error: {e}"

    async def abort(self) -> str:
        """Cancel the current run; session stays alive."""
        try:
            await self._send({"id": f"abort-{self._req_id + 1}", "type": "abort"})
            return "ABORTED"
        except RuntimeError as e:
            return f"Error: {e}"

    async def _abort_quiet(self):
        """Fire-and-forget abort (no response wait) — used on barge-in where
        the caller is already unwinding. Never raises."""
        try:
            if self._dead or self._proc is None or self._proc.stdin is None:
                return
            self._proc.stdin.write((json.dumps({"type": "abort"}) + "\n").encode())
            await self._proc.stdin.drain()
        except Exception:
            pass
