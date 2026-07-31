# GLB Import Spike — Findings

## Test Model

**Model:** Duck (Khronos glTF Sample Models)
**Source:** `https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Models/main/2.0/Duck/glTF-Binary/Duck.glb`
**License:** Public domain (Khronos Group glTF sample models)
**Format:** glTF 2.0 Binary (.glb)
**Original vertex count:** ~1,400

## Pipeline

1. Load via `GLTFLoader` (`three/addons/loaders/GLTFLoader.js`)
2. Traverse scene tree, collect `position` attributes from all `Mesh` nodes
3. Weld duplicate vertices (threshold 0.001)
4. Farthest Point Sampling → N=478 points
5. k-NN edges (k=6) on sampled points

## Visual Evaluation

### Positive

- FPS produces uniformly distributed points across the duck's body surface
- k-NN edges connect points into near-equilateral triangles on convex surfaces (body, head)
- The icosahedron-like visual pattern is clearly recognizable — the duck surface is draped in the same wireframe net as the sphere and face
- No visible vertex clustering or gaps

### Known Issues

- **Bridging across concave regions is visible.** The gap between the duck's bill and chest shows some edges connecting across empty space. This is the expected k-NN Euclidean failure mode on non-convex shapes. The effect is minor at N=478 — most k-NN neighbors are close enough that Euclidean ≈ geodesic locally. The bill gap bridging is noticeable on close inspection but doesn't dominate the visual.
- **Density mismatch.** The duck has a larger surface area than the procedural shapes (cube/torus). At N=478, the points are noticeably sparser on the duck. The wireframe looks less dense than on the sphere or face.
- **Scale independence.** The absolute scale of the GLB model (meters) doesn't match the scene units. FPS doesn't care about scale, but the visual size of the rendered wireframe depends on the camera distance.

### Acceptability

The bridging artifacts are **acceptable** at N=478 for this model. The icosahedron-like wireframe pattern is clearly present. The gaps across the bill gap are minor and read as "the wireframe stretched over a form" rather than "broken geometry."

## Decision

**Defer geodesic-aware k-NN.** The Euclidean k-NN + FPS pipeline produces acceptable results on this test model. The visual quality is good enough for the current scope.

### Recommendations

1. **Ship with Euclidean k-NN** for GLB models as-is.
2. **Add per-model point count multiplier** if density mismatch becomes an issue (duck at N=478 is sparse).
3. **Re-evaluate geodesic k-NN** if concave bridging becomes visually unacceptable — only then implement Dijkstra on the mesh face-adjacency graph.
4. **Do not pursue isotropic remeshing** in the browser. FPS + k-NN is simpler, faster, and produces the icosahedron-like visual pattern on all tested shapes.

## Verification

- Duck model loads via GLTFLoader and renders with FPS + k-NN edges
- FPS is deterministic — same model produces identical points on every load
- k-NN edges produce icosahedron-like triangular wireframe on convex regions
- Minor bridging across concave gaps (bill/chest) is visible but acceptable
