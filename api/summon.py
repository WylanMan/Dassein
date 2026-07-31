"""Spec synthesis for /api/summon (B1). Shared by the local dev server
(server.py) and the Vercel serverless function (api/index.py).

Contract: the endpoint returns a JSON *spec* — never geometry. The client owns
building. Flow: cache lookup (id + seed) -> DeepSeek call (one fix-prompt retry
on validation failure) -> validate -> cache. Second failure degrades to a 422
with an abstractify directive: the client shows a seeded abstract form instead
of crashing.

Seeds are pinned (B2): default seed = hash(canonical id), and re-rolls move the
seed by +1 — deterministic jitter variants, all cacheable.
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

ALLOWED_TYPES = [
    "cube", "cylinder", "pyramid", "cone", "torus", "gem", "rock", "crystal",
    "pebble", "blob", "vase", "goblet", "rocket", "bowl", "star", "gear",
    "cross", "hexagon", "polygon", "knot", "spiral", "helix",
]
ALLOWED_ROT = ("up", "flat", "side")
MAX_PARTS = 12
WORK_VOLUME = 0.8

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


def build_prompt(curated=None) -> str:
    examples = json.dumps(curated if curated is not None else load_curated(),
                          indent=None, separators=(",", ":"))
    return (
        "You are the spec engine for Dassein, a wireframe 3D avatar. The user asks for a "
        "concept and you reply with exactly one JSON object describing how to build it as a "
        "478-point wireframe net. You NEVER render anything and never describe in words — "
        "you only emit the spec JSON.\n\n"
        "## Spec grammar\n"
        "{\n"
        '  "id": "canonical_lowercase_id",   // stable cache key, e.g. "hourglass_wide"\n'
        '  "type": "one of the builder names",  // OR "parts" below, never both\n'
        '  "params": { ... },   // family params: sides/teeth/turns/inner/thickness/bulge/waist;\n'
        '                        //   OR "profile" (see below)\n'
        '  "size": "medium",    // "small" | "medium" | "large"\n'
        '  "parts": [           // optional compound form (OR type above, never both)\n'
        '    { "type": "builder", "pos": [x, y, z], "rot": "up", "scale": 1, "params": {} }\n'
        "  ],\n"
        '  "mods": { ... }      // optional: squash {kx,ky,kz}, bend n, twist deg, taper k,\n'
        '                        //   bulge k, spherize k, jitter {amp}\n'
        "}\n"
        "## Orientation vocabulary (never raw Euler angles)\n"
        '- "up"  = standing vertical (default)\n'
        '- "flat" = lying down along the Z axis\n'
        '- "side" = lying down along the X axis\n'
        '- or {"preset": "flat", "deg": 15} for a small extra spin in degrees\n\n'
        "## Compound forms\n"
        "- The FIRST part is the anchor at the origin; every other part's pos is relative to it.\n"
        f"- At most {MAX_PARTS} parts. Keep part positions inside the ±{WORK_VOLUME} work volume.\n"
        "- Parts merge before the wireframe net is sampled, so they read as one solid form.\n\n"
        "## Profiles\n"
        '- Lathe (vase/goblet/rocket/bowl): params.profile is [[y, r], ...] — height first, '
        "radius second, y strictly increasing, r >= 0.\n"
        '- Extrusion (star/gear/cross/polygon): params.profile is [[x, y], ...] — flat outline '
        "points; params.depth defaults to 0.18, override for thicker slabs.\n\n"
        "## Simple-forms contract\n"
        "Prefer solid, simple, stylized forms built from chunky primitives. Avoid thin, lacy, "
        "hollow, or mechanically complex requests. The 478-point wireframe forgives crudeness — "
        "the silhouette must read. If a request is fragile (\"a spiderweb\", \"a doily\"), summon "
        "its essence as a simple solid form (\"web\" -> a flat star; \"bridge\" -> a stone arch).\n\n"
        "## Vocabulary notes\n"
        "- \"sphere\" is a RESERVED word (the landing sphere) — never emit it as a builder. "
        "For round/smooth forms use blob (soft sphere) or pebble.\n"
        "- Builders: " + ", ".join(ALLOWED_TYPES) + ".\n\n"
        "## Worked examples (curated library — study the shapes, then generalize)\n"
        f"{examples}\n\n"
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
    """Cache for summoned specs, keyed by (id, seed). Filesystem in dev,
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
        if self._kv_url or not self._index:
            return
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = self._index_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._index))
        tmp.replace(self._index_file)

    def _key(self, spec_id, seed):
        return f"{spec_id}__{seed}.json"

    async def get(self, spec_id, seed):
        key = self._key(spec_id, seed)
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

    async def set(self, spec_id, seed, spec):
        key = self._key(spec_id, seed)
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

    def id_for_slug(self, slug):
        if self._kv_url:
            return None
        return self._index.get(slug)

    def record_slug(self, slug, spec_id):
        if self._kv_url:
            return
        self._index[slug] = spec_id
        self._save_index()


