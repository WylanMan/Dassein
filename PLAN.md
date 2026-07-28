# Dassein — Scroll-Driven Rotation + Face Auto-Correction Plan

## Goal

Replace the hardcoded autonomous tumble with scroll-driven rotation:
1. **Landing state (globe/icosahedron):** Slow continuous auto-rotate. User scroll (horizontal) adds spin velocity with inertial decay. Globe never stops — it always rotates, user input just adds energy.
2. **Agent state (face):** No auto-rotate. Face faces forward by default. User scroll rotates it temporarily. After 1.5s of no input, it springs back to center using two-zone correction (quick glances snap back fast; deliberate look-aways return slowly).
3. **All rendered objects** share the same `icoGroup` rotation, so the mechanic works on the globe, the face, and any future geometry.
4. **Horizontal scroll** maps to left/right Y-axis rotation. Trackpad swipe, shift+scroll, and regular mouse wheel all work.

## Gap Analysis (issues found and fixed)

| # | Gap | Fix |
|---|-----|-----|
| 1 | Body `overflow:hidden` means no native scrollbar. Wheel events work but `preventDefault` must not conflict. | Use `{passive: false}` on wheel listener. Call `preventDefault()` only on the canvas element, not window. |
| 2 | Regular mice have no horizontal scroll — only vertical wheel. | Fallback: if `deltaX === 0` and no shift key, map `deltaY` to rotation. Shift+scroll also works. |
| 3 | Touch events could conflict with the click-to-transform raycaster. | Differentiate tap (< 5px movement, < 300ms) from swipe (> 5px movement). Only rotate on swipe. Tap still triggers transform. |
| 4 | During the 2-second GSAP transform animation, scroll input would fight the morph. | Disable scroll input when `isAnimating === true`. Buffer is unnecessary — just ignore. |
| 5 | Damping `0.92^60 ≈ 0.007` after 1 second — too fast, rotation feels dead. | Use `0.96` damping (half-life ~0.9s). Velocity halves every 17 frames at 60fps. After 3s, velocity is 0.96^180 ≈ 0.0006 — essentially gone. |
| 6 | No `prefers-reduced-motion` check. | Add check: if user prefers reduced motion, disable scroll rotation entirely. Globe still auto-rotates at 10% speed. |
| 7 | `scrollend` event not universally supported for wheel-based scrolling. | Use velocity dead-zone: when `abs(spinVelocity) < 0.0005` for 3 consecutive frames, treat as "scroll stopped". |
| 8 | Vertical scroll could zoom the camera, but this is a nice-to-have that adds complexity. | Defer zoom to a future phase. For now, all scroll input (horizontal and vertical) maps to Y rotation. |
| 9 | Face sway (breathing) at lines 798-803 fights with scroll rotation. | When `faceScrollActive || faceSpringActive`, suppress breathing sway. Resume sway only when face is at rest (offset < 0.002). |
| 10 | Camera Z position is currently animated by GSAP (z: 4.5 in agent, z: 6 in landing). Scroll zoom would conflict. | Don't modify camera Z with scroll for now. GSAP camera animations in transform remain un-touched. |
| 11 | Reset to landing (Escape key, nav click) should also reset scroll state. | `resetToLanding()` calls `scrollController.reset()`. |
| 12 | Frame-rate independence: `dt` varies. Damping formula must be independent of frame rate. | Use `Math.pow(damping, dt * 60)` pattern — same decay feel at 30fps, 60fps, or 120fps. |
| 13 | Safari 30fps Low Power Mode cap — damping still works correctly due to frame-rate-independent formula. | No special Safari code needed. The `dt * 60` normalization handles it. |
| 14 | Multiple simultaneous inputs (trackpad + touch). | Track velocity per input source. Use a single `spinVelocity` accumulator — whereever the delta comes from, it adds to the same variable. |
| 15 | Face iris positions relative to rotated group. | Iris nodes are children of icoGroup — they rotate with it. No change needed. |
| 16 | Edge wireframe and point cloud are both children of `icoGroup` — they rotate together naturally. | No change needed. |

## File to Modify

**Single file:** `index.html` — all changes are within the existing `<script type="module">` block (lines 155-1384). No new files. No new dependencies.

---

## Implementation Steps

### Step 1: Add `prefers-reduced-motion` check (insert after line 156)

