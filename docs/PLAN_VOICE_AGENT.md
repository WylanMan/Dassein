# Voice Agent Improvements — Implementation Plan

## Overview

6 improvements to the Dassein voice agent, ordered by value-to-effort ratio. Total: ~90 lines across 5 files.

| # | Improvement | Files | Lines | Effort |
|---|---|---|---|---|
| 1 | Streaming LLM responses | `api/index.py`, `server.py`, `index.html` | 45 | Medium |
| 2 | Cancel previous speech + abort fetch | `index.html` | 8 | Low |
| 3 | Persist chat history to localStorage | `index.html` | 10 | Low |
| 4 | Multi-message conversation UI | `index.html` | 25 | Low |
| 5 | Blend analyser RMS into viseme intensity | `index.html` | 8 | Low |
| 6 | Guard transcription placeholder | `index.html` | 5 | Low |

---

## 1. Streaming LLM Responses

**Problem:** `ask()` does `await fetch('/api/chat')` — blocks 2-5 seconds with frozen UI ("..."), then the full response blinks in at once. The agent looks dead while "thinking."

**Solution:** Backend yields SSE chunks. Frontend reads the stream and appends tokens as they arrive. Viseme engine starts animating partial text.

### 1a. Backend: `api/index.py` — new streaming endpoint

Add alongside `/_chat` at line 119. Keep the existing non-streaming endpoint for backward compatibility. The streaming endpoint returns `text/event-stream`.

```python
# Add import at top of file (line 6 area):
from fastapi.responses import StreamingResponse

# Add after health endpoint (line 117), before existing /api/chat:
@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    history = [m for m in req.history if m.get("role") in ("user", "assistant")][-10:]

    deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "")
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    llm_provider = os.environ.get("LLM_PROVIDER", "deepseek")

    async def generate():
        try:
            # DeepSeek streaming
            if deepseek_key and _HAVE_OPENAI:
                client = OpenAI(api_key=deepseek_key, base_url="https://api.deepseek.com")
                msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
                for h in history:
                    msgs.append({"role": h.get("role", "user"), "content": h.get("content", "")})
                msgs.append({"role": "user", "content": req.message})
                model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
                stream = client.chat.completions.create(model=model, messages=msgs, max_tokens=300, stream=True)
                for chunk in stream:
                    if chunk.choices[0].delta.content:
                        yield f"data: {json.dumps({'token': chunk.choices[0].delta.content})}\n\n"
                yield "data: [DONE]\n\n"
                return

            # OpenAI streaming
            if openai_key and _HAVE_OPENAI:
                client = OpenAI(api_key=openai_key)
                msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
                for h in history:
                    msgs.append({"role": h.get("role", "user"), "content": h.get("content", "")})
                msgs.append({"role": "user", "content": req.message})
                model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
                stream = client.chat.completions.create(model=model, messages=msgs, max_tokens=300, stream=True)
                for chunk in stream:
                    if chunk.choices[0].delta.content:
                        yield f"data: {json.dumps({'token': chunk.choices[0].delta.content})}\n\n"
                yield "data: [DONE]\n\n"
                return

            # Anthropic streaming
            if anthropic_key and _HAVE_ANTHROPIC:
                client = anthropic.Anthropic(api_key=anthropic_key)
                msgs = []
                for h in history:
                    msgs.append({"role": h.get("role", "user"), "content": h.get("content", "")})
                msgs.append({"role": "user", "content": req.message})
                model = os.environ.get("ANTHROPIC_MODEL", "claude-3-haiku-20240307")
                with client.messages.stream(model=model, system=SYSTEM_PROMPT, messages=msgs, max_tokens=300) as stream:
                    for text in stream.text_stream:
                        yield f"data: {json.dumps({'token': text})}\n\n"
                yield "data: [DONE]\n\n"
                return

            # Fallback: send full response as single chunk
            fallback = random.choice(CHAT_RESPONSES)
            yield f"data: {json.dumps({'token': fallback})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception:
            fallback = random.choice(CHAT_RESPONSES)
            yield f"data: {json.dumps({'token': fallback})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

### 1b. Backend: `server.py` — streaming for local dev

Add a streaming chat handler at line ~120 (inside `do_POST`, after the existing `/api/chat` handler):

```python
def _chat_stream_handler(self):
    """SSE streaming chat for local dev."""
    length = int(self.headers.get('Content-Length', 0))
    body = json.loads(self.rfile.read(length)) if length else {}
    msg = body.get('message', '')
    history = [h for h in body.get('history', []) if h.get('role') in ('user', 'assistant')][-10:]

    self.send_response(200)
    self.send_header('Content-Type', 'text/event-stream')
    self.send_header('Cache-Control', 'no-cache')
    self.send_header('Connection', 'keep-alive')
    self.end_headers()

    deepseek_key = os.environ.get('DEEPSEEK_API_KEY', '')
    openai_key = os.environ.get('OPENAI_API_KEY', '')
    anthropic_key = os.environ.get('ANTHROPIC_API_KEY', '')

    try:
        if deepseek_key and _HAVE_OPENAI:
            client = OpenAI(api_key=deepseek_key, base_url='https://api.deepseek.com')
            msgs = [{'role': 'system', 'content': SYSTEM_PROMPT}]
            for h in history:
                msgs.append({'role': h['role'], 'content': h['content']})
            msgs.append({'role': 'user', 'content': msg})
            model = os.environ.get('DEEPSEEK_MODEL', 'deepseek-chat')
            stream = client.chat.completions.create(model=model, messages=msgs, max_tokens=300, stream=True)
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    self.wfile.write(f"data: {json.dumps({'token': chunk.choices[0].delta.content})}\n\n".encode())
                    self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")
            return

        # Fallback: send full response as single token
        llm = _llm_response(msg, history)
        reply = llm if llm else random.choice(CHAT_RESPONSES)
        self.wfile.write(f"data: {json.dumps({'token': reply})}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")
    except Exception:
        self.wfile.write(f"data: {json.dumps({'token': random.choice(CHAT_RESPONSES)})}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")
