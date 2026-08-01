"""Spec synthesis for /api/summon (B1 / Tier-3 grammar v2). Shared by the local
dev server (server.py) and the Vercel serverless function (api/index.py).

Contract: the endpoint returns a JSON *spec* — never geometry. The client owns
building. Flow: cache lookup (canonical id + seed) -> DeepSeek call (one
fix-prompt retry on validation failure) -> validate -> cache. Second failure
degrades to a 422 with an abstractify directive: the client shows a seeded
abstract form instead of crashing.

Grammar v2 (Tier 3): specs carry `schema: 2` and a `root` SDF tree —
primitives, profile-prims, combinators (hard booleans default, smooth accent
k <= 0.15), domain transforms, surface detail. Single-pass generation: one call
+ one validator retry, then 422 abstractify. No critique/refine pass.

Seeds are pinned: default seed = hash(canonical id), and re-rolls move the seed
by +1 — deterministic jitter variants, all cacheable. The v2 cache is rekeyed
to `v2:<root-hash>:<seed>`; the slug->id index and v1 cache keys remain valid
for the v1 path.
"""

import hashlib
import json
import os
import re
from pathlib import Path

import httpx

BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
CACHE_DIR = Path(os.environ.get("SUMMON_CACHE_DIR", ".cache/specs"))

# ─── Grammar v2 catalog (mirrors sdf-core.mjs) ─────────────────────────────

V2_OPS = {
    "prim": {
        "sphere", "box", "rbox", "cylinder", "cone", "pyramid", "torus",
        "capsule", "ellipsoid", "superellipsoid", "gem", "rock", "crystal",
        "pebble", "blob", "revolve", "extrude", "star", "gear", "polygon",
        "cross", "rect", "rect_r",
    },
    "combinator": {
        "union", "intersect", "subtract",
        "smooth_union", "smooth_intersect", "smooth_subtract",
    },
    "binary": {"blend"},
    "unary": {
        "mirror", "polar_repeat", "repeat", "translate", "rotate", "scale",
        "twist", "bend", "taper", "squash", "bulge", "spherize",
        "displace", "facet", "ridged", "worley", "round",
    },
}
V2_ALL_OPS = V2_OPS["prim"] | V2_OPS["combinator"] | V2_OPS["binary"] | V2_OPS["unary"]

MAX_NODES = 32
MAX_DEPTH = 5
ALLOWED_ROT = ("up", "flat", "side")
ALLOWED_AXIS = ("x", "y", "z")


def _num(v, lo, hi):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and lo <= v <= hi


def _int_range(v, lo, hi):
    return isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi


def _vec(v, n, lo, hi):
    return (isinstance(v, list) and len(v) == n and
            all(_num(x, lo, hi) for x in v))


def _profile(prof, where, monotonic_y=False):
    """Common profile checks: list of [a, b] pairs, b >= 0, sane length."""
    errs = []
    if not (isinstance(prof, list) and 3 <= len(prof) <= 12 and
            all(isinstance(p, list) and len(p) == 2 and
                all(_num(x, -6, 6) for x in p) for p in prof)):
        errs.append(f"{where}: profile must be 3..12 [coord, r] pairs of numbers")
        return errs
    for p in prof:
        if p[1] < 0:
            errs.append(f"{where}: profile has a negative radius {p}")
    if monotonic_y:
        for a, b in zip(prof, prof[1:]):
            if b[0] <= a[0]:
                errs.append(f"{where}: profile height must be strictly increasing")
    return errs


def _depth_of(node):
    if not isinstance(node, dict) or not isinstance(node.get("op"), str):
        return 1
    kids = node.get("children")
    if isinstance(kids, list):
        return 1 + max((_depth_of(c) for c in kids), default=0)
    if isinstance(node.get("a"), dict):
        return 1 + max(_depth_of(node["a"]), _depth_of(node["b"]) if isinstance(node.get("b"), dict) else 0)
    if isinstance(node.get("child"), dict):
        return 1 + _depth_of(node["child"])
    return 1


class _V2Counter:
    def __init__(self):
        self.n = 0

    def tick(self):
        self.n += 1
        return self.n > MAX_NODES


