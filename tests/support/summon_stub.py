"""Local DeepSeek stub for tests (F3). Mirrors the OpenAI-compatible
/chat/completions contract so api/summon.py can be pointed at it via
DEEPSEEK_BASE_URL. Behavior is keyed off the concept in the last user message:

- "bad_spec"    -> always invalid (exercises the 422 abstractify path)
- "retry_spec"  -> invalid on first call, valid on the fix-prompt retry
- "slow_reliquary" -> sleeps, then returns a valid v2 spec (face-as-loading)
- anything else -> a valid grammar-v2 spec whose id is the concept slug
"""

import json
import re
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

# A valid grammar-v2 SDF root. Small and angular — the house idiom.
VALID_ROOT = {"op": "gem", "r": 1}
BAD_ROOT = {"op": "flux-capacitor"}


def v2_spec(spec_id, root):
    return {"id": spec_id, "schema": 2, "size": "medium", "root": root}


class StubHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        if self.path.startswith("/__calls"):
            payload = json.dumps({"count": StubServer.calls}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    def do_POST(self):
        StubServer.calls += 1
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        concept = "unknown"
        is_retry = False
        for m in (body.get("messages") or []):
            content = m.get("content", "")
            if m.get("role") == "user":
                match = re.search(r'Generate the spec for: "([^"]+)"', content)
                if match:
                    concept = match.group(1)
                if "previous output failed validation" in content:
                    is_retry = True

        if concept == "bad_spec":
            spec = v2_spec("bad", BAD_ROOT)
        elif concept == "retry_spec":
            spec = (v2_spec("bad", BAD_ROOT) if not is_retry
                    else v2_spec("retry_fixed", VALID_ROOT))
        elif concept == "slow_reliquary":
            # Slow response (Phase 0): lets the client's face-as-loading
            # contemplation state be observed before the spec lands.
            time.sleep(2.5)
            spec = v2_spec("slow_reliquary", VALID_ROOT)
        else:
            slug = re.sub(r"[^a-z0-9]+", "_", concept.lower()).strip("_") or "thing"
            spec = v2_spec(slug, VALID_ROOT)

        payload = json.dumps({"choices": [{"message": {"content": json.dumps(spec)}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        pass


class StubServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    calls = 0