```

Wire it in `do_POST` by adding before the existing `/api/chat` handler:

```python
if path == '/api/chat/stream':
    self._chat_stream_handler()
    return
```

### 1c. Frontend: `index.html` — replace `ask()` with streaming

Replace lines 1369-1387 (`let chatHistory`, `ask function`) with:

```js
let chatHistory = JSON.parse(localStorage.getItem('dassein_history') || '[]');
let abortController = null;

function addMessage(role, text) {
  const div = document.createElement('div');
  div.className = 'msg-line ' + role;
  div.textContent = text;
  convoEl.appendChild(div);
  convoEl.scrollTop = convoEl.scrollHeight;
}

async function ask(text) {
  if (!text.trim()) return;
  speechSynthesis.cancel();
  VisemeEngine.talking = false;
  if (abortController) abortController.abort();
  abortController = new AbortController();

  unlockSpeech();
  addMessage('user', text);

  const replyDiv = document.createElement('div');
  replyDiv.className = 'msg-line assistant streaming';
  convoEl.appendChild(replyDiv);
  let fullReply = '';

  try {
    const r = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, history: chatHistory.slice(-10) }),
      signal: abortController.signal,
    });

    const reader = r.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let startedSpeaking = false;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const data = line.slice(6);
        if (data === '[DONE]') continue;
        try {
          const { token } = JSON.parse(data);
          fullReply += token;
          replyDiv.textContent = fullReply;
          convoEl.scrollTop = convoEl.scrollHeight;

          if (!startedSpeaking && fullReply.length > 20) {
            startedSpeaking = true;
            VisemeEngine.buildSyllablePlan(fullReply);
            VisemeEngine.talking = true;
            say(fullReply).then(() => { replyDiv.classList.remove('streaming'); });
          }
        } catch {}
      }
    }

    if (!startedSpeaking && fullReply) {
      VisemeEngine.buildSyllablePlan(fullReply);
      VisemeEngine.talking = true;
      await say(fullReply);
    }

    replyDiv.classList.remove('streaming');
    chatHistory.push({ role: 'user', content: text }, { role: 'assistant', content: fullReply });
    localStorage.setItem('dassein_history', JSON.stringify(chatHistory.slice(-50)));
  } catch (err) {
    if (err.name === 'AbortError') return;
    replyDiv.textContent = 'Could not reach the agent. Is the server running?';
    replyDiv.classList.remove('streaming');
  } finally {
    abortController = null;
  }
}

