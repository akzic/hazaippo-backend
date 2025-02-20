from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5dba5a343b60'
down_revision = '0307d30d781e'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('materials', sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()))


def downgrade():
    op.drop_column('materials', 'created_at')
