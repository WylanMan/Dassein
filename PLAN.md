# Dassein — Unified Agent Page: Redesign Plan v4

## Summary

**Current state:** Two separate pages. `index.html` shows a green icosahedron that cracks/morphs into a face, then redirects to `agent.html` where the AI agent lives. The page transition breaks fluidity. The green phosphor theme (`#3dffb8`) doesn't match the cyan-blue design language of the robota 3D AI agent project.

**Goal:** Merge both into a single page. The icosahedron transforms into the AI agent face on the same page via JS (no navigation). Adopt the robota cyan-blue design system. Make the transformation simpler and more fluid — the current crack→seed→morph→emerge→redirect pipeline is too complex.

---

## Part 1: Design Language (from robota)

Every color, shadow, and visual element changes from green to blue:

| Element | Current (Green) | New (Blue — robota) |
|---------|-----------------|---------------------|
| Wireframe color | `#3dffb8` | `#00d4ff` |
| Box shadow glow | `rgba(61,255,184,...)` | `rgba(0,212,255,...)` |
| Stage border | `rgba(61,255,184,0.10)` | `rgba(0,212,255,0.10)` |
| Pulsing dot | green `#3dffb8` | cyan `#00d4ff` |
| Point light | `0x3dffb8` | `0x00d4ff` |
| Ambient light | `0x334466` | `0x1a1a2e` (blue-tinted) |
| Background | `#05080f` | `radial-gradient(1200px 800px at 50% 32%, #0c0c14, #06060a)` |
| Button bg | `#15151d` | `#15151d` (same) |
| Button border | `rgba(61,255,184,0.12)` | `rgba(0,212,255,0.12)` |
| Input focus | `rgba(61,255,184,0.35)` | `rgba(0,212,255,0.35)` |
| Text color | `#d7e1ee` | `#b9b6c2` |
| Dim text | `#7286a0` | `#9a97a3` |
| Mic active | green border | red border `#ff4466` |
| Font | Playfair Display + Caveat | ui-monospace + Space Grotesk + Caveat |
| Stage size | `min(60vmin, 400px)` | `min(78vmin, 600px)` |
| Stage ::after | none | scan grid lines (repeating-linear-gradient at 2px intervals, `rgba(0,212,255,0.015)`) |
| Surface mesh | `opacity: 0.05` | **REMOVED** (pure wireframe, no surface fill) |
| Neighbor lines | `opacity: 0.35` | `opacity: 0.45` (primary), `opacity: 0.10` (glow) |
| Mouth cavity | none | `0x000a1a` deep blue-black polygon |
| Node spheres | none | green `0x00ff88` on 24 key landmarks |
| Eye nodes | white, r=0.025 | white, r=0.015 |
| Iris nodes | none | white, r=0.028 with r=0.045 glow |