def validate_v2_root(root) -> list:
    """Recursive per-op validation of the root SDF tree. Returns error strings
    (empty = valid). Depth <= MAX_DEPTH, nodes <= MAX_NODES."""
    errs = []
    ctr = _V2Counter()

    def check(node, depth):
        if ctr.tick():
            errs.append(f"SDF tree exceeds {MAX_NODES} nodes")
            return
        if depth > MAX_DEPTH:
            errs.append(f"SDF tree exceeds depth {MAX_DEPTH}")
            return
        if not isinstance(node, dict) or not isinstance(node.get("op"), str):
            errs.append("SDF node must be an object with an op")
            return
        op = node["op"]
        if op not in V2_ALL_OPS:
            errs.append(f"unknown SDF op '{op}'")
            return

        def child():
            c = node.get("child")
            if not isinstance(c, dict):
                errs.append(f"{op}: child is required")
                return
            check(c, depth + 1)

        # Primitive params.
        if op == "sphere":
            if not _num(node.get("r", 0.5), 0.05, 3):
                errs.append("sphere: r in 0.05..3")
        elif op == "box":
            if not _vec(node.get("size"), 3, 0.05, 4):
                errs.append("box: size = [x,y,z] in 0.05..4")
        elif op == "rbox":
            if not _vec(node.get("size"), 3, 0.05, 4):
                errs.append("rbox: size = [x,y,z] in 0.05..4")
            if not _num(node.get("r", 0.05), 0.01, 0.5):
                errs.append("rbox: r in 0.01..0.5")
        elif op in ("cylinder", "cone"):
            if not _num(node.get("r", 0.4), 0.05, 3):
                errs.append(f"{op}: r in 0.05..3")
            if not _num(node.get("h", 1.2), 0.1, 6):
                errs.append(f"{op}: h in 0.1..6")
        elif op == "pyramid":
            if not _int_range(node.get("n", 4), 3, 12):
                errs.append("pyramid: n integer in 3..12")
            if not _num(node.get("r", 0.7), 0.05, 3):
                errs.append("pyramid: r in 0.05..3")
            if not _num(node.get("h", 1.2), 0.1, 6):
                errs.append("pyramid: h in 0.1..6")
        elif op == "torus":
            if not _num(node.get("R", 0.5), 0.1, 3):
                errs.append("torus: R in 0.1..3")
            if not _num(node.get("r", 0.2), 0.02, 1):
                errs.append("torus: r in 0.02..1")
        elif op == "capsule":
            if not _num(node.get("r", 0.2), 0.02, 1):
                errs.append("capsule: r in 0.02..1")
            if not _num(node.get("h", 1.2), 0.1, 6):
                errs.append("capsule: h in 0.1..6")
        elif op in ("ellipsoid", "superellipsoid"):
            if not _vec(node.get("size"), 3, 0.05, 4):
                errs.append(f"{op}: size = [x,y,z] in 0.05..4")
            if op == "superellipsoid" and not _num(node.get("n", 4), 1, 10):
                errs.append("superellipsoid: n in 1..10")
        elif op in ("gem", "rock", "pebble", "blob"):
            if not _num(node.get("r", 1), 0.1, 3):
                errs.append(f"{op}: r in 0.1..3")
        elif op == "crystal":
            if not _num(node.get("r", 0.6), 0.05, 3):
                errs.append("crystal: r in 0.05..3")
            if not _num(node.get("h", 1.8), 0.1, 6):
                errs.append("crystal: h in 0.1..6")
        elif op == "revolve":
            errs.extend(_profile(node.get("profile"), "revolve", monotonic_y=True))
        elif op == "extrude":
            errs.extend(_profile(node.get("profile"), "extrude"))
            if not _num(node.get("depth", 0.18), 0.02, 2):
                errs.append("extrude: depth in 0.02..2")
        elif op == "star":
            if not _int_range(node.get("points", 5), 3, 16):
                errs.append("star: points integer in 3..16")
            if not _num(node.get("outer", 0.7), 0.05, 3):
                errs.append("star: outer in 0.05..3")
            if not _num(node.get("inner", 0.35), 0.02, 3):
                errs.append("star: inner in 0.02..3")
            if not _num(node.get("depth", 0.18), 0.02, 2):
                errs.append("star: depth in 0.02..2")
        elif op == "gear":
            if not _int_range(node.get("teeth", 8), 3, 24):
                errs.append("gear: teeth integer in 3..24")
            if not _num(node.get("r", 0.6), 0.1, 3):
                errs.append("gear: r in 0.1..3")
            if not _num(node.get("depth", 0.18), 0.02, 2):
                errs.append("gear: depth in 0.02..2")
        elif op == "polygon":
            if not _int_range(node.get("n", 6), 3, 16):
                errs.append("polygon: n integer in 3..16")
            if not _num(node.get("r", 0.6), 0.05, 3):
                errs.append("polygon: r in 0.05..3")
            if not _num(node.get("depth", 0.18), 0.02, 2):
                errs.append("polygon: depth in 0.02..2")
        elif op == "cross":
            if not _vec(node.get("size"), 2, 0.1, 4):
                errs.append("cross: size = [x,y] in 0.1..4")
            if not _num(node.get("depth", 0.18), 0.02, 2):
                errs.append("cross: depth in 0.02..2")
        elif op in ("rect", "rect_r"):
            if not _vec(node.get("size"), 2, 0.1, 4):
                errs.append(f"{op}: size = [x,y] in 0.1..4")
            if op == "rect_r" and not _num(node.get("r", 0.05), 0, 0.5):
                errs.append("rect_r: r in 0..0.5")
            if not _num(node.get("depth", 0.18), 0.02, 2):
                errs.append(f"{op}: depth in 0.02..2")

        # Combinators.
        elif op in ("union", "intersect", "subtract", "smooth_union", "smooth_intersect", "smooth_subtract"):
            kids = node.get("children")
            if not (isinstance(kids, list) and len(kids) >= 2 and
                    all(isinstance(c, dict) for c in kids)):
                errs.append(f"{op}: children must be >= 2 objects")
            else:
                for c in kids:
                    check(c, depth + 1)
            if op.startswith("smooth") and not _num(node.get("k", 0.05), 0, 0.15):
                errs.append(f"{op}: k in 0..0.15 (smooth is an accent only)")

        elif op == "blend":
            for k in ("a", "b"):
                if not isinstance(node.get(k), dict):
                    errs.append("blend: a and b are required")
                else:
                    check(node[k], depth + 1)
            if not _num(node.get("t", 0.5), 0, 1):
                errs.append("blend: t in 0..1")

        # Unary ops.
        elif op == "mirror":
            if node.get("plane", "x") not in ("x", "y", "z"):
                errs.append("mirror: plane in x|y|z")
            child()
        elif op == "polar_repeat":
            if not _int_range(node.get("n", 6), 2, 24):
                errs.append("polar_repeat: n integer in 2..24")
            child()
        elif op == "repeat":
            if node.get("axis", "y") not in ALLOWED_AXIS:
                errs.append("repeat: axis in x|y|z")
            if not _int_range(node.get("n", 4), 2, 24):
                errs.append("repeat: n integer in 2..24")
            if not _num(node.get("spacing", 0.4), 0.1, 1.2):
                errs.append("repeat: spacing in 0.1..1.2")
            child()
        elif op == "translate":
            if not _vec(node.get("t"), 3, -3, 3):
                errs.append("translate: t = [x,y,z] in -3..3")
            child()
        elif op == "rotate":
            if node.get("preset", "up") not in ALLOWED_ROT:
                errs.append(f"rotate: preset in {'|'.join(ALLOWED_ROT)}")
            if not _num(node.get("deg", 0), -360, 360):
                errs.append("rotate: deg in -360..360")
            child()
        elif op == "scale":
            s = node.get("s", 1)
            if not (_num(s, 0.1, 6) or _vec(s, 3, 0.1, 6)):
                errs.append("scale: s in 0.1..6 or [x,y,z]")
            child()
        elif op == "twist":
            if not _num(node.get("deg", 0), -360, 360):
                errs.append("twist: deg in -360..360")
            child()
        elif op == "bend":
            if not _num(node.get("r", 0.1), 0, 0.5):
                errs.append("bend: r in 0..0.5")
            child()
        elif op == "taper":
            if not _num(node.get("k", 0), 0, 0.98):
                errs.append("taper: k in 0..0.98")
            child()
        elif op == "squash":
            if not _num(node.get("k", 1), 0.1, 4):
                errs.append("squash: k in 0.1..4")
            child()
        elif op == "bulge":
            if not _num(node.get("k", 0.2), 0, 0.5):
                errs.append("bulge: k in 0..0.5")
            child()
        elif op == "spherize":
            if not _num(node.get("k", 0), 0, 1):
                errs.append("spherize: k in 0..1")
            child()
        elif op == "displace":
            if not _num(node.get("amp", 0.1), 0, 0.3):
                errs.append("displace: amp in 0..0.3")
            if not _num(node.get("freq", 2), 0.1, 8):
                errs.append("displace: freq in 0.1..8")
            child()
        elif op == "facet":
            if not _int_range(node.get("levels", 4), 2, 12):
                errs.append("facet: levels integer in 2..12")
            if not _num(node.get("amp", 0.12), 0, 0.3):
                errs.append("facet: amp in 0..0.3")
            child()
        elif op == "ridged":
            if not _num(node.get("amp", 0.1), 0, 0.3):
                errs.append("ridged: amp in 0..0.3")
            if not _num(node.get("freq", 2), 0.1, 8):
                errs.append("ridged: freq in 0.1..8")
            child()
        elif op == "worley":
            if not _num(node.get("amp", 0.15), 0, 0.4):
                errs.append("worley: amp in 0..0.4")
            if not _num(node.get("freq", 2), 0.1, 8):
                errs.append("worley: freq in 0.1..8")
            child()
        elif op == "round":
            if not _num(node.get("r", 0.1), 0, 0.3):
                errs.append("round: r in 0..0.3")
            child()

    check(root, 0)
    return errs


