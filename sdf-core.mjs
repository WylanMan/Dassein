// sdf-core.js — pure SDF kernel for the Tier-3 shape grammar (Phase 1).
//
// Compiles a v2 `root` tree into a signed-distance closure, then samples the
// outer surface by radial probing along 478 canonical reference directions
// (the exact fibonacci ordering of the landing sphere). Index i always means
// "the surface point along direction d_i", so shape<->shape morphs lerp
// coherently. No marching cubes, no weld, no FPS in the common (star-shaped)
// case: exactly 478 ordered points, <5ms per build.
//
// Ray misses (holes / concave directions with no sign change) fall back to a
// deterministic seeded-FPS over a dense surface probe — the same resampling
// the v1 net builders use. Deterministic: `seed` touches only noise ops; the
// net itself is seed-free.

const NUM = 478;
const TAU = Math.PI * 2;
const DEPTH_MAX = 5;
const NODE_MAX = 32;

// ─── Reference directions ─────────────────────────────────────────────────
// Identical ordering to index.html's fibonacciSphere(478) — index i must mean
// the same direction here as it does for the landing sphere and face net.

export function fibonacciSphere(n) {
  const pts = []; const phi = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < n; i++) {
    const y = 1 - (i / (n - 1)) * 2;
    const r = Math.sqrt(1 - y * y);
    const theta = phi * i;
    pts.push({ x: Math.cos(theta) * r, y, z: Math.sin(theta) * r });
  }
  return pts;
}

export const referenceDirs = fibonacciSphere(NUM);

// Dense probe set for the ray-miss fallback — a distinct fibonacci set so the
// samples don't coincide with the canonical directions.
function denseDirs(n) {
  const pts = []; const phi = Math.PI * (3 - Math.sqrt(5)) * 1.618;
  for (let i = 0; i < n; i++) {
    const y = 1 - (i / (n - 1)) * 2;
    const r = Math.sqrt(1 - y * y);
    const theta = phi * i;
    pts.push({ x: Math.cos(theta) * r, y, z: Math.sin(theta) * r });
  }
  return pts;
}

// ─── Deterministic noise ───────────────────────────────────────────────────

function len3(x, y, z) { return Math.sqrt(x * x + y * y + z * z); }

function hash3(x, y, z, seed) {
  let h = seed ^ Math.imul(x, 374761393) ^ Math.imul(y, 668265263) ^ Math.imul(z, 1274126177);
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  h = h ^ (h >>> 16);
  return (h >>> 0) / 4294967296;
}

// Smooth 3D value noise over the integer lattice — a pure function of
// position, so ray tracing stays deterministic and convergible.
function smoothNoise(px, py, pz, seed) {
  const x0 = Math.floor(px), y0 = Math.floor(py), z0 = Math.floor(pz);
  const fx = px - x0, fy = py - y0, fz = pz - z0;
  const sx = fx * fx * (3 - 2 * fx), sy = fy * fy * (3 - 2 * fy), sz = fz * fz * (3 - 2 * fz);
  const n000 = hash3(x0, y0, z0, seed), n100 = hash3(x0 + 1, y0, z0, seed);
  const n010 = hash3(x0, y0 + 1, z0, seed), n110 = hash3(x0 + 1, y0 + 1, z0, seed);
  const n001 = hash3(x0, y0, z0 + 1, seed), n101 = hash3(x0 + 1, y0, z0 + 1, seed);
  const n011 = hash3(x0, y0 + 1, z0 + 1, seed), n111 = hash3(x0 + 1, y0 + 1, z0 + 1, seed);
  const nx00 = n000 + (n100 - n000) * sx, nx10 = n010 + (n110 - n010) * sx;
  const nx01 = n001 + (n101 - n001) * sx, nx11 = n011 + (n111 - n011) * sx;
  const nxy0 = nx00 + (nx10 - nx00) * sy, nxy1 = nx01 + (nx11 - nx01) * sy;
  return nxy0 + (nxy1 - nxy0) * sz;
}

// Directional cell hash — a pure function of the point's direction. Used by
// facet() so each angular patch of the surface shifts as one (the low-poly
// look).
function dirCellHash(dx, dy, dz, levels, seed) {
  return hash3(Math.round(dx * levels), Math.round(dy * levels), Math.round(dz * levels), seed);
}

// Worley / cellular noise: distance to the nearest random feature point.
function worley(px, py, pz, seed) {
  const xi = Math.floor(px), yi = Math.floor(py), zi = Math.floor(pz);
  let best = Infinity;
  for (let dx = -1; dx <= 1; dx++) {
    for (let dy = -1; dy <= 1; dy++) {
      for (let dz = -1; dz <= 1; dz++) {
        const cx = xi + dx, cy = yi + dy, cz = zi + dz;
        const rx = cx + hash3(cx, cy, cz, seed);
        const ry = cy + hash3(cx, cy, cz, seed + 101);
        const rz = cz + hash3(cx, cy, cz, seed + 202);
        const ddx = px - rx, ddy = py - ry, ddz = pz - rz;
        const d = ddx * ddx + ddy * ddy + ddz * ddz;
        if (d < best) best = d;
      }
    }
  }
  return Math.sqrt(best);
}

