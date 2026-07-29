# Dassein — Design Coherence Fix Plan

## Goal

Unify the visual language: **every shape, in every mode, renders as dots + triangulated wireframe edges only.** No filled surfaces, no model-native wireframes — just the 478-node point cloud connected by k-NN edges forming a triangular mesh. This gives the icosahedron, face, primitive shapes, and future GLB models the same coherent aesthetic.

---

## Problem Audit

### P1: Filled MeshPanels in Shape Renderer

**File:** `index.html`, lines 953-959

```javascript
const fillMat = new THREE.MeshBasicMaterial({
  color: 0x00d4ff, transparent: true, opacity: 0,
  side: THREE.DoubleSide, depthWrite: false
});
const fillMesh = new THREE.Mesh(geo.clone(), fillMat);
fillMesh.renderOrder = 2;
group.add(fillMesh);
```

This `fillMesh` is a solid filled surface that fades in at 10% opacity when switching to cube/cylinder/pyramid/torus. It breaks the wireframe-only aesthetic.

**Fix:** Remove `fillMat`, `fillMesh`, and all references to `shapeGroup.children[0].material.opacity` throughout `morphToTarget()`, `resetToLanding()`, and the render loop. The shape visual becomes: **k-NN edges (wireframe) + point cloud (already handled by shared `icoCloud`).**

### P2: Triangular Wireframe Edges Disappear During Face Mode

**File:** `index.html`, lines 770-771

```javascript
icoEdgeMat.opacity = 0.25 * (1 - t);  // → 0 at end of morph
icoEdgeGlowMat.opacity = 0.08 * (1 - t);  // → 0
```

And lines 1070-1073 in `morphToTarget()`:

```javascript
const tIeOp = isFace ? 0 : (isSphere ? 0.25 : 0.04);
const tIgOp = isFace ? 0 : (isSphere ? 0.08 : 0.02);
icoEdgeMat.opacity = ieOp + (tIeOp - ieOp) * t;
icoEdgeGlowMat.opacity = igOp + (tIgOp - igOp) * t;
```

The nearest-neighbor wireframe that creates the triangular look completely vanishes when the face is showing. The user wants triangular edges visible at ALL times.

