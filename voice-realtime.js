// VoiceRealtime — full speech-to-speech client for the OpenAI Realtime API.
//
// One WebRTC peer connection carries mic audio up and model audio down.
// One "oai-events" data channel carries session config, transcripts, and
// tool calls. Turn-taking and barge-in are native (server VAD +
// interrupt_response), so there is no client-side orchestration to get wrong.

const REALTIME_CALLS_URL = 'https://api.openai.com/v1/realtime/calls';

const INSTRUCTIONS =
  'You are Dassein — a clearing for thought. Be concise. One to three sentences. Never filler. ' +
  'Answer as Wylan would: clear, warm, philosophical when it matters, direct when it doesn\'t.\n\n' +
  'You have a switch_shape tool. Available shapes: face, sphere, cube, cylinder, pyramid, torus, model. ' +
  'Use it automatically when the user asks to see a different form. Do not describe using the tool — just use it, then respond briefly.\n' +
  'You also have web_search, get_time, and get_weather tools. Use them when the user asks for current information, the time, or the weather.';

const TOOL_DEFS = [
  {
    type: 'function',
    name: 'web_search',
    description: 'Search the web for current information',
    parameters: {
      type: 'object',
      properties: { query: { type: 'string', description: 'The search query' } },
      required: ['query'],
    },
  },
  {
    type: 'function',
    name: 'get_time',
    description: 'Get the current date and time',
    parameters: { type: 'object', properties: {} },
  },
  {
    type: 'function',
    name: 'get_weather',
    description: 'Get current weather for a city',
    parameters: {
      type: 'object',
      properties: { city: { type: 'string', description: 'City name' } },
      required: ['city'],
    },
  },
  {
    type: 'function',
    name: 'switch_shape',
    description: 'Switch the 3D avatar shape on screen. Use this when the user asks to change the visual form. Available shapes: face (default talking face), sphere (wireframe icosahedron), cube, cylinder, pyramid, torus, model (3D duck).',
    parameters: {
      type: 'object',
      properties: { shape: { type: 'string', description: 'The shape name to switch to', enum: ['face', 'sphere', 'cube', 'cylinder', 'pyramid', 'torus', 'model'] } },
      required: ['shape'],
    },
  },
];

const LOCAL_TOOLS = {
  async web_search({ query }) {
    try {
      const r = await fetch(`https://api.duckduckgo.com/?q=${encodeURIComponent(query)}&format=json&no_html=1`);
      const data = await r.json();
      return data.AbstractText || data.RelatedTopics?.slice(0, 3).map(t => t.Text).join('\n') || `Searched for "${query}" but found no results.`;
    } catch {
      return 'Web search not available.';
    }
  },
  async get_time() {
    return new Date().toLocaleString('en-US', {
      weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
      hour: 'numeric', minute: 'numeric', timeZoneName: 'short',
    });
  },
  async get_weather({ city }) {
    try {
      const r = await fetch(`https://wttr.in/${encodeURIComponent(city)}?format=%C+%t+%w+%h`);
      if (r.ok) return `Weather in ${city}: ${await r.text()}`;
      return `Could not fetch weather for ${city}.`;
    } catch {
      return 'Weather lookup not available.';
    }
  },
};

export class VoiceRealtime {
  constructor(options = {}) {
    this.onStateChange = options.onStateChange || (() => {});
    this.onSpeechStart = options.onSpeechStart || (() => {});
    this.onSpeechEnd = options.onSpeechEnd || (() => {});
    this.onUserTranscript = options.onUserTranscript || (() => {});
    this.onAssistantDelta = options.onAssistantDelta || (() => {});
    this.onAssistantDone = options.onAssistantDone || (() => {});
    this.onAudioStart = options.onAudioStart || (() => {});
    this.onAudioEnd = options.onAudioEnd || (() => {});
    this.onToolCall = options.onToolCall || (() => {});
    this.onError = options.onError || (() => {});

    this.voice = options.voice || 'shimmer';
    this._tools = { ...LOCAL_TOOLS, ...(options.tools || {}) };

    this.pc = null;
    this.dc = null;
    this.micStream = null;
    this.audioEl = null;
    this.audioCtx = null;
    this.analyser = null;
    this._levelBuf = null;

    this.state = 'idle';
    this._speaking = false;
    this.destroyed = false;

    this._connectResolve = null;
    this._connectReject = null;
    this._connectTimeout = null;
  }

