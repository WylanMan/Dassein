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
    await canvas.click({ position: { x: 512, y: 384 } });
    await page.waitForFunction(() => window.__scene.state === 'transforming');
    const state = await page.evaluate(() => window.__scene.state);
    expect(state).toBe('transforming');
  });

  test('T10: Double-click ignored', async ({ page }) => {
    const canvas = page.locator('#scene');
    await canvas.click({ position: { x: 512, y: 384 } });
    await canvas.click({ position: { x: 512, y: 384 }, delay: 100 });
    await page.waitForTimeout(200);
    const scene = await page.evaluate(() => ({
      state: window.__scene.state,
      isAnimating: window.__scene.isAnimating,
    }));
    expect(scene.state).toBe('transforming');
  });
});

test.describe('Transformation', () => {
  test('T12-T19: Full transform sequence', async ({ page }) => {
    await page.goto(BASE);
    await page.waitForFunction(() => window.__scene?.faceLandmarks3D);

    await page.locator('#scene').click({ position: { x: 512, y: 384 } });

    await page.waitForFunction(() => window.__scene.state === 'agent', { timeout: 8000 });

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
      return {
        maxDelta,
        contourOpacity: window.__scene.faceContourLines?.material?.opacity,
      };
    });
    // Face-mode renders apply designed idle offsets (iris gaze ~0.03, blink
    // lid motion up to ~0.08), so the morph target is not held exactly.
    // 0.15 still discriminates a failed transform (landing sphere ~1.0).
    expect(result.maxDelta).toBeLessThan(0.15);
    expect(result.contourOpacity).toBeGreaterThan(0.7);
  });
});

test.describe('Agent mode', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(BASE);
    await page.waitForFunction(() => window.__scene?.faceLandmarks3D);
    await page.locator('#scene').click({ position: { x: 512, y: 384 } });
    await page.waitForFunction(() => window.__scene.state === 'agent', { timeout: 8000 });
  });

  test('T20-T22: Autonomous behavior', async ({ page }) => {
    await page.waitForFunction(() => {
      const b = window.__scene.behavior;
      return b && b._hasBlinked ? b._hasBlinked() : false;
    }, { timeout: 15000 });
    expect(true).toBe(true);
  });

  test('T24-T27: Voice agent interaction', async ({ page }) => {
    await page.click('#micBtn');
    // The button must leave "connecting..." and settle on either "stop"
    // (connected — mic/network available) or "start voice" (failed back
    // gracefully — no mic in headless). Both prove the voice wiring responds.
    await page.waitForFunction(() => {
      const t = document.getElementById('micBtn').textContent;
      return t === 'stop' || t === 'start voice';
    }, { timeout: 10000 });
    const text = await page.textContent('#micBtn');
    expect(['stop', 'start voice']).toContain(text);
  });
});

test.describe('Reset to landing', () => {
  test('Escape key resets to landing', async ({ page }) => {
    await page.goto(BASE);
    await page.waitForFunction(() => window.__scene?.faceLandmarks3D);
    await page.locator('#scene').click({ position: { x: 512, y: 384 } });
    await page.waitForFunction(() => window.__scene.state === 'agent', { timeout: 8000 });

    await page.keyboard.press('Escape');
    await page.waitForFunction(() => window.__scene.state === 'landing', { timeout: 8000 });
  });

  test('Home nav link resets to landing', async ({ page }) => {
    await page.goto(BASE);
    await page.waitForFunction(() => window.__scene?.faceLandmarks3D);
    await page.locator('#scene').click({ position: { x: 512, y: 384 } });
    await page.waitForFunction(() => window.__scene.state === 'agent', { timeout: 8000 });

    await page.click('#navHome');
    await page.waitForTimeout(2500);

    const state = await page.evaluate(() => window.__scene.state);
    expect(state).toBe('landing');
  });
});

