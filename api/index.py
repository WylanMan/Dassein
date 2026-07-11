from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .agent import SupportAgent

agent = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent
    agent = SupportAgent()
    yield


app = FastAPI(title="Dassein Support Agent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    thread_id: str = "default"


class ChatResponse(BaseModel):
    response: str
    category: str
    urgency: str
    sentiment: str
    route: str
    confidence: float


@app.get("/api/health")
async def health():
    return {"status": "ok", "agent": "live"}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    return await agent.run(req.message, req.thread_id)
