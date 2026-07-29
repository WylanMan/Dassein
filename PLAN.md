# Dassein — Uniform Surface Sampling + Topology-Aware Edge Plan

## Goal

Replace the current Fibonacci-sphere→nearest-vertex sampling and 3D k-NN edge builder with a unified pipeline that produces **evenly-distributed points** and **surface-following triangular edges** for every shape type: primitives, GLB files, and the face. The result is a consistent wireframe aesthetic — no gaps, no cross-surface edge connections, uniform triangle sizes.

---

## Root Cause Analysis

The current pipeline has two independent problems:

### Problem 1: Fibonacci-biased point distribution

Points are sampled by mapping 478 Fibonacci-sphere directions to the nearest vertex on the target geometry (via `icoPoints[i]` → nearest `pos.getX(j)`). This means:

- Point density mirrors the Fibonacci sphere's density pattern (polar clustering at Y=±1)
- Dense mesh regions get many points; sparse regions get few
- The 478-point count is a hard constraint from the icosahedron, not chosen for the target shape
- No control over spacing uniformity

### Problem 2: 3D Euclidean k-NN edges

`nearestNeighborEdges(points, 6)` connects each point to its 6 closest neighbors in raw 3D space. For non-convex shapes:

- A cube vertex near a face edge connects to points on the adjacent face (closer in 3D than points further along the same face)
- Face landmarks connect across the face interior (nose tip neighbors forehead points)
- Cylinder end-cap points connect to side-wall points across the sharp rim
- Torus inner-ring points connect to opposing inner-ring points through the hole

Both problems combine to produce a wireframe with uneven triangle sizes and edges that look scrambled on non-convex shapes.

---

## The Unified Pipeline

### Architecture

```
Input (GLB / Three.js geometry / face landmarks)
        │
        ▼
┌──────────────────────────────────┐
│  1. Ensure triangle mesh         │
│     - Primitive: built-in geo     │
│     - GLB: GLTFLoader first mesh  │
│     - Face: Delaunay mesh from    │
│       landmarks projected to XY   │
└──────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────┐
│  2. MeshSurfaceSampler.build()   │
│     - O(n) cumulative area dist  │
│     - Triangle-area-weighted      │
└──────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────┐
│  3. Sample N points + face index │
│     - Barycentric coords per tri  │
│     - Record (pos, faceIdx)       │
│     - Normalize to unit sphere    │
└──────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────┐
│  4. Build topology-aware edges   │
│     - From original mesh index    │
│     - Triangle adjacency graph    │
│     - Map through faceIdx →       │
│       sample-point connectivity   │
└──────────────────────────────────┘
        │
        ▼
Output: { points[], edgePairs[] }
        │
        ▼
   Existing morph pipeline
   (icoGeo.attributes.position,
    icoEdgeGeo.setIndex, lerp)
```

### Key Dependency

`MeshSurfaceSampler` from Three.js examples CDN:

```
import { MeshSurfaceSampler } from 'three/addons/math/MeshSurfaceSampler.js';
```

Already available at `three@0.152.0`. No external packages needed. API:

- `new MeshSurfaceSampler(mesh)` — constructor, auto-converts indexed→non-indexed
- `.build()` — computes cumulative area distribution, O(n)
- `.sample(targetPos, targetNormal?, targetColor?)` — picks random surface point
- Internally: binary search on cumulative area → `sampleFace(faceIdx, ...)`

The sampler is built once per shape. Sampling N points calls `.sample()` N times — O(N log n).

### Why This Works

- **Even spacing:** Triangle-area-weighted sampling guarantees uniform density — every square unit of surface area has equal probability of receiving a point. No Fibonacci bias.
- **Surface-following edges:** Building edges from the original mesh's triangle adjacency means edges connect points whose source triangles share a geometric edge on the surface. These edges wrap around the surface, never crossing through interior or bridging across features.
- **Consistent N=478:** We sample exactly N points from any mesh. The vertex count invariant is preserved.

---

## Implementation Steps

### Step 0: Import MeshSurfaceSampler

**File:** `index.html`, near line 204 (alongside existing Three.js imports)

```javascript
import { MeshSurfaceSampler } from 'three/addons/math/MeshSurfaceSampler.js';
```

### Step 1: Build the `SurfaceMorphEngine` module

**File:** `index.html`, insert after the `ScrollController` IIFE (after line ~401)

