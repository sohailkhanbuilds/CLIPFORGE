"""Create initial CLIPFORGE tables, adopting existing tables safely."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table('channels'):
        op.create_table('channels',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('name', sa.String(120), nullable=False),
            sa.Column('platform', sa.String(30), nullable=False, server_default='youtube'),
            sa.Column('url', sa.String(500), nullable=False, unique=True),
            sa.Column('authorized', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('created_at', sa.DateTime(), nullable=False))
    inspector = inspect(bind)
    if not inspector.has_table('clip_tasks'):
        op.create_table('clip_tasks',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('video_url', sa.String(700), nullable=False),
            sa.Column('creator', sa.String(120), nullable=False),
            sa.Column('status', sa.String(30), nullable=False, server_default='queued'),
            sa.Column('created_at', sa.DateTime(), nullable=False))

def downgrade():
    # Non-destructive: never drop existing production tables automatically.
    pass
