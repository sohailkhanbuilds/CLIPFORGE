"""Record evidence and timestamp for creator authorization."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = '0002_creator_authorization_evidence'
down_revision = '0001_initial'
branch_labels = None
depends_on = None

def upgrade():
    inspector = inspect(op.get_bind())
    columns = {column['name'] for column in inspector.get_columns('channels')}
    if 'authorization_proof' not in columns:
        op.add_column('channels', sa.Column('authorization_proof', sa.String(length=500), nullable=True))
    if 'authorized_at' not in columns:
        op.add_column('channels', sa.Column('authorized_at', sa.DateTime(), nullable=True))

def downgrade():
    # Preserve authorization audit data; no automatic destructive downgrade.
    pass