// ─── 2D helpers (profiles) ─────────────────────────────────────────────────

function catmullRom(pts, samplesPerSeg) {
  const out = [];
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[Math.max(0, i - 1)], p1 = pts[i], p2 = pts[i + 1], p3 = pts[Math.min(pts.length - 1, i + 2)];
    for (let s = 0; s < samplesPerSeg; s++) {
      const t = s / samplesPerSeg;
      const t2 = t * t, t3 = t2 * t;
      const x = 0.5 * ((2 * p1.x) + (-p0.x + p2.x) * t + (2 * p0.x - 5 * p1.x + 4 * p2.x - p3.x) * t2 + (-p0.x + 3 * p1.x - 3 * p2.x + p3.x) * t3);
      const y = 0.5 * ((2 * p1.y) + (-p0.y + p2.y) * t + (2 * p0.y - 5 * p1.y + 4 * p2.y - p3.y) * t2 + (-p0.y + 3 * p1.y - 3 * p2.y + p3.y) * t3);
      out.push({ x, y });
    }
  }
  out.push({ x: pts[pts.length - 1].x, y: pts[pts.length - 1].y });
  return out;
}

function catmullRomClosed(pts, samplesPerSeg) {
  const n = pts.length;
  if (n < 3) return pts.map(p => ({ x: p.x, y: p.y }));
  const out = [];
  for (let i = 0; i < n; i++) {
    const p0 = pts[(i - 1 + n) % n], p1 = pts[i], p2 = pts[(i + 1) % n], p3 = pts[(i + 2) % n];
    for (let s = 0; s < samplesPerSeg; s++) {
      const t = s / samplesPerSeg;
      const t2 = t * t, t3 = t2 * t;
      const x = 0.5 * ((2 * p1.x) + (-p0.x + p2.x) * t + (2 * p0.x - 5 * p1.x + 4 * p2.x - p3.x) * t2 + (-p0.x + 3 * p1.x - 3 * p2.x + p3.x) * t3);
      const y = 0.5 * ((2 * p1.y) + (-p0.y + p2.y) * t + (2 * p0.y - 5 * p1.y + 4 * p2.y - p3.y) * t2 + (-p0.y + 3 * p1.y - 3 * p2.y + p3.y) * t3);
      out.push({ x, y });
    }
  }
  return out;
}

function sdPolygon2D(px, py, poly) {
  const n = poly.length;
  let sd = Infinity;
  let inside = false;
  for (let i = 0, j = n - 1; i < n; j = i++) {
    const ex = poly[j].x, ey = poly[j].y;
    const sx = poly[i].x, sy = poly[i].y;
    if ((sy > py) !== (ey > py)) {
      const xint = (sx - ex) * (py - ey) / (sy - ey) + ex;
      if (px < xint) inside = !inside;
    }
    const exx = px - ex, eyy = py - ey;
    const lx = sx - ex, ly = sy - ey;
    const ll = lx * lx + ly * ly;
    const t = ll > 0 ? Math.max(0, Math.min(1, (exx * lx + eyy * ly) / ll)) : 0;
    const cxx = exx - lx * t, cyy = eyy - ly * t;
    const d = cxx * cxx + cyy * cyy;
    if (d < sd) sd = d;
  }
  return (inside ? -1 : 1) * Math.sqrt(sd);
}

function sdExtrude(d2, u, half) {
  const du = Math.abs(u) - half;
  const wx = Math.max(d2, 0), wy = Math.max(du, 0);
  return Math.sqrt(wx * wx + wy * wy) + Math.min(Math.max(d2, du), 0);
}

function sdBox2D(px, py, hx, hy) {
  const qx = Math.abs(px) - hx, qy = Math.abs(py) - hy;
  const mx = Math.max(qx, qy);
  if (mx < 0) return mx;
  const ox = Math.max(qx, 0), oy = Math.max(qy, 0);
  return Math.sqrt(ox * ox + oy * oy);
}

function sdRoundBox2D(px, py, hx, hy, r) {
  const qx = Math.abs(px) - hx + r, qy = Math.abs(py) - hy + r;
  return Math.hypot(Math.max(qx, 0), Math.max(qy, 0)) + Math.min(Math.max(qx, qy), 0) - r;
}

function regularPolygon(n, r) {
  const pts = [];
  for (let i = 0; i < n; i++) {
    const a = (i / n) * TAU;
    pts.push({ x: Math.cos(a) * r, y: Math.sin(a) * r });
  }
  return pts;
}

function starPolygon(points, outer, inner) {
  const pts = [];
  const n = points * 2;
  for (let i = 0; i < n; i++) {
    const a = (i / n) * TAU;
    const r = i % 2 === 0 ? outer : inner;
    pts.push({ x: Math.cos(a) * r, y: Math.sin(a) * r });
  }
  return pts;
}

function gearPolygon(teeth, outer, inner) {
  const pts = [];
  const step = TAU / teeth;
  for (let i = 0; i < teeth; i++) {
    const a = i * step;
    for (const [da, r] of [[-0.25, outer], [-0.10, inner], [0.10, inner], [0.25, outer]]) {
      const b = a + da * step;
      pts.push({ x: Math.cos(b) * r, y: Math.sin(b) * r });
    }
  }
  return pts;
}

