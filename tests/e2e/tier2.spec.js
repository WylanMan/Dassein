const { test, expect } = require('@playwright/test');

const BASE = 'http://localhost:3000';

async function enterAgent(page) {
  await page.goto(BASE);
  await page.waitForFunction(() => window.__scene?.faceLandmarks3D);
  await page.locator('#scene').click({ position: { x: 512, y: 384 } });
  await page.waitForFunction(() => window.__scene.state === 'agent', { timeout: 8000 });
}

test.describe('Tier 2 client pipeline', () => {
  test('S18: compound + curated specs build 478 verts and morph clean (no API)', async ({ page }) => {
    await enterAgent(page);

    // Fixture compound spec.
    const compound = await page.evaluate(async () => {
      await window.__testHooks.spawnObject({
        id: 'fixture_chalice',
        parts: [
          { type: 'goblet', pos: [0, 0.1, 0] },
          { type: 'cylinder', pos: [0, -0.45, 0], scale: [0.9, 0.35, 0.9] },
          { type: 'cylinder', pos: [0, -0.15, 0], scale: [0.3, 0.45, 0.3] },
        ],
      }, undefined, { force: true });
      const t = window.__testHooks.shapeTargets;
      return {
        count: t.length,
        finite: t.every(p => Number.isFinite(p.x) && Number.isFinite(p.y) && Number.isFinite(p.z)),
        edgeCount: window.__testHooks.shapeTargetEdgeIndices.length,
        shape: window.__testHooks.currentShape,
        specParts: window.__scene.spec.parts.length,
      };
    });
    expect(compound.count).toBe(478);
    expect(compound.finite).toBe(true);
    expect(compound.edgeCount).toBeGreaterThan(0);
    expect(compound.shape).toBe('fixture_chalice');
    expect(compound.specParts).toBe(3);

    // Curated spec.
    const curated = await page.evaluate(async () => {
      const id = await window.__testHooks.spawnCurated('hourglass');
      const t = window.__testHooks.shapeTargets;
      return {
        id,
        count: t.length,
        finite: t.every(p => Number.isFinite(p.x) && Number.isFinite(p.y) && Number.isFinite(p.z)),
        edgeCount: window.__testHooks.shapeTargetEdgeIndices.length,
        specId: window.__scene.spec?.id,
      };
    });
    expect(curated.id).toBe('hourglass');
    expect(curated.count).toBe(478);
    expect(curated.finite).toBe(true);
    expect(curated.edgeCount).toBeGreaterThan(0);
    expect(curated.specId).toBe('hourglass');

    // Alias resolution ("stone arch" -> arch).
    const alias = await page.evaluate(() => window.__testHooks.getCuratedSpec('stone arch')?.id);
    expect(alias).toBe('arch');
  });

  test('S20: summon_object voice tool end-to-end (stub DeepSeek)', async ({ page }) => {
    await enterAgent(page);

    const result = await page.evaluate(async () => {
      const msg = await window.agentAvatar.realtime._tools.summon_object({ concept: 'widget' });
      const t = window.__testHooks.shapeTargets;
      return {
        msg,
        count: t.length,
        finite: t.every(p => Number.isFinite(p.x) && Number.isFinite(p.y) && Number.isFinite(p.z)),
        edgeCount: window.__testHooks.shapeTargetEdgeIndices.length,
        spec: window.__scene.spec,
      };
    });
    expect(result.msg).toContain('Summoned widget');
    expect(result.count).toBe(478);
    expect(result.finite).toBe(true);
    expect(result.edgeCount).toBeGreaterThan(0);
    expect(result.spec.id).toBe('widget');
    expect(result.spec.type).toBe('goblet'); // stub returns a goblet spec
  });

  test('S23: face-as-loading — summon wears a contemplation face, then morphs to shape', async ({ page }) => {
    await enterAgent(page);

    // Start the summon without awaiting it; the stub sleeps 2.5s so the
    // in-flight contemplation state is observable. (Concept avoids every
    // curated alias so it routes to the LLM tier, not the fast path.)
    const promise = page.evaluate(() =>
      window.agentAvatar.realtime._tools.summon_object({ concept: 'slow_reliquary' }));

    let sawFace = false;
    for (let i = 0; i < 25; i++) {
      const shape = await page.evaluate(() => window.__testHooks.currentShape);
      if (shape === 'face') { sawFace = true; break; }
      await page.waitForTimeout(100);
    }
    expect(sawFace).toBe(true);

    const msg = await promise;
    expect(msg).toContain('Summoned slow_reliquary');

    // Spec arrival runs the standard face -> shape morph.
    await page.waitForFunction(() => window.__testHooks.currentShape === 'slow_reliquary', { timeout: 5000 });
    const result = await page.evaluate(() => ({
      shape: window.__testHooks.currentShape,
      count: window.__testHooks.shapeTargets.length,
      specType: window.__scene.spec?.type,
      finite: window.__testHooks.shapeTargets.every(p =>
        Number.isFinite(p.x) && Number.isFinite(p.y) && Number.isFinite(p.z)),
    }));
    expect(result.shape).toBe('slow_reliquary');
    expect(result.count).toBe(478);
    expect(result.specType).toBe('goblet');
    expect(result.finite).toBe(true);
  });
});