def _root_hash(root) -> str:
    return hashlib.sha256(json.dumps(root, sort_keys=True).encode()).hexdigest()[:12]


# Hand-authored v2 few-shot examples (Phase 2 placeholder; Phase 3 replaces the
# example bank with the regenerated curated_specs.json). Trees stay small
# (4-8 nodes) to protect DeepSeek's nested-JSON reliability.
V2_EXAMPLES = {
    "hourglass": {
        "id": "hourglass", "schema": 2, "size": "medium",
        "root": {"op": "revolve", "profile": [[-1, 0.05], [-0.7, 0.55], [-0.4, 0.12], [0, 0.07], [0.4, 0.12], [0.7, 0.55], [1, 0.05]]},
    },
    "crown": {
        "id": "crown", "schema": 2, "size": "medium",
        "root": {"op": "union", "children": [
            {"op": "torus", "R": 0.7, "r": 0.22},
            {"op": "polar_repeat", "n": 6, "child": {"op": "translate", "t": [0.7, -0.05, 0], "child": {"op": "cone", "r": 0.18, "h": 0.7}}},
        ]},
    },
    "throne": {
        "id": "throne", "schema": 2, "size": "medium",
        "root": {"op": "union", "children": [
            {"op": "box", "size": [1.3, 0.16, 1.3]},
            {"op": "translate", "t": [0, 0.52, -0.28], "child": {"op": "box", "size": [1.3, 0.85, 0.22]}},
            {"op": "translate", "t": [-0.45, 0.3, 0], "child": {"op": "box", "size": [0.14, 0.85, 0.14]}},
            {"op": "translate", "t": [0.45, 0.3, 0], "child": {"op": "box", "size": [0.14, 0.85, 0.14]}},
            {"op": "translate", "t": [0, 1.05, -0.28], "child": {"op": "pyramid", "n": 4, "r": 0.3, "h": 0.5}},
        ]},
    },
    "gate": {
        "id": "gate", "schema": 2, "size": "medium",
        "root": {"op": "union", "children": [
            {"op": "translate", "t": [-0.5, 0, 0], "child": {"op": "box", "size": [0.18, 1.6, 0.18]}},
            {"op": "translate", "t": [0.5, 0, 0], "child": {"op": "box", "size": [0.18, 1.6, 0.18]}},
            {"op": "translate", "t": [0, 0.75, 0], "child": {"op": "box", "size": [1.3, 0.2, 0.18]}},
            {"op": "translate", "t": [0, 0.95, 0], "child": {"op": "pyramid", "n": 4, "r": 0.26, "h": 0.3}},
        ]},
    },
    "lantern": {
        "id": "lantern", "schema": 2, "size": "medium",
        "root": {"op": "union", "children": [
            {"op": "translate", "t": [0, -0.32, 0], "child": {"op": "sphere", "r": 0.5}},
            {"op": "translate", "t": [0, 0.28, 0], "child": {"op": "cone", "r": 0.36, "h": 0.55}},
        ]},
    },
    "obelisk": {
        "id": "obelisk", "schema": 2, "size": "medium",
        "root": {"op": "union", "children": [
            {"op": "translate", "t": [0, -0.85, 0], "child": {"op": "box", "size": [1.5, 0.3, 1.5]}},
            {"op": "translate", "t": [0, 0.15, 0], "child": {"op": "box", "size": [0.42, 1.5, 0.42]}},
            {"op": "translate", "t": [0, 0.95, 0], "child": {"op": "pyramid", "n": 4, "r": 0.6, "h": 0.9}},
        ]},
    },
}

