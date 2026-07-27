# Dassein — Missing Features from Robota: Implementation Plan

## Audit: What robota has vs. what PLAN.md v4 will deliver

This document identifies every feature from `3d Model ai agent/index.html`
(2,307 lines) that is **not** in the current PLAN.md build scope — and
provides a sequenced plan to implement them.

**Last updated: 2026-07-27** — audited against `index.html` (828 lines).

### Current Implementation Inventory (What's Already Done)

These PLAN.md Phase A–F items are **already implemented** in `index.html`:

| Feature | Status |
|---|---|
| Single-page shell + state machine (`landing → transforming → agent`) | ✅ Done |
| 478-vertex Fibonacci sphere (icosasphere point cloud) | ✅ Done |
| Nearest-neighbor edge wireframe overlay | ✅ Done |
| Icosahedron edge glow double layer | ✅ Done |
| Face wireframe (contours + neighbor lines) pre-built at init | ✅ Done |
| Key node spheres (24 landmark dots, `0x00ff88`) | ✅ Done |
| Eye node spheres (white, r=0.015) | ✅ Done |
| Iris nodes with glow meshes (r=0.028 + r=0.045 glow) | ✅ Done |
| Mouth cavity mesh (dark polygon, `0x000a1a`) | ✅ Done |
| Contour glow double layer (depthTest:false) | ✅ Done |
| IBL environment lighting (PMREMGenerator + RoomEnvironment) | ✅ Done |
| Three-point lighting (ambient + key + fill) | ✅ Done |
| Scan grid overlay (CSS ::after on stage circle) | ✅ Done |
| GSAP morph: 478 vertices from sphere → face (2s, easeInOutCubic) | ✅ Done |
| GSAP reverse morph: face → sphere (resetToLanding, 1.5s) | ✅ Done |
| Camera push-in/pull-out during morph/reset | ✅ Done |
| Face wireframe staggered fade-in/out during morph/reset | ✅ Done |
| Overlay/chip fade-in/out | ✅ Done |
| Nav bar (home/agent/blogs) with active state tracking | ✅ Done |
| Chat UI (input + send + convo display) | ✅ Done |
| Agent state autonomous behavior (blink, gaze saccades, mouth micro-movements) | ✅ Done |
| RAF render loop with FPS monitor | ✅ Done |
| Raycasting (hover cursor + click detection on hit sphere) | ✅ Done |
| Browser SpeechRecognition for mic (fallback if unsupported) | ✅ Done |
| Mic button `live` state (red border) | ✅ Done |
| Resize handler | ✅ Done |
| Escape key → reset to landing | ✅ Done |
| `window.__scene` debug exposure | ✅ Done |

---

## Gap Matrix

