# Dassein — Wireframe Triangulation Architecture (v8)

## Goal

Render any 3D object — procedural primitives, GLB models, face scans — as a **triangular mesh draped across its surface.** The mesh is formed by point-cloud dots and the wireframe edges that connect them. No filled surfaces, no edge-detected overlays, no model-native rectilinear wireframes. The final visual is always the same: a net of dots and lines that wraps the object's form.

The triangulation must be **geometrically similar** — triangles of roughly equal size and shape, distributed uniformly across the surface — like the faces of a subdivided icosahedron. Denser where curvature demands it, but never random, never stretched, never bridging across empty space.

The **icosahedron sphere** is the reference pattern. Every other shape — a cube, a torus, a face scan, an imported GLB model — should look like someone took that same icosahedral wireframe net and wrapped it around the new form. Same visual density, same triangle regularity, same point-to-edge relationship.

---

## Design Philosophy

All shapes render through a **single rendering engine** with shared geometry buffers and a common morph pipeline. The canonical examples are the **icosahedron** and the **face** — both use nearest-neighbor edges on well-distributed points, producing the target pattern of geometrically similar triangles with uniform density. This pattern must extend to all shapes.

**Core principle: visual output beats geometric purity.** The design goal is an icosahedron-like visual pattern, not correct surface triangulation. What produces the pattern is uniform points + k-NN edges. What produces the wrong visual (grids, bridges, gaps) is using the geometry's own vertex grid or projecting to a sphere for triangulation.

---

## The v7 Reckoning: What "Geometry-First" Gets Wrong

The v7 PLAN.md proposed extracting a procedural geometry's own vertices and using its own triangle indices as wireframe edges. This is geometrically correct but **visually wrong** for the stated design goal.

- A `BoxGeometry(8,8,8)` has vertices arranged in a rectangular grid on each face. k-NN on those grid vertices produces a grid-pattern wireframe — rectangular right triangles running in straight rows. This looks like a wireframe cube, not "an icosahedron net draped over a cube."
- The icosahedron visual pattern requires **near-equilateral triangles**, which requires uniformly distributed points on the surface — not grid-aligned vertices.
- Irony: `MeshSurfaceSampler` + k-NN edges produces **closer to the icosahedron-like visual** on a cube than native geometry edges do, because uniform random sampling breaks up the grid structure.

**The plan was solving for geometric correctness while the design goal demands visual pattern fidelity. These are not the same thing.** The geometry-first approach is correct for surface reconstruction. For a visual art piece, uniform sampling + k-NN is the correct approach. We choose the visual goal.

---

## The Real Tension (and Resolution)

| Goal | Requirement |
|---|---|
| Shared position buffer for morphing | All shapes must have identical vertex count |
| Geometry-first point sourcing | Each shape has a different vertex count |

These two requirements are **mutually exclusive** at the implementation level. The resolution:

**Keep the shared buffer. Sample every shape to a fixed point count using deterministic uniform sampling. This is the correct choice for the visual goal.**

The sampling step is not a compromise — it is the mechanism that produces icosahedron-like triangles on non-spherical shapes. Without it, native geometry vertices produce grid patterns. The sampling *is* the design.

---

## Rendering Layers

Three concurrent layers share a single position buffer. The morph engine drives the position buffer; all layers follow automatically.

| Layer | Type | Material | Role |
|---|---|---|---|
| Point cloud | `THREE.Points` | Additive blend, `opacity: 0.55` | N cyan dots — the "atoms" |
| Wireframe edges | `THREE.LineSegments` | Opaque cyan, `depthTest: true` | The visible triangulation |
| Edge glow | `THREE.LineSegments` | Opaque cyan, `depthTest: false` | Subtle bloom passthrough |

The point cloud and edge glow share the position buffer by reference (`icoEdgeGlow.geometry.attributes.position = icoGeo.attributes.position`). The wireframe edges use a separate `icoEdgeGeo` geometry but its `.attributes.position` is set to the same `icoGeo.attributes.position` array — morphs write to one buffer and all three layers update.