function crossPolygon(size) {
  const hx = size[0] / 2, hy = size[1] / 2;
  const arm = Math.min(hx, hy) * 0.35;
  return [
    { x: -hx, y: -arm }, { x: -hx, y: arm }, { x: -arm, y: arm },
    { x: -arm, y: hy }, { x: arm, y: hy }, { x: arm, y: arm },
    { x: hx, y: arm }, { x: hx, y: -arm }, { x: arm, y: -arm },
    { x: arm, y: -hy }, { x: -arm, y: -hy }, { x: -arm, y: -arm },
  ];
}

function polarPt(a, r) { return { x: Math.cos(a) * r, y: Math.sin(a) * r }; }

// ─── Ray tracing ───────────────────────────────────────────────────────────

// Step outward exponentially to bracket the first sign change, then bisect.
// Returns the surface radius along dir, or null when no sign change exists
// inside maxR (a hole / concave direction).
function traceRay(d, dx, dy, dz, maxR) {
  const v0 = d(0, 0, 0);
  let r0 = 0, vv0 = v0;
  let r = 0.02;
  while (true) {
    const v1 = d(dx * r, dy * r, dz * r);
    if (v1 === 0) return r;
    if ((v1 < 0) !== (vv0 < 0)) {
      let lo = r0, hi = r, vlo = vv0;
      for (let it = 0; it < 8; it++) {
        const mid = (lo + hi) * 0.5;
        const vm = d(dx * mid, dy * mid, dz * mid);
        if ((vm < 0) !== (vlo < 0)) { hi = mid; } else { lo = mid; vlo = vm; }
      }
      return (lo + hi) * 0.5;
    }
    if (r >= maxR) return null;
    r0 = r; vv0 = v1;
    r = Math.min(r * 1.6, maxR);
  }
}

// Step outward exponentially, collecting EVERY sign change along the ray
// (near wall, far wall, cavity walls). Used to build the FPS-fill cloud so
// hollow/ring forms get full surface coverage — the first crossing alone only
// sees the near wall.
function probeSurfaces(d, dx, dy, dz, maxR) {
  const out = [];
  const v0 = d(0, 0, 0);
  let r0 = 0, vv0 = v0;
  let r = 0.02;
  while (true) {
    const v1 = d(dx * r, dy * r, dz * r);
    if (v1 === 0) {
      out.push(r);
    } else if ((v1 < 0) !== (vv0 < 0)) {
      let lo = r0, hi = r, vlo = vv0;
      for (let it = 0; it < 8; it++) {
        const mid = (lo + hi) * 0.5;
        const vm = d(dx * mid, dy * mid, dz * mid);
        if ((vm < 0) !== (vlo < 0)) { hi = mid; } else { lo = mid; vlo = vm; }
      }
      out.push((lo + hi) * 0.5);
    }
    if (r >= maxR) break;
    r0 = r; vv0 = v1;
    r = Math.min(r * 1.6, maxR);
  }
  return out;
}

function farthestPointSample(candidates, count, seed) {
  const n = candidates.length;
  if (count > n) throw new Error(`SDF fill: ${count} > ${n} surface probes`);
  const selected = new Array(count);
  const distances = new Float64Array(n).fill(Infinity);
  selected[0] = seed % n;
  for (let i = 1; i < count; i++) {
    const li = selected[i - 1];
    const lx = candidates[li][0], ly = candidates[li][1], lz = candidates[li][2];
    let maxD = -1, maxI = -1;
    for (let j = 0; j < n; j++) {
      const dx = candidates[j][0] - lx, dy = candidates[j][1] - ly, dz = candidates[j][2] - lz;
      const d = dx * dx + dy * dy + dz * dz;
      if (d < distances[j]) distances[j] = d;
      if (distances[j] > maxD) { maxD = distances[j]; maxI = j; }
    }
    selected[i] = maxI;
  }
  const out = new Array(count);
  for (let i = 0; i < count; i++) {
    const c = candidates[selected[i]];
    out[i] = { x: c[0], y: c[1], z: c[2] };
  }
  return out;
}

// ─── Bounding-radius estimate (keeps ray probing bounded) ──────────────────