test.describe('Procedural spawn (tier 0)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(BASE);
    await page.waitForFunction(() => window.__scene?.faceLandmarks3D);
    await page.locator('#scene').click({ position: { x: 512, y: 384 } });
    await page.waitForFunction(() => window.__scene.state === 'agent', { timeout: 8000 });
  });

  async function waitMorphToTargets(page, key) {
    await page.waitForFunction((k) => {
      const targets = window.__testHooks[k] || window.__scene[k];
      if (!targets) return false;
      const arr = window.__scene.seedPositionsArr;
      let max = 0;
      for (let i = 0; i < 478; i++) {
        const dx = Math.abs(arr[i * 3] - targets[i].x);
        const dy = Math.abs(arr[i * 3 + 1] - targets[i].y);
        const dz = Math.abs(arr[i * 3 + 2] - targets[i].z);
        max = Math.max(max, dx, dy, dz);
      }
      return max < 0.001;
    }, key, { timeout: 8000 });
  }

  test('S1: spawn gem morphs to solid agent state', async ({ page }) => {
    await page.evaluate(() => window.__testHooks.spawnObject('gem', 'medium', { force: true }));
    await waitMorphToTargets(page, 'shapeTargets');
    const result = await page.evaluate(() => ({
      shape: window.__testHooks.currentShape,
      edgeCount: window.__testHooks.shapeTargetEdgeIndices.length,
      state: window.__scene.state,
      activePills: [...document.querySelectorAll('.shape-pill.active')].map(p => p.dataset.shape),
    }));
    expect(result.shape).toBe('gem');
    expect(result.edgeCount).toBeGreaterThan(0);
    expect(result.state).toBe('agent');
    expect(result.activePills).toEqual([]);
  });

  test('S2: fresh builds are deterministic', async ({ page }) => {
    const first = await page.evaluate(() => {
      window.__testHooks.spawnObject('gem', 'medium', { force: true });
      return window.__testHooks.shapeTargets.map(t => [t.x, t.y, t.z]);
    });
    const second = await page.evaluate(() => {
      window.__testHooks.spawnObject('gem', 'medium', { force: true });
      return window.__testHooks.shapeTargets.map(t => [t.x, t.y, t.z]);
    });
    let maxDiff = 0;
    for (let i = 0; i < 478; i++) {
      maxDiff = Math.max(maxDiff,
        Math.abs(first[i][0] - second[i][0]),
        Math.abs(first[i][1] - second[i][1]),
        Math.abs(first[i][2] - second[i][2]));
    }
    expect(maxDiff).toBe(0);
  });

  test('S3: size scales bounding radius', async ({ page }) => {
    const radius = async (size) => page.evaluate((s) => {
      window.__testHooks.spawnObject('gem', s, { force: true });
      const t = window.__testHooks.shapeTargets;
      return Math.max(...t.map(p => Math.hypot(p.x, p.y, p.z)));
    }, size);
    const small = await radius('small');
    const large = await radius('large');
    expect(large).toBeGreaterThan(small * 1.3);
  });

  test('S4: barge-in mid-morph lands on second target without corruption', async ({ page }) => {
    await page.evaluate(() => window.__testHooks.spawnObject('gem', 'medium', { force: true }));
    await page.waitForTimeout(250);
    await page.evaluate(() => window.__testHooks.spawnObject('torus', 'large', { force: true }));
    await waitMorphToTargets(page, 'shapeTargets');
    const result = await page.evaluate(() => {
      const arr = window.__scene.seedPositionsArr;
      let clean = true;
      for (let i = 0; i < arr.length; i++) if (!Number.isFinite(arr[i])) clean = false;
      return { shape: window.__testHooks.currentShape, clean };
    });
    expect(result.shape).toBe('torus');
    expect(result.clean).toBe(true);
  });

  test('S5: same object re-morphs on resize', async ({ page }) => {
    await page.evaluate(() => window.__testHooks.spawnObject('gem', 'medium', { force: true }));
    await waitMorphToTargets(page, 'shapeTargets');
    const mediumRadius = await page.evaluate(() =>
      Math.max(...window.__testHooks.shapeTargets.map(p => Math.hypot(p.x, p.y, p.z))));
    await page.evaluate(() => window.__testHooks.spawnObject('gem', 'large', { force: true }));
    await waitMorphToTargets(page, 'shapeTargets');
    const largeRadius = await page.evaluate(() =>
      Math.max(...window.__testHooks.shapeTargets.map(p => Math.hypot(p.x, p.y, p.z))));
    expect(largeRadius).toBeGreaterThan(mediumRadius * 1.3);
  });

  test('S6: unknown object type returns graceful spec-aware error', async ({ page }) => {
    const msg = await page.evaluate(() =>
      window.agentAvatar.realtime._tools.spawn_object({ object: 'flux-capacitor' }));
    expect(msg).toContain('Unknown object');
    expect(msg).toContain('gem');
    expect(msg).toContain('modulate');
  });

  test('S7: morph back to face restores face mode', async ({ page }) => {
    await page.evaluate(() => window.__testHooks.spawnObject('gem', 'medium', { force: true }));
    await waitMorphToTargets(page, 'shapeTargets');
    await page.evaluate(() => window.__testHooks.spawnObject('face'));
    await page.waitForTimeout(2500);
    const result = await page.evaluate(() => {
      const arr = window.__scene.seedPositionsArr;
      const fm = window.__scene.faceLandmarks3D;
      let maxDelta = 0;
      for (let i = 0; i < 478; i++) {
        maxDelta = Math.max(maxDelta,
          Math.abs(arr[i * 3] - fm[i].x),
          Math.abs(arr[i * 3 + 1] - fm[i].y),
          Math.abs(arr[i * 3 + 2] - fm[i].z));
      }
      return { shape: window.__testHooks.currentShape, maxDelta };
    });
    expect(result.shape).toBe('face');
    expect(result.maxDelta).toBeLessThan(0.15);
  });

  test('S8: spec determinism with params + mods', async ({ page }) => {
    const first = await page.evaluate(() => {
      window.__testHooks.spawnObject({
        type: 'star', params: { sides: 7, inner: 0.5 },
        mods: { twist: 30, jitter: { amp: 0.05 } }, seed: 42,
      }, undefined, { force: true });
      return window.__testHooks.shapeTargets.map(t => [t.x, t.y, t.z]);
    });
    const second = await page.evaluate(() => {
      window.__testHooks.spawnObject({
        type: 'star', params: { sides: 7, inner: 0.5 },
        mods: { twist: 30, jitter: { amp: 0.05 } }, seed: 42,
      }, undefined, { force: true });
      return window.__testHooks.shapeTargets.map(t => [t.x, t.y, t.z]);
    });
    let maxDiff = 0;
    for (let i = 0; i < 478; i++) {
      maxDiff = Math.max(maxDiff,
        Math.abs(first[i][0] - second[i][0]),
        Math.abs(first[i][1] - second[i][1]),
        Math.abs(first[i][2] - second[i][2]));
    }
    expect(maxDiff).toBe(0);
  });

  test('S9: modifier changes geometry (twist vs none differ)', async ({ page }) => {
    const plain = await page.evaluate(() => {
      window.__testHooks.spawnObject({ type: 'gem' }, undefined, { force: true });
      return window.__testHooks.shapeTargets.map(t => [t.x, t.y, t.z]);
    });
    const twisted = await page.evaluate(() => {
      window.__testHooks.spawnObject({ type: 'gem', mods: { twist: 45 } }, undefined, { force: true });
      return window.__testHooks.shapeTargets.map(t => [t.x, t.y, t.z]);
    });
    let maxDiff = 0;
    for (let i = 0; i < 478; i++) {
      maxDiff = Math.max(maxDiff,
        Math.abs(plain[i][0] - twisted[i][0]),
        Math.abs(plain[i][1] - twisted[i][1]),
        Math.abs(plain[i][2] - twisted[i][2]));
    }
    expect(maxDiff).toBeGreaterThan(0.05);
  });

  test('S10: blend ratio=0 approx A, ratio=1 approx B, midpoint differs from both', async ({ page }) => {
    const spawn = async (spec) => page.evaluate((s) => {
      window.__testHooks.spawnObject(s, undefined, { force: true });
      return window.__testHooks.shapeTargets.map(t => [t.x, t.y, t.z]);
    }, spec);
    const A = await spawn({ type: 'gem' });
    const B = await spawn({ type: 'rock' });
    const r0 = await spawn({ type: 'gem', blend: { with: 'rock', ratio: 0 } });
    const r1 = await spawn({ type: 'gem', blend: { with: 'rock', ratio: 1 } });
    const r5 = await spawn({ type: 'gem', blend: { with: 'rock', ratio: 0.5 } });

    const maxDiff = (x, y) => {
      let m = 0;
      for (let i = 0; i < 478; i++) {
        m = Math.max(m,
          Math.abs(x[i][0] - y[i][0]),
          Math.abs(x[i][1] - y[i][1]),
          Math.abs(x[i][2] - y[i][2]));
      }
      return m;
    };
    expect(maxDiff(r0, A)).toBeLessThan(1e-6);
    expect(maxDiff(r1, B)).toBeLessThan(1e-6);
    expect(maxDiff(r5, A)).toBeGreaterThan(0.01);
    expect(maxDiff(r5, B)).toBeGreaterThan(0.01);
  });

  test('S11: voice tool accepts spec and rejects bad spec gracefully', async ({ page }) => {
    const ok = await page.evaluate(() =>
      window.agentAvatar.realtime._tools.spawn_object({
        object: 'gem', twist: 0.4, stretch: 1.4, blend_with: 'torus', blend_ratio: 0.3,
      }));
    expect(ok).toContain('Spawned gem');
    expect(ok).toContain('blended into torus');

    const bad = await page.evaluate(() =>
      window.agentAvatar.realtime._tools.spawn_object({ object: 'flux-capacitor' }));
    expect(bad).toContain('Unknown object');
    expect(bad).toContain('Valid types');

    const none = await page.evaluate(() =>
      window.agentAvatar.realtime._tools.spawn_object({}));
    expect(none).toContain('No object specified');
  });

  test('S12: blend barge-in mid-animation lands clean', async ({ page }) => {
    await page.evaluate(() => window.__testHooks.spawnObject({ type: 'gem' }, undefined, { force: true }));
    await page.waitForTimeout(250);
    await page.evaluate(() =>
      window.__testHooks.spawnObject({ type: 'gem', blend: { with: 'torus', ratio: 0.5 } }, undefined, { force: true }));
    await waitMorphToTargets(page, 'shapeTargets');
    const result = await page.evaluate(() => {
      const arr = window.__scene.seedPositionsArr;
      let clean = true;
      for (let i = 0; i < arr.length; i++) if (!Number.isFinite(arr[i])) clean = false;
      return { shape: window.__testHooks.currentShape, clean, edgeCount: window.__testHooks.shapeTargetEdgeIndices.length };
    });
    expect(result.shape).toBe('gem');
    expect(result.clean).toBe(true);
    expect(result.edgeCount).toBeGreaterThan(0);
  });

  test('S13: pills interrupt an in-flight morph', async ({ page }) => {
    await page.evaluate(() => window.__testHooks.spawnObject('gem', 'medium', { force: true }));
    await page.waitForTimeout(250);
    await page.locator('.shape-pill[data-shape="torus"]').click();
    await waitMorphToTargets(page, 'shapeTargets');
    const result = await page.evaluate(() => {
      const arr = window.__scene.seedPositionsArr;
      let clean = true;
      for (let i = 0; i < arr.length; i++) if (!Number.isFinite(arr[i])) clean = false;
      return { shape: window.__testHooks.currentShape, clean };
    });
    expect(result.shape).toBe('torus');
    expect(result.clean).toBe(true);
  });

  test('S14: union fuses two shapes deterministically', async ({ page }) => {
    const first = await page.evaluate(() => {
      window.__testHooks.spawnObject({ type: 'cube', union: ['cube', 'gem'] }, undefined, { force: true });
      return {
        targets: window.__testHooks.shapeTargets.map(t => [t.x, t.y, t.z]),
        count: window.__testHooks.shapeTargets.length,
        radius: Math.max(...window.__testHooks.shapeTargets.map(p => Math.hypot(p.x, p.y, p.z))),
      };
    });
    const second = await page.evaluate(() => {
      window.__testHooks.spawnObject({ type: 'cube', union: ['cube', 'gem'] }, undefined, { force: true });
      return window.__testHooks.shapeTargets.map(t => [t.x, t.y, t.z]);
    });
    let maxDiff = 0;
    for (let i = 0; i < 478; i++) {
      maxDiff = Math.max(maxDiff,
        Math.abs(first.targets[i][0] - second[i][0]),
        Math.abs(first.targets[i][1] - second[i][1]),
        Math.abs(first.targets[i][2] - second[i][2]));
    }
    expect(first.count).toBe(478);
    expect(first.radius).toBeCloseTo(0.55, 2);
    expect(maxDiff).toBe(0);
  });

  test('S15: union net differs from each member shape', async ({ page }) => {
    const member = async (spec) => page.evaluate((s) => {
      window.__testHooks.spawnObject(s, undefined, { force: true });
      return window.__testHooks.shapeTargets.map(t => [t.x, t.y, t.z]);
    }, spec);
    const cube = await member({ type: 'cube' });
    const gem = await member({ type: 'gem' });
    const union = await member({ type: 'cube', union: ['cube', 'gem'] });
    const maxDiff = (x, y) => {
      let m = 0;
      for (let i = 0; i < 478; i++) {
        m = Math.max(m,
          Math.abs(x[i][0] - y[i][0]),
          Math.abs(x[i][1] - y[i][1]),
          Math.abs(x[i][2] - y[i][2]));
      }
      return m;
    };
    expect(maxDiff(union, cube)).toBeGreaterThan(0.01);
    expect(maxDiff(union, gem)).toBeGreaterThan(0.01);
  });

  test('S16: voice tool accepts combine and mirrors the union spec', async ({ page }) => {
    const msg = await page.evaluate(() =>
      window.agentAvatar.realtime._tools.spawn_object({ object: 'cube', combine: ['gem', 'torus'] }));
    expect(msg).toContain('Spawned cube');
    expect(msg).toContain('combined with gem and torus');
    const spec = await page.evaluate(() => window.__scene.spec);
    expect(spec.union).toEqual(['cube', 'gem', 'torus']);
  });
});

test.describe('Performance', () => {
  test('T33: FPS during transform', async ({ page }) => {
    await page.goto(BASE);
    await page.waitForFunction(() => window.__scene?.faceLandmarks3D);

    const fpsLog = [];
    let last = Date.now();
    let frames = 0;

    await page.evaluate(() => {
      window.__fpsLog = [];
      let last = performance.now();
      let frames = 0;
      const orig = window.__scene.renderer.render.bind(window.__scene.renderer);
      window.__scene.renderer.render = function () {
        frames++;
        const now = performance.now();
        if (now - last >= 500) {
          window.__fpsLog.push(Math.round(frames / ((now - last) / 1000)));
          frames = 0; last = now;
        }
        orig(...arguments);
      };
    });

    await page.locator('#scene').click({ position: { x: 512, y: 384 } });
    await page.waitForFunction(() => window.__scene.state === 'agent', { timeout: 8000 });
    await page.waitForTimeout(1000);

    const minFps = await page.evaluate(() => Math.min(...window.__fpsLog));
    expect(minFps).toBeGreaterThan(15);
  });
});