**Fix:** Compute `nearestNeighborEdges(faceLMs, 6)` to generate triangle-style edges for the face landmark positions. Set these as the edge geometry indices during face mode. Keep edge opacity at 0.12–0.20 during face mode (lower than sphere's 0.25 so contour lines remain readable).

### P3: Face Lacks Triangulated Geometry — Only Contour Outlines

**File:** `index.html`, lines 548-556

```javascript
function contourEdges(contours) {
  const e = [];
  for (const c of Object.values(contours)) {
    for (let i = 0; i < c.length - 1; i++) e.push([c[i], c[i + 1]]);
    if (c.length > 2) e.push([c[c.length - 1], c[0]]);
  }
  return e;
}
```

The face wireframe is built from predefined contour paths (face oval, eye outlines, lip outlines, etc.) — essentially 2D drawing outlines. There are no 3D triangular edges connecting adjacent face landmarks.

**Fix:** After `faceLMs` is populated, compute `nearestNeighborEdges(faceLMs, 6)` to generate the triangulated face mask. Store these as `faceNNIndices` and set them on `icoEdgeGeo` when switching to face mode. The contour lines remain as an overlay (they serve a different purpose: facial feature guidelines), but the core structural wireframe becomes triangular.

### P4: Shape Wireframe Uses Model-Native Topology Instead of Triangular Edges

**File:** `index.html`, lines 961-964

```javascript
const wireGeo = new THREE.WireframeGeometry(geo);
const wireMat = new THREE.LineBasicMaterial({
  color: 0x00d4ff, transparent: true, opacity: 0,
  depthTest: false
});
const wireframe = new THREE.LineSegments(wireGeo, wireMat);
```

This creates a wireframe from the original mesh's own edge topology (e.g., a CubeGeometry wireframe is rectangular grid lines, not a triangular one). The user wants the same k-NN triangulated look as the sphere.

**Fix:** After `shapeTargets` is computed (line 947), run `nearestNeighborEdges(shapeTargets, 6)` to get triangle-style edges between the 478 sampled points. Set those as the edge indices on `icoEdgeGeo` during shape mode, exactly like the sphere. Remove `WireframeGeometry` and `shapeWire` entirely.

---

## Unified Design System

After all fixes, the visual rule becomes:

| Mode | Point cloud | Wireframe edges | Opacity | Contour lines |
|------|------------|-----------------|---------|--------------|
| Landing (sphere) | icoCloud (478 dots) | NN edges on icoPoints, k=6 | 0.25 / glow 0.08 | None |
| Face | icoCloud (478 dots) | NN edges on faceLMs, k=6 | 0.16 / glow 0.05 | Face contours 0.75 |
| Primitive shapes | icoCloud (478 dots) | NN edges on shapeTargets, k=6 | 0.20 / glow 0.06 | None |
| GLB model | icoCloud (478 dots) | NN edges on sampled points, k=6 | 0.20 / glow 0.06 | None |

---

## Implementation Steps

### Step 1: Compute Face NN Edges (insert after line 700, after `faceLMs` is built)

Add after `workingBuffer = faceLMs.map(p => ({ ...p }));`:

```javascript
      const faceNNEdges = nearestNeighborEdges(faceLMs, 6);
      const faceNNIndices = [];
      for (const [a, b] of faceNNEdges) faceNNIndices.push(a, b);
```

Store `faceNNIndices` on `window.__scene` for cross-mode access.

### Step 2: Rewrite `buildShapeGeometry()` — Remove Filled Panels, Use NN Edges

Replace lines 922-976 (`buildShapeGeometry` function) with a version that:
- Removes `fillMesh`, `fillMat`
- Removes `WireframeGeometry`, `shapeWire`
- Computes `nearestNeighborEdges(shapeTargets, 6)` after sampling
- Stores shape-specific edge indices in `shapeTargetEdgeIndices`
- Does NOT create or attach meshes to `icoGroup` — the shared `icoEdgeGeo` handles the wireframe

```javascript
    let shapeTargetEdgeIndices = null; // Edge indices for the current shape's NN wireframe

    async function buildShapeGeometry(name) {
      let geo;
      switch (name) {
        case 'cube':     geo = new THREE.BoxGeometry(1, 1, 1, 12, 12, 12); break;
        case 'cylinder': geo = new THREE.CylinderGeometry(0.5, 0.5, 1, 40, 1); break;
        case 'pyramid':  geo = new THREE.ConeGeometry(0.5, 1.0, 4, 1); break;
        case 'torus':    geo = new THREE.TorusGeometry(0.45, 0.18, 20, 60); break;
        default: return null;
      }
      const pos = geo.attributes.position;
      const vertCount = pos.count;

      // Sample shape surface at each Fibonacci direction → 478 morph targets
      const targets = new Array(NUM);
      for (let i = 0; i < NUM; i++) {
        let bestD = Infinity, bestJ = 0;
        const ip = icoPoints[i];
        for (let j = 0; j < vertCount; j++) {
          const dx = ip.x - pos.getX(j), dy = ip.y - pos.getY(j), dz = ip.z - pos.getZ(j);
          const d2 = dx * dx + dy * dy + dz * dz;
          if (d2 < bestD) { bestD = d2; bestJ = j; }
        }
        targets[i] = { x: pos.getX(bestJ), y: pos.getY(bestJ), z: pos.getZ(bestJ) };
      }
      shapeTargets = targets;

      // Compute triangular nearest-neighbor edges for this shape's point cloud
      const shapeEdges = nearestNeighborEdges(targets, 6);
      shapeTargetEdgeIndices = [];
      for (const [a, b] of shapeEdges) shapeTargetEdgeIndices.push(a, b);

      geo.dispose();
      return true;
    }
```

### Step 3: Update Edge Index Switching

The triangular wireframe is drawn by `icoEdges` and `icoEdgeGlow` (which share `icoEdgeGeo`). To switch the edge topology per mode, we update `icoEdgeGeo.setIndex()` (and `icoEdgeGlow.geometry.setIndex()`) when switching shapes.

Create a helper:

```javascript
    function setWireframeEdgeIndices(indices) {
      icoEdgeGeo.setIndex(indices);
      icoEdgeGeo.setDrawRange(0, indices.length);
      // Neighbors and indices
      icoEdgeGlow.geometry.setIndex(indices);
      icoEdgeGlow.geometry.setDrawRange(0, indices.length);
    }
```

Calling points:
- **Landing / sphere mode:** `setWireframeEdgeIndices(nnIndices)` (the original icosahedron edges)
- **Face mode:** `setWireframeEdgeIndices(faceNNIndices)` (triangulated face edges)
- **Primitive shapes:** `setWireframeEdgeIndices(shapeTargetEdgeIndices)` (sampled shape edges)
- **GLB mode:** `setWireframeEdgeIndices(glbEdgeIndices)` (sampled GLB edges)

### Step 4: Fix Opacity Logic in `morphToTarget()`

Remove all references to `fillMesh`/`shapeWire` materials. Replace with the new unified opacity scheme:

```javascript
// Target opacities (unified wireframe-only scheme)
const tEdgeOp = isFace ? 0.16 : (isSphere ? 0.25 : 0.20);
const tGlowOp = isFace ? 0.05 : (isSphere ? 0.08 : 0.06);
const tFcOp = isFace ? 0.75 : 0;
const tFgOp = isFace ? 0.18 : 0;
const tFmOp = isFace ? 0.55 : 0;
const tKnOp = isFace ? 0.25 : 0;
```

Remove all `smOp`, `swOp`, `tSmOp`, `tSwOp` variables and the shape group opacity updates.

### Step 5: Fix `triggerTransform()` Opacity (lines 770-771)

Change from fading edges to 0 to fading to face-mode edge opacity:

```javascript
// Instead of:
icoEdgeMat.opacity = 0.25 * (1 - t);
icoEdgeGlowMat.opacity = 0.08 * (1 - t);

// Update to crossfade between sphere and face edge topologies:
// First half: fade sphere edges out
if (t < 0.5) {
  icoEdgeMat.opacity = 0.25 * (1 - t * 2);
  icoEdgeGlowMat.opacity = 0.08 * (1 - t * 2);
} else {
  // Second half: switch indices to face NN edges, fade in
  icoEdgeMat.opacity = 0.16 * ((t - 0.5) * 2);
  icoEdgeGlowMat.opacity = 0.05 * ((t - 0.5) * 2);
}
```

Actually, a cleaner approach: at t=0.5, switch `icoEdgeGeo.setIndex()` from `nnIndices` to `faceNNIndices`, and crossfade the opacity. So at t<0.5 the sphere edges fade out, at t=0.5 the indices switch, at t>0.5 the face edges fade in.

### Step 6: Fix `resetToLanding()` Opacity and Edge Restoration

At lines 842-851, reverse the crossfade and restore `nnIndices` at the right time. Remove shape group opacity cleanup (since there's no more shape group).

### Step 7: Clean Up Shape Pills & State Management

- Remove `shapeGroup` and `shapeWire` variables from the module scope
- Remove shapeWire usage from `morphToTarget()`, `resetToLanding()`, render loop
- Update `window.__scene` to expose `faceNNIndices`
- Remove `buildShapeGeometry`'s original group creation code
- Update `resetToLanding()` to clean up `shapeTargets` and `shapeTargetEdgeIndices` instead of shapeGroup

### Step 8: Update GLB Morph Engine Plan to Match

The existing `PLAN.md` Part 3 Step 3 already uses `GLBMorphEngine.edgesToIndexArray(glbData.edges)` and calls `icoEdgeGeo.setIndex()`. This is already correct — the GLB sampled points use `nearestNeighborEdges()` internally, producing triangular edges. No changes needed to the GLB morph plan itself.

One addition to the GLB plan: when morphing from face mode to GLB, the edge indices need to transition from `faceNNIndices` to the GLB's sampled indices at the midpoint of the morph.

---

## Affected Code Map

| Change | File | Lines | Action |
|--------|------|-------|--------|
| Remove fillMesh/fillMat | index.html | 953-959 | Delete |
| Remove WireframeGeometry/shapeWire | index.html | 961-968 | Delete, replace with NN edges |
| Remove shapeGroup/shapeWire vars | index.html | 236-237 | Delete `let shapeGroup`, `let shapeWire` |
| Compute faceNNEdges | index.html | After 702 | Add |
| Create setWireframeEdgeIndices() | index.html | After 528 | Add helper |
| Update morphToTarget opacity | index.html | 1017-1101 | Rewrite opacity targets |
| Update triggerTransform opacity | index.html | 739-797 | Rewrite edge crossfade |
| Update resetToLanding opacity | index.html | 800-900 | Rewrite reverse crossfade |
| Remove shapeGroup from reset | index.html | 868-869, 888 | Clean up references |
| Expose faceNNIndices | index.html | 712-722 | Add to window.__scene |
| GLB plan edge transition | PLAN.md | Step 3 | Add midpoint edge switch note |

---

## Verification Checklist

- [ ] Landing state: 478 blue dots on a unit sphere, connected by 6-NN triangulated edges (0.25 opacity)
- [ ] Click → face: dots morph to face positions, edges transition to face NN triangulation (0.16 opacity), contour lines overlay at 0.75
- [ ] Shape pills ("cube" etc.): no filled surface, no rectilinear wireframe — only triangular k-NN edges (0.20 opacity) + dots
- [ ] All shape switches preserve triangular wireframe, never showing filled panels
- [ ] Escape resets correctly: edges restore to sphere NN indices, opacity returns to 0.25
- [ ] Scroll rotation works in all modes
- [ ] Face viseme animation still shows contour lines + triangular edges simultaneously
- [ ] No references to `fillMesh`, `fillMat`, `shapeWire`, `WireframeGeometry` remain in code
- [ ] `shapeGroup` variable is fully removed
- [ ] No console errors during morph transitions
