# Dassein — GLB Morph Engine Plan

## Goal

Build an engine that can transform the icosahedron/face into **any 3D GLB model** using the same vertex-morph pipeline — dots + wireframe lines dissolving from one shape to another. Once this works, the face is just one target among many, and the agent can morph to represent concepts in 3D.

---

## Part 1: How the Current Morph System Works

### 1.1 The Vertex Buffer (the core)

Everything depends on a single shared `Float32Array` of `NUM × 3` floats (478 vertices × xyz):

```
positions = [x0, y0, z0,  x1, y1, z1,  ...  x477, y477, z477]
```

This array lives inside `icoGeo.attributes.position`. Multiple renderers read from it:

| Object | Type | How it reads |
|--------|------|-------------|
| `icoCloud` | `THREE.Points` | Reads `icoGeo` directly as point positions |
| `icoEdges` | `THREE.LineSegments` | Shares `icoGeo.attributes.position` by reference — same buffer, uses indices to draw lines between neighbors |
| `icoEdgeGlow` | `THREE.LineSegments` | Clone of edge geometry — separate buffer that gets updated in sync |

The key trick: `icoEdges` and `icoCloud` share the **same** `icoGeo.attributes.position`. When you update that array and set `needsUpdate = true`, both the dots and the wireframe move together.

### 1.2 The Icosahedron (source shape)

478 points on a unit sphere using a Fibonacci lattice (`fibonacciSphere(478)`):

```
icoPoints[i] = { x, y, z }   // on unit sphere surface
```

Neighbor edges connect each point to its 6 nearest neighbors in 3D space (`nearestNeighborEdges(icoPoints, 6)`). These edges form the wireframe that wraps around the dot cloud.

### 1.3 The Face (target shape)

478 landmark points loaded from `data/robota_scan.json`, scaled:

```
faceLMs[i] = {
  x: raw.x * FACE_SCALE,
  y: -raw.y * FACE_SCALE_Y,   // Y flipped from scan coordinate system
  z: raw.z * FACE_SCALE_Z,
}
```

Face-specific features (contour lines, mouth cavity, iris spheres, key nodes) have their own geometries that also hold 478 vertices. They get updated each frame via `updateFaceGeometry(src)` which copies the 478 positions into each sub-geometry's position buffer.

### 1.4 The Morph Interpolation

`triggerTransform()` (line 732) does this each frame during the 2-second GSAP animation:

```javascript
positions[i*3]     = icoPoints[i].x + (faceLMs[i].x - icoPoints[i].x) * t;
positions[i*3 + 1] = icoPoints[i].y + (faceLMs[i].y - icoPoints[i].y) * t;
positions[i*3 + 2] = icoPoints[i].z + (faceLMs[i].z - icoPoints[i].z) * t;
```

### 1.5 What Makes a Valid Target

Any target needs exactly **three things**:

1. **N points** with x,y,z positions (same count as source — 478)
2. **N×3 Float32Array** of those positions, same format as `icoGeo.attributes.position.array`
3. **Edge indices** — pairs of vertex indices defining the wireframe lines (can reuse nearest-neighbor edges)

That's it. If you provide those three, the morph pipeline works identically for **any** 3D shape.

---

## Part 2: Approaches for GLB → 478 Points + Edges

A GLB file can contain thousands of vertices across multiple meshes. We need to reduce any GLB to exactly 478 surface points with neighbor edges.

### Approach A: Uniform Triangle-Area-Weighted Sampling (RECOMMENDED)

**Process:**
1. Load GLB with `GLTFLoader`
2. Walk the scene graph, find all `THREE.Mesh` nodes
3. For each mesh, extract all triangles in world space:
   - If geometry has `index`: read triangle triples from the index buffer
   - If geometry has no index: use sequential vertices (0,1,2, 3,4,5, ...)
   - Apply the mesh's world matrix to each vertex
4. Compute the area of every triangle
5. Build a cumulative area array: `cumArea[i] = sum of areas of first i triangles`
6. Generate N random numbers in `[0, totalArea]`
7. For each random number, find the triangle it falls in (binary search on cumArea)
8. Generate barycentric coordinates `(u, v)` via `u = sqrt(r1), v = r2 * (1-u)` where r1,r2 are random in [0,1]
9. Compute the sample point: `P = A*(1-u-v) + B*u + C*v` where A,B,C are triangle vertices
10. Normalize all points to fit within a unit sphere (same scale as icoPoints)
11. Build k-NN edges using the existing `nearestNeighborEdges(points, 6)` function