// Restore history UI on load
document.addEventListener('DOMContentLoaded', () => {
  chatHistory = JSON.parse(localStorage.getItem('dassein_history') || '[]');
  for (const m of chatHistory.slice(-20)) {
    addMessage(m.role, m.content);
  }
});
```

### 1d. CSS additions for message bubbles

Add after `.convo` block (line 88):

```css
.convo {
  min-height: 20px; max-width: 480px; text-align: center;
  font-size: 14px; color: #9a97a3; line-height: 1.5;
  max-height: 36vh; overflow-y: auto;
  display: flex; flex-direction: column; gap: 8px;
  padding: 0 16px;
}
.msg-line {
  max-width: 85%; padding: 8px 14px; border-radius: 16px;
  font-size: 13px; line-height: 1.45; word-break: break-word;
}
.msg-line.user {
  align-self: flex-end;
  background: rgba(0, 212, 255, 0.08); color: #b9b6c2;
  border: 1px solid rgba(0, 212, 255, 0.12);
}
.msg-line.assistant {
  align-self: flex-start;
  background: rgba(255, 255, 255, 0.03); color: #b9b6c2;
  border: 1px solid rgba(255, 255, 255, 0.05);
}
.msg-line.streaming::after {
  content: '|'; animation: blink-cursor 0.7s infinite;
  color: #00d4ff; font-weight: bold;
}
@keyframes blink-cursor {
  50% { opacity: 0; }
}
```

---

## 2. Cancel Previous Speech + Abort Fetch

**Problem:** Sending a new message while the agent is speaking causes two overlapping TTS voices. No abort on the pending fetch.

**Solution:** Already covered by #1 — `speechSynthesis.cancel()` at top of new `ask()`, `AbortController` on fetch. Confirming these are the only changes needed:

```js
// Inside ask(), before anything:
speechSynthesis.cancel();
VisemeEngine.talking = false;
if (abortController) abortController.abort();
abortController = new AbortController();
```

---

## 3. Persist Chat History to localStorage

**Problem:** Page refresh = complete amnesia. The agent loses all conversation context.

**Solution:** Already integrated into #1 — load from localStorage at init, save on each exchange. Confirming the lines in `ask()`:

```js
// Top of file (init):
let chatHistory = JSON.parse(localStorage.getItem('dassein_history') || '[]');

// After each assistant reply (inside ask):
localStorage.setItem('dassein_history', JSON.stringify(chatHistory.slice(-50)));