_curated = None


def load_curated():
    """Load the curated spec library (the few-shot example bank)."""
    global _curated
    if _curated is None:
        here = Path(__file__).resolve().parent
        path = here.parent / "data" / "curated_specs.json"
        if path.is_file():
            _curated = json.loads(path.read_text())
        else:
            _curated = {}
    return _curated


def build_prompt(examples=None) -> str:
    """Grammar-v2 prompt around the angular identity. The curated library is
    the few-shot bank; Phase 2 uses the hand-authored V2_EXAMPLES placeholder
    until Phase 3 regenerates curated_specs.json. Small example trees keep
    DeepSeek's nested-JSON output reliable."""
    if examples is None:
        examples = V2_EXAMPLES
    bank = json.dumps(examples, indent=None, separators=(",", ":"))
    return (
        "You are the spec engine for Dassein, a wireframe 3D avatar site. The user asks for a "
        "concept and you reply with exactly one JSON object describing how to build it as a "
        "478-point wireframe net. You NEVER render anything and never describe in words — "
        "you only emit the spec JSON.\n\n"
        "## Spec shape\n"
        "{\n"
        '  "id": "canonical_lowercase_id",   // stable cache key, e.g. "hourglass_wide"\n'
        '  "schema": 2,                       // always 2 (the SDF grammar)\n'
        '  "size": "medium",                  // "small" | "medium" | "large"\n'
        '  "root": { "op": "union", ... }     // the SDF tree, described below\n'
        "}\n\n"
        "## SDF tree grammar\n"
        "Every node is {\"op\": \"...\", params..., and children where listed}. All numbers are "
        "world units.\n"
        "- Primitives: sphere {r}; box {size:[x,y,z]}; rbox {size:[x,y,z], r}; "
        "cylinder {r, h}; cone {r, h}; pyramid {n, r, h}; torus {R, r}; capsule {r, h}; "
        "ellipsoid {size:[x,y,z]}; superellipsoid {size:[x,y,z], n}; gem {r}; rock {r}; "
        "crystal {r, h}; pebble {r}; blob {r}\n"
        "- Profile-prims (2D silhouette): revolve {profile:[[y,r],...]} — y strictly increasing, "
        "r >= 0; extrude {profile:[[x,y],...], depth}; star {points, outer, inner, depth}; "
        "gear {teeth, r, depth}; polygon {n, r, depth}; cross {size:[x,y], depth}; "
        "rect {size:[x,y], depth}; rect_r {size:[x,y], r, depth}\n"
        "- Combinators: union/intersect/subtract {children:[node,...]} — hard joins, the default; "
        "smooth_union/smooth_intersect/smooth_subtract {children, k} with k <= 0.15 (smooth is an "
        "accent only); blend {a, b, t} with t in 0..1\n"
        "- Unary (each wraps one child node): mirror {plane: x|y|z, child}; "
        "polar_repeat {n, child}; repeat {axis: x|y|z, n, spacing, child}; "
        "translate {t:[x,y,z], child}; rotate {preset: up|flat|side, deg, child}; "
        "scale {s (number or [x,y,z]), child}; twist {deg, child}; bend {r, child}; "
        "taper {k, child}; squash {k, child}; bulge {k, child}; spherize {k, child}; "
        "displace {amp, freq, child}; facet {levels, amp, child}; ridged {amp, freq, child}; "
        "worley {amp, freq, child}; round {r, child}\n\n"
        "## The house style — angular (hard constraint)\n"
        "Crisp, structural, angular silhouettes. Hard booleans (union/intersect/subtract) are the "
        "default idiom; faceted prims (box, pyramid, crystal, gem) are the house look. Smooth "
        "forms and smooth_* accents are the exception, never the base.\n"
        "Idiom cookbook:\n"
        "- fused parts that read as one solid -> hard union of primitives\n"
        "- spikes, teeth, columns -> repeat / polar_repeat around a band\n"
        "- left-right symmetry -> mirror\n"
        "- vessels, vases, urns -> revolve (smooth profile)\n"
        "- slabs, plates, outlined shapes -> extrude (2D silhouette)\n"
        "- rings and bands -> torus; hollow/dug-out forms -> subtract\n\n"
        "Negative guidance (do NOT): no thin, lacy, or fragile forms; no crowds of small floating "
        "pieces; no blobby mush. Prefer hard joins and flat facets. Keep ONE dominant gesture; "
        "everything else is subordinate. If a concept is fragile (\"spiderweb\", \"doily\"), summon "
        "its essence as a solid angular form (web -> a flat star; bridge -> a stone arch).\n\n"
        "## Limits\n"
        f"- At most {MAX_NODES} nodes and depth {MAX_DEPTH}. Aim for small trees (4-8 nodes).\n"
        "- Profiles are 3..12 [coord, r] pairs; radii/sizes in world units ~0.05..3.\n"
        "- rotate uses the orientation vocabulary (up|flat|side) plus optional deg in degrees — "
        "never raw Euler angles.\n\n"
        "## Worked examples (study the shapes, then generalize)\n"
        f"{bank}\n\n"
        "Return ONLY the JSON object. Use a canonical, human-meaningful id."
    )


