"""FastAPI server para el chatbot de hoteles."""
import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from contextlib import asynccontextmanager

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from chatbot_app import recommender
    recommender.init()
    yield


app = FastAPI(lifespan=lifespan)


class ChatRequest(BaseModel):
    message: str


class SearchRequest(BaseModel):
    query: str
    destination: str
    top_n: int = 5


@app.post("/chat")
def chat(req: ChatRequest):
    from chatbot_app import recommender
    return recommender.chat(req.message)


@app.post("/search")
def search(req: SearchRequest):
    from chatbot_app import recommender
    return recommender.direct_search(req.query, req.destination, req.top_n)


@app.get("/destinations")
def destinations():
    from chatbot_app import recommender
    return {"destinations": recommender.list_destinations()}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