function estimateMaxR(node) {
  const op = node.op;
  const size = (a) => { const s = node.size || node[a] || [1, 1, 1]; return Math.hypot(s[0], s[1], s[2]); };
  switch (op) {
    case 'sphere': case 'gem': case 'rock': case 'pebble': case 'blob':
      return node.r ?? 0.5;
    case 'crystal':
      return Math.hypot(node.r ?? 0.5, (node.h ?? 1.5) / 2);
    case 'box':
      return size('size') * 0.5;
    case 'rbox':
      return size('size') * 0.5 + (node.r ?? 0.05);
    case 'cylinder': case 'cone': case 'pyramid':
      return Math.hypot(node.r ?? 0.5, (node.h ?? 1.2) / 2);
    case 'torus':
      return (node.R ?? 0.5) + (node.r ?? 0.2);
    case 'capsule':
      return (node.r ?? 0.2) + (node.h ?? 1.2) / 2;
    case 'ellipsoid': case 'superellipsoid':
      return Math.max(node.size?.[0] ?? 1, node.size?.[1] ?? 1, node.size?.[2] ?? 1);
    case 'revolve': {
      const prof = node.profile || [];
      let m = 0.1;
      for (const pt of prof) m = Math.max(m, Math.hypot(pt[0] || 0, pt[1] || 0));
      return m;
    }
    case 'extrude': case 'star': case 'gear': case 'polygon': case 'cross': case 'rect': case 'rect_r': {
      const half = (node.depth ?? 0.18) / 2;
      if (op === 'extrude') {
        let m = 0.1;
        for (const pt of (node.profile || [])) m = Math.max(m, Math.hypot(pt[0] || 0, pt[1] || 0));
        return m + half;
      }
      if (op === 'rect' || op === 'rect_r') return Math.hypot(node.size[0], node.size[1]) * 0.5 + half;
      const r = node.r ?? node.outer ?? 0.6;
      return r + half;
    }
    case 'union': case 'smooth_union': case 'blend': {
      let m = 0;
      for (const c of (node.children || (op === 'blend' ? [node.a, node.b] : []))) m = Math.max(m, estimateMaxR(c));
      return m;
    }
    case 'intersect': case 'smooth_intersect': {
      let m = Infinity;
      for (const c of (node.children || [])) m = Math.min(m, estimateMaxR(c));
      return m === Infinity ? 1 : m;
    }
    case 'subtract': case 'smooth_subtract':
      return node.children?.[0] ? estimateMaxR(node.children[0]) : 1;
    case 'mirror': case 'polar_repeat': case 'rotate': case 'twist': case 'bend':
    case 'taper': case 'squash': case 'bulge': case 'spherize':
      return node.child ? estimateMaxR(node.child) * 1.3 + 0.15 : 1;
    case 'repeat':
      return node.child ? estimateMaxR(node.child) + (node.n ?? 1) * (node.spacing ?? 0.4) : 1;
    case 'translate': {
      const t = node.t || [0, 0, 0];
      return (node.child ? estimateMaxR(node.child) : 1) + Math.hypot(t[0], t[1], t[2]);
    }
    case 'scale': {
      const s = node.s ?? 1;
      const sm = typeof s === 'number' ? s : Math.max(s[0] ?? 1, s[1] ?? 1, s[2] ?? 1);
      return (node.child ? estimateMaxR(node.child) : 1) * sm;
    }
    case 'displace': case 'facet': case 'ridged': case 'worley':
      return (node.child ? estimateMaxR(node.child) : 1) + (node.amp ?? 0.1) + 0.1;
    case 'round':
      return (node.child ? estimateMaxR(node.child) : 1) + (node.r ?? 0.1);
    default:
      return 4;
  }
}

// ─── Compiler ──────────────────────────────────────────────────────────────