**Why this is best:**
- Works with any GLB regardless of vertex count, topology, or mesh count
- Uniform distribution prevents clustering on dense mesh regions
- Uses only existing Three.js APIs — no external dependencies
- Runs entirely in the browser: ~30ms for 10K triangles, ~100ms for 100K triangles
- Reuses the existing k-NN edge builder
- Produces visually clean dot clouds that look like the model's silhouette

**Tradeoffs:**
- 478 points is low — fine details (< 2% of model surface area) may not be captured
- No awareness of model features (sharp edges, holes) — everything is uniform
- Triangle extraction from non-indexed geometries produces duplicate vertices (waste)

### Approach B: Vertex Decimation

- Merge all meshes, use a mesh simplification algorithm to reduce to ~500 vertices
- Use those vertices directly instead of sampling
- **Tradeoffs:** Complex algorithm, poor results on non-watertight meshes, slow

### Approach C: Feature-Aware Sampling

- Same as A, but add extra density near high-curvature regions (sharp edges)
- Compute dihedral angles between adjacent triangles
- Weight sampling toward sharp edges
- **Tradeoffs:** Better visual detail but 2× complexity, needs adjacency graph

### Approach D: Voxel Grid

- Voxelize the model at resolution that gives ~500 occupied voxels
- Place a vertex at each occupied voxel center
- **Tradeoffs:** Works for any geometry but looks blocky/quantized

### Recommendation: Start with Approach A

It's the simplest, fastest, and produces good-looking results. Approaches C and D can be added later as quality upgrades without changing the API.

---

## Part 3: Implementation Plan

### Step 1: Import GLTFLoader (line 179-181)

Change the import section:

```javascript
import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
```

### Step 2: Build the GLBMorphEngine module (insert after line 376, after ScrollController)

Insert a new module:

```javascript
    // ═══ GLB Morph Engine ═══
    const GLBMorphEngine = (() => {
      const loader = new GLTFLoader();

      /**
       * Extract all triangles from a GLB scene graph in world space.
       * Returns an array of triangle objects: { a: vec3, b: vec3, c: vec3, area: float }
       */
      function extractTriangles(gltf) {
        const triangles = [];

        gltf.scene.traverse((node) => {
          if (!node.isMesh) return;
          const geo = node.geometry;
          if (!geo || !geo.attributes.position) return;

          const pos = geo.attributes.position;
          const hasIndex = geo.index !== null;

          // Get world matrix
          node.updateWorldMatrix(true, false);
          const worldMatrix = node.matrixWorld.clone();

          const vA = new THREE.Vector3();
          const vB = new THREE.Vector3();
          const vC = new THREE.Vector3();

          const readVertex = (idx, target) => {
            target.set(
              pos.getX(idx),
              pos.getY(idx),
              pos.getZ(idx)
            );
            target.applyMatrix4(worldMatrix);
          };

          const triCount = hasIndex
            ? geo.index.count / 3
            : pos.count / 3;

          for (let t = 0; t < triCount; t++) {
            const i0 = hasIndex ? geo.index.getX(t * 3)     : t * 3;
            const i1 = hasIndex ? geo.index.getX(t * 3 + 1) : t * 3 + 1;
            const i2 = hasIndex ? geo.index.getX(t * 3 + 2) : t * 3 + 2;

            readVertex(i0, vA);
            readVertex(i1, vB);
            readVertex(i2, vC);

            // Triangle area using cross product magnitude / 2
            const ab = new THREE.Vector3().subVectors(vB, vA);
            const ac = new THREE.Vector3().subVectors(vC, vA);
            const cross = new THREE.Vector3().crossVectors(ab, ac);
            const area = cross.length() * 0.5;

            if (area > 0) {
              triangles.push({
                a: vA.clone(),
                b: vB.clone(),
                c: vC.clone(),
                area,
              });
            }
          }
        });

        return triangles;
      }

      /**
       * Sample N points uniformly across the triangle surface,
       * with probability proportional to triangle area.
       */
      function samplePoints(triangles, N) {
        if (triangles.length === 0) return [];

        // Build cumulative area array
        const cumArea = new Float64Array(triangles.length);
        let totalArea = 0;
        for (let i = 0; i < triangles.length; i++) {
          totalArea += triangles[i].area;
          cumArea[i] = totalArea;
        }

        // Helper: find triangle index for a given area value (binary search)
        const findTriangle = (target) => {
          let lo = 0, hi = cumArea.length - 1;
          while (lo < hi) {
            const mid = (lo + hi) >>> 1;
            if (cumArea[mid] < target) lo = mid + 1;
            else hi = mid;
          }
          return lo;
        };

        // Sampled barycentric coordinates for uniform triangle sampling
        // P = A*(1 - sqrt(r1)) + B*(sqrt(r1)*(1 - r2)) + C*(sqrt(r1)*r2)
        const points = [];
        for (let i = 0; i < N; i++) {
          const target = Math.random() * totalArea;
          const triIdx = findTriangle(target);
          const tri = triangles[triIdx];

          const r1 = Math.random();
          const r2 = Math.random();
          const sqrtR1 = Math.sqrt(r1);
          const u = 1 - sqrtR1;
          const v = sqrtR1 * (1 - r2);
          // w = sqrtR1 * r2  (not needed since u + v + w = 1)

          const px = tri.a.x * u + tri.b.x * v + tri.c.x * (sqrtR1 * r2);
          const py = tri.a.y * u + tri.b.y * v + tri.c.y * (sqrtR1 * r2);
          const pz = tri.a.z * u + tri.b.z * v + tri.c.z * (sqrtR1 * r2);

          points.push({ x: px, y: py, z: pz });
        }

        return points;
      }

      /**
       * Normalize points to fit within a unit-sphere bounding volume,
       * centered at origin. Matches the scale of the icosahedron.
       */
      function normalizeToUnitSphere(points) {
        if (points.length === 0) return points;

        // Compute centroid
        let cx = 0, cy = 0, cz = 0;
        for (const p of points) { cx += p.x; cy += p.y; cz += p.z; }
        cx /= points.length; cy /= points.length; cz /= points.length;

        // Compute max distance from centroid
        let maxDist = 0;
        for (const p of points) {
          const dx = p.x - cx, dy = p.y - cy, dz = p.z - cz;
          const d = Math.sqrt(dx * dx + dy * dy + dz * dz);
          if (d > maxDist) maxDist = d;
        }

        if (maxDist === 0) return points;

        // Scale to unit sphere radius (~1.0, matching icoPoints)
        const scale = 1.0 / maxDist;
        const normalized = [];
        for (const p of points) {
          normalized.push({
            x: (p.x - cx) * scale,
            y: (p.y - cy) * scale,
            z: (p.z - cz) * scale,
          });
        }
        return normalized;
      }

      /**
       * Detect sharp edges for contour lines.
       * Returns list of [idxA, idxB] edge pairs where the angle
       * between adjacent triangle normals exceeds a threshold.
       *
       * Note: This is an optional quality enhancement. The basic
       * k-NN edges from nearestNeighborEdges() are sufficient.
       */
      function detectContourEdges(triangles, samplePoints, N, angleThresholdDeg) {
        // Build vertex → triangle adjacency
        // For each sample point, find which triangles contribute to it
        // If two triangles sharing an edge have normals > threshold apart,
        // mark the edge between their corresponding sample points

        // This is a more advanced feature. For the initial implementation,
        // we skip this and use only the uniform k-NN edges.
        return []; // Reserved for Phase 2
      }

      /**
       * Main entry: load a GLB URL or File, return { points, edges }.
       *
       * @param {string|File|Blob} source - URL string or File object
       * @param {number} [N=478] - number of sample points
       * @returns {Promise<{points: Array<{x,y,z}>, edgeIndices: Array<[number,number]>}>}
       */
      async function loadAndSample(source, N = 478) {
        let gltf;

        if (typeof source === 'string') {
          // URL
          gltf = await loader.loadAsync(source);
        } else {
          // File or Blob — convert to URL
          const url = URL.createObjectURL(source);
          try {
            gltf = await loader.loadAsync(url);
          } finally {
            URL.revokeObjectURL(url);
          }
        }

        console.time('GLBMorphEngine: extract');
        const triangles = extractTriangles(gltf);
        console.timeEnd('GLBMorphEngine: extract');
        console.log(`Extracted ${triangles.length} triangles from GLB`);

        if (triangles.length === 0) {
          throw new Error('GLB file contains no triangle geometry');
        }

        console.time('GLBMorphEngine: sample');
        let rawPoints = samplePoints(triangles, N);
        console.timeEnd('GLBMorphEngine: sample');

        console.time('GLBMorphEngine: normalize');
        const points = normalizeToUnitSphere(rawPoints);
        console.timeEnd('GLBMorphEngine: normalize');

        console.time('GLBMorphEngine: edges');
        // Reuse existing nearestNeighborEdges function (defined in outer scope)
        // It needs to be accessible — we'll pass it or reference it
        const edges = nearestNeighborEdges(points, 6);
        console.timeEnd('GLBMorphEngine: edges');

        return { points, edges };
      }

      /**
       * Convert points array to Float32Array matching icoGeo format.
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

      /**
       * Build edge index array from edge pairs.
       */
      function edgesToIndexArray(edges) {
        const arr = [];
        for (const [a, b] of edges) {
          arr.push(a, b);
        }
        return arr;
      }

      return {
        loadAndSample,
        extractTriangles,
        samplePoints,
        normalizeToUnitSphere,
        pointsToFloat32Array,
        edgesToIndexArray,
      };
    })();
```