**Key visual additions from robota:**
- Scan grid overlay on the stage circle (::after pseudo-element)
- 24 green node marker spheres on key facial landmarks
- Dark mouth cavity mesh (so you can't see through the head when mouth opens)
- Radial gradient background instead of flat dark
- IBL environment lighting (`PMREMGenerator` + `RoomEnvironment`)
- Three-point lighting: ambient blue (`0x1a1a2e`) + key cool white (`0xc8e8ff`) + fill blue (`0x334466`)

---

## Part 2: Single-Page Architecture

### Before (current)
```
index.html                          agent.html
┌─────────────────────┐  redirect  ┌─────────────────────┐
│ Icosahedron         │ ────────→  │ Face Avatar (static)│
│ → click             │            │ → chat/mic          │
│ → crack/morph/face  │            │ → autonomous anim   │
│ → fade out          │            │                     │
│ → window.location   │            │                     │
└─────────────────────┘            └─────────────────────┘
```

### After (new)
```
index.html  (single page, all JS)
┌──────────────────────────────────────────────┐
│  PHASE 1: Landing                           │
│  ┌──────────────────────────────────────┐   │
│  │ "Dassein" + icosahedron (rotating)   │   │
│  │ "click the form" hint                │   │
│  └──────────────────────────────────────┘   │
│                    ↓ click                   │
│  PHASE 2: Transformation (in-place)          │
│  ┌──────────────────────────────────────┐   │
│  │ Icosahedron → Face (fluid morph)     │   │
│  └──────────────────────────────────────┘   │
│                    ↓ morph complete          │
│  PHASE 3: Agent Mode (no navigation)         │
│  ┌──────────────────────────────────────┐   │
│  │ Face avatar (autonomous behavior)    │   │
│  │ Chat input + mic + conversation      │   │
│  │ Nav bar (home/agent/blogs)           │   │
│  └──────────────────────────────────────┘   │
└──────────────────────────────────────────────┘
```

### How it works

The page always has:
1. **A full-viewport scene** (canvas) for the 3D rendering — this canvas never changes
2. **An overlay layer** for HTML UI — this changes visibility/opacity based on phase

State machine:
```
'landing'  →  click  →  'transforming'  →  morph complete  →  'agent'
```

In `landing` state: icosahedron rotates, title overlay visible, chat hidden.  
In `transforming` state: animation plays, title fades out.  
In `agent` state: face animates autonomously, chat UI visible, title hidden.

The **same Three.js scene** is used throughout — objects are added/removed, not recreated. The face wireframe exists in the scene from the start (invisible at first), revealed during the transformation.

---

## Part 3: Transformation Brainstorm

The current approach has 5 phases (CRACK → REVEAL → MORPH → EMERGE → REDIRECT) with a seed cloud, vertex interpolation, and page navigation. Too many moving parts.

Here are 5 simpler alternatives, ranked by simplicity + visual impact:

### Option A: Shell Dissolve (★★★ SIMPLEST)

**How:** The icosahedron wireframe fades out while the face wireframe simultaneously fades in at the same position. A simple crossfade with slight scale-up.

**Pros:** Dead simple. 2 lines of GSAP. No geometry manipulation.  
**Cons:** No sense of transformation — just a swap. Feels cheap.

### Option B: Particle Stream (★★★★ FLUID)

**How:** The icosahedron edges are rendered as particle streams (small dots flowing along each edge). On click, the flow direction reverses — particles detach from the icosahedron and stream through space to land at face wireframe positions. Think of data flowing from one shape to another.

**Pros:** Very fluid, "data/AI" themed, visually impressive.  
**Cons:** Needs custom particle system with target positions per particle. ~150 lines of new code. Particles can look messy mid-transition.

### Option C: Wavefront Scanner (★★★★ SCI-FI)

**How:** A horizontal blue scan line sweeps across the icosahedron. Where the line passes, the icosahedron wireframe is "erased" and the face wireframe is "drawn" in its place. Like a CT scan or laser scanner.

**Implementation:** Use two clipping planes (or shader-based dissolve) on both geometries. As the scan line moves from top to bottom (over ~1.5s), the icosahedron becomes transparent below the line and the face becomes opaque below the line.

**Pros:** Simple to implement (1 clipping plane, 2 geometry groups). Dramatic sci-fi feel. One continuous motion. No morph/seed/crack complexity.  
**Cons:** The face is revealed linearly (top-to-bottom) rather than "emerging" organically. Still feels mechanical.

### Option D: Petal Unfold (★★★★ ELEGANT)

**How:** The icosahedron's 20 triangular faces act like flower petals. On click, each face rotates open around its outer edge hinge — like a flower blooming. Behind the petals, the face wireframe is revealed (already fully formed).

**Implementation:** Each icosahedron face group gets a hinge point (outer edge midpoint) and rotation axis (tangent to the sphere). GSAP animates each face's rotation from 0° to ~150° (folded back). Faces fade out once past 90°. The face wireframe underneath fades in simultaneously.

**Pros:** Beautiful organic metaphor (blooming/flowering). One fluid motion. No morphing needed — face is pre-built.  
**Cons:** Computing hinge axes for 20 triangles requires non-trivial geometry math. Triangles can clip through each other during rotation.

### Option E: Vertex Dissolve → Face Coalesce (★★★★★ RECOMMENDED)

**How:** The icosahedron is re-rendered as a 478-vertex spherical mesh (not subdivision-2 with 162 vertices, but a custom mesh with exactly 478 vertices that approximates an icosahedron shape). Each vertex starts on a sphere surface at an icosahedron-faceted position.

On click:
1. The mesh switches from "faceted sphere" rendering to "smooth wireframe dots" rendering
2. The 478 vertices smoothly tween (via GSAP, ~1.8s, power2.inOut) from their spherical positions to the face landmark positions
3. As vertices move, the geometry deforms — the sphere collapses inward in some areas (eye sockets), pushes outward in others (nose, lips)
4. When complete, the contour edges, surface mesh, and eye nodes fade in
5. Camera pushes inward slightly during the morph

**Why this is the best approach:**
- **No seed cloud needed** — the icosahedron IS the morph source. One fewer abstraction.
- **No crack animation** — no faces splitting and drifting randomly. Just vertices moving purposefully.
- **No page navigation** — the same scene continues seamlessly.
- **One continuous motion** — all 478 vertices move in a single GSAP tween. Clean, predictable.
- **Conceptually pure** — "the geometric form reshapes into the human form." This is the original vision, executed cleanly.
- **478 vertices exactly** — matches the face landmark count by design. Fibonacci sphere distribution on the icosahedron surface gives a faceted-sphere appearance that still reads as "icosahedron."

**How to make the 478-vertex icosahedron look like an icosahedron:**
1. Generate 478 Fibonacci sphere points at radius 1.0
2. Compute the 3D convex hull of these points (or use Delaunay triangulation on the sphere)
3. Render with `flatShading: true` on a `MeshPhongMaterial` — the flat normals make each triangular face visible, creating the faceted icosahedron look
4. Render wireframe edges on top for the classic icosahedron silhouette

The key insight: the 478-point convex hull on a sphere will have ~950 triangular faces (vs the icosahedron's 20). But with flat shading, it still looks faceted — just with more facets. The wireframe overlay (contour edges with a threshold angle to skip interior edges) makes it read as "icosahedron-like."

**Alternative 478-vertex approximation (simpler):**
Instead of convex hull, just render the 478 points as a `Points` cloud with size tuned to appear solid from a distance. The point cloud reads as an icosahedron shape because of the Fibonacci sphere distribution. On click, the point size shrinks and the dots morph to face positions. This is essentially the current seed cloud approach but without a separate icosahedron — the point cloud IS the icosahedron.

**Final verdict: Option E with the point-cloud rendering approach** — simplest to implement, most fluid, and conceptually cleanest. The Fibonacci sphere points (currently the "seed cloud") become the visible icosahedron form from the start. On click, they morph to face positions in one GSAP tween. No separate icosahedron geometry needed. No cracking. No seed/face duality.

---

## Part 4: Recommended Implementation Plan

### Phase 4.1: Single-page shell + state machine

Create the new `index.html` with:
- Full-viewport canvas for 3D
- HTML overlay layer with title text + chat UI (title visible in landing state, chat visible in agent state)
- State machine: `landing → transforming → agent`
- Nav bar (hidden in landing, fades in during transformation)
- All CSS adopts robota color scheme

### Phase 4.2: 478-vertex "icosasphere" rendering

**Replaces** the current `IcosahedronGeometry(1.0, 2)` + separate seed cloud.

The 478 Fibonacci sphere points (currently `seedPoints`) become the **primary** visible geometry:
```js
// 478 Fibonacci points on unit sphere — visible from the start
const icoPoints = fibonacciSphere(478).map(p => ({
  x: p.x, y: p.y, z: p.z
}));

// Render as visible point cloud (larger dots for "solid" appearance)
const icoDotMat = new THREE.PointsMaterial({
  size: 0.04,          // larger for solid-ish look
  color: 0x00d4ff,     // cyan-blue
  blending: THREE.AdditiveBlending,
  depthWrite: false,
  transparent: true,
  opacity: 0.8,
});
const icoCloud = new THREE.Points(icoGeo, icoDotMat);

// Wireframe overlay: connect nearest neighbors to create icosahedron-like edges
const nnEdges = nearestNeighborEdges(icoPoints, 6); // k=6 gives good wireframe density
// Render these as LineSegments for the icosahedron wireframe look
```

The point cloud + neighbor wireframe together create the icosahedron visual.

### Phase 4.3: Pre-build the face wireframe (always present, hidden)

The face wireframe (contours, neighbors, eye nodes, iris nodes, mouth cavity, key node spheres — NO surface mesh) is built at init time from the loaded scan JSON. All face geometry exists in the scene from the start, with opacity 0. The face is pure wireframe — exactly like the robota avatar. No "build during animation" — everything is ready.

### Phase 4.4: The transformation (one GSAP tween)

```js
function triggerTransform() {
  if (state !== 'landing') return;
  state = 'transforming';

  // 1. Title fades out
  gsap.to('#overlay', { opacity: 0, duration: 0.5 });

  // 2. Shrink point size (sphere → dots)
  gsap.to(icoDotMat, { size: 0.02, duration: 0.3 });

  // 3. MORPH: 478 vertices move from Fibonacci sphere to face landmarks
  const morphObj = { progress: 0 };
  gsap.to(morphObj, {
    progress: 1,
    duration: 2.0,
    ease: 'power2.inOut',
    onUpdate: () => {
      const t = easeInOutCubic(morphObj.progress);
      for (let i = 0; i < 478; i++) {
        const sx = icoPoints[i].x, sy = icoPoints[i].y, sz = icoPoints[i].z;
        const fx = faceLandmarks3D[i].x, fy = faceLandmarks3D[i].y, fz = faceLandmarks3D[i].z;
        positions[i * 3]     = sx + (fx - sx) * t;
        positions[i * 3 + 1] = sy + (fy - sy) * t;
        positions[i * 3 + 2] = sz + (fz - sz) * t;
      }
      icoGeo.attributes.position.needsUpdate = true;
      // Also update all face geometry positions:
      updateFaceGeometry(positions);
    },
    onComplete: () => {
      // Snap to exact face positions
      for (let i = 0; i < 478; i++) {
        positions[i * 3]     = faceLandmarks3D[i].x;
        positions[i * 3 + 1] = faceLandmarks3D[i].y;
        positions[i * 3 + 2] = faceLandmarks3D[i].z;
      }
      icoGeo.attributes.position.needsUpdate = true;
      updateFaceGeometry(positions);
    }
  });

  // 4. Face wireframe fades in (staggered — no surface mesh)
  gsap.to(contourLines.material,  { opacity: 0.75, duration: 0.5, delay: 1.3 });
  gsap.to(neighborLines.material, { opacity: 0.45, duration: 0.5, delay: 1.5 });
  gsap.to(nodeSpheres,            { opacity: 0.9,  duration: 0.4, delay: 1.7 });
  gsap.to(eyeNodes,               { opacity: 0.95, duration: 0.4, delay: 1.8 });
  // Mouth cavity is already at target opacity (deep dark, not animated)

  // 5. Camera pushes in
  gsap.to(camera.position, { z: 4.5, duration: 2.0, delay: 0.3, ease: 'power2.inOut' });

  // 6. Chat UI fades in
  gsap.to('#agent-ui', { opacity: 1, duration: 0.6, delay: 2.2 });

  // 7. Enter agent state
  gsap.to({}, {
    delay: 2.5,
    onComplete: () => { state = 'agent'; startAutonomousBehavior(); }
  });
}
```

### Phase 4.5: Full robota feature parity

Port these systems from robota's `index.html`:
- **Mouth cavity mesh** — dark polygon behind lips so head isn't see-through
- **Key node spheres** — 24 green (`0x00ff88`) glowing dots on strategic landmarks
- **Iris nodes** — white spheres with glows at iris positions
- **Autonomous behavior** — blink (with micro-pause), gaze saccades, idle breathing
- **Mouth physics** — spring-damper jaw system with syllable oscillation when talking
- **Three-point lighting** — ambient blue + key cool white + fill blue
- **IBL environment** — PMREMGenerator + RoomEnvironment (from robota vendor)
- **Scan grid overlay** — CSS ::after pseudo-element on stage circle

### Phase 4.6: Chat + mic integration

Bring over from current `agent.html`:
- POST `/api/chat` with message
- Web Speech API for voice input
- Live mic button styling (red when recording)
- Text input + send button

Keep the same server endpoint — no changes needed to `server.py` or API.

---

## Part 5: File Changes

| File | Action | Description |
|------|--------|-------------|
| `index.html` | **Rewrite** | Single unified page: icosahedron → face → agent |
| `agent.html` | **Delete** | Content merged into index.html |
| `styles.css` | **Keep** | Only used by SelfShip app.js (not Dassein pages) |
| `app.js` | **Keep** | SelfShip pipeline (unchanged) |
| `server.py` | **Keep** | Chat API backend (unchanged) |
| `data/robota_scan.json` | **Keep** | Face scan data (unchanged) |
| `vendor/` | **Create (copy)** | Copy `three.module.js`, `RoomEnvironment.js` from robota vendor/ |
| `tests/e2e/` | **Create** | E2E test suite (see Part 6) |

---

## Part 6: E2E Testing Plan

### Test Framework: Playwright

All tests run against a local server. Test file: `tests/e2e/dassein.spec.js`

### 6.1 Landing State Tests

| # | Test | Assertion |
|---|---|---|
| T1 | Page loads without errors | No console errors, canvas renders |
| T2 | Icosahedron visible | `window.__scene.icoCloud.visible === true` |
| T3 | Face wireframe hidden | All face materials have `opacity === 0` |
| T4 | Title overlay visible | `#overlay h1` text = "Dassein" |
| T5 | Agent UI hidden | `#agent-ui` opacity = 0 or display none |
| T6 | 478 vertices exist | `icoGeo.attributes.position.count === 478` |
| T7 | Scan data loaded | `window.__scene.faceLandmarks3D.length === 478` |

### 6.2 Interaction Tests

| # | Test | Assertion |
|---|---|---|
| T8 | Hover over icosahedron changes cursor | cursor = 'pointer' |
| T9 | Click triggers transformation | `window.__scene.state === 'transforming'` |
| T10 | Rapid double-click is ignored | state stays 'transforming', no duplicate animation |
| T11 | Click elsewhere does nothing | state stays 'landing' |

### 6.3 Transformation Animation Tests

| # | Test | Assertion |
|---|---|---|
| T12 | Point size shrinks | `icoDotMat.size` transitions from 0.04 to 0.02 |
| T13 | Vertices reach exact face positions | After 2.5s, all 478 vertices match `faceLandmarks3D` within 0.001 tolerance |
| T14 | Contour lines fade in | `contourLines.material.opacity` reaches 0.75 |
| T15 | Face wireframe fully visible | All face materials have target opacity |
| T16 | Camera pushed in | `camera.position.z` transitions from 6 to ~4.5 |
| T17 | Title overlay hidden | `#overlay` opacity = 0 |
| T18 | Chat UI visible | `#agent-ui` opacity = 1 |
| T19 | State transitions to 'agent' | `window.__scene.state === 'agent'` |

### 6.4 Agent Mode Tests

| # | Test | Assertion |
|---|---|---|
| T20 | Autonomous behavior running | Face blinks within 5s (blinkFactor > 0) |
| T21 | Eye nodes update positions | Eye node positions change from initial (gaze shifts) |
| T22 | Mouth moves when idle | Micro-movements detected (mouthOpen varies) |
| T23 | Nav bar visible | Nav links present and clickable |
| T24 | Chat input accepts text | Can type and send message |
| T25 | Send button triggers API call | POST to `/api/chat` made |
| T26 | Response displays in convo | `#convo` textContent updates |
| T27 | Enter key sends message | Same as send button |
| T28 | Mic button toggles | `#micBtn` class toggles 'live' |

### 6.5 Visual Regression Tests

| # | Test | Assertion |
|---|---|---|
| T29 | Landing screenshot matches baseline | Pixel diff < 1% |
| T30 | Transform mid-frame screenshot | Positive visual change (not frozen) |
| T31 | Agent mode screenshot matches baseline | Pixel diff < 1% |
| T32 | Blue color scheme verified | Dominant colors in screenshot are cyan/blue range |

### 6.6 Performance Tests

| # | Test | Assertion |
|---|---|---|
| T33 | FPS during transformation > 30 | `window.__fps` never drops below 30 |
| T34 | FPS during agent idle > 50 | `window.__fps` stays above 50 |
| T35 | Memory stable over 30s | No continuous heap growth (leak check) |
| T36 | Animation frame time < 16ms | `performance.now()` delta per frame within budget |

### 6.7 Responsive Tests

| # | Test | Assertion |
|---|---|---|
| T37 | Mobile viewport (375px) | Stage scales correctly, touch events work |
| T38 | Tablet viewport (768px) | Stage scales correctly |
| T39 | Desktop viewport (1440px) | Stage scales correctly |
| T40 | Resize during animation | No crash, canvas resizes, camera aspect updates |

### 6.8 Playwright Test Script

```js
// tests/e2e/dassein.spec.js
const { test, expect } = require('@playwright/test');

const BASE = 'http://localhost:3000';

test.describe('Landing state', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(BASE);
    await page.waitForFunction(() => window.__scene && window.__scene.faceLandmarks3D);
  });

  test('T1-T7: Landing state integrity', async ({ page }) => {
    const state = await page.evaluate(() => ({
      state: window.__scene.state,
      vertexCount: window.__scene.icoGeo.attributes.position.count,
      faceLandmarks: window.__scene.faceLandmarks3D?.length,
      contourOpacity: window.__scene.faceContourLines?.material?.opacity,
    }));
    expect(state.state).toBe('landing');
    expect(state.vertexCount).toBe(478);
    expect(state.faceLandmarks).toBe(478);
    expect(state.contourOpacity).toBe(0);
  });

  test('T8-T9: Click triggers transform', async ({ page }) => {
    const canvas = page.locator('#scene');
    await canvas.click({ position: { x: 512, y: 384 } }); // center of 1024x768
    await page.waitForFunction(() => window.__scene.state === 'transforming');
    const state = await page.evaluate(() => window.__scene.state);
    expect(state).toBe('transforming');
  });

  test('T10: Double-click ignored', async ({ page }) => {
    const canvas = page.locator('#scene');
    await canvas.click({ position: { x: 512, y: 384 } });
    await canvas.click({ position: { x: 512, y: 384 }, delay: 100 });
    await page.waitForTimeout(200);
    const animating = await page.evaluate(() => window.__scene.isAnimating);
    expect(animating).toBe(true);
  });
});

test.describe('Transformation', () => {
  test('T12-T19: Full transform sequence', async ({ page }) => {
    await page.goto(BASE);
    await page.waitForFunction(() => window.__scene?.faceLandmarks3D);
    
    // Trigger
    await page.locator('#scene').click({ position: { x: 512, y: 384 } });
    
    // Wait for morph completion (2.5s buffer)
    await page.waitForFunction(() => window.__scene.state === 'agent', { timeout: 5000 });
    
    // Verify vertex positions match face landmarks
    const result = await page.evaluate(() => {
      const arr = window.__scene.seedPositionsArr;
      const targets = window.__scene.faceLandmarks3D;
      let maxDelta = 0;
      for (let i = 0; i < 478; i++) {
        const dx = Math.abs(arr[i * 3] - targets[i].x);
        const dy = Math.abs(arr[i * 3 + 1] - targets[i].y);
        const dz = Math.abs(arr[i * 3 + 2] - targets[i].z);
        maxDelta = Math.max(maxDelta, dx, dy, dz);
      }
      return { maxDelta, contourOpacity: window.__scene.faceContourLines?.material?.opacity };
    });
    expect(result.maxDelta).toBeLessThan(0.001);
    expect(result.contourOpacity).toBeGreaterThan(0.7);
  });
});

test.describe('Agent mode', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(BASE);
    await page.waitForFunction(() => window.__scene?.faceLandmarks3D);
    await page.locator('#scene').click({ position: { x: 512, y: 384 } });
    await page.waitForFunction(() => window.__scene.state === 'agent', { timeout: 5000 });
  });

  test('T20-T22: Autonomous behavior', async ({ page }) => {
    // Wait 6s to guarantee a blink
    await page.waitForTimeout(6000);
    const blinked = await page.evaluate(() => window.__scene.behavior?._hasBlinked || false);
    // Note: need to expose this on behavior — add _hasBlinked = true when blinkPhase > 0.5
    expect(blinked).toBe(true);
  });

  test('T24-T27: Chat functionality', async ({ page }) => {
    await page.fill('#chatInput', 'Hello');
    await page.click('#sendBtn');
    await page.waitForTimeout(1000);
    const convo = await page.textContent('#convo');
    expect(convo).not.toBe('...');
    expect(convo).not.toContain('Could not reach');
  });
});

test.describe('Performance', () => {
  test('T33: FPS during transform', async ({ page }) => {
    await page.goto(BASE);
    await page.waitForFunction(() => window.__scene?.faceLandmarks3D);
    
    // Inject FPS monitor
    await page.evaluate(() => {
      window.__fpsLog = [];
      let last = performance.now();
      let frames = 0;
      const orig = window.__scene.animate;
      // Override to capture FPS
      const measure = () => {
        frames++;
        const now = performance.now();
        if (now - last >= 500) {
          window.__fpsLog.push(Math.round(frames / ((now - last) / 1000)));
          frames = 0; last = now;
        }
      };
      // Simple interval-based FPS capture
      setInterval(() => measure(), 16);
    });
    
    await page.locator('#scene').click({ position: { x: 512, y: 384 } });
    await page.waitForFunction(() => window.__scene.state === 'agent', { timeout: 5000 });
    await page.waitForTimeout(1000);
    
    const minFps = await page.evaluate(() => Math.min(...window.__fpsLog));
    expect(minFps).toBeGreaterThan(30);
  });
});
```

### 6.9 Manual Test Checklist

| # | Test | Expected |
|---|---|---|
| M1 | Open index.html | Blue-dark background, cyan point-cloud icosahedron rotating, "Dassein" title, "click the form" pulsing |
| M2 | Hover icosahedron | Cursor → pointer, glow intensifies |
| M3 | Click icosahedron | Points shrink, then smoothly morph into face wireframe shape |
| M4 | During morph | Camera pushes in, title fades out |
| M5 | After morph | Face wireframe fully visible, contours clear, eyes/nose/mouth recognizable |
| M6 | Agent mode active | Chat UI visible below face, "the questioner" with pulsing cyan dot |
| M7 | Face animates | Blinks every few seconds, eyes shift gaze, mouth has micro-movements |
| M8 | Type question, Enter | Response appears, face mouth moves while "talking" |
| M9 | Click mic | Mic activates (red border), speak, text appears and sends |
| M10 | Nav links | Click "home" → page resets to landing state. Click "blogs" → goes to blogs.html |
| M11 | Mobile | Works on iOS Safari / Chrome. Touch triggers transform. Stage scales. |
| M12 | Refresh on agent state | Face loads directly in agent mode (skip transform if desired) |

---

## Part 7: Build Order (Sequenced)

### Stage A: Foundation (Files: index.html rewrite)
1. Strip out old icosahedron geometry (WireframeGeometry, EdgesGeometry, face groups)
2. Copy robota CSS: colors, stage styling, scan grid overlay, button/input styles, background gradient
3. Set up state machine (landing / transforming / agent)
4. Add HTML: overlay layer + agent UI layer + nav bar
5. Copy robota 3D setup: PMREMGenerator, three-point lighting, camera configuration

### Stage B: 478-Vertex Icosasphere (Files: index.html)
6. Replace IcosahedronGeometry with Fibonacci 478-point cloud
7. Add nearest-neighbor edge rendering on top for wireframe look
8. Adjust point size/opacity for solid appearance at distance
9. Verify rotation and hover behavior still works

### Stage C: Pre-built Face Wireframe (Files: index.html)
10. At init, build all face geometry (contours, neighbors, nodes, iris, mouth cavity — NO surface mesh)
11. Set all materials to opacity 0
12. Add to scene but keep invisible
13. Verify face geometry is correct by temporarily setting opacity to 1

### Stage D: The Transformation (Files: index.html)
14. Write `triggerTransform()` — one GSAP tween on 478 vertices
15. Wire camera push-in
16. Wire face wireframe fade-in (staggered opacities)
17. Wire title fade-out + chat UI fade-in
18. Handle edge: state guard (no double-trigger)
19. Add `updateFaceGeometry()` helper that copies morph buffer to all face sub-geometries

### Stage E: Agent Mode (Files: index.html)
20. Port AutonomousBehavior class from robota (blink, gaze, breath)
21. Port MouthPhysics class (spring-damper jaw)
22. Port animateWorkingBuffer (blink, gaze, mouth deformation)
23. Add RAF loop that runs behavior + updates geometry + renders
24. Port chat functionality (POST /api/chat, mic, send)
25. Port nav bar behavior (reset to landing on "home" click)

### Stage F: Polish (Files: index.html)
26. Add a "reset" mechanism: clicking "home" in nav returns to landing state
27. Handle resize for all renderers (main + background)
28. Add FPS monitor for development
29. Mobile viewport adjustments
30. Keyboard shortcut: Escape returns to landing

### Stage G: E2E Tests (Files: tests/e2e/dassein.spec.js)
31. Set up Playwright config
32. Write landing state tests (T1-T7)
33. Write interaction tests (T8-T11)
34. Write transformation tests (T12-T19)
35. Write agent mode tests (T20-T28)
36. Write performance tests (T33-T36)
37. Write responsive tests (T37-T40)
38. Run full suite, fix failures

---

## Part 8: Key Technical Decisions

| Decision | Rationale |
|----------|-----------|
| 478-vertex point cloud IS the icosahedron | Eliminates the seed/icosahedron duality. One geometry, one morph target. No separate objects to coordinate. |
| Face wireframe pre-built at init | Avoids building geometry during animation (causes frame drops). Everything is ready, just opacity-tweened in. |
| Single GSAP tween for morph | One interpolation variable drives all 478 vertices. Consistent timing, no phase coordination bugs. |
| State machine over boolean flags | `landing → transforming → agent` is clearer than multiple booleans. Easy to add more states later. |
| Robota AutonomousBehavior class | Proven, tested, handles blink timing + gaze + mouth. No need to reinvent. |
| Mouth cavity mesh | Essential for realism — without it, when the mouth opens during speech you see through the head. |
| IBL lighting | PMREMGenerator + RoomEnvironment gives natural reflections on the surface mesh. Makes the face look less flat. |
| Playwright for E2E | Can test WebGL canvas (via evaluate), network requests, DOM state, and take screenshots. Better than iframe-based tests. |
| No build step | Keep everything CDN/vendor-loaded. Single HTML file. No bundler, no framework. |

---

## Part 9: What the User Will Experience

**Landing on dassein.io:**
1. Deep blue-black space with subtle radial gradient
2. A cyan-blue point-cloud sphere (reading as icosahedron) rotates at center
3. "Dassein" in elegant type, "a clearing" in cursive below
4. "click the form" softly pulses
5. Hovering: cursor turns to pointer, glow intensifies

**Clicking the form:**
6. The point cloud's dots shrink slightly
7. All 478 dots begin moving — flowing from a sphere into a face shape
8. The transition is smooth, organic — like a face emerging from geometric noise
9. Eye sockets indent, nose pushes forward, lips define themselves
10. The contoured wireframe fades in over the dots
11. Key nodes glow green at strategic landmarks
12. The camera pushes in closer to the face
13. The title fades away

**Now the agent is alive:**
14. The face blinks naturally every few seconds
15. Eyes shift gaze, as if looking around
16. The mouth has subtle micro-movements (breathing)
17. A cyan pulsing dot appears below: "the questioner"
18. A chat bar fades in: "Ask me something..."
19. Type a question, the face's mouth animates with the response
20. Click mic to speak instead
21. The nav bar at top: home | agent | blogs
22. Click "home" to return to the icosahedron (reset)

**The entire experience is seamless — one page, one scene, one continuous transformation.**
