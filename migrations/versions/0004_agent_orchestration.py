"""Add agent plan persistence and creator binding to tasks."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0004_agent_orchestration"
down_revision = "0003_task_lifecycle"
branch_labels = None
depends_on = None


def upgrade():
    inspector = inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("clip_tasks")}
    additions = [
        sa.Column("channel_id", sa.Integer(), nullable=True),
        sa.Column("agent_plan", sa.Text(), nullable=True),
        sa.Column("agent_status", sa.String(length=40), nullable=False, server_default="not_started"),
        sa.Column("human_approved_at", sa.DateTime(), nullable=True),
    ]
    for column in additions:
        if column.name not in columns:
            op.add_column("clip_tasks", column)


def downgrade():
    op.drop_column("clip_tasks", "human_approved_at")
    op.drop_column("clip_tasks", "agent_status")
    op.drop_column("clip_tasks", "agent_plan")
    op.drop_column("clip_tasks", "channel_id")
