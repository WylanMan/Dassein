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
    expect(result.maxDelta).toBeLessThan(0.001);
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

  test('T24-T27: Chat functionality', async ({ page }) => {
    await page.fill('#chatInput', 'Hello');
    await page.click('#sendBtn');
    await page.waitForTimeout(1500);
    const convo = await page.textContent('#convo');
    expect(convo).not.toBe('...');
    expect(convo).not.toContain('Could not reach');
  });
});

test.describe('Reset to landing', () => {
  test('Escape key resets to landing', async ({ page }) => {
    await page.goto(BASE);
    await page.waitForFunction(() => window.__scene?.faceLandmarks3D);
    await page.locator('#scene').click({ position: { x: 512, y: 384 } });
    await page.waitForFunction(() => window.__scene.state === 'agent', { timeout: 8000 });

    await page.keyboard.press('Escape');
    await page.waitForTimeout(2500);

    const state = await page.evaluate(() => window.__scene.state);
    expect(state).toBe('landing');
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
