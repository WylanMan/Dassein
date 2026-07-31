# Dassein — Wireframe Triangulation Architecture

## Goal

Render any 3D object — procedural primitives, GLB models, face scans — as a **triangular mesh draped across its surface.** The mesh is formed by point-cloud dots and the wireframe edges that connect them. No filled surfaces, no edge-detected overlays, no model-native rectilinear wireframes. The final visual is always the same: a net of dots and lines that wraps the object's form.

The triangulation must be **geometrically similar** — triangles of roughly equal size and shape, distributed uniformly across the surface — like the faces of a subdivided icosahedron. Denser where curvature demands it, but never random, never stretched, never bridging across empty space.

The **icosahedron sphere** is the reference pattern. Every other shape — a cube, a torus, a face scan, an imported GLB model — should look like someone took that same icosahedral wireframe net and wrapped it around the new form. Same visual density, same triangle regularity, same point-to-edge relationship.

## Design Philosophy

All shapes render through a **single rendering engine** with shared geometry buffers and a common morph pipeline. The canonical examples are the **icosahedron** and the **face** — both use nearest-neighbor edges on well-distributed points, producing the target pattern of geometrically similar triangles with uniform density. This pattern must extend to all shapes.

---

## Rendering Layers

Three concurrent layers share a single position buffer. The morph engine drives the position buffer; all layers follow automatically.

| Layer | Type | Material | Role |
|---|---|---|---|
| Point cloud | `THREE.Points` | Additive blend, `opacity: 0.55` | 478 cyan dots — the "atoms" |
| Wireframe edges | `THREE.LineSegments` | Opaque cyan, `depthTest: true` | The visible triangulation |
| Edge glow | `THREE.LineSegments` | Opaque cyan, `depthTest: false` | Subtle bloom passthrough |

The point cloud and edge glow share the position buffer by reference (`icoEdgeGlow.geometry.attributes.position = icoGeo.attributes.position`). The wireframe edges use a separate `icoEdgeGeo` geometry but its `.attributes.position` is set to the same `icoGeo.attributes.position` array — morphs write to one buffer and all three layers update.

---

## Shared Position Buffer

```
icoGeo (BufferGeometry)
 ├── attributes.position → positions (Float32Array[478*3])
 │
 ├── icoCloud (Points)          ← reads positions, renders dots
 ├── icoEdges (LineSegments)    ← reads positions via icoEdgeGeo, renders edges
 └── icoEdgeGlow (LineSegments) ← reads positions via cloned geometry, renders glow
```

The face contour layer (`faceContourLines`, `faceContourGlow`, `faceMouthCavity`, `faceKeyNodes`, `faceIrisNodes`) has its own position buffer but is synced via `updateFaceGeometry(positions)` on every animation frame during morphs — it follows the shared buffer indirectly.

---

## Point Distribution

Points define where the dots render and where edges connect. Each mode has its own point source.

### Landing (icosahedron sphere)

- **Source:** `fibonacciSphere(478)` — deterministic, evenly distributed points on a unit sphere
- **Property:** Euclidean neighbor distances are near-constant; the distribution is visually uniform with no clusters or gaps
- **Works because:** Sphere is convex, so Euclidean distance ≈ geodesic distance

### Face

- **Source:** 478 3D landmarks from `data/robota_scan.json`, scaled by `FACE_SCALE`
- **Property:** Dense in high-curvature regions (nose, lips, eyes), sparse on flat surfaces (forehead). Not uniform but follows the natural topology of a face scan
- **Works because:** The face is roughly convex at this scale, so k-NN Euclidean edges still produce a reasonable surface triangulation

### Procedural shapes (cube, cylinder, pyramid, torus)

**Current (broken):**
- `MeshSurfaceSampler` produces 478 random area-proportional samples
- Random distribution means clusters and gaps; pattern changes every call
- Fixed 478 points ignores surface area (cube and torus get the same count)

**Target:**
- Use the procedural geometry's own vertices directly — the geometry already has uniform vertex distribution at the given subdivision level
- Point count scales with surface area naturally (higher subdivision → more vertices)
- No sampling step needed — the geometry is the point source

### Imported GLB models

**Target:**
- Load the model, extract the mesh geometry
- Apply an isotropic remesh step to produce uniformly sized triangles with controlled density
- Use the remeshed vertices as point positions and the remeshed triangle edges as wireframe edges
- Density parameter controls the point/triangle count, scaling with object surface area
- This produces the same "icosahedron-like" visual pattern on any model

---

## Edge Generation

Edges define which point pairs are connected by visible lines. This is the most critical design decision — the wrong edge model produces irregular, wrong-looking wireframes.

### Current implementations

#### k-NN Euclidean edges (`nearestNeighborEdges(points, k)`)

For each point, connect to its `k` nearest neighbors by straight-line 3D distance. Deduplicate.