---

## Shared Position Buffer

```
icoGeo (BufferGeometry)
 ├── attributes.position → positions (Float32Array[N*3])
 │
 ├── icoCloud (Points)          ← reads positions, renders dots
 ├── icoEdges (LineSegments)    ← reads positions via icoEdgeGeo, renders edges
 └── icoEdgeGlow (LineSegments) ← reads positions via cloned geometry, renders glow
```

The face contour layer (`faceContourLines`, `faceContourGlow`, `faceMouthCavity`, `faceKeyNodes`, `faceIrisNodes`) has its own position buffer but is synced via `updateFaceGeometry(positions)` on every animation frame during morphs — it follows the shared buffer indirectly.

---

## Point Distribution

Points define where the dots render and where edges connect. Every shape produces exactly `N` points (where `N` is a global constant, baseline 478). Points are generated once at shape load time and cached.

### Point sourcing by shape type

#### 1. Sphere (landing)

**Source:** `fibonacciSphere(N)` — deterministic, evenly distributed points on a unit sphere.
**Property:** Euclidean neighbor distances are near-constant; distribution is visually uniform with no clusters or gaps. This is the gold standard reference.

#### 2. Face

**Source:** N 3D landmarks from `data/robota_scan.json`, scaled by `FACE_SCALE`.
**Property:** Dense in high-curvature regions (nose, lips, eyes), sparse on flat surfaces (forehead). Not uniform but follows the natural topology of a face scan. Fixed at N points by the scan itself.

#### 3. Procedural shapes (cube, cylinder, pyramid, torus)

**Source:** Farthest Point Sampling (FPS) on the geometry's dense vertex set.

**Algorithm:**
1. Create the procedural geometry at a controlled subdivision level (e.g., `BoxGeometry(0.5, 0.5, 0.5, 16, 16, 16)`)
2. Weld duplicate vertices (positions that are identical at corners/edges across faces)
3. Run FPS to select exactly N points:
   - Start from a random seed vertex
   - Iteratively pick the vertex farthest from all already-selected vertices (Euclidean 3D distance)
   - Repeat until N points are selected
4. Dispose the temp geometry

**Properties:**
- **Deterministic** (same seed → same output, unlike MeshSurfaceSampler)
- **Vertex-respecting** — every sampled point is a real vertex position from the geometry, not a random point on a face (satisfies the "geometry-first" spirit without adopting its flaws)
- **Uniform coverage** — FPS inherently maximizes point spread, avoiding clusters
- **Same point count** for all shapes (solves the morph pipeline constraint)
- **Icosahedron-like visual** when combined with k-NN edges, because the uniform FPS distribution produces near-equilateral k-NN connections on convex surfaces

**Why FPS over MeshSurfaceSampler:**
- FPS is deterministic (MeshSurfaceSampler is random)
- FPS picks real mesh vertices (MeshSurfaceSampler picks arbitrary surface points)
- FPS produces mathematically guaranteed uniform spread (MeshSurfaceSampler has variance)
- FPS is O(N²) for N=478 with ~2000 input vertices → ~0.1s in JS — negligible at load time

**Why FPS over Poisson Disk Sampling:**
- PDS requires geodesic distance computation and a mesh adjacency graph — much more code, no standard Three.js path
- FPS uses only Euclidean distance and runs on raw vertex arrays — trivial to implement
- For the convex/near-convex shapes in the current set, FPS quality is excellent
- PDS is the upgrade path if concave GLB models are added later

#### 4. Imported GLB models

**Source:** FPS on extracted mesh vertices (same algorithm as procedural shapes).

1. Load model via GLTFLoader
2. Traverse scene, collect all mesh geometries
3. Merge vertex positions from all geometries into one array
4. Weld approximate duplicates (positions within threshold distance)
5. Run FPS to select exactly N points
6. Generate k-NN edges on the FPS result