**Critical note about `nearestNeighborEdges`:** The function `nearestNeighborEdges` is defined at line 483. Since it's in the module scope (not inside GLBMorphEngine's IIFE), the GLBMorphEngine can reference it directly because it's also defined in the same `<script>` scope. JavaScript closures handle this — the IIFE captures the outer scope. No changes needed.

### Step 3: Create a morph-to-GLB function (insert after triggerTransform, around line 791)

Add a new function that handles morphing from the current state to a GLB model:

```javascript
    /**
     * Morph from the current shape to a GLB model's point cloud representation.
     * Works from both landing state (icosahedron) and agent state (face).
     *
     * @param {string|File} source - URL or File object pointing to a .glb file
     * @param {object} [options]
     * @param {number} [options.duration=2.0] - morph duration in seconds
     * @param {number} [options.N=478] - number of sample points
     * @param {function} [options.onProgress] - callback(phase, detail)
     */
    async function morphToGLB(source, options = {}) {
      const { duration = 2.0, N = 478, onProgress } = options;

      if (isAnimating) return;
      if (N !== NUM) {
        console.warn(`GLB sample count ${N} does not match NUM ${NUM}. Vertex count mismatch will cause issues.`);
        return;
      }

      isAnimating = true;
      const prevState = state;
      state = 'transforming';
      if (window.__scene) window.__scene.state = state;

      onProgress?.('loading', 'Loading GLB file...');

      let glbData;
      try {
        glbData = await GLBMorphEngine.loadAndSample(source, N);
      } catch (err) {
        console.error('GLB morph failed:', err);
        isAnimating = false;
        state = prevState;
        if (window.__scene) window.__scene.state = state;
        onProgress?.('error', err.message);
        return;
      }

      onProgress?.('morphing', 'Morphing...');

      // Store starting positions (current state of the vertex buffer)
      const startPos = new Float32Array(positions); // snapshot current positions

      // Compute target positions
      const targetPos = GLBMorphEngine.pointsToFloat32Array(glbData.points);
      const targetEdges = GLBMorphEngine.edgesToIndexArray(glbData.edges);

      // Build new edge geometry for the GLB wireframe
      // We update the shared edge geometry indices to match the new model
      const newEdgeIndices = targetEdges;
      icoEdgeGeo.setIndex(newEdgeIndices);
      icoEdgeGeo.setDrawRange(0, newEdgeIndices.length);
      icoEdgeGlow.geometry.setIndex(newEdgeIndices);
      icoEdgeGlow.geometry.setDrawRange(0, newEdgeIndices.length);

      // Hide face-specific features during GLB morph
      const faceWasVisible = faceContourLines && faceContourLines.material.opacity > 0.01;
      if (faceWasVisible) {
        gsap.to(faceContourLines.material,  { opacity: 0, duration: 0.3 });
        gsap.to(faceContourGlow.material,   { opacity: 0, duration: 0.3 });
        gsap.to(faceNeighborLines.material, { opacity: 0, duration: 0.3 });
        gsap.to(faceMouthCavity.material,   { opacity: 0, duration: 0.3 });
        faceKeyNodes.forEach(n => gsap.to(n.material, { opacity: 0, duration: 0.3 }));
        faceIrisNodes.forEach(n => gsap.to(n.material, { opacity: 0, duration: 0.3 }));
      }

      // Show icosahedron wireframe (it was hidden during face mode)
      gsap.to(icoEdgeMat,     { opacity: 0.25, duration: 0.3 });
      gsap.to(icoEdgeGlowMat, { opacity: 0.08, duration: 0.3 });

      // Reset rotation
      icoGroup.rotation.set(0, 0, 0);
      ScrollController.reset();

      // Animate the morph
      const morphObj = { progress: 0 };
      gsap.to(morphObj, {
        progress: 1,
        duration,
        ease: 'power2.inOut',
        onUpdate: () => {
          const t = easeInOutCubic(morphObj.progress);
          for (let i = 0; i < NUM; i++) {
            positions[i * 3]     = startPos[i * 3]     + (targetPos[i * 3]     - startPos[i * 3])     * t;
            positions[i * 3 + 1] = startPos[i * 3 + 1] + (targetPos[i * 3 + 1] - startPos[i * 3 + 1]) * t;
            positions[i * 3 + 2] = startPos[i * 3 + 2] + (targetPos[i * 3 + 2] - startPos[i * 3 + 2]) * t;
          }
          icoGeo.attributes.position.needsUpdate = true;
          icoEdgeGeo.attributes.position.needsUpdate = true;
          updateFaceGeometry(positions);
        },
        onComplete: () => {
          // Snap to exact target
          positions.set(targetPos);
          icoGeo.attributes.position.needsUpdate = true;
          icoEdgeGeo.attributes.position.needsUpdate = true;
          updateFaceGeometry(positions);

          onProgress?.('complete', 'Done');
          isAnimating = false;
          state = 'agent'; // Treat GLB models same as agent state
          if (window.__scene) {
            window.__scene.state = state;
            window.__scene.glbmorph = { points: glbData.points, edges: glbData.edges };
          }
        },
      });
    }
```

