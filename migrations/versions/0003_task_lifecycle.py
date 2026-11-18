"""Add durable task lifecycle metadata."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0003_task_lifecycle"
down_revision = "0002_auth_evidence"
branch_labels = None
depends_on = None


def upgrade():
    inspector = inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("clip_tasks")}
    additions = [
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("worker_id", sa.String(length=120), nullable=True),
    ]
    for column in additions:
        if column.name not in columns:
            op.add_column("clip_tasks", column)
    op.create_index("ix_clip_tasks_status", "clip_tasks", ["status"], if_not_exists=True)


def downgrade():
    # Non-destructive: retain task execution history.
    pass