def validate_spec(spec) -> list:
    """Returns a list of error strings; empty list = valid."""
    errors = []
    if not isinstance(spec, dict):
        return ["spec is not a JSON object"]

    sid = spec.get("id")
    if not (isinstance(sid, str) and 0 < len(sid) <= 64 and
            all(c.isalnum() or c == "_" for c in sid)):
        errors.append("id must be a lowercase alphanumeric/underscore string (max 64)")

    size = spec.get("size", "medium")
    if size not in ("small", "medium", "large"):
        errors.append("size must be small|medium|large")

    for k, v in (spec.get("mods") or {}).items():
        if k not in ("squash", "bend", "twist", "taper", "bulge", "spherize", "jitter"):
            errors.append(f"unknown modifier '{k}'")
        if k == "squash" and isinstance(v, dict):
            for a in ("kx", "ky", "kz"):
                if a in v and not (0.05 <= float(v[a]) <= 4):
                    errors.append(f"squash.{a} out of range (0.05..4)")
        elif k == "jitter" and isinstance(v, dict):
            if "amp" in v and not (0 <= float(v["amp"]) <= 0.25):
                errors.append("jitter.amp out of range (0..0.25)")

    parts = spec.get("parts")
    if parts is not None:
        if not isinstance(parts, list) or not parts:
            errors.append("parts must be a non-empty array")
        elif len(parts) > MAX_PARTS:
            errors.append(f"more than {MAX_PARTS} parts")
        else:
            for i, p in enumerate(parts):
                errors.extend(validate_part(p, i))
        if "type" in spec or "union" in spec:
            errors.append("spec cannot combine parts with type or union")
        if parts and isinstance(parts[0], dict) and parts[0].get("type") not in ALLOWED_TYPES:
            errors.append("first (anchor) part must have a valid type")
    else:
        t = spec.get("type")
        if t not in ALLOWED_TYPES:
            errors.append(f"unknown type '{t}' — allowed: {', '.join(ALLOWED_TYPES)}")
        else:
            params = spec.get("params") or {}
            if isinstance(params, dict) and "profile" in params:
                errors.extend(validate_profile(params["profile"], "spec"))

    seed = spec.get("seed")
    if seed is not None and not isinstance(seed, (int, float)):
        errors.append("seed must be a number")
    return errors