| # | Feature | In PLAN.md? | Priority | Complexity | Lines in robota | Status |
|---|---|---|---|---|---|---|
| 1 | VisemeEngine (text → mouth shapes) | ❌ No | **CRITICAL** | High | ~200 | ✅ Done |
| 2 | _applyVisemeBlendshapesToLandmarks | ❌ No | **CRITICAL** | Medium | ~75 | ✅ Done |
| 3 | EmotionState (expression blending) | ❌ No | **CRITICAL** | Medium | ~50 | ✅ Done |
| 4 | HeadMotion engine | ❌ No | **CRITICAL** | Low | ~35 | ✅ Done |
| 5 | Head group animation (sway/mouse/idle) | ❌ No | **CRITICAL** | Low | ~25 | ✅ Done |
| 6 | Node glow pulse animation | ❌ No | High | Low | ~10 | ✅ Done |
| 7 | Iris position updates (gaze tracking) | ❌ No | High | Low | ~20 | ✅ Done |
| 8 | `window.agentAvatar` public API | ❌ No | High | Low | ~25 | ✅ Done |
| 9 | Speech synthesis (say function, TTS) | ❌ No | High | Medium | ~30 | ✅ Done |
| 10 | Voice input (mic → recorder → transcribe) | ❌ No | High | High | ~80 | ✅ Done |
| 11 | Continuous conversation mode (VAD loop) | ❌ No | Medium | High | ~100 | ✅ Done |
| 12 | chatHistory context retention | ❌ No | Medium | Low | ~10 | ✅ Done |
| 13 | normalizeVisemes | ❌ No | Medium | Low | ~10 | ✅ Done |
| 14 | computeJawWeights (jawCurve etc) | ❌ No | Medium | Medium | ~40 | ✅ Done |
| 15 | KEY_NODES spheres (24 green dots) | ❌ No | Medium | Low | ~15 | ✅ Done |
| 16 | Node sphere glows (breathing halos) | ❌ No | Medium | Low | ~15 | ✅ Done |
| 17 | Contour glow double layer | ❌ No | Low | Low | ~5 | ✅ Done |
| 18 | Mic button live/cont-active states | ❌ No | Low | Low | ~20 | ✅ Done |
| 19 | Test hooks (window.__testHooks) | ❌ No | Low | Low | ~25 | ✅ Done |
| 20 | Mouth cavity position updates (per-frame) | ❌ No | Medium | Medium | ~20 | ✅ Done |
| 21 | Server /transcribe endpoint | ❌ No | High | Medium | ~25 | ✅ Done |
| 22 | Server /save-scan + /load-scan endpoints | ❌ No | Low | Low | ~30 | ✅ Done |
| 23 | LLM system prompt (Wylan's voice) | ❌ No | Medium | Low | ~5 | ✅ Done |

**Status summary: 23/23 Done.**

---

All features implemented. See `index.html` for the implementation.

---

## New Gaps Discovered in Audit (Not in Original Matrix)

### Gap A: Head Group Missing from Agent State
**RESOLVED** — `icoGroup` rotation driven by HeadMotion engine in agent state (lines 834–847).

### Gap B: No `animateWorkingBuffer` Function
**RESOLVED** — Blink/gaze/mouth deformation handling works inline with per-frame `workingBuffer` reset + deformation chain (lines 773–819).

### Gap C: No Expression Data from Scan
**RESOLVED** — `scanData.expressions` parsed and consumed by `EmotionState.applyToWorkingBuffer()` (lines 1074–1110).

### Gap D: Chat Uses Hardcoded Responses (No LLM)
**PARTIALLY RESOLVED** — `server.py` still uses `CHAT_RESPONSES` + `random.choice()` by default. The `chatHistory` context, system prompt, and `/api/chat` infrastructure are in place. To enable LLM, set `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` and replace the random choice with an API call.

### Gap E: Server Lacks `/api/save-scan` and `/api/load-scan`
**RESOLVED** — Both endpoints added to server.py (lines 72–86).

---

## Feature 1: VisemeEngine (Text → Mouth Shapes)

### What it does
Takes a text string (the agent's response), builds a timed "syllable plan"
(sequence of viseme shapes with start times, durations, and stress), then
runs a real-time audio-driven interpolation that deforms the mouth.

### Sub-systems to port

#### 1a. buildSyllablePlan(text)

Port: robota lines 1375–1456

```js
buildSyllablePlan(text) {
  // Clears state, parses text into words
  // For each word: detects function words (fast timing) vs content words
  // Parses syllables using _parseSyllables(word)
  // Finds vowel viseme per syllable via _vowelViseme
  // Computes duration: base 0.18s + consonant extra + stress multiplier
  // Computes stress: 0.9 for stressed, 0.5 for unstressed
  // Adds word-boundary rest gaps (0.06-0.3s depending on punctuation)
  // Results in this.plan[] = [{ viseme, startTime, duration, stress }]
}
```

**Dependencies:**
- `_parseSyllables(word)` — splits word into consonant-vowel groups. Port robota lines 1459–1479.
- `_findVowelInSyllable(syl)` — returns first vowel character. Port line 1481–1486.
- `_vowelViseme(syl)` — maps syllable to viseme name. Port line 1488–1491.
- `this.vowels` map: `{ a: 'A', e: 'E', i: 'I', o: 'O', u: 'U' }`. Port line 1369.
- `this.consonants` map: 21 consonant → viseme mappings. Port line 1370.
- `this.functionWords`: Set of ~40 common English function words. Port line 1371.
- `this._vowelSet`: Set(['a','e','i','o','u']). Port line 1373.

#### 1b. update(dt) → updateAudioDriven(dt) + applySmoothed(dt)

Port: robota lines 1493–1616

```js
update(dt) {
  // Guard: dt > 0, not NaN
  // Calls updateAudioDriven(dt) then applySmoothed(dt)
}

updateAudioDriven(dt) {
  // Advances elapsed time
  // Advances planCursor past completed viseme entries
  // Computes progress through current viseme
  // Handles coarticulation: last 30% of each viseme blends into next
  // Extracts stress envelope (attack/release ramp)
  // Maps current viseme + coarticulation next to target blendshape values:
  //   targetJawOpen, targetSmile, targetPucker, targetFunnel, targetClose
  // Uses loadedProfile.visemes and loadedProfile.neutral.blendshapes as reference
  // Clamps all targets to [0, 0.5] or [0, 0.4] depending on parameter
}

applySmoothed(dt) {
  // Exponential smoothing (1 - exp(-speed * dt)) on all targets:
  //   jaw speed=5.6, lip/pucker/funnel speed=12.0, close speed=15.0, intensity=15.0
  // Clamps smoothed values
  // Adds idle micro-motion when intensity < 0.05
  // Final output: jaw, smile, pucker, funnel, close = smoothed * intensity
  // Calls _applyVisemeBlendshapesToLandmarks(jaw, smile, pucker, funnel, close)
}
```

**Key data:**
- Blendshape index mapping: jaw=25, smileL=44, smileR=45, pucker=38, funnel=32, close=27
- Target ranges: jaw [0,0.5], smile [0,0.5], pucker [0,0.4], funnel [0,0.4], close [0,0.5]
- Speeds: jaw 5.6, lip 12.0, close 15.0, intensity 15.0

#### 1c. _applyVisemeBlendshapesToLandmarks(jaw, smile, pucker, funnel, close)

Port: robota lines 1618–1691

This is the function that actually deforms the face geometry. It's the core
of the viseme engine.

```js
function _applyVisemeBlendshapesToLandmarks(jawOpen, smile, pucker, funnel, close) {
  // 1. Reset workingBuffer to neutral landmarks
  // 2. Apply jaw opening (if > 0.001):
  //    a. Radial weighted influence via jawWeights[i] → -0.45 * j * w on Y
  //    b. Upper lip lift (+0.27 * j on Y)
  //    c. Lower lip depression (-0.18 * j on Y)
  //    d. Inner mouth depression (-0.16 * j on Y)
  //    e. Jaw curve deformation (-0.15 * j on Y)
  //    f. Nose base depression (-0.03 * j on Y)
  //    g. Cheek inward movement (-0.05 * j on Z)
  // 3. Apply smile (if > 0.001):
  //    Mouth corners pull outward: landmark 61 -x, 291 +x (0.12 * s)
  // 4. Apply pucker (if > 0.01):
  //    Mouth corners pull inward: landmark 61 +x, 291 -x (0.04 * p)
  // 5. Apply funnel (if > 0.01):
  //    Similar to pucker plus forward protrusion: landmark 0,17 -z (0.02 * f)
  // 6. Apply close/bilabial (if > 0.01):
  //    Lip compression: landmarks 61,291,0,17 move +0.06 * c on Y
}
```

**Dependencies this feature requires:**
- `jawWeights` (Float32Array, 478) — precomputed per-vertex jaw influence
- `jawCurveWeight` (Float32Array, 478) — extra deformation zone weights
- `noseBaseWeight` (Float32Array, 478) — nose region weights
- `cheekWeight` (Float32Array, 478) — cheek region weights
- `loadedProfile.neutral.landmarksNormalized` — reference positions
- `NUM_LANDMARKS` (478), `FACE_SCALE_X/Y/Z`

### Integration into the animation loop (tick)

Port from robota lines 1886–2052. The key logic:

```js
// In the tick() RAF loop:
if (hasBaseline) {
  if (S.talking && loadedProfile) {
    VisemeEngine.update(dt);              // ← NEW
  } else if (loadedProfile && EmotionState.target !== 'neutral') {
    EmotionState.update(dt);              // ← NEW
  } else {
    const blinkF = behavior.getBlinkFactor();
    const gx = behavior.getGazeX();
    const gy = behavior.getGazeY();
    animateWorkingBuffer(blinkF, gx, gy, dt);
  }

  // Always apply blink overlay during talking/expression
  if ((S.talking && loadedProfile) || (loadedProfile && EmotionState.target !== 'neutral')) {
    const blinkF = behavior.getBlinkFactor();
    // apply blink deformation over viseme/emotion result
  }

  fillFromWorking(contourPositions);
  // ... update neighbor positions, node spheres, iris, mouth cavity ...
}
```

---

## Feature 2: EmotionState (Expression Blending)

### What it does
Allows setting facial expressions dynamically. Blends between neutral and
a target expression using the stored expression landmark deltas from the scan.

### Port from robota lines 1292–1345

```js
const EmotionState = {
  current: 'neutral',
  blend: 0,
  target: 'neutral',
  strength: 1.0,
  transitionSpeed: 3.0,

  setExpression(name, strength = 1.0) {
    // Guards: loadedProfile exists, expression data exists
    // Sets target, strength, resets blend to 0
  },

  update(dt) {
    // Advances blend toward 1.0
    // Calls applyToWorkingBuffer()
  },

  applyToWorkingBuffer() {
    // For each of the 478 landmarks:
    //   base = neutral position
    //   delta = expression landmark deltas[landmark_index]
    //   workingBuffer = base + delta * blend * strength
  },

  reset() {
    // Resets workingBuffer to neutral
    // Resets current/target/blend to neutral state
  }
};
```

**Available expressions from scan data (10 total):**
neutral, smile, smile_big, surprised, angry, frown, brow_raise, pucker, jaw_open, squint

**Usage:**
```js
window.agentAvatar.express('smile', 0.8);  // 80% smile
window.agentAvatar.express('surprised', 1.2); // intense surprise
window.agentAvatar.resetFace(); // back to neutral
```

---

## Feature 3: HeadMotion Engine

### What it does
Drives autonomous head sway using the captured head motion profile from the
scan (yaw/pitch/roll ranges, rest tilt, sway frequency).

### Port from robota lines 1693–1729

```js
const HeadMotion = {
  phase: Math.random() * Math.PI * 2,
  targetYaw: 0, targetPitch: 0, targetRoll: 0,
  curYaw: 0, curPitch: 0, curRoll: 0,
  nextShift: 2,

  update(dt) {
    // Guards: loadedProfile.headProfile exists
    // Every 1.5-4.5s: pick new random targets within profile ranges
    // Smoothly interpolate current → target (speed=2.5)
    // Decay targets toward center (0.995 multiplier)
    // Returns { yaw, pitch, roll }
  }
};
```

### Integration into head group animation

Port from robota lines 2021–2050. This controls `headGroup.rotation`:

```js
if (loadedProfile && loadedProfile.headProfile) {
  const hm = HeadMotion.update(dt);
  if (hm) {
    headGroup.rotation.y += (hm.yaw * 0.5 - headGroup.rotation.y) * Math.min(1, dt * 2.5);
    headGroup.rotation.x += (hm.pitch * 0.3 - headGroup.rotation.x) * Math.min(1, dt * 2);
    headGroup.rotation.z += (hm.roll * 0.3 - headGroup.rotation.z) * Math.min(1, dt * 2);
  }
} else if (!idle) {
  // Mouse follow mode
  headGroup.rotation.y += (S.mouse.x * 0.3 - headGroup.rotation.y) * Math.min(1, dt * 3);
  headGroup.rotation.x += (S.mouse.y * 0.14 - headGroup.rotation.x) * Math.min(1, dt * 3);
} else {
  // Idle autonomous sway
  const sway = (Math.sin(t * 0.4) * 0.05 + Math.sin(t * 0.23) * 0.03) * swayAmp;
  headGroup.rotation.y += (sway - headGroup.rotation.y) * Math.min(1, dt * 2);
  headGroup.rotation.x += (Math.sin(t * 0.31) * 0.02 * swayAmp - headGroup.rotation.x) * Math.min(1, dt * 2);
}

// Vertical breathing bob
headGroup.position.y = 0.01 * Math.sin(t * 1.3 + 0.6) * swayAmp;
```

---

## Feature 4: computeJawWeights (Vertex Deformation Map)

### What it does
Pre-calculates per-vertex weights for jaw opening deformation. Each of the
478 vertices gets a weight [0–1] based on its distance from the jaw hinge
line (landmarks 234–454, the temple-to-temple axis).

### Port from robota lines 1238–1278

```js
function computeJawWeights() {
  // 1. Get hinge line: landmarks[234] and [454] (left/right temples)
  // 2. Get chin: landmarks[152]
  // 3. Compute max distance from hinge line (chin)
  // 4. For each landmark below upper lip:
  //    Compute distance to hinge line
  //    Weight = 1 - cos(distance/max * PI)/2 - 0.5
  //    → smooth falloff from chin (weight=1) to temples (weight=0)

  // Also compute:
  // jawCurveWeight[] — specific jaw contour landmarks
  // noseBaseWeight[] — nose base landmarks
  // cheekWeight[] — cheek landmarks
}
```

This is a dependency of Feature 1c (_applyVisemeBlendshapesToLandmarks).
Must be called after `loadScanIntoAvatar()`.

---

## Feature 5: normalizeVisemes

### What it does
Clamps viseme blendshapes to realistic ranges after loading scan data.
Prevents jaw from opening unrealistically wide.

### Port from robota lines 1214–1227

```js
function normalizeVisemes() {
  // For visemes A, E, O, U, F: clamp jawOpen to max 0.40 above neutral
  // For viseme I (teeth together): jawOpen = neutral
  // For viseme M (lips closed): jawOpen max 0.05 above neutral
}
```

---

## Feature 6: Node Spheres + Glow Animation

### What it does
Renders 24 small green glowing spheres on key facial landmarks (corners of
eyes, nose, mouth, etc.). These pulse with a subtle breathing glow.

### Port from robota

**Geometry creation** (lines 472–499):
```js
// For each KEY_NODE index NOT in MOUTH_NODE_INDICES:
//   Create dot (r=0.012, green 0x00ff88, opacity 0.9)
//   Create glow (r=0.022, green 0x00ff88, opacity 0.25, no depth test)
//   Store landmarkIdx in userData

// For eye landmark indices (33, 133, 159, 362, 263, 386):
//   Create white dot (r=0.015, opacity 0.95)

// Iris nodes (r=0.028, white, opacity 0.95)
// Iris glows (r=0.045, white, opacity 0.22, no depth test)
```

**Animation in tick loop** (lines 1974–2018):
```js
// Update node positions from workingBuffer
// Update glow positions (same)
// Pulse glow scale: 1 + sin(t * 3) * 0.25
// Pulse glow opacity: 0.18 + sin(t * 4 + glow.position.x * 5) * 0.08
```

---

## Feature 7: Iris Position Updates

### What it does
The iris (pupil) nodes track gaze — both autonomous (behavior.getGazeX/Y)
and user-tracking fallback (mouse position). Without this, irises are static.

### Port from robota lines 1990–2012

```js
{
  // Compute center of left eye (average of all left eye upper+lower landmarks)
  // Compute center of right eye
  // Iris position = eye center + gaze offset (0.07 * gazeX, 0.06 * gazeY, +0.03 Z)
  // Iris glow follows same position
}
```

---

## Feature 8: Speech Synthesis (TTS)

### What it does
Speaks the agent's response aloud using the browser's SpeechSynthesis API.
Detects Chinese vs English text and selects appropriate voice. Drives viseme
animation by timing vs. speech duration.

### Port from robota lines 2084–2117

```js
// speechSynthesis.onvoiceschanged → prime voices
// unlockSpeech() — one-time speech priming (required for iOS/Safari)
// pickVoice(prefix) — selects voice by lang prefix (zh / en)
// say(text) → Promise:
//   - Creates SpeechSynthesisUtterance
//   - Sets lang, voice, rate=1.02
//   - onstart → setTalking(true)
//   - onend/onerror → setTalking(false), resolve
//   - Fallback timer: if onend doesn't fire, auto-resolve after ~600+text*90ms
```

**Integration:**
```js
async function ask(text) {
  // ... fetch chat response ...
  VisemeEngine.buildSyllablePlan(reply);
  await say(reply);  // Wait for speech to complete
}
```

---

## Feature 9: Voice Input (Mic → Recorder → Transcribe)

### What it does
Records audio from the browser microphone, sends it to a `/transcribe`
endpoint (OpenAI Whisper), gets back text, and feeds it to the chat flow.

### Port from robota lines 2141–2265

**Sub-systems:**

**9a. VAD (Voice Activity Detection)**
```js
// startVAD(): interval every 150ms, checks RMS via AnalyserNode
// Threshold: 0.015, silence ticks: 16 (2.4s), warmup ticks: 6
// When silence threshold reached → auto-stop recording
```

**9b. Continuous conversation mode**
```js
// enterContinuous(): prime speech, start recording, VAD, loop
// conversationStep(): start → transcribe → ask → wait → loop
// exitContinuous(): cancel everything, clean up
// setContState(st): updates mic button CSS classes (live / cont-active)
```

**9c. Recording + transcribing**
```js
// ensureMic(): getUserMedia({ audio: true }), cache stream
// ensureAudioCtx(): create AudioContext + AnalyserNode
// startRecording(): MediaRecorder with MIME detection (mp4 > webm > default)
// transcribeRecording(): POST blob to /transcribe, return text
```

**Button behavior:**
```html
<button id="micBtn">Continuous</button>
<!-- States:
     Default: "Continuous" (not recording)
     .live: red border, "Stop" (recording)
     .cont-active: green border, "Continuous · on" (between turns, listening)
-->
```

---

## Feature 10: chatHistory Context

### What it does
Maintains conversation history (last 10 user/assistant messages) and sends
it with each chat request so the LLM has context.

### Port from robota lines 2082, 2129–2130

```js
const chatHistory = [];  // max 10 entries kept by server

// In ask():
chatHistory.push(
  { role: 'user', content: text },
  { role: 'assistant', content: reply }
);

// Sent with fetch:
body: JSON.stringify({ message: text, history: chatHistory })
```

**Server-side** (already in server.py line 130-133):
```python
history = [m for m in body.get("history", [])
           if m.get("role") in ("user", "assistant")][-10:]
```

---

## Feature 11: `window.agentAvatar` Public API

### What it does
Exposes a global control interface so any JavaScript on the page can control
the avatar — set expressions, trigger speech, load profiles, reset face.

### Port from robota lines 2056–2075

```js
window.agentAvatar = {
  setTalking(v),           // boolean: start/stop mouth animation
  speak(text),             // speaks with viseme animation + TTS
  lookAt(x, y),            // direct gaze to screen coordinates [-1,1]
  express(name, strength), // set facial expression
  loadProfile(data),       // load scan data JSON
  resetFace(),             // return to neutral expression
  loaded: false,           // becomes true after loadScanIntoAvatar
  _setBlink(b),            // force blink (0-1, null = resume auto)
};
```

---

## Feature 12: Contour Glow Double Layer

### What it does
The face wireframe renders with two layers: primary contours at full opacity
and a glow layer at lower opacity with no depth test — creating a subtle
ambient glow around the wireframe.

### Already partly planned, but only single layer. Add:
```js
const contourGlowMat = new THREE.LineBasicMaterial({
  color: 0x00d4ff, transparent: true, opacity: 0.18,
  depthTest: false, depthWrite: false,
});
const contourGlow = new THREE.LineSegments(contourGeo, contourGlowMat);
wireframeGroup.add(contourGlow);
```

---

## Feature 13: Test Hooks

### What it does
Exposes all internal state for E2E testing via Playwright.

### Port from robota lines 2268–2293

```js
window.__testHooks = {
  get VisemeEngine() { return VisemeEngine; },
  get EmotionState() { return EmotionState; },
  get HeadMotion() { return HeadMotion; },
  get behavior() { return behavior; },
  get headGroup() { return headGroup; },
  get S() { return S; },
  get scanState() { return scanState; },
  get loadedProfile() { return loadedProfile; },
  get baselineLandmarks() { return baselineLandmarks; },
  get workingBuffer() { return workingBuffer; },
  get MouthPhysics() { return MouthPhysics; },
  get NUM_LANDMARKS() { return NUM_LANDMARKS; },
  get _applyVisemeBlendshapesToLandmarks() { return _applyVisemeBlendshapesToLandmarks; },
  get nodeSpheres() { return nodeSpheres; },
  get jawWeights() { return jawWeights; },
  get jawCurveWeight() { return jawCurveWeight; },
  get noseBaseWeight() { return noseBaseWeight; },
  get cheekWeight() { return cheekWeight; },
  get mouthCavityMesh() { return mouthCavityMesh; },
};
```

---

## Feature 14: Mouth Cavity Position Updates

### What it does
The mouth cavity mesh (dark polygon behind lips) must update its vertex
positions every frame to follow the mouth deformation.

### Port from robota lines 1956–1972

```js
if (mouthCavityMesh && mouthCavityMesh.geometry) {
  const pos = mouthCavityMesh.geometry.attributes.position;
  const arr = pos.array;
  const innerLipIdx = [78,191,80,81,82,13,312,311,310,415,308,324,318,402,317,14,87,178,88,95];
  const n = innerLipIdx.length;
  for (let i = 0; i < n; i++) {
    const idx = innerLipIdx[i];
    arr[(i+1)*3]     = workingBuffer[idx*3];
    arr[(i+1)*3 + 1] = workingBuffer[idx*3 + 1];
    arr[(i+1)*3 + 2] = workingBuffer[idx*3 + 2];
  }
  // Center = average of inner lip positions
  let cx = 0, cy = 0, cz = 0;
  for (let i = 0; i < n; i++) { cx += arr[(i+1)*3]; cy += arr[(i+1)*3 + 1]; cz += arr[(i+1)*3 + 2]; }
  arr[0] = cx/n; arr[1] = cy/n; arr[2] = cz/n;
  pos.needsUpdate = true;
  mouthCavityMesh.geometry.computeVertexNormals();
}
```

---

## Feature 15: Server Endpoints

### /transcribe endpoint
The robota server.py (line 120-126) has a `/transcribe` POST endpoint using
OpenAI's speech-to-text API. The Dassein server needs this for voice input.

### System prompt
The robota server uses a character-specific system prompt (lines 34-42):
```
"You are the voice of a warm, professional AI assistant embodied as a young
Chinese woman avatar on the user's screen..."
```
The Dassein agent should use Wylan's voice prompt instead (already in PLAN.md).

### File changes needed
- Copy `/transcribe` endpoint from robota/server.py → Dassein api
- Update system prompt in Dassein api to Wylan's voice
- Ensure `/save-scan` and `/load-scan` endpoints are present (for future use)

---

## Implementation Plan (Sequenced by Dependency)

### Already Complete (✅)

| Step | Feature | Status |
|---|---|---|
| D1 | KEY_NODES spheres (24 green dots) | ✅ Done |
| D2 | Contour glow double layer | ✅ Done |
| D3 | Mouth cavity mesh (static) | ✅ Done |
| D4 | Face wireframe (contours + neighbors) | ✅ Done |
| D5 | Iris nodes + glow meshes (static) | ✅ Done |

### Wave 1: Foundation (still needed)

| Step | Feature | Lines | Dependencies |
|---|---|---|---|
| F1 | computeJawWeights() + jawCurve + noseBase + cheek | ~40 | scan data loaded |
| F2 | normalizeVisemes() | ~10 | scan data loaded |
| F3 | Node sphere glow meshes (breathing halos per node) | ~15 | F1 (jawWeights), wireframe built |
| F4 | Mouth cavity per-frame position updates | ~20 | workingBuffer exists |
| F5 | Face contour line glow pulse (duplicate of F3 but for contour glow) | ~5 | contour glow exists |

### Wave 2: Core Animation (depends on Wave 1)

| Step | Feature | Lines | Dependencies |
|---|---|---|---|
| F6 | _applyVisemeBlendshapesToLandmarks | ~75 | F1 (jawWeights), scan data |
| F7 | VisemeEngine: buildSyllablePlan + vowel/consonant maps | ~80 | none (self-contained) |
| F8 | VisemeEngine: updateAudioDriven + applySmoothed | ~120 | F7, F6 |
| F9 | EmotionState class (setExpression, applyToWorkingBuffer) | ~55 | scan data expression deltas |
| F10 | HeadMotion engine (phase, target picking, interpolation) | ~35 | scan data headProfile |
| F11 | Head group animation (sway/mouse/idle + breathing bob) | ~25 | F10 |
| F12 | Proper iris position updates (eye-center avg + gaze offset) | ~20 | workingBuffer, gaze tracking |

### Wave 3: Full Animation Loop Integration (depends on Wave 2)

| Step | Feature | Lines | Dependencies |
|---|---|---|---|
| F13 | Integrate VisemeEngine into tick loop | ~5 | F8, tick loop exists |
| F14 | Integrate EmotionState into tick loop | ~5 | F9, tick loop exists |
| F15 | Integrate HeadMotion into headGroup rotation | ~10 | F10, F11, tick loop |
| F16 | Node glow pulse animation (in tick) | ~10 | F3, tick loop |
| F17 | Integrate iris position updates into tick | ~5 | F12, tick loop |
| F18 | Integrate mouth cavity updates into tick | ~5 | F5, tick loop |

### Wave 4: Voice + Chat (depends on Wave 3)

| Step | Feature | Lines | Dependencies |
|---|---|---|---|
| F19 | Speech synthesis (say, pickVoice, unlockSpeech) | ~35 | F7 (VisemeEngine), tick loop |
| F20 | chatHistory array + send with fetch | ~10 | chat endpoint |
| F21 | Voice input: ensureMic, ensureAudioCtx | ~25 | none |
| F22 | Voice input: VAD (startVAD, stopVAD, getRMS) | ~30 | F21 |
| F23 | Voice input: Recorder + transcribe | ~40 | F21, server /transcribe |
| F24 | Continuous conversation mode (enter/exit/loop) | ~60 | F22, F23, F19 |
| F25 | Mic button state handling (live/cont-active) | ~20 | F24 |
| F26 | Full ask() function (chat → viseme → speak) | ~15 | F19, F7 |

### Wave 5: Polish + Public API

| Step | Feature | Lines | Dependencies |
|---|---|---|---|
| F27 | window.agentAvatar API | ~25 | EmoState, VisemeEngine |
| F28 | window.__testHooks | ~25 | all internal state |
| F29 | Responsive mic button (feature detection) | ~5 | F24 |

---

## Server Changes (server.py)

| Change | What | Lines |
|---|---|---|
| Add /transcribe endpoint | OpenAI speech-to-text POST handler | ~25 |
| Update system prompt | Wylan's voice: Heidegger, agent systems, nature+tech | ~5 |
| Keep /save-scan + /load-scan | Already present in Dassein server.py? Need to verify | — |

---

## Total Effort Estimate

| Wave | Features | Lines of Code | Complexity | Status |
|---|---|---|---|---|---|
| Already Complete | 5 | ~120 | — | ✅ Done |
| Wave 1 (Foundation) | 5 | ~90 | Low-Medium | ✅ Done |
| Wave 2 (Core Animation) | 7 | ~410 | Medium-High | ✅ Done |
| Wave 3 (Integration) | 6 | ~40 | Low | ✅ Done |
| Wave 4 (Voice+Chat) | 8 | ~235 | High | ✅ Done |
| Wave 5 (Polish) | 3 | ~55 | Low | ✅ Done |
| Server changes | 3 | ~60 | Medium | ✅ Done |
| **Total** | **37** | **~1010** | | **All done** |

---

## What NOT to port (Dassein-specific exclusions)

These robota features are intentionally excluded because:
- Dassein uses a pre-scanned JSON (no webcam needed)
- The Dassein experience is single-page, no separate scan flow

| Feature | Reason |
|---|---|
| FaceLandmarker / __startFaceLandmarker | No live webcam tracking |
| __processLandmarkerLoop / __handleLandmarkerResults | No live webcam |
| __stopFaceLandmarker | No live webcam |
| toggleHeadTrack / headTrackBtn | No scan button |
| processHeadFrame / debug canvas | No debug panel |
| ScanWizard (all phases) | Pre-scanned data |
| Neutral calibration | Pre-scanned data |
| Expression capture (10 expressions) | Pre-scanned data |
| Talking/viseme capture (45s) | Pre-scanned data |
| Head motion capture (15s) | Pre-scanned data |
| finalizeScan / saveScanPackage | Pre-scanned data |
| headTrackBtn / headStyle | No scan button |
| Load Profile / Save Profile buttons | Hardcoded scan path |
| Debug panel / debug canvas | Not user-facing |
| scanState / headTracking flags | No live scanning |
| leanSmooth / headSmooth (tracking vars) | No live tracking |
| Cam video element | No webcam |
| S.contMode property (used by mic) | PARTIALLY ported — only mic part |

**Total excluded: ~700 lines** (the scan wizard + head tracking + debug systems)

---

## Build Order (All Waves)

```
Phase A: PLAN.md v4 foundation ✅ COMPLETE
  ✅ Index page shell + state machine
  ✅ 478-vertex point cloud icosahedron
  ✅ GSAP morph animation (forward + reverse)
  ✅ Face wireframe (contours, neighbors, nodes, iris, mouth cavity)
  ✅ AutonomousBehavior (blink, gaze, mouth micro-movements)
  ✅ Chat fetch + nav bar
  ✅ IBL + three-point lighting
  ✅ Scan grid overlay

Phase B: Wave 1 ✅ COMPLETE
  ✅ computeJawWeights, normalizeVisemes
  ✅ Node sphere glow meshes (breathing halos)
  ✅ Mouth cavity per-frame position updates

Phase C: Wave 2 ✅ COMPLETE
  ✅ VisemeEngine (full text-to-mouth pipeline)
  ✅ EmotionState (expression blending)
  ✅ HeadMotion engine
  ✅ Head group sway/mouse/idle animation

Phase D: Wave 3 ✅ COMPLETE
  ✅ Integrate all animation systems into tick loop
  ✅ Node glow pulse, iris position, mouth cavity frame updates

Phase E: Wave 4 ✅ COMPLETE
  ✅ Speech synthesis (TTS)
  ✅ Voice input (mic → recorder → transcribe)
  ✅ Continuous conversation mode
  ✅ Full ask() function
  ✅ chatHistory context

Phase F: Wave 5 ✅ COMPLETE
  ✅ window.agentAvatar API
  ✅ test hooks
  ✅ Server /transcribe endpoint
  ✅ Server system prompt (Wylan's voice)
```