```javascript
    // ═══ Surface Morph Engine (uniform sampling + topology-aware edges) ═══
    const SurfaceMorphEngine = (() => {

      /**
       * Sample N points uniformly from a Three.js mesh surface.
       * Returns { points, faceIndices } where faceIndices[i] is the source
       * triangle index for point i — needed for topology-aware edge building.
       */
      function sampleFromMesh(mesh, N) {
        const sampler = new MeshSurfaceSampler(mesh);
        sampler.build();

        const points = new Array(N);
        const faceIndices = new Int32Array(N);

        const pos = new THREE.Vector3();
        const distribution = sampler.distribution;
        const totalArea = distribution[distribution.length - 1];

        for (let i = 0; i < N; i++) {
          const r = Math.random() * totalArea;
          const faceIdx = sampler.binarySearch(r);
          sampler.sampleFace(faceIdx, pos);
          points[i] = { x: pos.x, y: pos.y, z: pos.z };
          faceIndices[i] = faceIdx;
        }

        return { points, faceIndices };
      }

      /**
       * Build edge indices from a triangle mesh's adjacency graph,
       * mapped through sample-point face assignments.
       *
       * @param {THREE.BufferGeometry} geo - original triangle mesh geometry
       * @param {Int32Array} faceIndices - which triangle each sample point
       *        belongs to (output of sampleFromMesh)
       * @param {number} N - number of sample points
       * @returns {number[]} flat array of edge index pairs [a,b, c,d, ...]
       */
      function topologyEdges(geo, faceIndices, N) {
        const pos = geo.attributes.position;
        const hasIndex = geo.index !== null;
        const vertCount = pos.count / 3; // faces are triples

        // Build adjacency: face A and face B share an edge if they
        // have two vertices in common
        const faceAdj = {};
        const edgeToFace = {};

        const addFaceEdge = (vA, vB, faceIdx) => {
          const key = Math.min(vA, vB) + '-' + Math.max(vA, vB);
          if (!edgeToFace[key]) edgeToFace[key] = [];
          edgeToFace[key].push(faceIdx);
        };

        for (let t = 0; t < vertCount; t++) {
          const i0 = hasIndex ? geo.index.getX(t * 3) : t * 3;
          const i1 = hasIndex ? geo.index.getX(t * 3 + 1) : t * 3 + 1;
          const i2 = hasIndex ? geo.index.getX(t * 3 + 2) : t * 3 + 2;
          addFaceEdge(i0, i1, t);
          addFaceEdge(i1, i2, t);
          addFaceEdge(i2, i0, t);
        }

        // Build face adjacency from shared edges
        for (const [key, faces] of Object.entries(edgeToFace)) {
          for (let i = 0; i < faces.length; i++) {
            for (let j = i + 1; j < faces.length; j++) {
              const fa = faces[i], fb = faces[j];
              if (!faceAdj[fa]) faceAdj[fa] = new Set();
              if (!faceAdj[fb]) faceAdj[fb] = new Set();
              faceAdj[fa].add(fb);
              faceAdj[fb].add(fa);
            }
          }
        }

        // Map sample points to edges via face adjacency
        const faceToSamples = {};
        for (let i = 0; i < N; i++) {
          const f = faceIndices[i];
          if (!faceToSamples[f]) faceToSamples[f] = [];
          faceToSamples[f].push(i);
        }

        const indices = [];
        const used = new Set();
        for (let fa = 0; fa < vertCount; fa++) {
          const neighbors = faceAdj[fa];
          if (!neighbors) continue;
          const samplesA = faceToSamples[fa];
          if (!samplesA) continue;

          for (const fb of neighbors) {
            const samplesB = faceToSamples[fb];
            if (!samplesB) continue;
            for (const sa of samplesA) {
              for (const sb of samplesB) {
                const key = Math.min(sa, sb) + '-' + Math.max(sa, sb);
                if (!used.has(key)) {
                  used.add(key);
                  indices.push(sa, sb);
                }
              }
            }
          }
        }

        return indices;
      }

      /**
       * Normalize points to fit within a unit sphere bounding volume,
       * centered at origin.
       */
      function normalizeToUnitSphere(points) {
        if (points.length === 0) return [];
        let cx = 0, cy = 0, cz = 0;
        for (const p of points) { cx += p.x; cy += p.y; cz += p.z; }
        cx /= points.length; cy /= points.length; cz /= points.length;

        let maxDist = 0;
        for (const p of points) {
          const d = Math.hypot(p.x - cx, p.y - cy, p.z - cz);
          if (d > maxDist) maxDist = d;
        }

        if (maxDist === 0) return points;
        const scale = 1.0 / maxDist;
        return points.map(p => ({
          x: (p.x - cx) * scale,
          y: (p.y - cy) * scale,
          z: (p.z - cz) * scale,
        }));
      }

      /**
       * Convert {x,y,z}[] to Float32Array matching icoGeo format.
       */
      function pointsToFloat32Array(points) {
        const arr = new Float32Array(points.length * 3);
        for (let i = 0; i < points.length; i++) {
          arr[i * 3]     = points[i].x;
          arr[i * 3 + 1] = points[i].y;
          arr[i * 3 + 2] = points[i].z;
        }
        return arr;
      }

      return { sampleFromMesh, topologyEdges, normalizeToUnitSphere, pointsToFloat32Array };
    })();
```