**Works well for:** Sphere (convex, Euclidean ≈ geodesic), face (roughly convex, dense points)
**Fails for:** Torus (connects through hole), concave surfaces, any shape where surface distance diverges from straight-line distance

#### Spherical Delaunay edges (`sphericalDelaunayEdges(points)`)

Project all 3D points to spherical coordinates `(theta, phi)`, run 2D Delaunay triangulation on those coordinates, extract triangle edges.

**Used in:** `loadShapeGLB()` for procedural shapes
**Problem:** Every point is projected to a sphere before triangulating. The resulting edges have no relationship to the actual 3D surface. On a cube, points on the front face get connected to points on the back face because their `(theta, phi)` is nearby. On a torus, the triangulation bridges across the hole. On a cylinder, top-cap points connect to bottom-cap points. The output is geometrically meaningless.

**Why it's in the codebase:** It was chosen in PLAN.md v6 as a "fix" to replace the even worse nearest-vertex approach from v4/v5. It eliminated the filled-mesh layer but introduced a worse triangulation model.

### Target edge model: intrinsic surface edges

The edge set must respect the actual surface geometry. There are three correct approaches:

#### A. Native geometry edges (simplest, preferred for procedural shapes)

Use the geometry's own triangle indices directly. A `BoxGeometry(0.5, 0.5, 0.5, 8, 8, 8)` already has uniformly distributed vertices and proper surface-respecting triangles. Extract the vertex positions → point cloud positions. Extract the unique edges from the index array → wireframe edges.

**Properties:**
- Always surface-correct (the geometry defines the surface)
- Triangles are geometrically similar (controlled by subdivision)
- Point count scales with subdivision level
- Zero additional computation — no sampling, no triangulation, no projection

#### B. Geodesic k-NN edges

For each point, compute geodesic (surface-following) distance to every other point on the mesh using Dijkstra or heat method on the mesh graph. Connect to the k nearest. This generalizes the Euclidean k-NN pattern to arbitrary surfaces.

**When to use:** When you want the same k-NN visual pattern as the icosahedron on an arbitrary mesh, but the raw mesh vertices are too dense or irregular.

#### C. Isotropic remesh → native edges

Run an isotropic remeshing algorithm (e.g., Botsch & Kobbelt 2004) on the input geometry to produce uniformly sized, near-equilateral triangles. Then use the remeshed geometry's vertices and edges directly (same as approach A).

**Properties:**
- Guaranteed uniform triangles on any input
- Controllable edge length target
- Surface area → point count relationship is deterministic
- The canonical approach for "make this arbitrary model look like an icosahedron"

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
| Solid shapes | `shapeTargetEdgeIndices` | → should come from geometry's native indices, not Delaunay |

### Swap timing

All morph transitions use the same pattern:
- **t < 0.5:** Old edge indices active, opacity crossfading out
- **t = 0.5:** `setWireframeEdgeIndices(targetIndices)` swaps the index buffer
- **t > 0.5:** New edge indices active, opacity crossfading in

This avoids popping — the position buffer is mid-morph at t=0.5, so both the old and new edge sets would look wrong. The index swap happens invisibly while opacity is at its minimum.

---

## Opacity Scheme

Unified wireframe-only scheme. No solid layer remains.

| Mode | Wireframe edges | Edge glow | Point cloud | Contours | Mouth | Key nodes | Iris nodes |
|---|---|---|---|---|---|---|---|
| Landing (sphere) | 0.28 | 0.10 | 0.55 | 0 | 0 | 0 | 0 |
| Face | 0.35 | 0.12 | 0.55 | 0.75 | 0.55 | 0.25 | 1.0/0.15 |
| Solid shapes | 0.22 | 0.08 | 0.55 | 0 | 0 | 0 | 0 |

Face mode gets higher wireframe opacity (0.35 vs 0.22) because the face contour lines overlay on top and the wireframe is a secondary visual element. In solid shape mode, the wireframe is the primary visual element and lower opacity reads better against the point cloud.

Iris nodes follow their own rule: opaque black dot (1.0) + subtle white glow (0.15) in face mode, hidden (0) otherwise.

---

## Morph Pipeline

Three morph paths exist:

### 1. Landing → Face (`triggerTransform()`)

Source positions: `icoPoints` (Fibonacci sphere)
Target positions: `faceLMs` (face scan landmarks)
Edge swap: `nnIndices` → `faceNNIndices` at t=0.5
Duration: 2.0s
Camera: z=6 → z=4.5
UI: overlay fades out, agent-ui and nav fade in

### 2. Shape switching (`switchShape()` → `morphToTarget()`)

Source positions: current position buffer state
Target positions: `getTargetsForShape(name)` — `faceLMs` for face, `icoPoints` for sphere, `shapeTargets` for solids
Edge swap: `nnIndices`/`faceNNIndices`/`shapeTargetEdgeIndices` at t=0.5
Duration: 1.5s
Resolves `shapeTargets` via `loadShapeGLB()` on first access