Location: After `import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';` (line 157), before `const NUM = 478;` (line 159).

Insert:
```javascript
const REDUCED_MOTION = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
```

---

### Step 2: Insert ScrollController module (insert after line 186, before `let scanData = null;`)

Location: After `let state = 'landing';` (line 186), before `// --- Wave 1: Deformation weights` (line 188).

Insert the full ScrollController:

```javascript
    // ═══ Scroll-Driven Rotation Controller ═══
    const ScrollController = (() => {
      // ── Configuration ──
      const CFG = {
        // Globe auto-rotate speeds (radians per frame at 60fps)
        globeSpeedX: 0.0008,    // was 0.003 — 3.75x slower
        globeSpeedY: 0.0015,    // was 0.005 — 3.3x slower
        globeSpeedZ: 0.0003,    // was 0.001 — 3.3x slower

        // Reduced-motion overrides (10% of normal)
        reducedGlobeSpeedX: 0.00008,
        reducedGlobeSpeedY: 0.00015,
        reducedGlobeSpeedZ: 0.00003,

        // Scroll sensitivity
        scrollFactor: 0.004,       // delta → spinVelocity multiplier
        fallbackMouseFactor: 0.003, // slightly less sensitive for regular mouse wheel fallback

        // Inertia damping per frame at 60fps (higher = longer glide)
        // 0.96 → half-life ~0.9s → velocity halves every 17 frames
        damping: 0.96,

        // Velocity clamps
        maxSpinVelocity: 2.5,      // rad/sec cap (~143°/sec)
        velocityDeadZone: 0.0005,  // below this, treated as stopped

        // Face spring-back
        faceIdleDelay: 1500,       // ms before spring-back starts
        faceSpringFast: 0.06,      // lerp rate for small angles (< threshold)
        faceSpringSlow: 0.02,      // lerp rate for large angles (≥ threshold)
        faceZoneThreshold: 0.35,   // radians (~20°) — boundary between fast/slow spring
        faceSnapThreshold: 0.001,  // snap to 0 when this close
        faceRestThreshold: 0.002,  // below this, face is "at rest" (sway resumes)

        // Touch gesture detection
        tapMaxMovement: 5,         // px — less than this = tap, not swipe
        tapMaxDuration: 300,       // ms — shorter than this = tap
      };

      // ── State ──
      let spinVelocity = 0;          // current rotational velocity from user input
      let globeAngleY = 0;          // accumulated Y rotation in globe mode
      let faceOffsetY = 0;          // user-driven Y rotation in face mode
      let faceSpringActive = false;
      let faceSpringTimer = null;
      let lastScrollTime = 0;
      let consecutiveStillFrames = 0;
      let enabled = !REDUCED_MOTION;  // disabled entirely for reduced-motion users

      // Touch state
      let touchStartX = 0;
      let touchStartY = 0;
      let touchStartTime = 0;
      let touchActive = false;
      let touchPrevX = 0;

      function handleWheel(e) {
        if (!enabled) return;
        if (typeof isAnimating !== 'undefined' && isAnimating) return;
        if (REDUCED_MOTION) return;

        e.preventDefault();

        let delta = 0;
        let isTrackpad = false;

        // Detect trackpad: pixel-level deltas, or very small line/page deltas
        if (e.deltaMode === WheelEvent.DOM_DELTA_PIXEL) {
          isTrackpad = true;
          delta = e.deltaX;
          // If no horizontal delta, use shift+vertical as horizontal
          if (Math.abs(delta) < 0.01 && e.shiftKey) {
            delta = e.deltaY;
          }
          // Fallback: if still no horizontal, use vertical (mouse wheel with no shift)
          if (Math.abs(delta) < 0.01) {
            delta = e.deltaY;
            isTrackpad = false;
          }
        } else {
          // Line or page scroll — likely a mouse wheel
          delta = e.deltaX;
          if (Math.abs(delta) < 0.01 && e.shiftKey) {
            delta = e.deltaY;
          }
          if (Math.abs(delta) < 0.01) {
            delta = e.deltaY;
          }
        }

        const factor = isTrackpad ? CFG.scrollFactor : CFG.fallbackMouseFactor;
        const addition = Math.sign(delta) * Math.min(Math.abs(delta) * factor, 0.15);

        spinVelocity += addition;
        spinVelocity = Math.max(-CFG.maxSpinVelocity, Math.min(CFG.maxSpinVelocity, spinVelocity));

        lastScrollTime = performance.now();
        consecutiveStillFrames = 0;

        // Cancel face spring-back on new input
        if (faceSpringActive) {
          faceSpringActive = false;
        }
        if (faceSpringTimer) {
          clearTimeout(faceSpringTimer);
          faceSpringTimer = null;
        }
      }

      function handleTouchStart(e) {
        if (!enabled) return;
        if (typeof isAnimating !== 'undefined' && isAnimating) return;
        if (REDUCED_MOTION) return;
        if (e.touches.length !== 1) return; // ignore multi-touch

        touchStartX = e.touches[0].clientX;
        touchStartY = e.touches[0].clientY;
        touchPrevX = touchStartX;
        touchStartTime = performance.now();
        touchActive = true;

        e.preventDefault();
      }

      function handleTouchMove(e) {
        if (!touchActive) return;
        e.preventDefault();

        const x = e.touches[0].clientX;
        const dx = x - touchPrevX;
        touchPrevX = x;

        if (Math.abs(dx) > 0.5) {
          spinVelocity += dx * 0.004;
          spinVelocity = Math.max(-CFG.maxSpinVelocity, Math.min(CFG.maxSpinVelocity, spinVelocity));
          lastScrollTime = performance.now();
          consecutiveStillFrames = 0;

          if (faceSpringActive) faceSpringActive = false;
          if (faceSpringTimer) { clearTimeout(faceSpringTimer); faceSpringTimer = null; }
        }
      }

      function handleTouchEnd(e) {
        if (!touchActive) return;
        touchActive = false;

        const totalDx = (e.changedTouches[0]?.clientX || touchPrevX) - touchStartX;
        const totalDy = (e.changedTouches[0]?.clientY || touchStartY) - touchStartY;
        const duration = performance.now() - touchStartTime;
        const distance = Math.sqrt(totalDx * totalDx + totalDy * totalDy);

        // If it was a tap (short, small movement), don't consume — let click handler fire
        if (distance < CFG.tapMaxMovement && duration < CFG.tapMaxDuration) {
          touchActive = false;
          return;
        }

        // Otherwise, prevent the click that would follow
        e.preventDefault();
      }

      function update(dt) {
        if (REDUCED_MOTION) {
          // Reduced motion: only slow auto-rotate, no scroll input
          globeAngleY += CFG.reducedGlobeSpeedY * dt * 60;
          return;
        }

        // ── Damping ──
        spinVelocity *= Math.pow(CFG.damping, dt * 60);

        // Dead zone: snap very small velocities to 0
        if (Math.abs(spinVelocity) < CFG.velocityDeadZone) {
          spinVelocity = 0;
          consecutiveStillFrames++;
        } else {
          consecutiveStillFrames = 0;
        }

        // ── Globe mode ──
        if (state === 'landing') {
          globeAngleY += (CFG.globeSpeedY + spinVelocity) * dt * 60;
        }

        // ── Face mode ──
        if (state === 'agent') {
          faceOffsetY += spinVelocity * dt * 60;

          // Start spring-back timer when scroll has truly stopped
          // (velocity at 0 for 3+ consecutive frames AND 1.5s elapsed)
          const scrolledRecently = (performance.now() - lastScrollTime) < CFG.faceIdleDelay;
          const velocityDead = spinVelocity === 0 && consecutiveStillFrames >= 3;

          if (!scrolledRecently && velocityDead && !faceSpringActive) {
            faceSpringActive = true;
          }

          // Apply spring-back
          if (faceSpringActive) {
            const absOffset = Math.abs(faceOffsetY);

            // Two-zone spring rate
            const springRate = absOffset < CFG.faceZoneThreshold
              ? CFG.faceSpringFast   // < 20°: quick return (glances)
              : CFG.faceSpringSlow;  // ≥ 20°: slow return (deliberate looks)

            faceOffsetY += (0 - faceOffsetY) * springRate * dt * 60;

            // Snap when very close to center
            if (absOffset < CFG.faceSnapThreshold) {
              faceOffsetY = 0;
              faceSpringActive = false;
              consecutiveStillFrames = 0;
            }
          }
        }
      }

      function isFaceAtRest() {
        return Math.abs(faceOffsetY) < CFG.faceRestThreshold && !faceSpringActive;
      }

      function isFaceScrolling() {
        return Math.abs(spinVelocity) > CFG.velocityDeadZone || faceSpringActive;
      }

      function reset() {
        spinVelocity = 0;
        globeAngleY = 0;
        faceOffsetY = 0;
        faceSpringActive = false;
        consecutiveStillFrames = 0;
        lastScrollTime = 0;
        if (faceSpringTimer) {
          clearTimeout(faceSpringTimer);
          faceSpringTimer = null;
        }
      }

      // Expose for use in animate()
      return {
        get spinVelocity() { return spinVelocity; },
        get globeAngleY() { return globeAngleY; },
        get faceOffsetY() { return faceOffsetY; },
        get faceSpringActive() { return faceSpringActive; },
        get enabled() { return enabled; },
        get CFG() { return CFG; },
        handleWheel,
        handleTouchStart,
        handleTouchMove,
        handleTouchEnd,
        update,
        isFaceAtRest,
        isFaceScrolling,
        reset,
      };
    })();
```