function compilePrim(node) {
  switch (node.op) {
    case 'sphere': {
      const r = node.r ?? 0.5;
      return (px, py, pz) => len3(px, py, pz) - r;
    }
    case 'box': {
      const sx = (node.size?.[0] ?? 1) * 0.5, sy = (node.size?.[1] ?? 1) * 0.5, sz = (node.size?.[2] ?? 1) * 0.5;
      return (px, py, pz) => {
        const qx = Math.abs(px) - sx, qy = Math.abs(py) - sy, qz = Math.abs(pz) - sz;
        const mx = Math.max(qx, Math.max(qy, qz));
        if (mx < 0) return mx;
        const ox = Math.max(qx, 0), oy = Math.max(qy, 0), oz = Math.max(qz, 0);
        return Math.sqrt(ox * ox + oy * oy + oz * oz);
      };
    }
    case 'rbox': {
      const sx = (node.size?.[0] ?? 1) * 0.5, sy = (node.size?.[1] ?? 1) * 0.5, sz = (node.size?.[2] ?? 1) * 0.5;
      const r = node.r ?? 0.05;
      return (px, py, pz) => {
        const qx = Math.abs(px) - sx + r, qy = Math.abs(py) - sy + r, qz = Math.abs(pz) - sz + r;
        return Math.hypot(Math.max(qx, 0), Math.max(qy, 0), Math.max(qz, 0)) + Math.min(Math.max(qx, Math.max(qy, qz)), 0) - r;
      };
    }
    case 'cylinder': {
      const r = node.r ?? 0.4, h = (node.h ?? 1.2) * 0.5;
      return (px, py, pz) => {
        const dx = Math.hypot(px, pz) - r;
        const dy = Math.abs(py) - h;
        const ox = Math.max(dx, 0), oy = Math.max(dy, 0);
        return Math.sqrt(ox * ox + oy * oy) + Math.min(Math.max(dx, dy), 0);
      };
    }
    case 'cone': {
      const r = node.r ?? 0.4, h = node.h ?? 1.2;
      return (px, py, pz) => {
        const w = { x: Math.hypot(px, pz), y: py - h * 0.5 };
        const q = { x: r, y: -h };
        const dqq = q.x * q.x + q.y * q.y;
        const t = Math.max(0, Math.min(1, (w.x * q.x + w.y * q.y) / dqq));
        const ax = w.x - q.x * t, ay = w.y - q.y * t;
        const b = q.x > 0 ? q.x * Math.max(0, Math.min(1, w.x / q.x)) : 0;
        const bx = w.x - b, by = w.y - q.y;
        const d = Math.min(ax * ax + ay * ay, bx * bx + by * by);
        const k = q.y < 0 ? -1 : 1;
        const s = Math.max(k * (w.x * q.y - w.y * q.x), k * (w.y - q.y));
        return Math.sqrt(d) * (s < 0 ? -1 : 1);
      };
    }
    case 'torus': {
      const R = node.R ?? 0.5, r = node.r ?? 0.2;
      return (px, py, pz) => Math.hypot(Math.hypot(px, pz) - R, py) - r;
    }
    case 'capsule': {
      const r = node.r ?? 0.2, h = (node.h ?? 1.2) * 0.5;
      return (px, py, pz) => {
        const cy = Math.max(-h, Math.min(h, py));
        return len3(px, py - cy, pz) - r;
      };
    }
    case 'ellipsoid': {
      const sx = node.size?.[0] ?? 1, sy = node.size?.[1] ?? 1, sz = node.size?.[2] ?? 1;
      const m = Math.min(sx, Math.min(sy, sz));
      return (px, py, pz) => (Math.sqrt((px / sx) ** 2 + (py / sy) ** 2 + (pz / sz) ** 2) - 1) * m;
    }
    case 'superellipsoid': {
      const sx = node.size?.[0] ?? 1, sy = node.size?.[1] ?? 1, sz = node.size?.[2] ?? 1;
      const m = node.n ?? 4;
      const e = 2 * m;
      const mn = Math.min(sx, Math.min(sy, sz));
      return (px, py, pz) => {
        const v = Math.min(1e6,
          Math.pow(Math.abs(px / sx), e) + Math.pow(Math.abs(py / sy), e) + Math.pow(Math.abs(pz / sz), e));
        return (Math.pow(v, 1 / e) - 1) * mn;
      };
    }
    case 'pyramid': {
      const n = node.n ?? 4, r = node.r ?? 0.7, h = node.h ?? 1.2;
      const poly = regularPolygon(n, r);
      const half = h * 0.5;
      return (px, py, pz) => {
        const t = Math.max(0, Math.min(1, (py + half) / h));
        let s = 1 - 0.97 * t;
        if (s < 1e-3) s = 1e-3;
        return sdExtrude(sdPolygon2D(px / s, pz / s, poly), py, half) * s;
      };
    }
    case 'gem': {
      const r = node.r ?? 1, seed = node.seed ?? 0;
      return (px, py, pz) => {
        const o = (Math.abs(px) + Math.abs(py) + Math.abs(pz) - r) / Math.sqrt(3);
        const l = len3(px, py, pz) || 1e-6;
        return o + (dirCellHash(px / l, py / l, pz / l, 3, seed) - 0.5) * 0.12;
      };
    }
    case 'rock': {
      const r = node.r ?? 1, seed = node.seed ?? 0;
      return (px, py, pz) => len3(px, py, pz) - r + (smoothNoise(px * 2.2, py * 2.2, pz * 2.2, seed) - 0.5) * 0.3;
    }
    case 'crystal': {
      const r = node.r ?? 0.6, h = node.h ?? 1.8, seed = node.seed ?? 0;
      const poly = regularPolygon(6, r);
      const half = h * 0.5;
      return (px, py, pz) => {
        const t = Math.max(0, Math.min(1, (py + half) / h));
        let s = 1 - 0.985 * t;
        if (s < 1e-3) s = 1e-3;
        const d = sdExtrude(sdPolygon2D(px / s, pz / s, poly), py, half) * s;
        return d + (smoothNoise(px * 2.5, py * 2.5, pz * 2.5, seed) - 0.5) * 0.2;
      };
    }
    case 'pebble': {
      const r = node.r ?? 1, seed = node.seed ?? 0;
      return (px, py, pz) => len3(px, py, pz) - r + (smoothNoise(px * 3, py * 3, pz * 3, seed) - 0.5) * 0.12;
    }
    case 'blob': {
      const r = node.r ?? 1, seed = node.seed ?? 0;
      return (px, py, pz) => len3(px, py, pz) - r + (worley(px * 1.6, py * 1.6, pz * 1.6, seed) - 0.85) * 0.3;
    }
    case 'revolve': {
      const prof = (node.profile || []).map(pt => ({ x: pt[0], y: pt[1] }));
      const smooth = catmullRom(prof, 8);
      // Full 2D cross-section through the axis: profile on the positive radius
      // side plus its mirror on the negative side. Closing the polygon through
      // the axis would put the origin ON the boundary (d(0)=0) — every ray then
      // reports a "surface" at r≈0. Mirroring keeps the axis strictly interior.
      const mirrored = [...smooth].reverse().map(pt => ({ x: pt.x, y: -pt.y }));
      const poly = [...smooth, ...mirrored];
      return (px, py, pz) => sdPolygon2D(py, Math.hypot(px, pz), poly);
    }
    case 'extrude': {
      const prof = (node.profile || []).map(pt => ({ x: pt[0], y: pt[1] }));
      const poly = catmullRomClosed(prof, 6);
      const half = (node.depth ?? 0.18) * 0.5;
      return (px, py, pz) => sdExtrude(sdPolygon2D(px, py, poly), pz, half);
    }
    case 'polygon': {
      const poly = regularPolygon(node.n ?? 6, node.r ?? 0.6);
      const half = (node.depth ?? 0.18) * 0.5;
      return (px, py, pz) => sdExtrude(sdPolygon2D(px, py, poly), pz, half);
    }
    case 'star': {
      const poly = starPolygon(node.points ?? 5, node.outer ?? 0.7, node.inner ?? 0.35);
      const half = (node.depth ?? 0.18) * 0.5;
      return (px, py, pz) => sdExtrude(sdPolygon2D(px, py, poly), pz, half);
    }
    case 'gear': {
      const outer = node.r ?? 0.6;
      const poly = gearPolygon(node.teeth ?? 8, outer, outer * 0.72);
      const half = (node.depth ?? 0.18) * 0.5;
      return (px, py, pz) => sdExtrude(sdPolygon2D(px, py, poly), pz, half);
    }
    case 'cross': {
      const poly = crossPolygon(node.size ?? [1, 1]);
      const half = (node.depth ?? 0.18) * 0.5;
      return (px, py, pz) => sdExtrude(sdPolygon2D(px, py, poly), pz, half);
    }
    case 'rect': {
      const size = node.size ?? [1, 1];
      const half = (node.depth ?? 0.18) * 0.5;
      return (px, py, pz) => sdExtrude(sdBox2D(px, py, size[0] * 0.5, size[1] * 0.5), pz, half);
    }
    case 'rect_r': {
      const size = node.size ?? [1, 1];
      const r = node.r ?? 0.05;
      const half = (node.depth ?? 0.18) * 0.5;
      return (px, py, pz) => sdExtrude(sdRoundBox2D(px, py, size[0] * 0.5, size[1] * 0.5, r), pz, half);
    }
    default:
      throw new Error(`Unknown SDF primitive op: '${node.op}'`);
  }
}

