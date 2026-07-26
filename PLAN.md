# Dassein.io — Revised Build Plan (v2)

## What changed

The old plan was scroll-driven with 4 sections scrolling through 3D
transforms. Feedback:
- Homepage has too much Wylan/portfolio stuff — should be pure Dassein
- Scroll animations are wrong for the index — 3D should always animate
- Nav bar needs to go — the 3D shape itself IS the navigation
- Text is too low / requires scrolling — "Dassein" must be visible on load

## New architecture

| Page | Strategy |
|---|---|
| `index.html` | One viewport. 3D scene fills screen. Auto-animating geometry. Clickable sub-shapes navigate to wylan/blogs. Text overlay centered. No scroll, no nav bar. |
| `wylan.html` | Static content with lightweight 3D background (particles + small rotating form). Scroll-reveal animations on content sections. Keep index-list nav. |
| `blogs.html` | Same as wylan — lightweight 3D background, scroll-reveal on post cards. Index-list nav. |

---

## 2. The Index Page (index.html) — Complete Rewrite

### 2.1 Concept

The page IS the 3D clearing. No HTML sections. No scroll. One viewport.
- A dark particle field fills the background
- A central torus knot (phosphor green) rotates continuously — the Dassein mark
- Two smaller orbiting shapes circle the torus:
  - A wireframe icosahedron (signal blue) — the Wylan path
  - A curved ribbon/tube (violet) — the Forest Paths (blogs) path
  - An amber dot (small sphere) — the agent (future, disabled for now)
- "Dassein" in large serif type, centered, overlaid on the scene
- A subtle subtitle below: "a clearing"
- Hovering over a navigation shape: it glows, a small text label appears
- Clicking a nav shape: navigates to the corresponding page
- The torus knot itself: clicking it does nothing special, it's the anchor

### 2.2 HTML Structure

```html
<canvas id="scene"></canvas>

<div id="overlay">
  <h1>Dassein</h1>
  <p>a clearing</p>
</div>

<div id="tooltip"></div>   <!-- hidden, appears on hover over a nav shape -->
```

That's it. No `<nav>`, no `<main>`, no `<section>`.

### 2.3 CSS

```css
* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  background: #05080f;
  overflow: hidden;          /* NO SCROLL */
  font-family: "Playfair Display", serif;
  cursor: default;
}

#scene {
  position: fixed; inset: 0;
  width: 100vw; height: 100vh;
  display: block;
}

#overlay {
  position: fixed; inset: 0; z-index: 1;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  pointer-events: none;     /* clicks pass through to canvas */
}

#overlay h1 {
  color: #d7e1ee;
  font-family: "Playfair Display", serif;
  font-size: clamp(56px, 10vw, 120px);
  font-weight: 700;
  letter-spacing: -0.03em;
  opacity: 0.85;
}

#overlay p {
  color: #7286a0;
  font-family: "Caveat", cursive;
  font-size: 22px;
  margin-top: 12px;
  opacity: 0.6;
}

#tooltip {
  position: fixed; z-index: 2;
  pointer-events: none;
  color: #d7e1ee;
  font-family: "Caveat", cursive;
  font-size: 16px;
  opacity: 0;
  transition: opacity 0.25s;
  transform: translate(-50%, -50%);
  text-shadow: 0 0 12px rgba(61, 255, 184, 0.4);
}

#tooltip.visible { opacity: 1; }
```

The key: `pointer-events: none` on the overlay so mouse events fall through to
the canvas for raycasting. Text is purely visual.

### 2.4 3D Scene Setup

Same core as before — Three.js scene, camera, renderer, fog, lights.

**Changes from old plan:**
- Camera does NOT move with scroll. Camera has a subtle idle breathing animation
  (sine wave on position.y and position.z — very small amplitude, very slow).
- No ScrollTrigger, no GSAP timeline on the 3D elements.
- 3D shapes constantly rotate using `requestAnimationFrame` auto-increment.

```js
// Idle breathing
const time = performance.now() * 0.001
camera.position.y = Math.sin(time * 0.3) * 0.15
camera.position.z = 8 + Math.sin(time * 0.4) * 0.3
camera.lookAt(0, 0, 0)
```

### 2.5 3D Geometry

