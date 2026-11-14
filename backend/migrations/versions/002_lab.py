from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE TABLE lab_faults(source text PRIMARY KEY)")


def downgrade():
    op.execute("DROP TABLE lab_faults")
