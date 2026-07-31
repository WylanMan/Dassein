import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

try:
    from .summon import summon, SummonError  # package context (local uvicorn)
except ImportError:  # pragma: no cover
    from summon import summon, SummonError  # Vercel runtime (api/ on sys.path)

app = FastAPI(title="Dassein API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"status": "ok", "agent": "live"}


@app.post("/api/realtime/session")
async def realtime_session():
    """Mint a short-lived ephemeral token for the browser's Realtime WebRTC
    connection. The master API key never leaves the server."""
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if not openai_key:
        return JSONResponse({"error": "OpenAI API key not configured"}, status_code=503)

    import httpx

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                "https://api.openai.com/v1/realtime/client_secrets",
                json={
                    "session": {
                        "type": "realtime",
                        "model": "gpt-realtime-mini",
                        "audio": {"output": {"voice": "shimmer"}},
                    }
                },
                headers={"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"},
            )
    except Exception as e:
        return JSONResponse({"error": f"Session creation failed: {e}"}, status_code=502)

    if r.status_code != 200:
        return JSONResponse({"error": f"Realtime session endpoint error ({r.status_code})"}, status_code=502)

    data = r.json()
    token = data.get("value") or data.get("client_secret", {}).get("value", "")
    if not token:
        return JSONResponse({"error": "Realtime session response missing token"}, status_code=502)
    return {"token": token, "expires_at": data.get("expires_at")}


@app.post("/api/summon")
async def api_summon(request: Request):
    """Synthesize a spec for a concept (B1). Concept -> JSON spec, cached by
    canonical id + seed. Never returns geometry; never exposes keys."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)
    body = body or {}
    concept = body.get("concept")
    if not concept or not str(concept).strip():
        return JSONResponse({"error": "concept is required"}, status_code=400)
    if not os.environ.get("DEEPSEEK_API_KEY", ""):
        return JSONResponse(
            {"error": "DeepSeek API key not configured", "abstractify": True}, status_code=503
        )
    try:
        return await summon(concept, body.get("seed"))
    except SummonError as e:
        return JSONResponse(
            {"error": str(e), "abstractify": bool(e.abstractify)}, status_code=422
        )