  async _fetchToken() {
    const r = await fetch('/api/realtime/session', { method: 'POST' });
    if (!r.ok) {
      const data = await r.json().catch(() => ({}));
      throw new Error(data.error || `Session token fetch failed: ${r.status}`);
    }
    const data = await r.json();
    if (!data.token) throw new Error('Session response did not include an ephemeral token');
    return data.token;
  }

  async connect() {
    if (this.pc && (this.pc.connectionState === 'connected' || this.pc.connectionState === 'connecting')) return;
    this._setState('connecting');

    const token = await this._fetchToken();

    return new Promise((resolve, reject) => {
      this._connectResolve = resolve;
      this._connectReject = reject;

      this._connectTimeout = setTimeout(() => {
        this._failConnect(new Error('Connection timed out after 10s'));
      }, 10000);

      (async () => {
        try {
          this.pc = new RTCPeerConnection();
          this.pc.ontrack = (e) => this._onRemoteTrack(e);
          this.pc.onconnectionstatechange = () => {
            if (this.pc && this.pc.connectionState === 'failed') {
              this._failConnect(new Error('WebRTC connection failed'));
              this.onError(new Error('WebRTC connection failed'));
            }
          };

          this.dc = this.pc.createDataChannel('oai-events');
          this.dc.onopen = () => this._sendSessionUpdate();
          this.dc.onmessage = (e) => this._onDataChannelMessage(e);

          this.micStream = await navigator.mediaDevices.getUserMedia({
            audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
          });
          for (const track of this.micStream.getAudioTracks()) {
            this.pc.addTrack(track, this.micStream);
          }

          const offer = await this.pc.createOffer();
          await this.pc.setLocalDescription(offer);

          // GA WebRTC signaling: multipart form carrying the SDP offer; the
          // ephemeral token binds the session config minted server-side.
          const form = new FormData();
          form.set('sdp', offer.sdp);
          const sdpResponse = await fetch(REALTIME_CALLS_URL, {
            method: 'POST',
            headers: { Authorization: `Bearer ${token}` },
            body: form,
          });

          if (!sdpResponse.ok) {
            throw new Error(`Realtime SDP exchange failed: ${sdpResponse.status}`);
          }

          const answerSdp = await sdpResponse.text();
          await this.pc.setRemoteDescription({ type: 'answer', sdp: answerSdp });
        } catch (err) {
          this._failConnect(err);
        }
      })();
    });
  }

  _failConnect(err) {
    const reject = this._connectReject;
    this._cleanupConnectPromise();
    this._teardownMedia();
    this._setState('idle');
    if (reject) reject(err);
  }

  _cleanupConnectPromise() {
    if (this._connectTimeout) { clearTimeout(this._connectTimeout); this._connectTimeout = null; }
    this._connectResolve = null;
    this._connectReject = null;
  }

  _sendSessionUpdate() {
    this._send({
      type: 'session.update',
      session: {
        type: 'realtime',
        instructions: INSTRUCTIONS,
        audio: {
          input: {
            turn_detection: {
              type: 'server_vad',
              threshold: 0.5,
              prefix_padding_ms: 300,
              silence_duration_ms: 500,
              create_response: true,
              interrupt_response: true,
            },
            transcription: { model: 'gpt-4o-mini-transcribe' },
          },
          output: { voice: this.voice },
        },
        tools: TOOL_DEFS,
      },
    });
  }