// On load, restore UI:
document.addEventListener('DOMContentLoaded', () => {
  chatHistory = JSON.parse(localStorage.getItem('dassein_history') || '[]');
  for (const m of chatHistory.slice(-20)) {
    addMessage(m.role, m.content);
  }
});
```

---

## 4. Multi-Message Conversation UI

**Problem:** `convoEl.textContent = reply` shows only one message. Previous exchanges disappear.

**Solution:** Already implemented in #1 via `addMessage()` helper and `.msg-line` divs. The UI now shows scrollable chat bubbles accumulating. Confirming the helpers:

```js
function addMessage(role, text) {
  const div = document.createElement('div');
  div.className = 'msg-line ' + role;
  div.textContent = text;
  convoEl.appendChild(div);
  convoEl.scrollTop = convoEl.scrollHeight;
}
```

Added CSS from #1d completes the visual styling.

---

## 5. Blend Analyser RMS into Viseme Intensity

**Problem:** Viseme plan runs on fixed text-based clock with no feedback from actual audio. Mouth drifts out of sync with speech over long responses.

**Solution:** In `VisemeEngine.update()` (line 1191), blend the existing `analyser` RMS value into the jaw calculation. When audio is loud, jaw opens wider. When audio goes silent (speech ended but plan still has time), mouth closes naturally.

Add after line 1192 (`if (!this.talking || dt <= 0 || isNaN(dt)) return;`):

```js
// Blend live audio intensity into viseme — compensates for fixed-plan drift
let audioBoost = 0;
if (analyser) {
  const freqData = new Uint8Array(analyser.frequencyBinCount);
  analyser.getByteFrequencyData(freqData);
  let sum = 0;
  for (let i = 0; i < freqData.length; i++) sum += freqData[i];
  const avg = sum / freqData.length / 255;
  audioBoost = avg > 0.02 ? avg * 1.5 : 0;
}
```

Then modify line 1223 (where `jaw` is clamped):

```js
// Original:
jaw = Math.min(0.5, jaw * intensity);

// Replace with:
jaw = Math.min(0.5, jaw * intensity + audioBoost * 0.3);
```

And in `stop()` (line 1246), ensure smooth decay by not immediately zeroing the smoothed values — they'll decay naturally over a few frames because `audioBoost` drops to 0 when the analyser is disconnected.

---

## 6. Guard Transcription Placeholder

**Problem:** When `OPENAI_API_KEY` is unset, `/api/transcribe` returns `"Transcribed (server-side Whisper not configured)"`. This string gets fed to `ask()` and the agent philosophizes about a debug message.

**Solution:** In `conversationStep()` (line 1488), after line `const text = await transcribeRecording(blob);`:

```js
const text = await transcribeRecording(blob);
if (!text || text.startsWith('Transcribed') || text === '(Transcription failed)') {
  if (continuousMode && !contAbort) {
    setTimeout(() => conversationStep(), 300);
  } else {
    contLoopActive = false;
  }
  return;
}
```

Replace lines 1499-1508 (the block inside `if (text.trim())` through the end of the VAD callback) since we're now guarding before that check:

```js
chatInput.value = text;
await ask(text);
chatInput.value = '';
if (continuousMode && !contAbort) {
  setTimeout(() => conversationStep(), 300);
} else {
  contLoopActive = false;
}
```

---

## Verification Checklist

| # | Test | Expected |
|---|---|---|
| 1a | Send message via text input | Tokens appear character-by-character, cursor blinks, agent starts speaking after ~20 chars |
| 1b | Refresh page during response | Page reloads, no crash |
| 1c | Production: Vercel deploy with `DEEPSEEK_API_KEY` | Streaming works via serverless function |
| 2 | Send message while TTS is playing | Previous speech stops immediately, new response begins |
| 3a | Have a conversation, refresh page | Previous messages visible, agent remembers context |
| 3b | Open in new tab | Same history shows (shared localStorage) |
| 4 | Send 5 messages in a row | All 10 bubbles visible, scrollable, user right-aligned cyan, agent left-aligned dark |
| 5 | Listen to a long response | Mouth animation feels tighter to audio, no visible lag between audio end and mouth stop |
| 6 | Start continuous mode without OPENAI_API_KEY set | Agent doesn't say "Transcribed..." — mic stays active, waits for valid input |

---

## Files Changed

| File | Sections modified |
|---|---|
| `api/index.py` | Add `/api/chat/stream` endpoint, add `StreamingResponse` import |
| `server.py` | Add `/api/chat/stream` handler in `do_POST`, add `_chat_stream_handler` method |
| `index.html` | Replace `ask()` (lines 1369-1387) with streaming version, replace `chatHistory` init, add `addMessage()`, add CSS for `.msg-line`, modify `VisemeEngine.update()` (line 1192+), modify `conversationStep()` (line 1499+), add `DOMContentLoaded` history restore |