---

### Step 3: Replace landing rotation in `animate()` (lines 730-735)

**Remove** these 6 lines:
```javascript
      // --- Landing rotation ---
      if (state === 'landing') {
        icoGroup.rotation.x += 0.003;
        icoGroup.rotation.y += 0.005;
        icoGroup.rotation.z += 0.001;
      }
```

**Replace with:**
```javascript
      // --- Scroll-driven rotation ---
      ScrollController.update(dt);

      if (state === 'landing') {
        icoGroup.rotation.x += ScrollController.CFG.globeSpeedX;
        icoGroup.rotation.y = ScrollController.globeAngleY;
        icoGroup.rotation.z += ScrollController.CFG.globeSpeedZ;
      }
```

---

### Step 4: Modify agent-mode head rotation (lines 792-803)

**Find** lines 792-803:
```javascript
        // --- Head group animation (F11/F15) ---
        const headMotion = HeadMotion.update(dt);
        if (headMotion && icoGroup) {
          icoGroup.rotation.y += (headMotion.yaw * 0.5 - icoGroup.rotation.y) * Math.min(1, dt * 2.5);
          icoGroup.rotation.x += (headMotion.pitch * 0.3 - icoGroup.rotation.x) * Math.min(1, dt * 2);
          icoGroup.rotation.z += (headMotion.roll * 0.3 - icoGroup.rotation.z) * Math.min(1, dt * 2);
        } else if (icoGroup && state === 'agent') {
          const swayAmp = 0.6;
          const sway = (Math.sin(t * 0.4) * 0.05 + Math.sin(t * 0.23) * 0.03) * swayAmp;
          icoGroup.rotation.y += (sway - icoGroup.rotation.y) * Math.min(1, dt * 2);
          icoGroup.rotation.x += (Math.sin(t * 0.31) * 0.02 * swayAmp - icoGroup.rotation.x) * Math.min(1, dt * 2);
        }
```

