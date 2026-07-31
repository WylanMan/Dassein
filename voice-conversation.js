// VoiceConversation — thin wiring between VoiceRealtime (S2S transport) and
// the UI. Turn-taking, interruption, STT, LLM, and TTS all live inside the
// realtime session; this class only maps events to visual state and chat text.

const STATE = {
  IDLE: 'IDLE',
  LISTENING: 'LISTENING',
  THINKING: 'THINKING',
  SPEAKING: 'SPEAKING',
};

const STATE_VISUALS = {
  IDLE: { color: '#9a97a3', pulse: false, label: 'idle' },
  LISTENING: { color: '#44ff88', pulse: true, label: 'listening' },
  THINKING: { color: '#00d4ff', pulse: true, label: 'thinking' },
  SPEAKING: { color: '#00d4ff', pulse: false, label: 'speaking' },
};

export class VoiceConversation {
  constructor(options = {}) {
    this.realtime = options.realtime;
    this.onStateChange = options.onStateChange || (() => {});
    this.onUserTranscript = options.onUserTranscript || (() => {});
    this.onToken = options.onToken || (() => {});
    this.onMessage = options.onMessage || (() => {});
    this.onToolCall = options.onToolCall || (() => {});
    this.onAudioStart = options.onAudioStart || (() => {});
    this.onAudioEnd = options.onAudioEnd || (() => {});
    this.onError = options.onError || (() => {});

    this.state = STATE.IDLE;
    this.active = false;
  }

  setState(newState) {
    if (this.state === newState) return;
    this.state = newState;
    const visual = STATE_VISUALS[newState] || STATE_VISUALS.IDLE;
    this.onStateChange(newState, visual);
  }

  async start() {
    if (this.active) return;
    this.active = true;
    this._wireEvents();

    try {
      await this.realtime.connect();
    } catch (err) {
      this.active = false;
      throw err;
    }
    this.setState(STATE.IDLE);
  }

  _wireEvents() {
    // User starts speaking — possibly barging in while the agent talks.
    // The realtime session truncates its own audio natively; we just reflect it.
    this.realtime.onSpeechStart = () => {
      this.setState(STATE.LISTENING);
    };

    // User finished a turn — the model is now generating.
    this.realtime.onSpeechEnd = () => {
      this.setState(STATE.THINKING);
    };

    this.realtime.onUserTranscript = (text) => {
      this.onUserTranscript(text);
      this.onMessage('user', text);
    };

    this.realtime.onAssistantDelta = (delta) => {
      this.onToken(delta);
    };

    this.realtime.onAssistantDone = (text) => {
      if (text) this.onMessage('assistant', text);
    };

    this.realtime.onAudioStart = () => {
      this.setState(STATE.SPEAKING);
      this.onAudioStart();
    };

    this.realtime.onAudioEnd = () => {
      this.onAudioEnd();
      if (this.active) this.setState(STATE.IDLE);
    };

    this.realtime.onToolCall = (name, args) => {
      this.onToolCall(name, args);
    };

    this.realtime.onError = (err) => {
      this.onError(err);
      if (this.active) this.setState(STATE.IDLE);
    };
  }

  stop() {
    this.active = false;
    this.realtime.disconnect();
    this.setState(STATE.IDLE);
  }

  destroy() {
    this.stop();
    this.realtime.destroy();
  }
}

export { STATE, STATE_VISUALS };