| Element | Shape | Color | Role |
|---|---|---|---|
| Central mark | TorusKnot (radius 0.7) | Phosphor `#3dffb8` | Brand anchor, auto-rotates Y |
| Wylan link | Icosahedron (radius 0.35, wireframe) | Signal `#58c4ff` | Orbits torus, clickable |
| Blogs link | Tube (cubic bezier, 0.03 radius) | Violet `#b79cff` | Orbits torus, clickable |
| Particles | 2000 Points in sphere | Dim `#7286a0` | Ambient field, slow drift |

**Orbit mechanics:**
- The icosahedron and ribbon tube are NOT children of the torus knot.
  They are in a parent `THREE.Group` that rotates on Y at a different rate.
  This gives them an orbital path around the torus.

```js
const orbitGroup = new THREE.Group()
scene.add(orbitGroup)

// Icosahedron positioned offset from center
icosahedron.position.set(2.2, 0.3, -1)
orbitGroup.add(icosahedron)

// Ribbon positioned on opposite side
ribbonGroup.position.set(-2.0, -0.2, 1.2)
orbitGroup.add(ribbonGroup)

// Auto-rotate the orbit group
// In RAF loop: orbitGroup.rotation.y += 0.002
```

**Torus knot auto-rotation:**
```js
// In RAF loop:
knot.rotation.x += 0.003
knot.rotation.y += 0.005
knot.rotation.z += 0.001
```

### 2.6 Raycasting — Clickable 3D Navigation

This is the key new feature. We use `THREE.Raycaster` to detect which 3D
object the mouse is over.

```js
const raycaster = new THREE.Raycaster()
const mouse = new THREE.Vector2()

const clickables = [
  { mesh: icosahedron, url: '/wylan.html', label: 'wylan' },
  { mesh: ribbonMesh,  url: '/blogs.html', label: 'forest paths' },
]

// On mousemove: cast ray, check intersections with clickables
window.addEventListener('mousemove', (e) => {
  mouse.x = (e.clientX / window.innerWidth) * 2 - 1
  mouse.y = -(e.clientY / window.innerHeight) * 2 + 1

  raycaster.setFromCamera(mouse, camera)
  const intersects = raycaster.intersectObjects(clickables.map(c => c.mesh))

  if (intersects.length > 0) {
    const obj = intersects[0].object
    const target = clickables.find(c => c.mesh === obj)
    document.body.style.cursor = 'pointer'
    // Show tooltip near cursor
    tooltip.textContent = target.label
    tooltip.classList.add('visible')
    tooltip.style.left = e.clientX + 'px'
    tooltip.style.top = (e.clientY - 30) + 'px'
    // Highlight: scale up + increase emissive
    hoveredMesh = obj
  } else {
    document.body.style.cursor = 'default'
    tooltip.classList.remove('visible')
    hoveredMesh = null
  }
})

// On click: navigate
window.addEventListener('click', () => {
  if (hoveredMesh) {
    const target = clickables.find(c => c.mesh === hoveredMesh)
    if (target) window.location.href = target.url
  }
})
```

**Hover effect in RAF loop:**
```js
// Smoothly interpolate hover scale
if (hoveredMesh) {
  hoveredMesh.scale.lerp(new THREE.Vector3(1.2, 1.2, 1.2), 0.1)
  if (hoveredMesh.material.emissiveIntensity !== undefined) {
    hoveredMesh.material.emissiveIntensity += (0.5 - hoveredMesh.material.emissiveIntensity) * 0.1
  }
} else {
  clickables.forEach(c => {
    c.mesh.scale.lerp(new THREE.Vector3(1, 1, 1), 0.1)
  })
}
```

### 2.7 Fonts

- "Dassein" — Playfair Display (serif, elegant, weight 700)
- "a clearing" and tooltips — Caveat (cursive, human, handwritten feel)
- These are already loaded from Google Fonts in the current index.html

---

## 3. Wylan Page (wylan.html) — Animation Pass

### 3.1 Keep existing content, add:

**Lightweight 3D background** (Three.js canvas, but simpler):
- 800 particles (not 2000 — lighter)
- A small wireframe icosahedron rotating slowly in one corner
- No fog, no complex lighting — just ambient
- Fixed position canvas behind content

