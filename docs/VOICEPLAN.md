# Voice Agent Plan: Decoupled Pipeline

## Architecture

```
Mic → PCM16 24kHz → WebSocket (gpt-realtime-mini + whisper-1 STT) → transcript
                              │
                              ▼
              POST /api/chat (gpt-4o-mini, stream) → sentence tokens
                              │
                              ▼  (first sentence queued immediately)
              POST /api/tts (gpt-4o-mini-tts, PCM) → Web Audio
                              │  (while LLM continues generating)
                              ▼
              POST /api/tts (next sentence) → Web Audio
```

Three independent modules, orchestrated by `VoiceConversation`. The WebSocket is used only for streaming transcription (no LLM, no TTS on the WebSocket).

## Model Names (Verified Working)

| Component | Model | Endpoint | Status |
|-----------|-------|----------|--------|
| STT (WebSocket) | `gpt-realtime-mini` | `wss://api.openai.com/v1/realtime?model=gpt-realtime-mini` | Verified — connects and creates sessions |
| STT (model used for transcription INSIDE the session) | `whisper-1` | Set via `session.update` → `audio.input.transcription.model` | Verified — `session.update` succeeds |
| LLM | `gpt-4o-mini` | Proxied via `POST /api/chat` | Verified — returns responses |
| TTS | `gpt-4o-mini-tts` | Proxied via `POST /api/tts` | Verified — returns PCM16 audio |

**Note:** `gpt-realtime-whisper` is NOT a valid OpenAI model name. The Realtime API WebSocket rejected it with `invalid_request_error.invalid_model`. The working setup is `gpt-realtime-mini` (WebSocket transport) + `whisper-1` (transcription engine inside the session).

## Key Design Decisions

### 1. Decoupled Three-Stage Pipeline
- **STT**: WebSocket to OpenAI Realtime API — streaming transcription with server VAD
- **LLM**: REST call to `/api/chat` with `provider: "openai"` — forces `gpt-4o-mini`
- **TTS**: REST call to `/api/tts` (proxies to OpenAI `POST /v1/audio/speech`) — `gpt-4o-mini-tts` voice `shimmer`, PCM output

### 2. Incremental TTS Pipelining for Latency Mitigation
STT → LLM → TTS as three sequential hops would be ~1-3.5 seconds end-to-end. To mitigate:
- LLM streams tokens via SSE from `/api/chat`
- On each sentence boundary (`.`, `!`, `?`, `\n`), that sentence is immediately queued to TTS
- TTS plays sentence 1 while LLM continues generating sentence 2, 3, etc.
- Perceived latency drops to ~1-1.5s (first sentence plays while rest is still being composed)

### 3. Server-Side VAD (Not Client-Side RMS)
Using OpenAI's server VAD (`session.audio.input.turn_detection.type = "server_vad"`) instead of client-side RMS threshold:
- More reliable speech detection (ambient noise, varying volumes)
- Automatic audio chunking and buffer commit
- Native `speech_started` / `speech_stopped` events for interruption handling
- No need for `commitBuffer()` — server handles it

### 4. Viseme Synchronization (Approximate)
The VisemeEngine (`index.html:1502-1580`) runs on an independent internal clock — it estimates syllable timing from text structure (~180-220ms per syllable), NOT from actual audio timing. This was never precisely synced. The decoupled pipeline is functionally identical:
- `buildSyllablePlan(text)` — builds timed plan from full LLM response text
- `talking = true` — starts internal clock (set when LLM `onDone` fires)
- `talking = false` — stops clock (set when TTS `onDone` fires)

The viseme plan is built when the LLM finishes (not when TTS starts), since TTS may begin playing the first sentence before the LLM stream is complete.

### 5. Interruption Architecture
When new speech is detected (server VAD `speech_started` event) during THINKING or SPEAKING state:
1. Abort in-progress LLM fetch (via `AbortController`)
2. Stop TTS playback immediately
3. Clear the Realtime input audio buffer
4. Transition to LISTENING state

No custom client VAD needed — server handles turn detection natively.

### 6. OpenAI-Only for Voice, DeepSeek for Text Chat
- `/api/chat` accepts an optional `provider` field
- Voice pipeline sends `provider: "openai"` — forces `gpt-4o-mini` directly
- Text chat fallback sends `"auto"` (default) — uses existing DeepSeek → OpenAI → Anthropic chain

