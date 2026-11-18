from datetime import datetime, timezone
from typing import Optional
import hmac
import os

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, HttpUrl, Field
from sqlalchemy import Boolean, DateTime, Integer, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

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
    authorization_proof: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    authorized_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class ClipTask(Base):
    __tablename__ = "clip_tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_url: Mapped[str] = mapped_column(String(700))
    creator: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30), default="queued")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))



class ChannelIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    platform: str = Field(default="youtube", pattern="^(youtube|twitch)$")
    url: HttpUrl


class TaskIn(BaseModel):
    video_url: HttpUrl
    creator: str = Field(min_length=1, max_length=120)


class AuthorizationIn(BaseModel):
    proof_reference: str = Field(min_length=5, max_length=500)


def _check_secret(provided: Optional[str], env_name: str, label: str):
    expected = os.getenv(env_name)
    if not expected:
        raise HTTPException(status_code=503, detail=f"{label} is not configured")
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail=f"Invalid or missing {label}")


def require_api_key(x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")):
    _check_secret(x_api_key, "CLIPFORGE_API_KEY", "API key")


def require_admin_key(x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key")):
    _check_secret(x_admin_key, "CLIPFORGE_ADMIN_KEY", "admin key")


def channel_dict(c: Channel):
    return {
        "id": c.id,
        "name": c.name,
        "platform": c.platform,
        "url": c.url,
        "authorized": c.authorized,
        "enabled": c.enabled,
        "authorization_proof": c.authorization_proof,
        "authorized_at": c.authorized_at.isoformat() if c.authorized_at else None,
    }


def task_dict(t: ClipTask):
    return {
        "id": t.id,
        "video_url": t.video_url,
        "creator": t.creator,
        "status": t.status,
        "created_at": t.created_at.isoformat(),
    }


app = FastAPI(
    title="CLIPFORGE API",
    version="0.3.0",
    description="Creator-authorized clipping workflow. API routes require X-API-Key; creator approval requires X-Admin-Key.",
)


@app.get("/")
def root():
    return {"name": "CLIPFORGE", "status": "online", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/api/channels", dependencies=[Depends(require_api_key)])
def list_channels():
    with SessionLocal() as db:
        return [channel_dict(c) for c in db.scalars(select(Channel).order_by(Channel.id)).all()]


@app.post("/api/channels", status_code=201, dependencies=[Depends(require_api_key)])
def add_channel(payload: ChannelIn):
    with SessionLocal() as db:
        existing = db.scalar(select(Channel).where(Channel.url == str(payload.url)))
        if existing:
            raise HTTPException(409, "Channel URL already exists")
        # A newly registered creator is always unapproved and disabled.
        channel = Channel(
            name=payload.name,
            platform=payload.platform,
            url=str(payload.url),
            authorized=False,
            enabled=False,
        )
        db.add(channel)
        db.commit()
        db.refresh(channel)
        return channel_dict(channel)


@app.post("/api/channels/{channel_id}/authorize", dependencies=[Depends(require_admin_key)])
def authorize_channel(channel_id: int, payload: AuthorizationIn):
    # The operator must verify creator permission and record its evidence before calling this route.
    with SessionLocal() as db:
        channel = db.get(Channel, channel_id)
        if not channel:
            raise HTTPException(404, "Channel not found")
        channel.authorized = True
        channel.authorization_proof = payload.proof_reference
        channel.authorized_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(channel)
        return channel_dict(channel)


@app.delete("/api/channels/{channel_id}/authorization", dependencies=[Depends(require_admin_key)])
def revoke_channel_authorization(channel_id: int):
    with SessionLocal() as db:
        channel = db.get(Channel, channel_id)
        if not channel:
            raise HTTPException(404, "Channel not found")
        channel.authorized = False
        channel.enabled = False
        db.commit()
        db.refresh(channel)
        return channel_dict(channel)


@app.patch("/api/channels/{channel_id}", dependencies=[Depends(require_api_key)])
def update_channel(channel_id: int, enabled: Optional[bool] = None):
    with SessionLocal() as db:
        channel = db.get(Channel, channel_id)
        if not channel:
            raise HTTPException(404, "Channel not found")
        if enabled is not None:
            channel.enabled = enabled and channel.authorized
        db.commit()
        db.refresh(channel)
        return channel_dict(channel)


@app.delete("/api/channels/{channel_id}", status_code=204, dependencies=[Depends(require_api_key)])
def delete_channel(channel_id: int):
    with SessionLocal() as db:
        channel = db.get(Channel, channel_id)
        if not channel:
            raise HTTPException(404, "Channel not found")
        db.delete(channel)
        db.commit()


@app.get("/api/tasks", dependencies=[Depends(require_api_key)])
def list_tasks():
    with SessionLocal() as db:
        return [task_dict(t) for t in db.scalars(select(ClipTask).order_by(ClipTask.id.desc())).all()]


@app.post("/api/tasks", status_code=201, dependencies=[Depends(require_api_key)])
def enqueue_task(payload: TaskIn):
    with SessionLocal() as db:
        task = ClipTask(video_url=str(payload.video_url), creator=payload.creator)
        db.add(task)
        db.commit()
        db.refresh(task)
        return task_dict(task)
