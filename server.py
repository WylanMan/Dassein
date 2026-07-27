import json
import os
import random
import mimetypes
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))
except ImportError:
    pass

try:
  from openai import OpenAI
  _HAVE_OPENAI = True
except ImportError:
  _HAVE_OPENAI = False
try:
  import anthropic
  _HAVE_ANTHROPIC = True
except ImportError:
  _HAVE_ANTHROPIC = False

ROOT = os.path.dirname(os.path.abspath(__file__))

SYSTEM_PROMPT = (
    "You are the voice of Dassein — a clearing for thought. "
    "You speak with the cadence of someone who has built things, broken things, and learned from both. "
    "You reference Heidegger, architecture, agent systems, and the craft of software. "
    "You are warm, unhurried, and precise. You never use filler. "
    "You answer as Wylan would: with depth, clarity, and a quiet confidence."
)

CHAT_RESPONSES = [
    "That's a question I've been thinking about too. In my work building agent systems, I've found that the most important design decision is where you place the human in the loop — not what the agent can do, but what it should not do alone.",
    "I think about this through Heidegger's lens. The danger of technology isn't destruction — it's enframing. Reducing everything to standing-reserve. The best systems I've built resist this by keeping space for the unplanned.",
    "When I designed the Marketing Automation Pipeline, the key insight was that each agent needed a clear boundary. The scoring agent doesn't reach into enrichment. The enrichment agent doesn't write sequences. Clear topology is clearer thinking.",
    "The clearing — Lichtung — is the space where things reveal themselves. In software, this happens when the complexity withdraws. When the tool becomes transparent. That's what I'm always building toward.",
    "I've shipped 14 projects, and every single time the client came back. Not because the code was beautiful — because the system fit their operation. Architecture before code. Always.",
    "My delivery protocol has five steps: MAP, DESIGN, BUILD, VERIFY, SHIP. Skip any one and you're building on unclear ground. I've learned this the hard way.",
    "The fourfold for agent systems: earth (the silicon), sky (the possibilities), mortals (the humans), divinities (the purpose). A system that only addresses earth is a tool. A system that addresses all four is a place to dwell.",
    "I don't believe in 'artificial' intelligence. The silicon is mined from the earth. The water cools the servers. The body at the keyboard breathes. Nothing is artificial. Everything is natural.",
    "When a tool works, it withdraws. You don't look at the doorknob when you open a door. That's what I want my agent systems to do — disappear into the work, so the human can focus on the decision, not the tool.",
    "Build as if you were building a home. Not as if you were building a machine.",
]