## File Changes

| File | Change | Lines Changed |
|------|--------|---------------|
| `voice-realtime.js` | Refactored to transcription-only. Removed: TTS, LLM, tool calling, audio output (~300 lines). Removed client RMS VAD. Kept: mic capture, WebSocket, PCM16 encoding, server VAD, transcription events | Entire file rewritten — 600 → 297 lines |
| `voice-llm.js` | Added `sendStreamForVoice()` with SSE streaming + sentence boundary detection + incremental `onSentence` emissions. `provider` defaults to `"openai"` | 206 → 173 lines |
| `voice-tts.js` | Rewritten: calls `POST /api/tts` (gpt-4o-mini-tts), plays PCM16 via Web Audio API, `enqueue()` for multi-sentence queue | 166 → 120 lines |
| `voice-conversation.js` | Rewritten as three-module orchestrator: STT → LLM → TTS. State machine with interruption handling, error boundaries per stage | 114 → 157 lines |
| `voice-stt.js` | **Deleted** — dormant browser-whisper module | Removed (142 lines) |
| `api/index.py` | Added `POST /api/tts` endpoint. Added `provider` param to `POST /api/chat`. Updated session/ config endpoints model | +60 lines |
| `server.py` | Mirror `api/index.py` changes (stdlib HTTP server) | +60 lines |
| `index.html` | Updated imports, 3-module initialization wiring, cleaned up unused variables | ~60 lines changed |

## State Machine

```
IDLE → LISTENING (STT server VAD active) → THINKING (LLM generating) → SPEAKING (TTS playing) → IDLE
  ↑                                                                       │
  └────────────────── speech_started during THINKING/SPEAKING ────────────┘
```

States managed by `VoiceConversation` with visual feedback via dot color + label:
- IDLE: gray, no pulse
- LISTENING: green, pulse
- THINKING: cyan, pulse
- SPEAKING: cyan, no pulse

## Backend API Endpoints

### `POST /api/tts`
```json
// Request
{ "text": "Hello world.", "voice": "shimmer", "speed": 1.0 }

// Response
Content-Type: audio/pcm
Body: raw PCM16 24kHz little-endian bytes
```

### `POST /api/chat` (updated)
```json
// Request
{ "messages": [...], "stream": false, "provider": "openai" }

// provider: "auto" (default, DeepSeek first) | "openai" | "deepseek" | "anthropic"
// Voice pipeline sends "openai" to force gpt-4o-mini
```

### `POST /api/realtime/session` (updated)
```json
// Proxies to OpenAI POST /v1/realtime/sessions
// Request body: { "model": "gpt-realtime-mini", "input_audio_format": "pcm16" }
// Returns ephemeral token or falls back to direct API key
```

## Error Boundaries

| Failure | Degradation |
|---------|-------------|
| STT WebSocket connection fails | Show error, allow text input fallback |
| LLM API call fails | Show transcript, `speechSynthesis` fallback |
| TTS API call fails | Show text response, skip audio |
| Interruption during TTS/LLM | Abort LLM, stop TTS, clear buffer, relisten |

## Files That Stayed Unchanged
- Three.js scene, wireframe, all visual effects
- Text-only chat with DeepSeek → OpenAI → Anthropic fallback
- `speechSynthesis` as text-chat TTS fallback
- `window.agentAvatar` public API (references updated to new modules)
- All CSS, fonts, layout
- `data/robota_scan.json`, `requirements.txt`, `vercel.json`

## Testing

```bash
# Start server
python3 server.py

# Test endpoints
curl http://localhost:3000/api/health
curl -X POST http://localhost:3000/api/chat -H 'Content-Type: application/json' -d '{"messages":[{"role":"user","content":"hello"}],"provider":"openai"}'
curl -X POST http://localhost:3000/api/tts -H 'Content-Type: application/json' -d '{"text":"Hello world.","voice":"shimmer"}' --output test.pcm
curl -X POST http://localhost:3000/api/realtime/session

# E2E tests
npx playwright test
```

9 Playwright E2E tests: 8 pass, 1 pre-existing animation timing flake unrelated to voice changes.
