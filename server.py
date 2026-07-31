import json
import os
import random
import mimetypes
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
from urllib.parse import urlparse

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

try:
  from openai import OpenAI
  _HAVE_OPENAI = True
except ImportError:
  _HAVE_OPENAI = False

ROOT = os.path.dirname(os.path.abspath(__file__))

SYSTEM_PROMPT = (
    "You are Dassein — a clearing for thought. "
    "Be concise. One to three sentences. Never filler. "
    "Answer as Wylan would: clear, warm, philosophical when it matters, direct when it doesn't.\n\n"
    "You have a switch_shape tool. Available shapes: face, sphere, cube, cylinder, pyramid, torus, model. "
    "Use it automatically when the user asks to see a different form. Do not describe using the tool — just use it, then respond briefly."
)

CHAT_RESPONSES = [
    "I'm having trouble reaching my thoughts right now. Could you check the API configuration or try again in a moment?",
]

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for current information",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "The search query"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_time",
            "description": "Get the current date and time",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather for a city",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string", "description": "City name"}},
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "switch_shape",
            "description": "Switch the 3D avatar shape on screen. Use this when the user asks to change the visual form. Available shapes: face (default talking face), sphere (wireframe icosahedron), cube, cylinder, pyramid, torus, model (3D duck).",
            "parameters": {
                "type": "object",
                "properties": {"shape": {"type": "string", "description": "The shape name to switch to", "enum": ["face", "sphere", "cube", "cylinder", "pyramid", "torus", "model"]}},
                "required": ["shape"],
            },
        },
    },
]