function smoothMin(a, b, k) {
  const h = Math.max(0, Math.min(1, 0.5 + 0.5 * (b - a) / k));
  return (b - a) * h + a - k * h * (1 - h);
}

export function compileSdf(root, seed = 0) {
  let count = 0;

  function compile(node, depth) {
    if (!node || typeof node !== 'object' || typeof node.op !== 'string') {
      throw new Error('SDF node must be an object with an op');
    }
    if (++count > NODE_MAX) throw new Error(`SDF tree exceeds ${NODE_MAX} nodes`);
    if (depth > DEPTH_MAX) throw new Error(`SDF tree exceeds depth ${DEPTH_MAX}`);

    switch (node.op) {
      case 'sphere': case 'box': case 'rbox': case 'cylinder': case 'cone': case 'torus':
      case 'capsule': case 'ellipsoid': case 'superellipsoid': case 'pyramid':
      case 'gem': case 'rock': case 'crystal': case 'pebble': case 'blob':
      case 'revolve': case 'extrude': case 'star': case 'gear': case 'polygon':
      case 'cross': case 'rect': case 'rect_r':
        return compilePrim(node);

      case 'union': case 'intersect': case 'subtract':
      case 'smooth_union': case 'smooth_intersect': case 'smooth_subtract': {
        const kids = (node.children || []).map(c => compile(c, depth + 1));
        if (kids.length < 2) throw new Error(`${node.op} needs >= 2 children`);
        if (node.op === 'union' || node.op === 'smooth_union') {
          const k = node.k ?? 0.05;
          if (node.op === 'union') {
            return (px, py, pz) => {
              let d = kids[0](px, py, pz);
              for (let i = 1; i < kids.length; i++) { const v = kids[i](px, py, pz); if (v < d) d = v; }
              return d;
            };
          }
          return (px, py, pz) => {
            let d = kids[0](px, py, pz);
            for (let i = 1; i < kids.length; i++) d = smoothMin(d, kids[i](px, py, pz), k);
            return d;
          };
        }
        if (node.op === 'intersect' || node.op === 'smooth_intersect') {
          if (node.op === 'intersect') {
            return (px, py, pz) => {
              let d = kids[0](px, py, pz);
              for (let i = 1; i < kids.length; i++) { const v = kids[i](px, py, pz); if (v > d) d = v; }
              return d;
            };
          }
          const k = node.k ?? 0.05;
          return (px, py, pz) => {
            let d = kids[0](px, py, pz);
            for (let i = 1; i < kids.length; i++) d = -smoothMin(-d, -kids[i](px, py, pz), k);
            return d;
          };
        }
        const k = node.k ?? 0.05;
        if (node.op === 'subtract') {
          return (px, py, pz) => {
            let d = kids[0](px, py, pz);
            for (let i = 1; i < kids.length; i++) { const v = -kids[i](px, py, pz); if (v > d) d = v; }
            return d;
          };
        }
        return (px, py, pz) => {
          let d = kids[0](px, py, pz);
          for (let i = 1; i < kids.length; i++) d = -smoothMin(-d, kids[i](px, py, pz), k);
          return d;
        };
      }

      case 'blend': {
        const a = compile(node.a, depth + 1);
        const b = compile(node.b, depth + 1);
        const t = Math.max(0, Math.min(1, node.t ?? 0.5));
        return (px, py, pz) => a(px, py, pz) + (b(px, py, pz) - a(px, py, pz)) * t;
      }

      case 'mirror': {
        const child = compile(node.child, depth + 1);
        const plane = node.plane || 'x';
        if (plane === 'y') return (px, py, pz) => child(px, Math.abs(py), pz);
        if (plane === 'z') return (px, py, pz) => child(px, py, Math.abs(pz));
        return (px, py, pz) => child(Math.abs(px), py, pz);
      }

      case 'polar_repeat': {
        const child = compile(node.child, depth + 1);
        const n = Math.max(2, Math.round(node.n ?? 6));
        const a = TAU / n;
        return (px, py, pz) => {
          const ang = Math.atan2(pz, px);
          const fold = ang - a * Math.floor((ang + a * 0.5) / a);
          const c = Math.cos(fold), s = Math.sin(fold);
          return child(c * px + s * pz, py, -s * px + c * pz);
        };
      }

      case 'repeat': {
        const child = compile(node.child, depth + 1);
        const axis = node.axis || 'y';
        const n = Math.max(2, Math.round(node.n ?? 4));
        const spacing = node.spacing ?? 0.4;
        const offs = [];
        for (let i = 0; i < n; i++) offs.push((i - (n - 1) * 0.5) * spacing);
        if (axis === 'x') {
          return (px, py, pz) => {
            let d = Infinity;
            for (let i = 0; i < n; i++) { const v = child(px - offs[i], py, pz); if (v < d) d = v; }
            return d;
          };
        }
        if (axis === 'z') {
          return (px, py, pz) => {
            let d = Infinity;
            for (let i = 0; i < n; i++) { const v = child(px, py, pz - offs[i]); if (v < d) d = v; }
            return d;
          };
        }
        return (px, py, pz) => {
          let d = Infinity;
          for (let i = 0; i < n; i++) { const v = child(px, py - offs[i], pz); if (v < d) d = v; }
          return d;
        };
      }

      case 'translate': {
        const child = compile(node.child, depth + 1);
        const t = node.t || [0, 0, 0];
        const tx = t[0] ?? 0, ty = t[1] ?? 0, tz = t[2] ?? 0;
        return (px, py, pz) => child(px - tx, py - ty, pz - tz);
      }

      case 'rotate': {
        const child = compile(node.child, depth + 1);
        const preset = node.preset || 'up';
        const deg = (node.deg ?? 0) * Math.PI / 180;
        let rx = 0, rz = 0;
        if (preset === 'flat') rx = Math.PI / 2;
        else if (preset === 'side') rz = Math.PI / 2;
        const cx = Math.cos(-rx), sx = Math.sin(-rx);
        const cy = Math.cos(-deg), sy = Math.sin(-deg);
        const cz = Math.cos(-rz), sz = Math.sin(-rz);
        return (px, py, pz) => {
          let y = py * cx - pz * sx, z = py * sx + pz * cx;
          py = y; pz = z;
          let x = px * cz - py * sz, y2 = px * sz + py * cz;
          px = x; py = y2;
          const x3 = px * cy + pz * sy, z3 = -px * sy + pz * cy;
          return child(x3, py, z3);
        };
      }

      case 'scale': {
        const child = compile(node.child, depth + 1);
        const s = node.s ?? 1;
        if (typeof s === 'number') {
          const si = 1 / Math.max(s, 1e-3);
          return (px, py, pz) => child(px * si, py * si, pz * si) * Math.max(s, 1e-3);
        }
        const sx = 1 / Math.max(s[0] ?? 1, 1e-3), sy = 1 / Math.max(s[1] ?? 1, 1e-3), sz = 1 / Math.max(s[2] ?? 1, 1e-3);
        const mn = Math.min(Math.max(s[0] ?? 1, 1e-3), Math.max(s[1] ?? 1, 1e-3), Math.max(s[2] ?? 1, 1e-3));
        return (px, py, pz) => child(px * sx, py * sy, pz * sz) * mn;
      }

      case 'twist': {
        const child = compile(node.child, depth + 1);
        const deg = (node.deg ?? 0) * Math.PI / 180;
        return (px, py, pz) => {
          const a = deg * py;
          const c = Math.cos(a), s = Math.sin(a);
          return child(c * px - s * pz, py, s * px + c * pz);
        };
      }

      case 'bend': {
        const child = compile(node.child, depth + 1);
        const r = node.r ?? 0.1;
        return (px, py, pz) => {
          const a = r * py;
          const c = Math.cos(a), s = Math.sin(a);
          return child(c * px + s * pz, py, -s * px + c * pz);
        };
      }

      case 'taper': {
        const child = compile(node.child, depth + 1);
        const k = Math.max(0, Math.min(0.98, node.k ?? 0));
        return (px, py, pz) => {
          const f = 1 - k * ((py + 1) * 0.5);
          const fi = Math.max(f, 1e-3);
          return child(px * fi, py, pz * fi) * f;
        };
      }

      case 'squash': {
        const child = compile(node.child, depth + 1);
        const k = Math.max(0.1, node.k ?? 1);
        return (px, py, pz) => child(px, py / k, pz) * Math.min(k, 1);
      }

      case 'bulge': {
        const child = compile(node.child, depth + 1);
        const k = node.k ?? 0.2;
        return (px, py, pz) => {
          const f = Math.max(1 + k * (1 - py * py), 1e-3);
          return child(px / f, py, pz / f) * f;
        };
      }

      case 'spherize': {
        const child = compile(node.child, depth + 1);
        const k = Math.max(0, Math.min(1, node.k ?? 0));
        return (px, py, pz) => {
          const l = len3(px, py, pz) || 1e-6;
          return child(px * (1 - k) + (px / l) * k, py * (1 - k) + (py / l) * k, pz * (1 - k) + (pz / l) * k);
        };
      }

      case 'displace': {
        const child = compile(node.child, depth + 1);
        const amp = node.amp ?? 0.1, freq = node.freq ?? 2, sd = (node.seed ?? seed) ^ 0x7f4a7c15;
        return (px, py, pz) => child(px, py, pz) + (smoothNoise(px * freq, py * freq, pz * freq, sd) - 0.5) * 2 * amp;
      }

      case 'facet': {
        const child = compile(node.child, depth + 1);
        const levels = Math.max(2, Math.round(node.levels ?? 4));
        const amp = node.amp ?? 0.12;
        const sd = (node.seed ?? seed) ^ 0x3f4d6c17;
        return (px, py, pz) => {
          const l = len3(px, py, pz) || 1e-6;
          return child(px, py, pz) + (dirCellHash(px / l, py / l, pz / l, levels, sd) - 0.5) * amp;
        };
      }

      case 'ridged': {
        const child = compile(node.child, depth + 1);
        const amp = node.amp ?? 0.1, freq = node.freq ?? 2, sd = (node.seed ?? seed) ^ 0x11939a77;
        return (px, py, pz) => child(px, py, pz) + Math.abs(2 * smoothNoise(px * freq, py * freq, pz * freq, sd) - 1) * amp;
      }

      case 'worley': {
        const child = compile(node.child, depth + 1);
        const amp = node.amp ?? 0.15, freq = node.freq ?? 2, sd = (node.seed ?? seed) ^ 0x5a5f9e33;
        return (px, py, pz) => child(px, py, pz) + (worley(px * freq, py * freq, pz * freq, sd) - 0.8) * amp;
      }

      case 'round': {
        const child = compile(node.child, depth + 1);
        const r = node.r ?? 0.1;
        return (px, py, pz) => child(px, py, pz) - r;
      }

      default:
        throw new Error(`Unknown SDF op: '${node.op}'`);
    }
  }

  return compile(root, 0);
}

