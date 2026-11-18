# CLIPFORGE

Creator-authorized short-form clipping workflow controller.

## Current MVP
- FastAPI health endpoint
- Channel registry with explicit authorization opt-in
- Manual clip-task queue
- SQLite for local development; configure `DATABASE_URL` for a persistent external database in production

## Run locally
```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Open `/docs` for the API.

## Important limitations
This service is only the control-plane MVP. It does not yet download videos, generate edits, or publish to Instagram/YouTube. Those require separate media workers and platform-approved integrations. Render's local filesystem is ephemeral, so do not rely on the default SQLite file for production persistence. Do not add creators unless you have explicit permission to clip and republish their content.