**Replace with:**
```javascript
        // --- Head group animation (F11/F15) — scroll-aware ---
        const scrollY = ScrollController.faceOffsetY;
        const scrolling = ScrollController.isFaceScrolling();
        const atRest = ScrollController.isFaceAtRest();

        const headMotion = HeadMotion.update(dt);
        if (headMotion && icoGroup) {
          // Head motion yaw layered on top of scroll offset
          const headYaw = headMotion.yaw * 0.5;
          icoGroup.rotation.y = scrollY + headYaw;
          icoGroup.rotation.x += (headMotion.pitch * 0.3 - icoGroup.rotation.x) * Math.min(1, dt * 2);
          icoGroup.rotation.z += (headMotion.roll * 0.3 - icoGroup.rotation.z) * Math.min(1, dt * 2);
        } else if (icoGroup && state === 'agent') {
          if (atRest) {
            // Face is at rest — gentle breathing sway (original behavior)
            const swayAmp = 0.6;
            const sway = (Math.sin(t * 0.4) * 0.05 + Math.sin(t * 0.23) * 0.03) * swayAmp;
            icoGroup.rotation.y = sway;  // sway replaces, not adds to, Y rotation at rest
            icoGroup.rotation.x += (Math.sin(t * 0.31) * 0.02 * swayAmp - icoGroup.rotation.x) * Math.min(1, dt * 2);
          } else if (scrolling) {
            // User is scrolling or spring-back is active — set rotation directly
            icoGroup.rotation.y = scrollY;
            // X rotation slowly drifts to 0 to avoid tilted face
            icoGroup.rotation.x += (0 - icoGroup.rotation.x) * Math.min(1, dt * 1.5);
          } else {
            // Intermediate: blend toward resting sway
            const swayAmp = 0.6;
            const sway = (Math.sin(t * 0.4) * 0.05 + Math.sin(t * 0.23) * 0.03) * swayAmp;
            icoGroup.rotation.y += (sway - icoGroup.rotation.y) * Math.min(1, dt * 2);
            icoGroup.rotation.x += (Math.sin(t * 0.31) * 0.02 * swayAmp - icoGroup.rotation.x) * Math.min(1, dt * 2);
          }
        }
```

