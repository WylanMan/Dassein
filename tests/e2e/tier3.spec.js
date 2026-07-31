const { test, expect } = require('@playwright/test');

const BASE = 'http://localhost:3000';

// Fixtures for the order-aligned morph property. Both are star-shaped from the
// origin (zero ray misses), so every index i keeps meaning "the surface point
// along canonical direction d_i" and the per-index morph is coherent.
const FIX_A = { op: 'box', size: [1.6, 1.6, 1.6] };
const FIX_B = { op: 'gem', r: 1 };
const FIX_HOURGLASS = { op: 'revolve', profile: [[-1, 0.05], [-0.7, 0.55], [-0.4, 0.12], [0, 0.07], [0.4, 0.12], [0.7, 0.55], [1, 0.05]] };
const FIX_TORUS = { op: 'torus', R: 0.8, r: 0.3 };

async function load(page) {
  await page.goto(BASE);
  await page.waitForFunction(() => window.__scene?.faceLandmarks3D);
}

test.describe('Tier 3 v2 SDF pipeline', () => {
  test('S18v2: v2 specs build 478 ordered, finite, on-surface points', async ({ page }) => {
    await load(page);

    const hourglass = await page.evaluate((root) => {
      const { targets, missCount } = window.__testHooks.buildSdfTargets(root);
      return {
        count: targets.length,
        finite: targets.every(p => Number.isFinite(p.x) && Number.isFinite(p.y) && Number.isFinite(p.z)),
        miss: missCount,
        radiusMax: Math.max(...targets.map(p => Math.hypot(p.x, p.y, p.z))),
      };
    }, FIX_HOURGLASS);
    expect(hourglass.count).toBe(478);
    expect(hourglass.finite).toBe(true);
    expect(hourglass.miss).toBe(0);
    expect(hourglass.radiusMax).toBeCloseTo(0.55, 1);

    // Miss-fill path (hollow/ring forms): still exactly 478 valid points.
    const torus = await page.evaluate((root) => {
      const { targets, missCount } = window.__testHooks.buildSdfTargets(root);
      return {
        count: targets.length,
        finite: targets.every(p => Number.isFinite(p.x) && Number.isFinite(p.y) && Number.isFinite(p.z)),
        miss: missCount,
        span: Math.max(...targets.map(p => Math.hypot(p.x, p.y, p.z))) -
              Math.min(...targets.map(p => Math.hypot(p.x, p.y, p.z))),
      };
    }, FIX_TORUS);
    expect(torus.count).toBe(478);
    expect(torus.finite).toBe(true);
    expect(torus.miss).toBeGreaterThan(0); // rays through the hole
    expect(torus.span).toBeGreaterThan(0.2); // full surface captured, not a collapsed ring

    // Morph-through the real pipeline: spawn a v2 spec as a shape.
    const spawn = await page.evaluate(async (root) => {
      await window.__testHooks.spawnObject({ id: 'sdf_hourglass', schema: 2, root }, undefined, { force: true });
      const t = window.__testHooks.shapeTargets;
      return {
        shape: window.__testHooks.currentShape,
        count: t.length,
        edgeCount: window.__testHooks.shapeTargetEdgeIndices.length,
        specSchema: window.__scene.spec?.schema,
      };
    }, FIX_HOURGLASS);
    expect(spawn.shape).toBe('sdf_hourglass');
    expect(spawn.count).toBe(478);
    expect(spawn.edgeCount).toBeGreaterThan(0);
    expect(spawn.specSchema).toBe(2);
  });

  test('S18v2b: v2 builds are deterministic (same spec + seed -> identical net)', async ({ page }) => {
    await load(page);

    const first = await page.evaluate((root) => {
      window.__testHooks.buildSdfTargets(root, 42);
      const { targets } = window.__testHooks.buildSdfTargets(root, 42);
      return targets.map(t => [t.x, t.y, t.z]);
    }, FIX_HOURGLASS);
    const second = await page.evaluate((root) => {
      const { targets } = window.__testHooks.buildSdfTargets(root, 42);
      return targets.map(t => [t.x, t.y, t.z]);
    }, FIX_HOURGLASS);

    let maxDiff = 0;
    for (let i = 0; i < 478; i++) {
      maxDiff = Math.max(maxDiff,
        Math.abs(first[i][0] - second[i][0]),
        Math.abs(first[i][1] - second[i][1]),
        Math.abs(first[i][2] - second[i][2]));
    }
    expect(maxDiff).toBe(0);
  });

  test('S22: order-aligned morph property — per-index travel stays bounded at t=0.5', async ({ page }) => {
    await load(page);

    const result = await page.evaluate(([a, b]) => {
      const A = window.__testHooks.buildSdfTargets(a).targets;
      const B = window.__testHooks.buildSdfTargets(b).targets;
      let minMidRadius = Infinity;
      let minCos = 1;
      for (let i = 0; i < A.length; i++) {
        const mx = (A[i].x + B[i].x) / 2, my = (A[i].y + B[i].y) / 2, mz = (A[i].z + B[i].z) / 2;
        minMidRadius = Math.min(minMidRadius, Math.hypot(mx, my, mz));
        const la = Math.hypot(A[i].x, A[i].y, A[i].z) || 1e-6;
        const lb = Math.hypot(B[i].x, B[i].y, B[i].z) || 1e-6;
        const cos = (A[i].x * B[i].x + A[i].y * B[i].y + A[i].z * B[i].z) / (la * lb);
        minCos = Math.min(minCos, cos);
      }
      return { minMidRadius, minCos };
    }, [FIX_A, FIX_B]);

    // No point crosses the volume center at mid-morph.
    expect(result.minMidRadius).toBeGreaterThan(0.15);
    // Per-index directions stay coherent (< ~60 deg) — the morph is a smooth
    // resurface, not a crumpled index remap.
    expect(result.minCos).toBeGreaterThan(0.5);
  });

  test('perf: v2 build stays under 25ms (the Phase-1 gate)', async ({ page }) => {
    await load(page);

    const ms = await page.evaluate((root) => {
      // Warm up JIT, then measure the cold build.
      window.__testHooks.buildSdfTargets({ op: 'sphere', r: 1 }, 0);
      const t0 = performance.now();
      const count = 8;
      for (let i = 0; i < count; i++) window.__testHooks.buildSdfTargets(root, i);
      return (performance.now() - t0) / count;
    }, {
      op: 'union',
      children: [
        { op: 'revolve', profile: [[-1, 0.05], [-0.7, 0.55], [-0.4, 0.12], [0, 0.07], [0.4, 0.12], [0.7, 0.55], [1, 0.05]] },
        { op: 'translate', t: [0, 0.9, 0], child: { op: 'cone', r: 0.5, h: 0.6 } },
        { op: 'translate', t: [0, -0.9, 0], child: { op: 'cone', r: 0.5, h: 0.6 } },
      ],
    });

    expect(ms).toBeLessThan(25);
  });
});
