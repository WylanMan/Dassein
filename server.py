import json
import os
import mimetypes
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import urlparse

class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

def _load_dotenv(path):
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, _, val = line.partition('=')
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key not in os.environ:
                    os.environ[key] = val
    except FileNotFoundError:
        pass

_load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

ROOT = os.path.dirname(os.path.abspath(__file__))


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def _headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "credentialless")

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/health":
            self._json(200, {"status": "ok", "agent": "live"})
            return
        if path == "/" or path == "":
            path = "/index.html"
        if not os.path.isfile(os.path.join(ROOT, path.lstrip("/"))) and "." not in path.split("/")[-1]:
            path += ".html"
        filepath = os.path.join(ROOT, path.lstrip("/"))
        if not os.path.isfile(filepath):
            self.send_error(404)
            return
        mime, _ = mimetypes.guess_type(filepath)
        self.send_response(200)
        self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Content-Length", str(os.path.getsize(filepath)))
        self._headers()
        self.end_headers()
        with open(filepath, "rb") as f:
            self.wfile.write(f.read())

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/realtime/session":
            self._handle_realtime_session()
        elif path == "/api/health":
            self._json(200, {"status": "ok", "agent": "live"})
        else:
            self._json(404, {"error": "not found"})

    def _handle_realtime_session(self):
        """Mint a short-lived ephemeral token for the browser's Realtime WebRTC
        connection. The master API key never leaves the server."""
        openai_key = os.environ.get("OPENAI_API_KEY", "")
        if not openai_key:
            self._json(503, {"error": "OpenAI API key not configured"})
            return
        try:
            import requests as _requests
            r = _requests.post(
                "https://api.openai.com/v1/realtime/client_secrets",
                json={
                    "session": {
                        "type": "realtime",
                        "model": "gpt-realtime-mini",
                        "audio": {"output": {"voice": "shimmer"}},
                    }
                },
                headers={"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"},
                timeout=10,
            )
        except Exception as e:
            self._json(502, {"error": f"Session creation failed: {e}"})
            return
        if r.status_code != 200:
            self._json(502, {"error": f"Realtime session endpoint error ({r.status_code})"})
            return
        data = r.json()
        token = data.get("value") or data.get("client_secret", {}).get("value", "")
        if not token:
            self._json(502, {"error": "Realtime session response missing token"})
            return
        self._json(200, {"token": token, "expires_at": data.get("expires_at")})

    def do_OPTIONS(self):
        self.send_response(204)
        self._headers()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _json(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._headers()
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    port = 3000
    print(f"Serving on http://localhost:{port}")
    ThreadingHTTPServer(("", port), Handler).serve_forever()
