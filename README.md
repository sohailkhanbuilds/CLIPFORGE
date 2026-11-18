# CLIPFORGE

Creator-authorized, approval-gated multi-agent workflow for planning short-form video clips.

## Agent workflow (current)

1. Register a creator channel. New channels are disabled and unauthorized by default.
2. A human verifies permission outside CLIPFORGE, records the evidence reference with the admin endpoint, then enables the channel.
3. Create a task bound to that authorized channel.
4. Run agent analysis; CLIPFORGE fetches YouTube captions automatically when available, or accepts a supplied transcript.
5. Four specialist agents run sequentially: research, moment selection, editorial strategy, and safety review.
6. Review the saved plan and approve it with the admin key.
7. Only approved tasks from still-authorized, enabled channels can be claimed by a worker.

The agent pipeline currently creates an editorial plan only. It does not download videos, generate clips, export media, or publish posts. OpusClip, Descript, transcript retrieval, and publishing adapters remain separate integration work. Human approval is mandatory.

## API quick start

Install and run:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Set environment variables:
- `DATABASE_URL`
- `CLIPFORGE_API_KEY`
- `CLIPFORGE_ADMIN_KEY`
- `CLIPFORGE_WORKER_KEY`
- `ANTHROPIC_API_KEY`
- Optional: `CLAUDE_MODEL` (defaults to `claude-3-7-sonnet-latest`)

Open `/docs` for the full API schema.

### Main endpoints

- `POST /api/channels` — register a creator (starts unauthorized/disabled)
- `POST /api/channels/{id}/authorize` — admin records externally verified permission evidence
- `PATCH /api/channels/{id}?enabled=true` — enable an authorized creator
- `POST /api/tasks` — create a task with `video_url`, `creator`, and `channel_id`
- `POST /api/tasks/{id}/analyze` — run specialist agents; optional `transcript` field overrides automatic YouTube caption retrieval
- `GET /api/tasks/{id}/plan` — retrieve the saved plan
- `POST /api/tasks/{id}/approve` — admin approval after reviewing the plan
- `POST /api/worker/tasks/claim` — worker claims an approved task
- `POST /api/worker/tasks/{id}/complete` / `fail` — worker reports outcome

## Local tests

```bash
pytest -q
```

## Production notes

Run `alembic upgrade head` before starting the service. Render's local filesystem is ephemeral; use the configured external PostgreSQL database. Never paste API keys into source control or chat. The current free Render web service may sleep and is not a reliable always-on worker. A separate persistent worker deployment is needed for unattended processing.

## Rights and safety

Do not register creators without explicit permission to clip and republish their content. A proof reference is an audit pointer, not automatic verification. Never treat a model's safety result as proof of legal rights. Human review and approval remain required before execution or publishing.
