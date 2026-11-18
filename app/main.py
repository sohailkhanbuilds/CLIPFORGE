from datetime import datetime, timezone
from typing import Optional
import hmac
import os

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import Boolean, DateTime, Integer, String, Text, create_engine, select, update
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./clipforge.db")
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
MAX_TASK_ATTEMPTS = 3


def utcnow():
    return datetime.now(timezone.utc)


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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    authorization_proof: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    authorized_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class ClipTask(Base):
    __tablename__ = "clip_tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_url: Mapped[str] = mapped_column(String(700))
    creator: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    worker_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)


class ChannelIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    platform: str = Field(default="youtube", pattern="^(youtube|twitch)$")
    url: HttpUrl


class TaskIn(BaseModel):
    video_url: HttpUrl
    creator: str = Field(min_length=1, max_length=120)


class AuthorizationIn(BaseModel):
    proof_reference: str = Field(min_length=5, max_length=500)


class TaskFailureIn(BaseModel):
    error_message: str = Field(min_length=1, max_length=2000)


class TaskCompletionIn(BaseModel):
    result_reference: Optional[str] = Field(default=None, max_length=700)


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


def require_worker_key(x_worker_key: Optional[str] = Header(default=None, alias="X-Worker-Key")):
    _check_secret(x_worker_key, "CLIPFORGE_WORKER_KEY", "worker key")


def channel_dict(c: Channel):
    return {
        "id": c.id, "name": c.name, "platform": c.platform, "url": c.url,
        "authorized": c.authorized, "enabled": c.enabled,
        "authorization_proof": c.authorization_proof,
        "authorized_at": c.authorized_at.isoformat() if c.authorized_at else None,
    }


def task_dict(t: ClipTask):
    return {
        "id": t.id, "video_url": t.video_url, "creator": t.creator,
        "status": t.status, "created_at": t.created_at.isoformat(),
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        "started_at": t.started_at.isoformat() if t.started_at else None,
        "finished_at": t.finished_at.isoformat() if t.finished_at else None,
        "attempt_count": t.attempt_count, "max_attempts": MAX_TASK_ATTEMPTS,
        "error_message": t.error_message, "worker_id": t.worker_id,
    }


app = FastAPI(
    title="CLIPFORGE API", version="0.4.0",
    description="Creator-authorized clipping workflow. API routes require X-API-Key, creator approval X-Admin-Key, and worker operations X-Worker-Key.",
)


@app.get("/")
def root():
    return {"name": "CLIPFORGE", "status": "online", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "ok", "timestamp": utcnow().isoformat()}


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
        channel = Channel(name=payload.name, platform=payload.platform, url=str(payload.url), authorized=False, enabled=False)
        db.add(channel)
        db.commit()
        db.refresh(channel)
        return channel_dict(channel)


@app.post("/api/channels/{channel_id}/authorize", dependencies=[Depends(require_admin_key)])
def authorize_channel(channel_id: int, payload: AuthorizationIn):
    # Human operator must verify actual creator permission before recording evidence here.
    with SessionLocal() as db:
        channel = db.get(Channel, channel_id)
        if not channel:
            raise HTTPException(404, "Channel not found")
        channel.authorized = True
        channel.authorization_proof = payload.proof_reference
        channel.authorized_at = utcnow()
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
def list_tasks(status: Optional[str] = None, limit: int = 50, offset: int = 0):
    if status and status not in {"queued", "processing", "completed", "failed"}:
        raise HTTPException(422, "Invalid task status")
    if not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(422, "limit must be 1-100 and offset must be non-negative")
    with SessionLocal() as db:
        query = select(ClipTask)
        if status:
            query = query.where(ClipTask.status == status)
        query = query.order_by(ClipTask.id.desc()).limit(limit).offset(offset)
        return [task_dict(t) for t in db.scalars(query).all()]


@app.get("/api/tasks/{task_id}", dependencies=[Depends(require_api_key)])
def get_task(task_id: int):
    with SessionLocal() as db:
        task = db.get(ClipTask, task_id)
        if not task:
            raise HTTPException(404, "Task not found")
        return task_dict(task)


@app.post("/api/tasks", status_code=201, dependencies=[Depends(require_api_key)])
def enqueue_task(payload: TaskIn):
    with SessionLocal() as db:
        task = ClipTask(video_url=str(payload.video_url), creator=payload.creator, status="queued", attempt_count=0)
        db.add(task)
        db.commit()
        db.refresh(task)
        return task_dict(task)


@app.post("/api/tasks/{task_id}/retry", dependencies=[Depends(require_api_key)])
def retry_task(task_id: int):
    with SessionLocal() as db:
        task = db.get(ClipTask, task_id)
        if not task:
            raise HTTPException(404, "Task not found")
        if task.status != "failed":
            raise HTTPException(409, "Only failed tasks can be retried")
        if task.attempt_count >= MAX_TASK_ATTEMPTS:
            raise HTTPException(409, "Maximum task attempts reached")
        task.status = "queued"
        task.error_message = None
        task.started_at = None
        task.finished_at = None
        task.worker_id = None
        task.updated_at = utcnow()
        db.commit()
        db.refresh(task)
        return task_dict(task)


@app.post("/api/worker/tasks/claim", dependencies=[Depends(require_worker_key)])
def claim_task(worker_id: str = "clipforge-worker"):
    if not worker_id.strip() or len(worker_id) > 120:
        raise HTTPException(422, "worker_id must be 1-120 characters")
    with SessionLocal() as db:
        # Conditional UPDATE makes claiming atomic: only one worker can win a queued task.
        task_id = db.scalar(
            update(ClipTask)
            .where(ClipTask.id == select(ClipTask.id).where(
                ClipTask.status == "queued",
                ClipTask.attempt_count < MAX_TASK_ATTEMPTS
            ).order_by(ClipTask.created_at, ClipTask.id).limit(1).scalar_subquery())
            .values(status="processing", started_at=utcnow(), updated_at=utcnow(),
                    attempt_count=ClipTask.attempt_count + 1, worker_id=worker_id,
                    error_message=None)
            .returning(ClipTask.id)
        )
        if task_id is None:
            return {"task": None, "message": "No queued tasks available"}
        db.commit()
        task = db.get(ClipTask, task_id)
        return {"task": task_dict(task)}


@app.post("/api/worker/tasks/{task_id}/complete", dependencies=[Depends(require_worker_key)])
def complete_task(task_id: int, payload: TaskCompletionIn):
    with SessionLocal() as db:
        task = db.get(ClipTask, task_id)
        if not task:
            raise HTTPException(404, "Task not found")
        if task.status != "processing":
            raise HTTPException(409, "Only processing tasks can be completed")
        task.status = "completed"
        task.finished_at = utcnow()
        task.updated_at = utcnow()
        task.error_message = None
        db.commit()
        db.refresh(task)
        return task_dict(task)


@app.post("/api/worker/tasks/{task_id}/fail", dependencies=[Depends(require_worker_key)])
def fail_task(task_id: int, payload: TaskFailureIn):
    with SessionLocal() as db:
        task = db.get(ClipTask, task_id)
        if not task:
            raise HTTPException(404, "Task not found")
        if task.status != "processing":
            raise HTTPException(409, "Only processing tasks can be failed")
        task.status = "failed"
        task.error_message = payload.error_message
        task.finished_at = utcnow()
        task.updated_at = utcnow()
        db.commit()
        db.refresh(task)
        return task_dict(task)
