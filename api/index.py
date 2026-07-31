import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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