---

### Step 5: Add `ScrollController.reset()` in `triggerTransform()` (line 553)

**Find** line 553:
```javascript
      // Reset accumulated landing rotation so face aligns with world
      icoGroup.rotation.set(0, 0, 0);
```

**Replace with:**
```javascript
      // Reset accumulated rotation so face aligns with world
      icoGroup.rotation.set(0, 0, 0);
      ScrollController.reset();
```

---

### Step 6: Add `ScrollController.reset()` in `resetToLanding()` (after line 608)

**Find** line 608:
```javascript
      if (state === 'landing' || isAnimating) return;
      isAnimating = true;
```

**Replace with:**
```javascript
      if (state === 'landing' || isAnimating) return;
      isAnimating = true;
      ScrollController.reset();
```

---

### Step 7: Register event listeners (insert after line 809, before `// --- Raycasting ---`)

Location: After `requestAnimationFrame(animate);` (line 809), before `// --- Raycasting ---` (line 811).

Insert:
```javascript

    // ═══ Scroll & Touch Listeners ═══
    canvas.addEventListener('wheel', (e) => ScrollController.handleWheel(e), { passive: false });

    canvas.addEventListener('touchstart', (e) => ScrollController.handleTouchStart(e), { passive: false });
    canvas.addEventListener('touchmove', (e) => ScrollController.handleTouchMove(e), { passive: false });
    canvas.addEventListener('touchend', (e) => ScrollController.handleTouchEnd(e), { passive: false });

    // Prevent the canvas from being a scroll target at the browser level
    canvas.addEventListener('wheel', (e) => {
      if (ScrollController.enabled && (typeof isAnimating === 'undefined' || !isAnimating)) {
        e.preventDefault();
      }
    }, { passive: false });
```

Note: The wheel listener is intentionally registered twice — the first calls `handleWheel` for the rotation logic, the second is the `preventDefault` guard that must run even if the controller itself decides to skip the frame (e.g., during animation). Actually, this is redundant since `handleWheel` already calls `preventDefault`. Simplify to just one listener.

**Revised insertion (single listener approach):**

```javascript

    // ═══ Scroll & Touch Listeners ═══
    canvas.addEventListener('wheel', (e) => {
      if (ScrollController.enabled && !isAnimating && !REDUCED_MOTION) {
        e.preventDefault();
        ScrollController.handleWheel(e);
      }
    }, { passive: false });

    canvas.addEventListener('touchstart', (e) => {
      if (ScrollController.enabled && !isAnimating && !REDUCED_MOTION) {
        ScrollController.handleTouchStart(e);
      }
    }, { passive: false });

    canvas.addEventListener('touchmove', (e) => {
      if (ScrollController.enabled && !isAnimating && !REDUCED_MOTION) {
        ScrollController.handleTouchMove(e);
      }
    }, { passive: false });

    canvas.addEventListener('touchend', (e) => {
      if (ScrollController.enabled && !isAnimating && !REDUCED_MOTION) {
        ScrollController.handleTouchEnd(e);
      }
    }, { passive: false });
```

---

### Step 8: Update `resetToLanding()` camera Z handling

In `resetToLanding()`, lines 672-673, the camera Z animates back to 6:
```javascript
      // Restore camera
      gsap.to(camera.position, { z: 6, duration: 1.2, ease: 'power2.inOut' });
```

This stays as-is — we are NOT touching camera Z with scroll zoom in this phase.

---

### Step 9: Handle `prefers-reduced-motion` changes at runtime

After the initial `REDUCED_MOTION` check in Step 1, also listen for runtime changes:

