from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl, Field
from sqlalchemy import Boolean, DateTime, Integer, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./clipforge.db")
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

class Base(DeclarativeBase):
    pass

class Channel(Base):
    __tablename__ = "channels"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    platform: Mapped[str] = mapped_column(String(30), default="youtube")
    url: Mapped[str] = mapped_column(String(500), unique=True)
    authorized: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

class ClipTask(Base):
    __tablename__ = "clip_tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_url: Mapped[str] = mapped_column(String(700))
    creator: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30), default="queued")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

Base.metadata.create_all(engine)

class ChannelIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    platform: str = Field(default="youtube", pattern="^(youtube|twitch)$")
    url: HttpUrl
    authorized: bool = False
    enabled: bool = False

class TaskIn(BaseModel):
    video_url: HttpUrl
    creator: str = Field(min_length=1, max_length=120)

def channel_dict(c: Channel):
    return {"id": c.id, "name": c.name, "platform": c.platform, "url": c.url,
            "authorized": c.authorized, "enabled": c.enabled}

def task_dict(t: ClipTask):
    return {"id": t.id, "video_url": t.video_url, "creator": t.creator,
            "status": t.status, "created_at": t.created_at.isoformat()}

app = FastAPI(title="CLIPFORGE API", version="0.1.0",
              description="Creator-authorized clipping workflow control plane.")

@app.get("/")
def root():
    return {"name": "CLIPFORGE", "status": "online", "docs": "/docs"}

@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}

@app.get("/api/channels")
def list_channels():
    with SessionLocal() as db:
        return [channel_dict(c) for c in db.scalars(select(Channel).order_by(Channel.id)).all()]

@app.post("/api/channels", status_code=201)
def add_channel(payload: ChannelIn):
    with SessionLocal() as db:
        existing = db.scalar(select(Channel).where(Channel.url == str(payload.url)))
        if existing:
            raise HTTPException(409, "Channel URL already exists")
        # Authorization is deliberately opt-in. No channel is monitored by default.
        channel = Channel(name=payload.name, platform=payload.platform, url=str(payload.url),
                          authorized=payload.authorized, enabled=payload.enabled and payload.authorized)
        db.add(channel)
        db.commit()
        db.refresh(channel)
        return channel_dict(channel)

@app.patch("/api/channels/{channel_id}")
def update_channel(channel_id: int, authorized: Optional[bool] = None, enabled: Optional[bool] = None):
    with SessionLocal() as db:
        channel = db.get(Channel, channel_id)
        if not channel:
            raise HTTPException(404, "Channel not found")
        if authorized is not None:
            channel.authorized = authorized
        if enabled is not None:
            channel.enabled = enabled
        if not channel.authorized:
            channel.enabled = False
        db.commit()
        db.refresh(channel)
        return channel_dict(channel)

@app.delete("/api/channels/{channel_id}", status_code=204)
def delete_channel(channel_id: int):
    with SessionLocal() as db:
        channel = db.get(Channel, channel_id)
        if not channel:
            raise HTTPException(404, "Channel not found")
        db.delete(channel)
        db.commit()

@app.get("/api/tasks")
def list_tasks():
    with SessionLocal() as db:
        return [task_dict(t) for t in db.scalars(select(ClipTask).order_by(ClipTask.id.desc())).all()]

@app.post("/api/tasks", status_code=201)
def enqueue_task(payload: TaskIn):
    with SessionLocal() as db:
        task = ClipTask(video_url=str(payload.video_url), creator=payload.creator)
        db.add(task)
        db.commit()
        db.refresh(task)
        return task_dict(task)