class SummonError(Exception):
    def __init__(self, message, abstractify=False):
        super().__init__(message)
        self.abstractify = abstractify


def _slug(concept: str) -> str:
    """Normalize a concept into a stable slug so "a chair" == "Chair"."""
    s = concept.lower().strip()
    s = re.sub(r"^(a|an|the|some|my|make|me)\s+", "", s)
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s or "abstract"


def _hash(s: str) -> int:
    return int(hashlib.sha256(s.encode()).hexdigest()[:8], 16)


class SpecCache:
    """Cache for summoned specs, rekeyed to `v2:<root-hash>:<seed>` for grammar
    v2. The slug index maps concept -> {id, root hash} so repeat requests (and
    re-rolls, which bump the seed) hit without an LLM call. Filesystem in dev,
    Vercel KV REST when KV_REST_API_URL is set (prod has no writable FS)."""

    def __init__(self):
        self._index_file = CACHE_DIR / "_index.json"
        self._kv_url = os.environ.get("KV_REST_API_URL", "").strip().rstrip("/")
        self._kv_token = os.environ.get("KV_REST_API_TOKEN", "").strip()
        self._index = self._load_index()

    def _load_index(self):
        try:
            if self._kv_url:
                return {}
            return json.loads(self._index_file.read_text()) if self._index_file.exists() else {}
        except Exception:
            return {}

    def _save_index(self):
        # Best-effort only: the Vercel serverless filesystem is read-only (no
        # KV configured), so a failed index write must never take the endpoint
        # down. Caching is purely an optimization — a read-only FS degrades to
        # a cache miss and a fresh synthesis call.
        if self._kv_url or not self._index:
            return
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            tmp = self._index_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._index))
            tmp.replace(self._index_file)
        except OSError:
            pass

    def _key(self, root_hash, seed):
        return f"v2:{root_hash}:{seed}.json"

    async def get(self, root_hash, seed):
        key = self._key(root_hash, seed)
        try:
            if self._kv_url:
                async with httpx.AsyncClient(timeout=5) as c:
                    r = await c.get(f"{self._kv_url}/{key}",
                                    headers={"Authorization": f"Bearer {self._kv_token}"})
                    if r.status_code == 200 and r.json().get("result"):
                        return json.loads(r.json()["result"])
                    return None
            path = CACHE_DIR / key
            return json.loads(path.read_text()) if path.exists() else None
        except Exception:
            return None

    async def set(self, root_hash, seed, spec):
        key = self._key(root_hash, seed)
        try:
            if self._kv_url:
                async with httpx.AsyncClient(timeout=5) as c:
                    await c.put(f"{self._kv_url}/{key}",
                                json={"value": json.dumps(spec)},
                                headers={"Authorization": f"Bearer {self._kv_token}"})
                return
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            tmp = CACHE_DIR / (key + ".tmp")
            tmp.write_text(json.dumps(spec))
            tmp.replace(CACHE_DIR / key)
        except Exception:
            pass

    def meta_for_slug(self, slug):
        """Returns {id, root} for a concept slug, or None on a miss. Legacy
        v1 index entries were bare id strings and carry no root hash, so they
        are treated as a miss (their cache files remain untouched)."""
        if self._kv_url:
            return None
        meta = self._index.get(slug)
        if isinstance(meta, dict) and isinstance(meta.get("id"), str) and isinstance(meta.get("root"), str):
            return meta
        return None

    def record_slug(self, slug, spec_id, root_hash):
        if self._kv_url:
            return
        self._index[slug] = {"id": spec_id, "root": root_hash}
        self._save_index()


