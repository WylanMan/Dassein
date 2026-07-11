# Dassein — Agent Notes

## What this is

A static single-page site that renders a 3D interactive Chinese tea tray model using Three.js. Deployed on Vercel.

## Structure

| File | Role |
|---|---|
| `index.html` | Entry point — no build step |
| `app.js` | Three.js scene setup, STL loader, orbit controls |
| `styles.css` | Dark theme, hero + model sections |
| `chinese-tea-tray.stl` | 3D model asset |
| `canvas/` | Empty directory (reserved) |

## Key conventions

- **No build tool** — serve files directly (e.g. `npx serve .` or VS Code Live Server)
- **Three.js via importmap** from CDN (`unpkg.com/three@0.164.1`), not bundled
- **Only npm dependency**: `@vercel/analytics` — run `npm install` before deploying
- STL model is loaded at runtime from `./chinese-tea-tray.stl`

## App logic summary

`app.js` creates a Three.js scene with:
- Perspective camera at `(0, 4.8, 5.8)` with 42° FOV
- OrbitControls (damped, distance 3.3–11, polar angle capped at ~86°)
- Three-point lighting (key, rim, fill)
- Auto-orients the STL so its flattest face sits down, then flips it upright
- Scales the model to fit within a 5.8-unit bounding box