def validate_part(p, i) -> list:
    errors = []
    if not isinstance(p, dict):
        return [f"part[{i}] is not an object"]
    t = p.get("type")
    if t not in ALLOWED_TYPES:
        errors.append(f"part[{i}] unknown type '{t}' — allowed: {', '.join(ALLOWED_TYPES)}")

    pos = p.get("pos", [0, 0, 0])
    if not (isinstance(pos, list) and len(pos) == 3 and
            all(isinstance(v, (int, float)) for v in pos)):
        errors.append(f"part[{i}] pos must be [x, y, z] numbers")

    rot = p.get("rot", "up")
    if isinstance(rot, str):
        if rot not in ALLOWED_ROT:
            errors.append(f"part[{i}] rot '{rot}' not in up|flat|side")
    elif isinstance(rot, dict):
        if rot.get("preset", "up") not in ALLOWED_ROT:
            errors.append(f"part[{i}] rot.preset invalid")
        if "deg" in rot and not isinstance(rot["deg"], (int, float)):
            errors.append(f"part[{i}] rot.deg must be a number")
    else:
        errors.append(f"part[{i}] rot must be a preset string or object")

    scale = p.get("scale", 1)
    if isinstance(scale, (int, float)):
        if not (0.05 <= scale <= 4):
            errors.append(f"part[{i}] scale out of range (0.05..4)")
    elif isinstance(scale, list):
        if not (len(scale) == 3 and all(isinstance(v, (int, float)) and v > 0 for v in scale)):
            errors.append(f"part[{i}] scale must be a number or [x,y,z] > 0")
    else:
        errors.append(f"part[{i}] scale invalid")

    params = p.get("params") or {}
    if isinstance(params, dict) and "profile" in params:
        errors.extend(validate_profile(params["profile"], f"part[{i}]"))

    mods = p.get("mods") or {}
    if isinstance(mods, dict):
        for k in mods:
            if k not in ("squash", "bend", "twist", "taper", "bulge", "spherize", "jitter"):
                errors.append(f"part[{i}] unknown modifier '{k}'")
    return errors


def validate_profile(profile, where) -> list:
    errors = []
    if not (isinstance(profile, list) and len(profile) >= 2 and
            all(isinstance(pt, list) and len(pt) == 2 and
                all(isinstance(v, (int, float)) for v in pt) for pt in profile)):
        return [f"{where}: profile must be a list of [y/x, r] number pairs (>= 2 points)"]
    if profile[0] == profile[-1]:
        errors.append(f"{where}: profile first and last points must differ (lathe) — no closed ring")
    for pt in profile:
        if pt[1] < 0:
            errors.append(f"{where}: profile has a negative radius {pt}")
    for a, b in zip(profile, profile[1:]):
        if b[0] <= a[0]:
            errors.append(f"{where}: profile ordering must be strictly increasing")
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
    """Resolve a concept to a validated spec. Returns
    {"spec": ..., "id": ..., "seed": ..., "cached": bool}.
    Raises SummonError(abstractify=True) on unrecoverable failure."""
    if not concept or not str(concept).strip():
        raise SummonError("concept is required")
    concept = str(concept).strip()
    slug = _slug(concept)

    cache = SpecCache()

    # Cache hit path: canonical id from the slug index, keyed by (id, seed).
    known_id = cache.id_for_slug(slug)
    if known_id:
        want_seed = seed if seed is not None else _hash(known_id)
        hit = await cache.get(known_id, want_seed)
        if hit is not None:
            return {"spec": hit, "id": known_id, "seed": want_seed, "cached": True}

    # Miss: synthesize with DeepSeek, one fix-prompt retry on validation failure.
    system = {"role": "system", "content": build_prompt()}
    user = {"role": "user", "content": f'Generate the spec for: "{concept}"'}
    spec = _call_deepseek([system, user])
    errors = validate_spec(spec)
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
            errors = validate_spec(spec)
        except SummonError:
            raise SummonError("spec synthesis failed", abstractify=True)
    if errors:
        raise SummonError("; ".join(errors), abstractify=True)

    spec_id = spec.get("id") or slug
    want_seed = seed if seed is not None else _hash(spec_id)
    spec.setdefault("seed", want_seed)
    await cache.set(spec_id, want_seed, spec)
    cache.record_slug(slug, spec_id)
    return {"spec": spec, "id": spec_id, "seed": want_seed, "cached": False}