def validate_v2_spec(spec) -> list:
    """Top-level grammar-v2 spec checks on top of validate_v2_root. Returns a
    list of error strings; empty list = valid."""
    if not isinstance(spec, dict):
        return ["spec is not a JSON object"]

    errors = []
    sid = spec.get("id")
    if not (isinstance(sid, str) and 0 < len(sid) <= 64 and
            all(c.isalnum() or c == "_" for c in sid)):
        errors.append("id must be a lowercase alphanumeric/underscore string (max 64)")

    size = spec.get("size", "medium")
    if size not in ("small", "medium", "large"):
        errors.append("size must be small|medium|large")

    root = spec.get("root")
    if not isinstance(root, dict):
        errors.append("root SDF tree is required")
    else:
        errors.extend(validate_v2_root(root))

    seed = spec.get("seed")
    if seed is not None and not isinstance(seed, (int, float)):
        errors.append("seed must be a number")
    return errors


def _call_deepseek(messages: list) -> dict:
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        raise SummonError("DeepSeek API key not configured", abstractify=True)
    url = f"{BASE_URL.rstrip('/')}/chat/completions"
    body = {
        "model": MODEL,
        "messages": messages,
        "response_format": {"type": "json_object"},
        "temperature": 0.6,
    }
    r = httpx.post(url, json=body,
                   headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                   timeout=60)
    if r.status_code != 200:
        raise SummonError(f"DeepSeek endpoint error ({r.status_code})", abstractify=True)
    content = r.json()["choices"][0]["message"]["content"]
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        raise SummonError("DeepSeek returned malformed JSON", abstractify=True)