### Step 2: Rewrite `loadShapeGLB` (line ~1051)

Replace the current function. For primitive shapes (cube, cylinder, pyramid, torus, sphere), build a Three.js geometry, wrap it in a temporary Mesh, sample via `SurfaceMorphEngine`, then dispose:

```javascript
    async function loadShapeGLB(name) {
      let geo;
      switch (name) {
        case 'cube':     geo = new THREE.BoxGeometry(1, 1, 1, 20, 20, 20); break;
        case 'cylinder': geo = new THREE.CylinderGeometry(0.5, 0.5, 1, 48, 1, true); break;
        case 'pyramid':  geo = new THREE.ConeGeometry(0.5, 1.0, 4, 1); break;
        case 'torus':    geo = new THREE.TorusGeometry(0.45, 0.18, 32, 80); break;
        default: return null;
      }

      // Wrap in mesh for MeshSurfaceSampler (requires Mesh, not raw geometry)
      const mat = new THREE.MeshBasicMaterial();
      const mesh = new THREE.Mesh(geo, mat);

      const { points, faceIndices } = SurfaceMorphEngine.sampleFromMesh(mesh, NUM);
      const normalized = SurfaceMorphEngine.normalizeToUnitSphere(points);

      shapeTargets = normalized;

      // Build edges from original triangle topology
      shapeTargetEdgeIndices = SurfaceMorphEngine.topologyEdges(geo, faceIndices, NUM);

      geo.dispose();
      mat.dispose();
      return true;
    }
```

**Changes from current:**
- Increased subdivision (cube 20×20×20, cylinder 48 radial, torus 32×80) for smoother sampling
- Cylinder uses `true` for open-ended (no caps — matches wireframe aesthetic)
- `Sphere` case removed from the switch (sphere shape pill maps to icoPoints)
- Sample positions + face indices via MeshSurfaceSampler (not Fibonacci→nearest-vertex)
- Edges via triangle adjacency (not k-NN)

### Step 3: Update `switchShape` for sphere (line ~1092)

When `name === 'sphere'`, `getTargetsForShape('sphere')` returns `icoPoints`. This is correct — no change needed. The sphere pill is the landing-state icosahedron, which already has perfect Fibonacci+k-NN geometry.

### Step 4: Face edge builder (re-add Delaunay)

**File:** `index.html`, after `loadScan()` builds `faceLMs` (line ~713)

The face is different from other shapes — it comes from landmark data, not a mesh. We use 2D Delaunay triangulation (same approach as the reverted commit):

Add Delaunator CDN (before the module script):

```html
<script src="https://cdn.jsdelivr.net/npm/delaunator@5.1.0/delaunator.min.js"></script>
```

Replace `nearestNeighborEdges(faceLMs, 6)` with:

```javascript
      // 2D Delaunay triangulation on XY projection of face landmarks
      function delaunayEdgesFace(points) {
        const coords = new Float64Array(points.length * 2);
        for (let i = 0; i < points.length; i++) {
          coords[i * 2] = points[i].x;
          coords[i * 2 + 1] = points[i].y;
        }
        const del = new Delaunator(coords);
        const edges = [];
        const used = new Set();
        const add = (a, b) => {
          if (a === b) return;
          const key = Math.min(a, b) + '-' + Math.max(a, b);
          if (!used.has(key)) { used.add(key); edges.push([a, b]); }
        };
        for (let i = 0; i < del.triangles.length; i += 3) {
          const a = del.triangles[i];
          const b = del.triangles[i + 1];
          const c = del.triangles[i + 2];
          add(a, b); add(b, c); add(c, a);
        }
        return edges;
      }

      const faceNNEdges = delaunayEdgesFace(faceLMs);
```

### Step 5: GLB file morphing (future-proofing)

When `morphToGLB()` is implemented (from the existing PLAN.md), instead of the triangle-area-sampling approach documented there, use `SurfaceMorphEngine`:

```javascript
async function morphToGLB(source, options = {}) {
  // ... existing setup ...

  // Load GLB
  const gltf = await new GLTFLoader().loadAsync(source);
  const mesh = gltf.scene.children.find(c => c.isMesh);
  if (!mesh) throw new Error('GLB contains no mesh');

  // Sample uniformly
  const { points, faceIndices } = SurfaceMorphEngine.sampleFromMesh(mesh, NUM);
  const normalized = SurfaceMorphEngine.normalizeToUnitSphere(points);

  // Build topology-aware edges
  const targetEdges = SurfaceMorphEngine.topologyEdges(mesh.geometry, faceIndices, NUM);
  const targetPos = SurfaceMorphEngine.pointsToFloat32Array(normalized);

  // ... morph animation (same as existing plan) ...
}
```

### Step 6: Remove unused code

- Remove `nearestNeighborEdges` usage for anything except the sphere (landing state stays Fibonacci + k-NN)
- Remove the `GLTFLoader` import from `loadShapeGLB` (no longer needed — primitives use built-in geometries)
- The `shapeTargets` variable now stores `{x,y,z}[]` from normalized MeshSurfaceSampler output

### Step 7: Handle the sphere shape pill

The shape row has a "sphere" pill. When clicked, `switchShape('sphere')` calls `getTargetsForShape('sphere')` which returns `icoPoints`. The edge indices should be `nnIndices` (the original icosahedron edges). Verify that `morphToTarget` uses `nnIndices` as `targetEdgeIndices` when `isSphere` is true — this already works (line ~1036).

Edge case: when switching from a sampled shape back to sphere, the indices swap from `shapeTargetEdgeIndices` (topology edges) to `nnIndices` (Fibonacci k-NN). This behaves the same as all other shape switches — the `morphToTarget` midpoint index swap handles it.

---

## Performance Budget

| Step | 1K triangles | 10K triangles | 100K triangles |
|------|-------------|--------------|----------------|
| `sampleFromMesh` (build) | <1ms | ~2ms | ~15ms |
| `sampleFromMesh` (478 samples) | ~3ms | ~3ms | ~3ms |
| `topologyEdges` (adjacency graph) | ~1ms | ~5ms | ~40ms |
| `normalizeToUnitSphere` | <1ms | <1ms | <1ms |
| **Total** | **~5ms** | **~10ms** | **~60ms** |

All operations are CPU-bound, single-threaded, and well within the 16ms frame budget. No Web Worker needed.

---

## Design Coherence

After this plan is implemented, every shape follows the same visual rules:

| Shape | Points via | Edges via | Triangle quality |
|-------|-----------|-----------|------------------|
| Sphere (landing) | Fibonacci sphere | 3D k-NN (k=6) | Perfect on convex |
| Face | Face landmarks (fixed) | 2D Delaunay on XY | Good ~ triangular |
| Cube | MeshSurfaceSampler | Triangle adjacency | Uniform on surface |
| Cylinder | MeshSurfaceSampler | Triangle adjacency | Uniform on surface |
| Pyramid | MeshSurfaceSampler | Triangle adjacency | Uniform on surface |
| Torus | MeshSurfaceSampler | Triangle adjacency | Uniform on surface |
| GLB (future) | MeshSurfaceSampler | Triangle adjacency | Uniform on surface |

Every shape renders as: **478 dots (shared icoCloud) + surface-following triangular wireframe (shared icoEdgeGeo) + optional contour overlay (face only).**

---

## Verification Checklist

### Sampling Quality
- [ ] Points are evenly distributed — no visible clustering on any primitive shape
- [ ] 478 points on a cube: all 6 faces have roughly equal point counts
- [ ] 478 points on a torus: inner and outer rings have proportional density
- [ ] Points from MeshSurfaceSampler are properly normalized to unit sphere

### Edge Quality
- [ ] Cube edges stay on cube faces — no cross-face connections
- [ ] Torus edges follow the ring surface — no bridge-through-hole edges
- [ ] Cylinder edges wrap the body — no cap-to-side crossings (open-ended cylinder)
- [ ] Face edges follow facial surface (Delaunay) — no cross-face interior edges
- [ ] Sphere edges unchanged from current (Fibonacci k-NN)

### Morph Integration
- [ ] Shape pill switching works for all 6 shapes
- [ ] Edge indices swap correctly at midpoint of each morph
- [ ] Edge opacity maintained during and after morph (0.20-0.35 range)
- [ ] `resetToLanding()` restores sphere nnIndices
- [ ] Face contour lines still overlay correctly with Delaunay edges visible underneath
- [ ] No console errors from disposed geometries

### Performance
- [ ] Shape switch completes in <50ms (including sampling + edge building)
- [ ] No visible frame drop during morph animation (60fps maintained)
