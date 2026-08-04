"""Initial operational ITSM schema."""
from alembic import op
from itsm.database import Base
from itsm import models
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None
def upgrade():
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
def downgrade():
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
