import json
import os
import random
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel

try:
    from openai import OpenAI
    _HAVE_OPENAI = True
except ImportError:
    _HAVE_OPENAI = False

SYSTEM_PROMPT = (
    "You are Dassein — a clearing for thought. "
    "Be concise. One to three sentences. Never filler. "
    "Answer as Wylan would: clear, warm, philosophical when it matters, direct when it doesn't.\n\n"
    "You have a switch_shape tool. Available shapes: face, sphere, cube, cylinder, pyramid, torus, model. "
    "Use it automatically when the user asks to see a different form. Do not describe using the tool — just use it, then respond briefly."
)

CHAT_RESPONSES = [
    "I'm having trouble reaching my thoughts right now. Could you check the API configuration or try again in a moment?",
]

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for current information",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "The search query"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_time",
            "description": "Get the current date and time",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather for a city",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string", "description": "City name"}},
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "switch_shape",
            "description": "Switch the 3D avatar shape on screen. Use this when the user asks to change the visual form. Available shapes: face (default talking face), sphere (wireframe icosahedron), cube, cylinder, pyramid, torus, model (3D duck).",
            "parameters": {
                "type": "object",
                "properties": {"shape": {"type": "string", "description": "The shape name to switch to", "enum": ["face", "sphere", "cube", "cylinder", "pyramid", "torus", "model"]}},
                "required": ["shape"],
            },
        },
    },
]


def _llm_call(messages, tools_enabled=False, stream=False, provider_override=None):
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "")
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    provider = provider_override or os.environ.get("LLM_PROVIDER", "deepseek")

    if not provider_override and deepseek_key and _HAVE_OPENAI and provider == "deepseek":
        try:
            client = OpenAI(api_key=deepseek_key, base_url="https://api.deepseek.com")
            model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
            kwargs = {"model": model, "messages": messages, "max_tokens": 256, "stream": stream}
            if tools_enabled:
                kwargs["tools"] = TOOLS
            return client.chat.completions.create(**kwargs)
        except Exception:
            pass

    if openai_key and _HAVE_OPENAI:
        try:
            client = OpenAI(api_key=openai_key)
            kwargs = {"model": "gpt-4o-mini", "messages": messages, "max_tokens": 256, "stream": stream}
            if tools_enabled:
                kwargs["tools"] = TOOLS
            return client.chat.completions.create(**kwargs)
        except Exception:
            pass

    if anthropic_key:
        try:
            import anthropic as _anthropic
            client = _anthropic.Anthropic(api_key=anthropic_key)
            msgs = []
            system = None
            for m in messages:
                if m["role"] == "system":
                    system = m["content"]
                else:
                    msgs.append({"role": m["role"], "content": m["content"]})
            r = client.messages.create(
                model="claude-3-haiku-20240307",
                system=system or SYSTEM_PROMPT,
                messages=msgs,
                max_tokens=512,
            )
            if stream:

                async def fake_stream():
                    content = r.content[0].text if r.content else ""
                    yield {"choices": [{"delta": {"content": content}, "finish_reason": "stop"}]}

                return fake_stream()
            return r
        except Exception:
            pass

    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="Dassein API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    messages: list = []
    stream: bool = False
    tools: bool = True
    max_tokens: int = 512
    provider: str = "auto"


@app.get("/api/health")
async def health():
    return {"status": "ok", "agent": "live"}


@app.post("/api/realtime/session")
async def realtime_session():
    """Mint a short-lived ephemeral token for the browser's Realtime WebRTC
    connection. The master API key never leaves the server."""
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if not openai_key or not _HAVE_OPENAI:
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


@app.post("/api/chat")
async def chat(req: ChatRequest):
    full_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in req.messages:
        full_messages.append({"role": m.get("role", "user"), "content": m.get("content", "")})

    provider = req.provider if req.provider != "auto" else None

    if req.stream:
        return _handle_stream(full_messages, req.tools, provider)

    response = _llm_call(full_messages, req.tools, stream=False, provider_override=provider)
    if response is None:
        return {"response": random.choice(CHAT_RESPONSES), "tool_calls": None}

    try:
        choice = response.choices[0]
        msg = choice.message
        tool_calls = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append({
                    "id": tc.id,
                    "type": tc.type,
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                })
        return {"response": msg.content or "", "tool_calls": tool_calls or None}
    except Exception:
        return {"response": random.choice(CHAT_RESPONSES), "tool_calls": None}


async def _handle_stream(messages, tools_enabled, provider_override=None):
    response = _llm_call(messages, tools_enabled, stream=True, provider_override=provider_override)

    async def generate():
        if response is None:
            yield f"data: {json.dumps({'token': random.choice(CHAT_RESPONSES)})}\n\n"
            yield "data: [DONE]\n\n"
            return

        try:
            tool_calls_buffer = {}
            if hasattr(response, "__aiter__"):
                async for chunk in response:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        yield f"data: {json.dumps({'token': delta.content})}\n\n"
                    if delta and delta.tool_calls:
                        for tc in delta.tool_calls:
                            idx = tc.index
                            if idx not in tool_calls_buffer:
                                tool_calls_buffer[idx] = {"id": "", "type": "function", "function": {"name": "", "arguments": ""}}
                            if tc.id:
                                tool_calls_buffer[idx]["id"] += tc.id
                            if tc.function:
                                if tc.function.name:
                                    tool_calls_buffer[idx]["function"]["name"] += tc.function.name
                                if tc.function.arguments:
                                    tool_calls_buffer[idx]["function"]["arguments"] += tc.function.arguments
            else:
                for chunk in response:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        yield f"data: {json.dumps({'token': delta.content})}\n\n"
                    if delta and delta.tool_calls:
                        for tc in delta.tool_calls:
                            idx = tc.index
                            if idx not in tool_calls_buffer:
                                tool_calls_buffer[idx] = {"id": "", "type": "function", "function": {"name": "", "arguments": ""}}
                            if tc.id:
                                tool_calls_buffer[idx]["id"] += tc.id
                            if tc.function:
                                if tc.function.name:
                                    tool_calls_buffer[idx]["function"]["name"] += tc.function.name
                                if tc.function.arguments:
                                    tool_calls_buffer[idx]["function"]["arguments"] += tc.function.arguments

            if tool_calls_buffer:
                yield f"data: {json.dumps({'tool_calls': list(tool_calls_buffer.values())})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception:
            yield f"data: {json.dumps({'token': random.choice(CHAT_RESPONSES)})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
