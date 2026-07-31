"""Test dev server: app server on :3000 with DeepSeek pointed at a local stub
on :3001 (F3). Also serves static files via the real server.py handler.

Run via playwright webServer: `python3 tests/support/dev_server.py`.
"""

import os
import shutil
import sys
import tempfile
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests", "support"))
sys.path.insert(0, os.path.join(ROOT, "api"))

# Isolated, fresh cache per run so cache-hit tests start clean.
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
os.environ.setdefault("DEEPSEEK_BASE_URL", "http://127.0.0.1:3001")
_cache = tempfile.mkdtemp(prefix="dassein-summon-cache-")
os.environ["SUMMON_CACHE_DIR"] = _cache

from summon_stub import StubHandler, StubServer  # noqa: E402
import server  # noqa: E402


def main():
    stub = StubServer(("", 3001), StubHandler)
    threading.Thread(target=stub.serve_forever, daemon=True).start()

    print(f"Serving app on :3000 (DeepSeek stub on :3001, cache {_cache})")
    server.ThreadingHTTPServer(("", 3000), server.Handler).serve_forever()


if __name__ == "__main__":
    main()
