// Unit tests for sdf-core.mjs — the pure SDF kernel, run in isolation with
// plain Node (no framework): `node tests/unit/sdf-core.test.mjs`.
//
// Covers what the browser E2E can't isolate: exact surface conformity,
// determinism, ray-miss fill coverage, op-catalog errors, and the 25ms build
// gate, all measured headless.

import { compileSdf, targetsFromSDF, referenceDirs } from '../../sdf-core.mjs';

let failures = 0;
function assert(cond, msg) {
  if (!cond) { failures++; console.error('  FAIL:', msg); }
}
function assertNear(a, b, tol, msg) {
  if (Math.abs(a - b) > tol) { failures++; console.error(`  FAIL: ${msg} (got ${a}, want ${b} ±${tol})`); }
}

const SHAPES = {
  sphere: { op: 'sphere', r: 1 },
  box: { op: 'box', size: [1.6, 1.6, 1.6] },
  cone: { op: 'cone', r: 0.8, h: 1.6 },
  pyramid: { op: 'pyramid', n: 4, r: 0.8, h: 1.6 },
  gem: { op: 'gem', r: 1 },
  torus: { op: 'torus', R: 0.8, r: 0.3 },
  hourglass: { op: 'revolve', profile: [[-1, 0.05], [-0.7, 0.55], [-0.4, 0.12], [0, 0.07], [0.4, 0.12], [0.7, 0.55], [1, 0.05]] },
  crown: {
    op: 'union', children: [
      { op: 'torus', R: 0.7, r: 0.22 },
      { op: 'polar_repeat', n: 6, child: { op: 'translate', t: [0.7, -0.05, 0], child: { op: 'cone', r: 0.18, h: 0.7 } } },
    ],
  },
  rock: { op: 'rock', r: 1, seed: 3 },
  crystal: { op: 'crystal', r: 0.6, h: 1.8, seed: 7 },
  chair: {
    op: 'union', children: [
      { op: 'box', size: [1.2, 0.12, 1.2] },
      { op: 'translate', t: [0, 0.55, 0], child: { op: 'box', size: [1.2, 0.95, 0.12] } },
      { op: 'translate', t: [-0.5, 0.2, 0], child: { op: 'box', size: [0.12, 0.85, 0.12] } },
      { op: 'translate', t: [0.5, 0.2, 0], child: { op: 'box', size: [0.12, 0.85, 0.12] } },
    ],
  },
};

console.log('sdf-core unit tests');

// Reference directions: 478, unit length, deterministic ordering.
assert(referenceDirs.length === 478, 'referenceDirs has 478 entries');
assert(referenceDirs.every(d => Math.abs(Math.hypot(d.x, d.y, d.z) - 1) < 1e-9), 'referenceDirs are unit vectors');
assertNear(referenceDirs[0].x, 0, 1e-9, 'referenceDirs[0] x = 0');
assertNear(referenceDirs[0].y, 1, 1e-9, 'referenceDirs[0] is +y (fibonacci ordering, i=0)');
// Second point: y = 1 - 2/477, theta = phi.
assertNear(referenceDirs[1].y, 1 - 2 / 477, 1e-9, 'referenceDirs[1] y matches fibonacciSphere');

// Every shape: exactly 478 finite points, each on its SDF surface, radius sane.
for (const [name, root] of Object.entries(SHAPES)) {
  const res = targetsFromSDF(root, 0);
  assert(res.targets.length === 478, `${name}: 478 points`);
  assert(res.targets.every(p => Number.isFinite(p.x) && Number.isFinite(p.y) && Number.isFinite(p.z)), `${name}: finite`);
  const d = compileSdf(root, 0);
  let surfErr = 0;
  for (const p of res.targets) surfErr = Math.max(surfErr, Math.abs(d(p.x, p.y, p.z)));
  assert(surfErr < 0.01, `${name}: points on surface (|d|max=${surfErr.toFixed(4)})`);
  assert(res.radius > 0.05, `${name}: non-degenerate radius (${res.radius.toFixed(3)})`);
}

// Order-aligned (miss=0) fixtures: index i is exactly the surface along d_i.
const a = targetsFromSDF(SHAPES.sphere, 0);
const b = targetsFromSDF(SHAPES.box, 0);
for (let i = 0; i < 478; i++) {
  const dir = referenceDirs[i];
  const pa = a.targets[i], pb = b.targets[i];
  const crossA = (pa.x * dir.y - pa.y * dir.x) ** 2 + (pa.y * dir.z - pa.z * dir.y) ** 2 + (pa.z * dir.x - pa.x * dir.z) ** 2;
  const crossB = (pb.x * dir.y - pb.y * dir.x) ** 2 + (pb.y * dir.z - pb.z * dir.y) ** 2 + (pb.z * dir.x - pb.x * dir.z) ** 2;
  assert(crossA < 1e-9 && crossB < 1e-9, `sphere/box point ${i} lies along direction ${i}`);
}

// Determinism: identical spec + seed -> identical net.
const d1 = targetsFromSDF(SHAPES.hourglass, 42);
const d2 = targetsFromSDF(SHAPES.hourglass, 42);
let maxDiff = 0;
for (let i = 0; i < 478; i++) {
  maxDiff = Math.max(maxDiff,
    Math.abs(d1.targets[i].x - d2.targets[i].x),
    Math.abs(d1.targets[i].y - d2.targets[i].y),
    Math.abs(d1.targets[i].z - d2.targets[i].z));
}
assert(maxDiff === 0, 'hourglass deterministic');

// Miss-fill: hollow forms still produce a full, spread net.
const t = targetsFromSDF(SHAPES.torus, 0);
assert(t.missCount > 0, 'torus has ray misses');
let minR = Infinity, maxR = 0;
for (const p of t.targets) {
  const l = Math.hypot(p.x, p.y, p.z);
  minR = Math.min(minR, l); maxR = Math.max(maxR, l);
}
assert(maxR - minR > 0.3, 'torus fill spans inner+outer wall (not collapsed)');
assertNear(maxR, 1.1, 0.02, 'torus outer radius = R + r');

// Grammar errors degrade loudly (client falls back, never crashes).
let threw = false;
try { targetsFromSDF({ op: 'nope' }, 0); } catch (e) { threw = true; assert(/Unknown SDF op/.test(e.message), 'unknown op error message'); }
assert(threw, 'unknown op throws');
threw = false;
try { targetsFromSDF({ op: 'union', children: [{ op: 'sphere', r: 1 }] }, 0); } catch (e) { threw = true; }
assert(threw, 'union with <2 children throws');

// Perf gate: star-shaped build < 25ms on average.
const times = [];
for (let i = 0; i < 6; i++) {
  const s0 = performance.now();
  targetsFromSDF(SHAPES.crown, i);
  times.push(performance.now() - s0);
}
const avg = times.reduce((x, y) => x + y, 0) / times.length;
assert(avg < 25, `build < 25ms (got ${avg.toFixed(1)}ms avg)`);

if (failures) {
  console.error(`\n${failures} assertion(s) failed`);
  process.exit(1);
}
console.log('  all assertions passed');