  _onDataChannelMessage(event) {
    let data;
    try { data = JSON.parse(event.data); } catch { return; }

    switch (data.type) {
      case 'session.updated':
        this._setState('idle');
        if (this._connectResolve) {
          const resolve = this._connectResolve;
          this._cleanupConnectPromise();
          resolve();
        }
        break;

      case 'input_audio_buffer.speech_started':
        this.onSpeechStart();
        break;

      case 'input_audio_buffer.speech_stopped':
        this.onSpeechEnd();
        break;

      case 'conversation.item.input_audio_transcription.completed':
        if (data.transcript && data.transcript.trim()) {
          this.onUserTranscript(data.transcript);
        }
        break;

      case 'response.output_audio_transcript.delta':
        if (data.delta) this.onAssistantDelta(data.delta);
        break;

      case 'response.output_audio_transcript.done':
        if (data.transcript) this.onAssistantDone(data.transcript);
        break;

      case 'output_audio_buffer.started':
        this._speaking = true;
        this.onAudioStart();
        break;

      case 'output_audio_buffer.stopped':
        this._speaking = false;
        this.onAudioEnd();
        break;

      case 'response.function_call_arguments.done':
        this._handleToolCall(data);
        break;

      case 'error': {
        const err = new Error(data.error?.message || 'Realtime API error');
        if (this._connectReject) {
          this._failConnect(err);
        } else {
          this.onError(err);
        }
        break;
      }
    }
  }

  async _handleToolCall(evt) {
    const callId = evt.call_id;
    const name = evt.name || '';
    let args = {};
    try { args = JSON.parse(evt.arguments || '{}'); } catch {}

    this.onToolCall(name, args);

    let output;
    const impl = this._tools[name];
    if (impl) {
      try { output = await impl(args); } catch (e) { output = `Error: ${e.message}`; }
    } else {
      output = 'Tool not found.';
    }

    this._send({
      type: 'conversation.item.create',
      item: { type: 'function_call_output', call_id: callId, output: String(output) },
    });
    this._send({ type: 'response.create' });
  }

  _onRemoteTrack(event) {
    const stream = event.streams && event.streams[0];
    if (!stream) return;

    if (!this.audioEl) {
      this.audioEl = new Audio();
      this.audioEl.autoplay = true;
    }
    this.audioEl.srcObject = stream;

    // Tap the remote stream for an honest amplitude signal (drives visemes).
    try {
      if (!this.audioCtx) {
        this.audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      }
      if (this.audioCtx.state === 'suspended') {
        this.audioCtx.resume().catch(() => {});
      }
      const src = this.audioCtx.createMediaStreamSource(stream);
      this.analyser = this.audioCtx.createAnalyser();
      this.analyser.fftSize = 512;
      src.connect(this.analyser);
      this._levelBuf = new Uint8Array(this.analyser.fftSize);
    } catch (err) {
      console.warn('[VoiceRealtime] analyser unavailable:', err);
    }
  }

  // RMS amplitude of the model's output audio, 0..1. Returns 0 whenever the
  // model is not actively producing audio, so silence is real silence.
  getAudioLevel() {
    if (!this.analyser || !this._levelBuf || !this._speaking) return 0;
    this.analyser.getByteTimeDomainData(this._levelBuf);
    let sum = 0;
    for (let i = 0; i < this._levelBuf.length; i++) {
      const v = (this._levelBuf[i] - 128) / 128;
      sum += v * v;
    }
    return Math.min(1, Math.sqrt(sum / this._levelBuf.length) * 4);
  }

  _send(obj) {
    if (this.dc?.readyState === 'open') {
      this.dc.send(JSON.stringify(obj));
    }
  }

  _setState(state) {
    if (this.state === state) return;
    this.state = state;
    this.onStateChange(state);
  }

  _teardownMedia() {
    if (this.dc) {
      try { this.dc.close(); } catch {}
      this.dc = null;
    }
    if (this.pc) {
      try { this.pc.close(); } catch {}
      this.pc = null;
    }
    if (this.micStream) {
      this.micStream.getTracks().forEach(t => t.stop());
      this.micStream = null;
    }
    if (this.audioEl) {
      this.audioEl.srcObject = null;
      this.audioEl = null;
    }
    this.analyser = null;
    this._levelBuf = null;
    this._speaking = false;
  }

  disconnect() {
    this._cleanupConnectPromise();
    this._teardownMedia();
    this._setState('idle');
  }

  destroy() {
    this.destroyed = true;
    this.disconnect();
    if (this.audioCtx) {
      this.audioCtx.close().catch(() => {});
      this.audioCtx = null;
    }
  }
}