**Caveat:** k-NN edges on Euclidean distance will bridge across concave regions (e.g., the gap between a character's arm and torso). This is a known limitation of the Euclidean k-NN model that affects any non-convex geometry. For the GLB models you intend to use, evaluate whether this is acceptable. If it isn't, the upgrade path is geodesic-aware k-NN using Dijkstra on the mesh graph — a deferred feature, not part of this plan.

**Isotropic remesh is deferred.** Browser-side isotropic remeshing of arbitrary meshes is not a solved problem. There is no Three.js addon, no WASM library, and no drop-in JavaScript implementation. The pragmatic path is FPS + k-NN edges now, evaluate visual quality, and spike a remesh solution only if the result is unacceptable.

---

## Edge Generation

Edges define which point pairs are connected by visible lines.

### The only edge model: k-NN Euclidean

For each point, connect to its `k` nearest neighbors by straight-line 3D distance. Deduplicate.

```
nearestNeighborEdges(points, k=6):
  for each point p_i:
    compute distance to all other points p_j
    select k nearest
    add edges (i, j) for each
  deduplicate (remove (j, i) when (i, j) already exists)
  return edge index array
```

**Why k=6:** The icosahedron reference has each vertex connected to 5-6 neighbors. k=6 produces the target visual density across all shapes. On the Fibonacci sphere, k=6 produces triangles visually identical to the icosahedron's own edges.

**Works for:** Sphere, face, cube, cylinder, pyramid — all shapes in the current set are either convex or near-convex at the relevant scale. k-NN Euclidean edges produce the icosahedron-like pattern on all of them.

**Known failure mode:** Concave shapes where surface distance diverges from Euclidean distance — the classic example is a torus, where k-NN connects points across the hole. Mitigations:
1. The current torus has a small hole relative to its ring thickness; at N=478, the Euclidean k-NN result may be visually acceptable
2. If unacceptable, the fix is to increase point density (N) for the torus specifically so that k-NN neighbors are close enough that Euclidean ≈ geodesic locally
3. True fix is geodesic k-NN via mesh-graph Dijkstra — deferred

### Removed: Spherical Delaunay

`sphericalDelaunayEdges()` is deleted. It was geometrically unsound — projecting all 3D shapes to a sphere before triangulation destroys surface topology. On a cube, front-face points connect to back-face points. On a torus, edges bridge the hole. On a cylinder, top-cap points connect to bottom-cap points. The output is geometrically meaningless for any non-spherical shape.

---

## Edge Index Swap Mechanism

All wireframe edges share the same `icoEdgeGeo` (and its glow twin). Switching between modes means swapping which index array is active:

```
icoEdgeGeo.setIndex(targetIndices);
icoEdgeGlow.geometry.setIndex(targetIndices);
```

| Mode | Edge index array | Source |
|---|---|---|
| Landing (sphere) | `nnIndices` | `nearestNeighborEdges(icoPoints, 6)` — precomputed at init |
| Face | `faceNNIndices` | `nearestNeighborEdges(faceLMs, 6)` — precomputed at scan load |
| Solid shapes | `shapeTargetEdgeIndices` | `nearestNeighborEdges(shapeTargets, 6)` — precomputed at shape load |

**All edge arrays use the same function.** There is only one edge model. The index arrays differ only because the input point sets differ. This is the unification that v6/v7 never achieved.

### Swap timing

All morph transitions use the same pattern:
- **t < 0.5:** Old edge indices active, opacity crossfading out
- **t = 0.5:** `setWireframeEdgeIndices(targetIndices)` swaps the index buffer
- **t > 0.5:** New edge indices active, opacity crossfading in

---

## Opacity Scheme

Unified wireframe-only scheme. No solid layer remains.

| Mode | Wireframe edges | Edge glow | Point cloud | Contours | Mouth | Key nodes | Iris nodes |
|---|---|---|---|---|---|---|---|
| Landing (sphere) | 0.28 | 0.10 | 0.55 | 0 | 0 | 0 | 0 |
| Face | 0.35 | 0.12 | 0.55 | 0.75 | 0.55 | 0.25 | 1.0/0.15 |
| Solid shapes | 0.22 | 0.08 | 0.55 | 0 | 0 | 0 | 0 |

---

## Morph Pipeline

Three morph paths exist. All use the shared position buffer. All target point sets have exactly N points.

### 1. Landing → Face (`triggerTransform()`)

Source positions: `icoPoints` (Fibonacci sphere, N points)
Target positions: `faceLMs` (face scan landmarks, N points)
Edge swap: `nnIndices` → `faceNNIndices` at t=0.5
Duration: 2.0s

### 2. Shape switching (`switchShape()` → `morphToTarget()`)

Source positions: current position buffer state (N points)
Target positions: `getTargetsForShape(name)` — `faceLMs` for face, `icoPoints` for sphere, `shapeTargets` for solids (all N points)
Edge swap: `nnIndices`/`faceNNIndices`/`shapeTargetEdgeIndices` at t=0.5
Duration: 1.5s

### 3. Agent → Landing (`resetToLanding()`)

Source positions: current position buffer state (N points)
Target positions: `icoPoints` (N points)
Edge swap: current → `nnIndices` at t=0.5
Duration: 1.5s

### Common morph function (`morphToTarget(targets, shapeName, duration)`)

1. Snapshots current opacities for all layers
2. Computes target opacities based on `shapeName`
3. Runs a GSAP tween interpolating positions and crossfading opacities
4. Swaps edge indices at t=0.5
5. On completion: snaps positions to exact targets, sets final opacities, sets state

---

## Shape Architecture

### Shape set

```javascript
const SHAPE_NAMES = ['face', 'sphere', 'cube', 'cylinder', 'pyramid', 'torus'];
```

### Shape loading pipeline

```
loadShape(name)
  ├── 'sphere': return { targets: fibonacciSphere(N), edges: nnIndices }
  ├── 'face':    return { targets: faceLMs, edges: faceNNIndices }
  │
  └── procedural shapes (cube, cylinder, pyramid, torus):
        1. Create geometry at subdivision level D (D varies by shape)
        2. Extract and weld vertex positions
        3. Run FPS to select exactly N points → shapeTargets
        4. Run nearestNeighborEdges(shapeTargets, 6) → shapeTargetEdgeIndices
        5. Dispose temp geometry
        6. Cache and return { targets, edges }
```

### Subdivision levels per shape

| Shape | Geometry | Subdivision D | Input vertices (approx) | Notes |
|---|---|---|---|---|
| Cube | `BoxGeometry(0.5, 0.5, 0.5, D, D, D)` | 16 | ~1,734 | D controls vertex grid density for FPS input |
| Cylinder | `CylinderGeometry(r, r, h, D)` | 32 | ~1,056 | Radial segments determine FPS input richness |
| Pyramid | `ConeGeometry(r, h, D)` | 32 | ~1,024 | Same structure as cylinder |
| Torus | `TorusGeometry(R, r, D, D)` | 32 | ~2,048 | Higher subdivision compensates for hole topology |

### FPS implementation

```
farthestPointSampling(vertices, targetCount, seed=0):
  // vertices: Float32Array of (x,y,z) triples
  // targetCount: N (e.g. 478)
  // Returns: indices of selected vertices

  const n = vertices.length / 3
  const selected = new Array(targetCount)
  const distances = new Float32Array(n).fill(Infinity)

  // Seed first point (deterministic from seed)
  selected[0] = seed % n

  for (let i = 1; i < targetCount; i++) {
    const lastIdx = selected[i - 1]
    const lx = vertices[lastIdx * 3]
    const ly = vertices[lastIdx * 3 + 1]
    const lz = vertices[lastIdx * 3 + 2]

    let maxDist = -1
    let maxIdx = -1

    for (let j = 0; j < n; j++) {
      const dx = vertices[j * 3] - lx
      const dy = vertices[j * 3 + 1] - ly
      const dz = vertices[j * 3 + 2] - lz
      const d = dx * dx + dy * dy + dz * dz  // squared distance
      if (d < distances[j]) distances[j] = d
      if (distances[j] > maxDist) {
        maxDist = distances[j]
        maxIdx = j
      }
    }

    selected[i] = maxIdx
  }

  return selected
```

**Optimization note:** For N=478 and input vertices ~2,000, the naive O(N × input) FPS completes in ~0.02s on modern hardware. Optimization (spatial hashing, GPU compute) is unnecessary at this scale. If N grows beyond ~2,000 or input vertices beyond ~10,000, add an octree.

---

## Point Count

### Fixed N = 478 (baseline)

The Fibonacci sphere at N=478 has been the visual reference since v1. Every shape targets exactly 478 points. This means:
- Shared position buffer is exactly `Float32Array(478 * 3)` for all modes
- Morph pipeline handles only one buffer size
- No drawRange tricks, no per-shape buffer allocation

### Why not variable point counts?

The v7 PLAN.md proposed surface-area-proportional point counts (60 for cube, 120 for torus). This is correct in principle — a small cube shouldn't have the same dot density as a large sphere. But it's premature optimization that introduces:

1. Per-shape buffer allocation (removes the shared buffer elegance)
2. Morph pipeline rewrite (GSAP can't interpolate between different-length arrays)
3. Crossfade fallback adds complexity for a gain that may not read visually

**Decision:** Ship with fixed N=478 first. If the cube looks too dense or the torus looks too sparse, adjust by changing `N` globally, or add per-shape density multipliers that FPS can respect while keeping the same output count. Variable count is a v9 concern.

### Per-shape density control (if needed)

If visual density is inconsistent at N=478, multiply each shape's target count:
- Cube: `N * 0.13` ≈ 62 (lower density on small surface area)
- Torus: `N * 0.25` ≈ 120

But this requires the variable-count morph solution. Deferred.

---

## What Gets Deleted

- `sphericalDelaunayEdges()` — entire function, geometrically unsound
- `MeshSurfaceSampler` usage in `loadShapeGLB()` — replaced by FPS (keep the import if used elsewhere)
- `loadShapeGLB()` `sphericalDelaunayEdges` call site — replaced by `nearestNeighborEdges`
- v7 PLAN.md's "Target edge model: intrinsic surface edges" section — geometric correctness is not the goal

---

## What Gets Added

- `farthestPointSampling(vertices, targetCount, seed)` — new function
- `weldVertices(positions, threshold)` — new function for deduplicating corner/edge vertices
- Seeded random for deterministic FPS initialization (a simple `seed % vertexCount` for the first pick)

---

## What Gets Changed

- `loadShapeGLB(name)`:
  - Keep: procedural geometry creation, vertex extraction
  - Change: replace `MeshSurfaceSampler` with FPS on welded vertices
  - Change: replace `sphericalDelaunayEdges` with `nearestNeighborEdges(shapeTargets, 6)`
  - Keep: temp geometry disposal

---

## GLB Import: Deferred Spike

Isotropic remeshing in the browser is not a solved problem. There is no library that takes an arbitrary mesh and returns a new mesh with uniformly sized, near-equilateral triangles — in JavaScript, in the browser, at acceptable performance for a real-time web app.

**Current state of the art:**
- `meshoptimizer` (C++, WASM-compilable): vertex cache optimization and simplification, not isotropic remesh
- `geometry-central` (C++): has Poisson disk surface sampling but no WASM port
- `MeshLab` (C++ desktop app): has isotropic explicit remeshing via "Uniform Mesh Resampling" filter — not available in-browser
- `point-cloud-utils` (Python): Poisson disk downsampling — not in-browser
- Three.js `SimplifyModifier`: edge collapse decimation, not remeshing — quality is poor for high-density meshes

**For the GLB import spike (future):**
1. Test FPS + k-NN on a real GLB model and evaluate visual quality
2. If concave bridging is visible and unacceptable, implement geodesic k-NN using Dijkstra on the mesh face-adjacency graph
3. If triangle irregularity is visible and unacceptable, research `meshoptimizer` WASM compilation for simplification + a custom subdivision pass
4. Accept that "isotropic remesh → icosahedron-like pattern" on arbitrary GLB models may require a desktop preprocessing step (Blender remesh, output GLB, load the pre-remeshed file) rather than a browser runtime solution

---

## Implementation Order

### Phase 1: Fix the edge model (1-2 hours)
1. Replace `sphericalDelaunayEdges` with `nearestNeighborEdges` in `loadShapeGLB()`
2. Delete `sphericalDelaunayEdges()` function
3. Verify: cube/torus/cylinder/pyramid all use k-NN edges on their MeshSurfaceSampler points
4. Visual check: triangles should look icosahedron-like, no sphere-projection artifacts

### Phase 2: Replace sampling with FPS (2-3 hours)
1. Implement `weldVertices(positions, threshold)`
2. Implement `farthestPointSampling(vertices, targetCount, seed)`
3. Wire `loadShapeGLB()` to use geometry vertices → weld → FPS → N points → k-NN edges
4. Remove `MeshSurfaceSampler` import from `loadShapeGLB()` (keep import if used elsewhere)
5. Verify determinism: same shape always produces identical points
6. Visual check: point distribution should be uniform, no clusters or gaps

### Phase 3: GLB spike (deferred, timebox 4 hours)
1. Load a test GLB model (use a free model from poly.pizza or sketchfab)
2. Extract vertices, weld, FPS to N points, k-NN edges
3. Render and evaluate: are there visible bridge-across-space edges?
4. If yes: are they acceptable at the current N? Can increasing N fix it?
5. Write findings to a GLB_REMESH_SPIKE.md doc — decision on whether to pursue geodesic edges

### Phase 4: Point count evaluation (deferred)
1. Render all shapes side by side at N=478
2. Evaluate visual density consistency
3. If cube looks too dense: test N=300 globally, or per-shape multipliers
4. If torus looks too sparse: test N=600 globally, or per-shape multipliers
5. Decision: keep fixed N, change N globally, or implement per-shape counts

---

## Verification Checklist

### Phase 1 (edge fix)
- [ ] `sphericalDelaunayEdges()` is deleted
- [ ] `loadShapeGLB()` calls `nearestNeighborEdges(shapeTargets, 6)`
- [ ] Cube wireframe is icosahedron-like (not sphere-projected nonsense)
- [ ] Torus wireframe is icosahedron-like (as much as k-NN allows on a torus)
- [ ] Cylinder wireframe is icosahedron-like
- [ ] Pyramid wireframe is icosahedron-like

### Phase 2 (FPS sampling)
- [ ] `farthestPointSampling()` exists and is deterministic
- [ ] `weldVertices()` exists and deduplicates corner vertices
- [ ] `loadShapeGLB()` uses FPS, not MeshSurfaceSampler
- [ ] Same shape produces identical points across reloads
- [ ] Point distribution is visually uniform on all procedural shapes
- [ ] MeshSurfaceSampler usage removed from `loadShapeGLB()`

### Phase 3 (GLB)
- [ ] Test GLB model loads and renders with FPS + k-NN edges
- [ ] Visual quality evaluated and documented
- [ ] GLB_REMESH_SPIKE.md written with findings and decision

### Phase 4 (density)
- [ ] All shapes rendered side by side at N=478
- [ ] Visual density consistency evaluated
- [ ] Decision documented: keep fixed N, change N, or implement per-shape counts