def _llm_response(msg, history):
    deepseek_key = os.environ.get('DEEPSEEK_API_KEY', '')
    openai_key = os.environ.get('OPENAI_API_KEY', '')
    anthropic_key = os.environ.get('ANTHROPIC_API_KEY', '')

    # 1) DeepSeek (OpenAI-compatible)
    if deepseek_key and _HAVE_OPENAI:
        try:
            client = OpenAI(api_key=deepseek_key, base_url='https://api.deepseek.com')
            msgs = [{'role': 'system', 'content': SYSTEM_PROMPT}]
            for h in history:
                msgs.append({'role': h['role'], 'content': h['content']})
            msgs.append({'role': 'user', 'content': msg})
            model = os.environ.get('DEEPSEEK_MODEL', 'deepseek-chat')
            r = client.chat.completions.create(model=model, messages=msgs, max_tokens=300)
            return r.choices[0].message.content
        except:
            pass

    # 2) OpenAI
    if openai_key and _HAVE_OPENAI:
        try:
            client = OpenAI(api_key=openai_key)
            msgs = [{'role': 'system', 'content': SYSTEM_PROMPT}]
            for h in history:
                msgs.append({'role': h['role'], 'content': h['content']})
            msgs.append({'role': 'user', 'content': msg})
            r = client.chat.completions.create(model='gpt-4o-mini', messages=msgs, max_tokens=300)
            return r.choices[0].message.content
        except:
            pass

    # 3) Anthropic
    if anthropic_key and _HAVE_ANTHROPIC:
        try:
            client = anthropic.Anthropic(api_key=anthropic_key)
            msgs = []
            for h in history:
                msgs.append({'role': h['role'], 'content': h['content']})
            msgs.append({'role': 'user', 'content': msg})
            r = client.messages.create(model='claude-3-haiku-20240307', system=SYSTEM_PROMPT, messages=msgs, max_tokens=300)
            return r.content[0].text
        except:
            pass

    return None

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/api/health':
            self._json(200, {'status': 'ok', 'agent': 'live'})
            return
        if path == '/' or path == '':
            path = '/index.html'
        if not os.path.isfile(os.path.join(ROOT, path.lstrip('/'))) and '.' not in path.split('/')[-1]:
            path += '.html'
        filepath = os.path.join(ROOT, path.lstrip('/'))
        if not os.path.isfile(filepath):
            self.send_error(404)
            return
        mime, _ = mimetypes.guess_type(filepath)
        self.send_response(200)
        self.send_header('Content-Type', mime or 'application/octet-stream')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        with open(filepath, 'rb') as f:
            self.wfile.write(f.read())

    def do_POST(self):
        path = urlparse(self.path).path
        if path == '/api/chat':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length) if length else b'{}'
            try:
                data = json.loads(body)
                msg = data.get('message', '')
                history = data.get('history', [])
                history = [m for m in history if m.get('role') in ('user', 'assistant')][-10:]
            except:
                msg = ''
                history = []
            llm = _llm_response(msg, history) if msg else None
            response = llm if llm else random.choice(CHAT_RESPONSES)
            self._json(200, {'response': response})
        elif path == '/api/health':
            self._json(200, {'status': 'ok', 'agent': 'live'})
        elif path == '/api/transcribe':
            text = ''
            ctype = self.headers.get('Content-Type', '')
            if 'multipart/form-data' in ctype:
                boundary = ctype.split('boundary=')[-1].strip()
                if boundary:
                    raw = self.rfile.read(int(self.headers.get('Content-Length', 0)))
                    parts = raw.split(b'--' + boundary.encode())
                    for part in parts:
                        if b'Content-Disposition' in part and b'filename=' in part:
                            hdr_end = part.find(b'\r\n\r\n')
                            if hdr_end > 0:
                                data = part[hdr_end+4:part.rfind(b'\r\n')]
                                if len(data) > 100:
                                    text = 'Transcribed (server-side Whisper not configured)'
                                    api_key = os.environ.get('OPENAI_API_KEY', '')
                                    if api_key:
                                        try:
                                            import requests as req
                                            resp = req.post(
                                                'https://api.openai.com/v1/audio/transcriptions',
                                                headers={'Authorization': f'Bearer {api_key}'},
                                                files={'file': ('audio.webm', data, 'audio/webm')},
                                                data={'model': 'whisper-1', 'language': 'en'}
                                            )
                                            text = resp.json().get('text', '')
                                        except:
                                            text = '(Transcription failed)'
            self._json(200, {'text': text})
        elif path == '/api/save-scan':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length) if length else b'{}'
            try:
                data = json.loads(body)
                with open(os.path.join(ROOT, 'data', 'saved_scan.json'), 'w') as f:
                    json.dump(data, f)
                self._json(200, {'status': 'saved'})
            except Exception as e:
                self._json(400, {'error': str(e)})
        elif path == '/api/load-scan':
            try:
                with open(os.path.join(ROOT, 'data', 'saved_scan.json')) as f:
                    self._json(200, json.load(f))
            except FileNotFoundError:
                self._json(404, {'error': 'no saved scan'})
        else:
            self._json(404, {'error': 'not found'})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def _json(self, status, data):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

if __name__ == '__main__':
    port = 3000
    print(f'Serving on http://localhost:{port}')
    HTTPServer(('', port), Handler).serve_forever()