async def summon(concept: str, seed=None) -> dict:
    """Resolve a concept to a validated grammar-v2 spec. Returns
    {"spec": ..., "id": ..., "seed": ..., "cached": bool}.
    Raises SummonError(abstractify=True) on unrecoverable failure."""
    if not concept or not str(concept).strip():
        raise SummonError("concept is required")
    concept = str(concept).strip()
    slug = _slug(concept)

    cache = SpecCache()

    # Cache hit path: {id, root hash} from the slug index, keyed by
    # v2:<root-hash>:<seed>. Re-rolls bump the seed; identical concepts with
    # the same seed (or the pinned default) hit without an LLM call.
    meta = cache.meta_for_slug(slug)
    if meta:
        want_seed = seed if seed is not None else _hash(meta["id"])
        hit = await cache.get(meta["root"], want_seed)
        if hit is not None:
            return {"spec": hit, "id": meta["id"], "seed": want_seed, "cached": True}

    # Miss: synthesize with DeepSeek, one fix-prompt retry on validation failure.
    system = {"role": "system", "content": build_prompt()}
    user = {"role": "user", "content": f'Generate the spec for: "{concept}"'}
    spec = _call_deepseek([system, user])
    errors = validate_v2_spec(spec)
    if errors:
        try:
            spec = _call_deepseek([
                system,
                user,
                {"role": "assistant", "content": json.dumps(spec)},
                {"role": "user", "content":
                    "Your previous output failed validation:\n- " + "\n- ".join(errors)
                    + "\nCorrect it. Return ONLY the corrected JSON."},
            ])
            errors = validate_v2_spec(spec)
        except SummonError:
            raise SummonError("spec synthesis failed", abstractify=True)
    if errors:
        raise SummonError("; ".join(errors), abstractify=True)

    spec.setdefault("schema", 2)
    spec.setdefault("size", "medium")
    spec_id = spec.get("id") or slug
    want_seed = seed if seed is not None else _hash(spec_id)
    spec["seed"] = want_seed
    root_hash = _root_hash(spec["root"])
    await cache.set(root_hash, want_seed, spec)
    cache.record_slug(slug, spec_id, root_hash)
    return {"spec": spec, "id": spec_id, "seed": want_seed, "cached": False}