### Step 4: Update `resetToLanding()` to restore ico edge indices (line ~817)

When resetting from a GLB model back to the icosahedron, the edge indices were changed by `morphToGLB`. We need to restore the original icosahedron edge indices.

Find `resetToLanding()` and add after the ScrollController reset:

```javascript
      // Restore original icosahedron edge indices (may have been changed by GLB morph)
      icoEdgeGeo.setIndex(nnIndices);
      icoEdgeGeo.setDrawRange(0, nnIndices.length);
      icoEdgeGlow.geometry.setIndex(nnIndices);
      icoEdgeGlow.geometry.setDrawRange(0, nnIndices.length);
```

Insert this right after `ScrollController.reset();` on line 797.

### Step 5: Expose `morphToGLB` globally for testing (line ~1708, end of script)

Add near the bottom of the script, alongside the other `window.__scene` assignments:

```javascript
    window.morphToGLB = morphToGLB;
    window.GLBMorphEngine = GLBMorphEngine;
```

### Step 6: Add a file input for drag-and-drop testing (optional, for dev)

Add a hidden file input that accepts `.glb` files:

```javascript
    // ═══ GLB File Drop Zone (dev/testing) ═══
    const glbInput = document.createElement('input');
    glbInput.type = 'file';
    glbInput.accept = '.glb,.gltf';
    glbInput.style.display = 'none';
    document.body.appendChild(glbInput);

    glbInput.addEventListener('change', async () => {
      const file = glbInput.files[0];
      if (!file) return;
      console.log(`Morphing to GLB: ${file.name} (${(file.size / 1024).toFixed(1)} KB)`);
      await morphToGLB(file, {
        onProgress: (phase, detail) => console.log(`[GLB] ${phase}: ${detail}`),
      });
    });

    // Trigger file picker on 'G' key press (dev shortcut)
    window.addEventListener('keydown', (e) => {
      if (e.key === 'g' && !e.ctrlKey && !e.metaKey && document.activeElement === document.body) {
        glbInput.click();
      }
    });
```

