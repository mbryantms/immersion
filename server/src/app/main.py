"""FastAPI app. This process serves JSON and (in dev) files — it must never
import torch/HanLP; heavy work goes through the job queue to the worker."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import db
from .api import (
    anki,
    app_settings,
    events,
    jobs,
    knowledge,
    library,
    media,
    progress,
    review,
    saved,
    search,
    sentences,
    stats,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_engine()
    db.upgrade_db()
    yield


app = FastAPI(title="Immersion", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (library, sentences, knowledge, saved, progress, events, jobs, app_settings, anki,
               review, search, stats):
    app.include_router(module.router, prefix="/api")
app.include_router(media.router)  # /media/* — Caddy owns this path in prod


@app.get("/api/health")
def health():
    return {"ok": True}