```js
// Minimal scene for wylan.html
const scene = new THREE.Scene()
scene.background = new THREE.Color(0x05080f)
const camera = new THREE.PerspectiveCamera(45, w/h, 0.1, 100)
camera.position.set(0, 0, 10)
// Only particles + one small icosahedron
```

**Scroll-reveal animations on content sections:**
- Each `<section>` fades in as you scroll to it
- Use GSAP ScrollTrigger with Lenis smooth scroll
- Sections slide up 30px + fade from opacity 0 → 1
- Stagger child elements within sections

```js
document.querySelectorAll('section').forEach((section) => {
  gsap.fromTo(section, { opacity: 0, y: 40 }, {
    opacity: 1, y: 0,
    scrollTrigger: {
      trigger: section,
      start: 'top 85%',
      end: 'top 40%',
      scrub: 0.5,
      toggleActions: 'play none none none'
    }
  })
})
```

**Index-list nav** remains at top, fixed position, dark transparent background.

### 3.2 Wylan page CSS additions

```css
body {
  background: #05080f;
  color: #d7e1ee;
  font-family: "Space Grotesk", system-ui, sans-serif;
}

#scene {
  position: fixed; inset: 0; z-index: 0;
  width: 100vw; height: 100vh;
  opacity: 0.5;
}

main {
  position: relative; z-index: 1;
  max-width: 720px;
  margin: 0 auto;
  padding: 120px 10vw 80px;
}

nav {
  position: fixed; top: 0; left: 0; right: 0; z-index: 10;
  padding: 20px 10vw;
  background: rgba(5, 8, 15, 0.85);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}

nav ul {
  list-style: none; display: flex; gap: 28px;
  font-family: "Caveat", cursive; font-size: 18px;
}

nav a { color: #7286a0; text-decoration: none; }
nav a.active { color: #3dffb8; }

section { margin: 60px 0; }
h1 { font-family: "Playfair Display", serif; font-size: clamp(40px, 6vw, 64px); font-weight: 700; }
h2 { font-family: "Playfair Display", serif; font-size: 28px; margin-top: 48px; font-weight: 700; }
h3 { font-family: "Space Grotesk", sans-serif; font-size: 18px; margin-top: 32px; color: #d7e1ee; }
p { color: #7286a0; line-height: 1.8; font-size: 16px; margin-top: 12px; }
a { color: #3dffb8; text-decoration: none; }
ul, ol { color: #7286a0; line-height: 1.8; margin-top: 12px; padding-left: 20px; }
li { margin-bottom: 8px; }
strong { color: #d7e1ee; }
```

### 3.3 Wylan page JS additions

```html
<script src="https://cdn.jsdelivr.net/npm/three@0.152.0/build/three.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.12.5/dist/gsap.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.12.5/dist/ScrollTrigger.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/@studio-freight/lenis@1.0.42/dist/lenis.min.js"></script>
```

Logic:
1. Init Three.js minimal scene (particles + icosahedron)
2. Init Lenis smooth scroll
3. Init GSAP ScrollTrigger section reveals
4. RAF loop renders scene

---

## 4. Blogs Page (blogs.html) — Animation Pass

### 4.1 Concepts

Same approach as wylan.html but with blog-specific touches:

**Lightweight 3D background** — same as wylan page (particles + small form).
Maybe the form is a tiny torus knot instead of icosahedron.

**Scroll-reveal animations:**
- Post list items stagger-fade in
- Article sections fade in as you scroll to them
- Each article has a subtle left-border highlight (phosphor green) that appears on scroll

**Post list card hover effect:**
- On hover, a gentle glow + subtle scale
- Links to article anchors

### 4.2 Blog page CSS

Same base as wylan page, plus:

```css
.post-list { list-style: none; padding: 0; }
.post-list li {
  margin-bottom: 40px;
  padding-bottom: 24px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.1);
  transition: transform 0.3s ease;
  cursor: pointer;
}
.post-list li:hover { transform: translateX(8px); }
.post-list li:hover a { color: #3dffb8; }

.post-list a {
  font-family: "Playfair Display", serif;
  font-size: 24px;
  font-weight: 700;
  color: #d7e1ee;
  text-decoration: none;
  transition: color 0.3s;
}

.post-list span {
  font-family: "Caveat", cursive;
  font-size: 15px;
  color: #7286a0;
  margin-left: 12px;
}

.post-list p {
  font-size: 15px;
  margin-top: 8px;
}

article {
  margin: 80px 0;
  padding-top: 40px;
  border-top: 1px solid rgba(148, 163, 184, 0.1);
  opacity: 0;
  transform: translateY(20px);
  transition: opacity 0.6s ease, transform 0.6s ease;
}

article.visible {
  opacity: 1;
  transform: translateY(0);
}
```

---

## 5. Build Order

### Phase A: Index page rewrite
1. Strip index.html to bare bones — canvas, overlay, tooltip only
2. Three.js scene: renderer, camera, fog, lights (keep from existing)
3. Particle field — 2000 particles (keep from existing, no scroll transforms)
4. Torus knot — central, auto-rotating (keep geometry, remove GSAP timelines)
5. Orbit group — icosahedron + ribbon, on a rotating parent group
6. Idle camera breathing — subtle sine-wave motion
7. Raycasting — mousemove hover detection + click navigation
8. Tooltip UI — show label near cursor on hover
9. Hover effects — smooth scale/interpolation on targeted meshes
10. Text overlay — "Dassein" + "a clearing", pointer-events: none
11. Font loading — Playfair Display + Caveat (already in current index.html)

### Phase B: Wylan page animations
1. Add minimal Three.js scene behind content
2. Add Lenis smooth scroll
3. Add GSAP ScrollTrigger section reveals
4. Style the page (dark theme, fonts)
5. Nav active state based on current page

### Phase C: Blogs page animations
1. Same as Phase B structure
2. Post list scroll-reveal with stagger
3. Article visibility transitions
4. Hover effects on post cards
5. Nav active state

---

## 6. Key Differences from Old Plan

| Aspect | Old Plan | New Plan |
|---|---|---|
| Scroll | 600vh scroll driving 3D | Index: no scroll at all. Sub-pages: smooth scroll for content. |
| Nav | Fixed nav bar on top | Index: no nav bar — 3D shapes are the nav. Sub-pages: index-list nav bar. |
| 3D animation | Scroll-driven via GSAP | Always-animating via RAF loop auto-increment |
| Content | Sections below the 3D scene | Index: single overlay text. Wylan/blogs: traditional scroll pages with 3D bg. |
| Wylan content on index | Teaser section for Wylan | Removed entirely from index — lives only on wylan.html |
| Clickable 3D | None | Raycasting on shapes navigates between pages |

---

## 7. Font Strategy

| Font | Usage |
|---|---|
| Playfair Display (serif) | Headlines — "Dassein", section titles, post titles |
| Caveat (cursive) | Subtitles, tooltips, dates, accent text |
| Space Grotesk (sans) | Body text, nav links, metadata |

All loaded from Google Fonts in `<head>`.

---

## 8. Responsive Behavior

**Index page:** Canvas fills viewport. Text scales with `clamp()`. Orbit shapes
scale down slightly on mobile. Raycasting still works with touch events
(`touchstart` for mobile click).

**Wylan/blogs:** Single column, max-width 720px, centered. Nav stays fixed top.
Particles reduced to 400 on mobile. 3D background opacity lowered.

---

## 9. What the user sees

**Index page load:**
- Dark space with drifting particles
- A glowing green torus knot rotating slowly at center
- "Dassein" in large elegant serif, centered
- "a clearing" in cursive below
- A blue wireframe icosahedron orbiting the torus
- A violet ribbon path orbiting on the other side
- No visible UI except the text and the shapes
- Hover over the icosahedron: it brightens, "wylan" appears near cursor
- Hover over the ribbon: it brightens, "forest paths" appears near cursor
- Click either shape: navigate to that page
- The torus knot is just the anchor — clicking it does nothing

**Wylan page:**
- Subtle particle background with small rotating icosahedron
- Smooth-scrolling content with fade-in reveals
- Clean index-list nav at top

**Blogs page:**
- Same subtle 3D background with small torus knot
- Post list with hover effects and scroll reveals
- Articles fade in as they enter viewport