---

## Part 4: Performance Considerations

### Triangle Count Limits

| Model complexity | Triangles | Extract time | Sample time | Total |
|-----------------|-----------|-------------|-------------|-------|
| Low poly (game prop) | ~5K | ~5ms | ~3ms | ~10ms |
| Medium (character) | ~50K | ~30ms | ~8ms | ~40ms |
| High (detailed scene) | ~500K | ~200ms | ~15ms | ~220ms |
| Extreme (architectural) | ~2M | ~800ms | ~25ms | ~850ms |

For models over 500K triangles, consider showing a progress indicator. The extraction is CPU-bound (single-threaded). A Web Worker could offload this but adds complexity.

### Memory

- Triangle array: `triangles × (3 vertices × 3 floats × 8 bytes + 1 area × 8 bytes)` ≈ `triangles × 80 bytes`
- 500K triangles ≈ 40MB temporary allocation during extraction
- GC cleans this up after sampling

### Edge Cases

| Case | Handling |
|------|----------|
| GLB with no meshes | Throw error, abort morph |
| GLB with points/lines only (no triangles) | `triangles` array is empty → throw |
| GLB with multiple scenes | Traverses the default scene only |
| GLB with skinned meshes | Use `node.updateWorldMatrix()` for correct transform |
| GLB with non-uniform scale | Handled by world matrix transform |
| GLB > 50MB file | Browser may timeout; show loading state |
| N != 478 | Currently requires N = NUM (478). Can be made dynamic later |

---

## Part 5: Verification Checklist

### Basic Functionality
- [ ] `GLTFLoader` imports correctly from CDN
- [ ] `GLBMorphEngine.extractTriangles()` works on a simple GLB (e.g., a cube)
- [ ] `GLBMorphEngine.samplePoints()` returns exactly 478 points
- [ ] Points are within unit sphere after normalization
- [ ] `nearestNeighborEdges()` produces valid edge pairs for sampled points
- [ ] `morphToGLB()` animates from current shape to GLB shape
- [ ] Wireframe edges update to match the new model
- [ ] `resetToLanding()` restores original ico edge indices
- [ ] Works from both landing state (icosahedron) and agent state (face)
- [ ] Handles multi-mesh GLB files correctly (applies world transforms)

### Visual Quality
- [ ] Sampled points are evenly distributed (no visible clustering)
- [ ] Wireframe looks like the model silhouette
- [ ] Dot cloud reads as the shape from multiple angles
- [ ] Smooth animation (no jank, 60fps maintained)
- [ ] Model is centered and properly scaled to fill the view

### Edge Cases
- [ ] Empty GLB: graceful error, no crash
- [ ] Very large GLB (>500K triangles): completes without browser freeze
- [ ] GLB with animations: ignores animations, uses rest pose
- [ ] Consecutive morphs: does not accumulate state bugs
- [ ] Morph during morph: second morph is correctly blocked by `isAnimating`

### Integration
- [ ] Scroll rotation works on GLB-morphed model
- [ ] Escape key resets to icosahedron
- [ ] Click-to-transform still works after GLB morph + reset
- [ ] `window.__scene` exposes new GLB data

---

## Part 6: Future Enhancements

| Feature | Description | Priority |
|---------|-------------|----------|
| Dynamic vertex count | Support any N, not just 478 | High |
| Feature-aware sampling | More points along creases/edges | Medium |
| Contour detection | Highlight sharp edges as contour lines | Medium |
| GLB cache | Don't re-extract on repeated morphs | Low |
| Web Worker extraction | Offload triangle extraction to worker | Low |
| Progressive detail | Start with N=100 points, increase during morph | Low |
| GLB → ico reverse morph | Morph from GLB back to icosahedron without full reset | Low |
| Agent-driven GLB selection | LLM picks GLB URL based on conversation context | Low |