### 3. Agent → Landing (`resetToLanding()`)

Source positions: current position buffer state
Target positions: `icoPoints`
Edge swap: current → `nnIndices` at t=0.5
Duration: 1.5s
Camera: current z → z=6
UI: overlay fades in, agent-ui and nav fade out

### Common morph function (`morphToTarget(targets, shapeName, duration)`)

The unified morph function:
1. Snapshots current opacities for all layers
2. Computes target opacities based on `shapeName`
3. Runs a GSAP tween interpolating positions and crossfading opacities
4. Swaps edge indices at t=0.5
5. On completion: snaps positions to exact targets, sets final opacities, sets state

---

## Shape Architecture

### Current shape set

```javascript
const SHAPE_NAMES = ['face', 'sphere', 'cube', 'cylinder', 'pyramid', 'torus'];
```

All non-face, non-sphere shapes route through `loadShapeGLB(name)` which:
1. Creates a procedural geometry with hardcoded subdivision
2. Runs `MeshSurfaceSampler` to get 478 random surface samples
3. Runs `sphericalDelaunayEdges` on the samples for edge indices
4. Disposes the temp geometry

### Target shape architecture

Shapes should use a **geometry-first** approach:

```
loadShape(name)
  ├── procedural shapes (cube, cylinder, pyramid, torus, sphere):
  │     1. Create geometry at controlled subdivision
  │     2. Extract vertices → shapeTargets (point positions)
  │     3. Extract unique edges from geometry.index → shapeTargetEdgeIndices
  │     4. Point count = vertex count (varies with subdivision)
  │
  └── imported GLB models:
        1. Load mesh via GLTFLoader
        2. Extract geometry
        3. Apply isotropic remesh to uniform triangle size
        4. Extract vertices → point positions
        5. Extract edges → wireframe edge indices
```

The key difference: **no sampling, no Delaunay, no projection.** The geometry itself is the truth.

---

## Point Count Scaling

The current fixed 478 is wrong. Point count should scale with object surface area to maintain consistent visual density across all shapes.

| Shape | Surface area (approx) | Appropriate point count |
|---|---|---|
| Icosahedron sphere (r=1) | 12.57 | 478 (baseline) |
| Cube (0.5³) | 1.5 | ~60 |
| Torus (R=0.45, r=0.18) | 3.2 | ~120 |
| Face (scaled) | ~3.0 | 478 (fixed by scan) |
| Imported GLB | varies | proportional to area |

For procedural shapes, subdivision level controls density: `new BoxGeometry(0.5, 0.5, 0.5, N, N, N)` gives `(N+1)² × 6` vertices. For GLB models, a remesh edge-length target controls density.

The icoCloud `THREE.Points` and the edge `LineSegments` have no fixed vertex count requirement — `BufferGeometry` handles arbitrary sizes. The morph engine needs to handle variable point counts, or at minimum, the shape-specific geometries get their own buffer and the morph crossfades between separate rendering groups.

---

## What v6 Got Wrong (Post-Mortem)

PLAN.md v6 correctly identified the need to remove the solid layer and unify the opacity scheme. But it inherited two flawed assumptions from v4/v5 and added one new mistake:

1. **Fixed 478 points for everything** — inherited from the original icosahedron design. Never questioned.
2. **Random sampling via MeshSurfaceSampler** — inherited from v5. Introduces non-deterministic clustering.
3. **Spherical Delaunay triangulation** — the v6-introduced mistake. Geometrically unsound for non-spherical shapes. Projects all geometry to a sphere, losing the actual surface topology.

The correct design principle: **the geometry owns its triangulation.** Use the mesh's vertices for point positions and the mesh's triangle edges for wireframe edges. No sampling, no projection, no external triangulation algorithm.

---

## Verification Checklist

### Current (v6 as-implemented)
- [x] No solid layer code remains
- [x] Unified wireframe-only opacity scheme in `morphToTarget()`
- [x] `loadShapeGLB()` uses MeshSurfaceSampler + sphericalDelaunayEdges
- [x] Edge index swap at t=0.5 in all morph paths
- [x] Landing sphere: Fibonacci points + k-NN edges
- [x] Face mode: scan landmarks + k-NN edges + contour overlays

### Target (v7 geometry-first)
- [ ] Procedural shapes use native geometry edges, not Delaunay
- [ ] Point count scales with surface area per shape
- [ ] `sphericalDelaunayEdges()` removed
- [ ] `MeshSurfaceSampler` removed (or reserved for GLB remesh fallback)
- [ ] GLB model loading pipeline with isotropic remesh
- [ ] Morph engine supports variable point counts
- [ ] Shape wireframe triangles are geometrically similar (icosahedron-like)
- [ ] Visual density is consistent across all shapes
- [ ] Edge generation respects actual surface geometry (not spherical projection)
