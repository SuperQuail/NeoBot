"""add image_source column"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("creator_images", sa.Column("image_source", sa.String(), nullable=True))
    op.add_column("emojis", sa.Column("image_source", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("creator_images", "image_source")
    op.drop_column("emojis", "image_source")
