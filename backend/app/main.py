from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


app = FastAPI(
    title="TokenGuard API",
    version="0.1.0",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=20_000)
    max_output_tokens: int = Field(default=300, ge=1, le=4_000)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "TokenGuard",
    }


@app.post("/chat")
def chat(payload: ChatRequest):
    input_tokens = max(1, len(payload.prompt) // 4)
    output_tokens = 20

    return {
        "answer": "Mock response from the TokenGuard gateway.",
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost_usd": 0.0001,
        "risk_level": "low",
        "decision": "allow",
        "reason": "Request is within configured limits.",
    }