```javascript
    window.matchMedia('(prefers-reduced-motion: reduce)').addEventListener('change', (e) => {
      if (e.matches) {
        ScrollController.reset();
      }
    });
```

Insert this after the event listeners block (after Step 7's insertion).

---

## Verification Checklist

After implementation, verify each bullet point:

### Globe Mode (Landing State)
- [ ] Globe auto-rotates at visibly slower speed than before (about 1/3 the original)
- [ ] Horizontal trackpad swipe (two fingers left/right) rotates the globe horizontally
- [ ] Shift + mouse wheel rotates the globe horizontally
- [ ] Regular mouse wheel (no shift) rotates the globe horizontally as fallback
- [ ] After scrolling stops, inertia carries the globe briefly before settling
- [ ] Globe never fully stops — auto-rotate continues even after inertia decays
- [ ] X and Z auto-rotate continue independently of scroll
- [ ] Tap on the globe still triggers the transform to face (touch tap = < 5px movement, < 300ms)

### Face Mode (Agent State)
- [ ] Face faces forward (0° Y rotation) by default after transform completes
- [ ] Horizontal scroll rotates the face left and right
- [ ] After ~1.5 seconds of no scroll input, the face begins springing back to center
- [ ] Small rotations (< ~20°) snap back quickly (~0.5s to settle)
- [ ] Large rotations (≥ ~20°) drift back slowly (~2s to settle)
- [ ] New scroll input immediately cancels the spring-back
- [ ] When face is at rest, breathing sway resumes
- [ ] When face is scrolling or springing, sway is suppressed
- [ ] Escape key resets to globe: rotation resets, scroll state resets

### Transitions
- [ ] Clicking globe to transform: rotation resets to (0,0,0), face appears centered
- [ ] During the 2-second transform animation, scroll input is ignored
- [ ] Escape / nav home to reset: rotation resets, globe auto-rotate resumes

### Reduced Motion
- [ ] When `prefers-reduced-motion: reduce` is active, scroll rotation is disabled
- [ ] Globe still auto-rotates at 10% speed
- [ ] If setting changes at runtime (e.g., user toggles accessibility setting), state resets

### Mobile / Touch
- [ ] Single-finger horizontal swipe rotates the globe/face
- [ ] Tap triggers transform (same as click)
- [ ] Multi-touch is ignored (no pinch zoom implemented yet)

### Performance
- [ ] No jank at 60fps
- [ ] Damping behaves identically at 30fps, 60fps, 120fps
- [ ] No memory leaks from event listeners

---

## Parameter Tuning Guide

All tuning values are in `ScrollController.CFG` (Step 2). Adjust these to change feel:

| Parameter | Default | Effect of increasing | Effect of decreasing |
|-----------|---------|---------------------|---------------------|
| `globeSpeedY` | `0.0015` | Faster auto-rotate | Slower auto-rotate |
| `scrollFactor` | `0.004` | More responsive scroll | Less responsive, heavier feel |
| `damping` | `0.96` | Longer inertia glide | Shorter, snappier stop |
| `maxSpinVelocity` | `2.5` | Faster max spin | Lower speed ceiling |
| `faceIdleDelay` | `1500` | Longer before spring-back | Quicker return |
| `faceSpringFast` | `0.06` | Snappier small-angle return | More gradual return |
| `faceSpringSlow` | `0.02` | Faster large-angle return | Slower, more respectful |
| `faceZoneThreshold` | `0.35` | More angles treated as "deliberate look-away" | More treated as "quick glance" |

To preview a parameter change without reimplementing: set `CFG.damping = 0.98` for a much longer glide, or `CFG.scrollFactor = 0.008` for more responsive scroll.

---

## Future Phases (out of scope)

- **Scroll zoom:** Map vertical scroll with no shift to camera Z. Requires GSAP coordination.
- **Smooth camera easing:** Currently camera Z is set directly by GSAP during transforms. Could smooth-scroll between z positions.
- **Pinch-to-zoom:** Two-finger pinch on trackpad/touchscreen → camera Z.
- **Mouse drag rotation:** Click-drag to rotate (currently only scroll, not drag).
- **Visual scroll indicator:** A subtle UI hint that the object is scroll-able.
- **Lock Y rotation:** Allow user to "lock" the face at a rotated angle (double-click or long-press).