// ─── Surface sampling ──────────────────────────────────────────────────────

export function targetsFromSDF(root, seed = 0) {
  const d = compileSdf(root, seed);
  const maxR = Math.max(0.5, estimateMaxR(root) * 1.2, 1.0);

  const hits = new Array(NUM);
  let missCount = 0;
  for (let i = 0; i < NUM; i++) {
    const dir = referenceDirs[i];
    const r = traceRay(d, dir.x, dir.y, dir.z, maxR);
    if (r === null) { hits[i] = null; missCount++; }
    else hits[i] = { x: dir.x * r, y: dir.y * r, z: dir.z * r };
  }

  let targets;
  if (missCount === 0) {
    targets = hits;
  } else if (missCount < NUM) {
    // Fill: gather a dense surface cloud from EVERY sign change along the
    // canonical + dense probes (near/far/cavity walls), dedupe, then seeded-FPS
    // exactly NUM points. Deterministic; order-alignment is traded for full
    // surface coverage, which hollow forms require.
    const dirs = denseDirs(700);
    const cloud = [];
    const seen = new Set();
    const addPt = (x, y, z) => {
      const key = `${Math.round(x * 1e4)},${Math.round(y * 1e4)},${Math.round(z * 1e4)}`;
      if (!seen.has(key)) { seen.add(key); cloud.push([x, y, z]); }
    };
    for (const dir of referenceDirs) {
      for (const r of probeSurfaces(d, dir.x, dir.y, dir.z, maxR)) addPt(dir.x * r, dir.y * r, dir.z * r);
    }
    for (const dir of dirs) {
      for (const r of probeSurfaces(d, dir.x, dir.y, dir.z, maxR)) addPt(dir.x * r, dir.y * r, dir.z * r);
    }
    if (cloud.length < NUM) throw new Error(`SDF fill: only ${cloud.length} surface probes`);
    targets = farthestPointSample(cloud, NUM, seed >>> 0);
  } else {
    throw new Error('SDF net: zero surface hits (empty or fully subtractive shape)');
  }

  let radius = 0;
  for (const p of targets) {
    const l = len3(p.x, p.y, p.z);
    if (l > radius) radius = l;
  }
  return { targets, radius, missCount };
}

export default { compileSdf, targetsFromSDF, referenceDirs, fibonacciSphere };