def _llm_call(messages, tools_enabled=False, stream=False, provider_override=None):
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "")
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    provider = provider_override or os.environ.get("LLM_PROVIDER", "deepseek")

    if not provider_override and deepseek_key and _HAVE_OPENAI and provider == "deepseek":
        try:
            client = OpenAI(api_key=deepseek_key, base_url="https://api.deepseek.com")
            model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
            kwargs = {
                "model": model,
                "messages": messages,
                "max_tokens": 256,
                "stream": stream,
            }
            if tools_enabled:
                kwargs["tools"] = TOOLS
            print(f"[server] Calling DeepSeek {model} stream={stream} tools={tools_enabled}")
            return client.chat.completions.create(**kwargs)
        except Exception as e:
            print(f"[server] DeepSeek error: {e}")

    if openai_key and _HAVE_OPENAI:
        try:
            client = OpenAI(api_key=openai_key)
            kwargs = {
                "model": "gpt-4o-mini",
                "messages": messages,
                "max_tokens": 256,
                "stream": stream,
            }
            if tools_enabled:
                kwargs["tools"] = TOOLS
            return client.chat.completions.create(**kwargs)
        except Exception as e:
            print(f"[server] OpenAI error: {e}")

    if anthropic_key:
        try:
            import anthropic as _anthropic
            client = _anthropic.Anthropic(api_key=anthropic_key)
            msgs = []
            system = None
            for m in messages:
                if m["role"] == "system":
                    system = m["content"]
                else:
                    msgs.append({"role": m["role"], "content": m["content"]})
            r = client.messages.create(
                model="claude-3-haiku-20240307",
                system=system or SYSTEM_PROMPT,
                messages=msgs,
                max_tokens=512,
            )
            if stream:
                class FakeStream:
                    def __iter__(self):
                        content = r.content[0].text if r.content else ""
                        chunk = type("Chunk", (), {
                            "choices": [type("Choice", (), {
                                "delta": type("Delta", (), {"content": content, "tool_calls": None})(),
                                "finish_reason": "stop",
                            })()]
                        })()
                        yield chunk
                    def __enter__(self): return self
                    def __exit__(self, *a): pass
                return FakeStream()
            return r
        except Exception as e:
            print(f"[server] Anthropic error: {e}")

    print("[server] No LLM provider available, using fallback")
    return None


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
        if path == "/api/chat":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b"{}"
            try:
                data = json.loads(body)
            except:
                data = {}
            stream = data.get("stream", False)
            tools_enabled = data.get("tools", False)
            messages = data.get("messages", [])
            max_tokens = data.get("max_tokens", 512)
            provider = data.get("provider", "auto")

            full_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            for m in messages:
                full_messages.append({"role": m.get("role", "user"), "content": m.get("content", "")})

            if stream:
                self._handle_stream(full_messages, tools_enabled, max_tokens, provider)
            else:
                self._handle_chat(full_messages, tools_enabled, max_tokens, provider)

        elif path == "/api/realtime/session":
            self._handle_realtime_session()
        elif path == "/api/health":
            self._json(200, {"status": "ok", "agent": "live"})
        elif path == "/api/save-scan":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b"{}"
            try:
                data = json.loads(body)
                with open(os.path.join(ROOT, "data", "saved_scan.json"), "w") as f:
                    json.dump(data, f)
                self._json(200, {"status": "saved"})
            except Exception as e:
                self._json(400, {"error": str(e)})
        elif path == "/api/load-scan":
            try:
                with open(os.path.join(ROOT, "data", "saved_scan.json")) as f:
                    self._json(200, json.load(f))
            except FileNotFoundError:
                self._json(404, {"error": "no saved scan"})
        else:
            self._json(404, {"error": "not found"})

    def _handle_chat(self, messages, tools_enabled, max_tokens, provider="auto"):
        provider_override = provider if provider != "auto" else None
        response = _llm_call(messages, tools_enabled, stream=False, provider_override=provider_override)
        if response is None:
            print("[server] Chat: no LLM response, using fallback")
            self._json(200, {"content": random.choice(CHAT_RESPONSES), "tool_calls": None})
            return

        try:
            choice = response.choices[0]
            msg = choice.message
            tool_calls = []
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_calls.append({
                        "id": tc.id,
                        "type": tc.type,
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    })
            self._json(200, {"content": msg.content or "", "tool_calls": tool_calls or None})
        except Exception as e:
            print(f"[server] Chat parse error: {e}")
            self._json(200, {"content": random.choice(CHAT_RESPONSES), "tool_calls": None})

    def _handle_realtime_session(self):
        """Mint a short-lived ephemeral token for the browser's Realtime WebRTC
        connection. The master API key never leaves the server."""
        openai_key = os.environ.get("OPENAI_API_KEY", "")
        if not openai_key or not _HAVE_OPENAI:
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

    def _handle_stream(self, messages, tools_enabled, max_tokens, provider="auto"):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self._headers()
        self.end_headers()

        provider_override = provider if provider != "auto" else None
        response = _llm_call(messages, tools_enabled, stream=True, provider_override=provider_override)
        if response is None:
            print("[server] Stream: no LLM response, using fallback")
            self._sse_send({"token": random.choice(CHAT_RESPONSES)})
            self._sse_done()
            self.close_connection = True
            return

        try:
            tool_calls_buffer = {}
            for chunk in response:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    self._sse_send({"token": delta.content})
                if delta and delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_buffer:
                            tool_calls_buffer[idx] = {"id": "", "type": "function", "function": {"name": "", "arguments": ""}}
                        if tc.id:
                            tool_calls_buffer[idx]["id"] += tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls_buffer[idx]["function"]["name"] += tc.function.name
                            if tc.function.arguments:
                                tool_calls_buffer[idx]["function"]["arguments"] += tc.function.arguments

            if tool_calls_buffer:
                self._sse_send({"tool_calls": list(tool_calls_buffer.values())})
            self._sse_done()
        except Exception as e:
            print(f"[server] Stream iteration error: {e}")
            self._sse_send({"token": random.choice(CHAT_RESPONSES)})
            self._sse_done()

        self.close_connection = True

    def _sse_send(self, data):
        try:
            self.wfile.write(f"data: {json.dumps(data)}\n\n".encode())
            self.wfile.flush()
        except BrokenPipeError:
            pass

    def _sse_done(self):
        try:
            self.wfile.write("data: [DONE]\n\n".encode())
            self.wfile.flush()
        except BrokenPipeError:
            pass

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
