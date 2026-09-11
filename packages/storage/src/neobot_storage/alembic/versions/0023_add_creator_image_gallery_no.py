"""creator_images 新增固定图库编号

Revision ID: 0023
Revises: 0022
Create Date: 2026-09-10

图库编号此前是「按列表顺序数第几个」，会随图库增删与 gallery_update 变化，
导致 Agent 刚查完的编号指向别的图片。改为入库时分配一次的固定编号。

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0023'
down_revision: Union[str, None] = '0022'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('creator_images', sa.Column('gallery_no', sa.Integer(), nullable=True))
    # 历史图库记录按入库时间回填 1..N，保证编号唯一且此后固定不变
    op.execute(
        """
        UPDATE creator_images
           SET gallery_no = (
               SELECT COUNT(*)
                 FROM creator_images AS older
                WHERE older.source = 'gallery'
                  AND (
                        older.created_at < creator_images.created_at
                     OR (older.created_at = creator_images.created_at
                         AND older.id <= creator_images.id)
                  )
           )
         WHERE source = 'gallery'
        """
    )
    op.create_index(
        'ix_creator_images_gallery_no',
        'creator_images',
        ['gallery_no'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index('ix_creator_images_gallery_no', table_name='creator_images')
    op.drop_column('creator_images', 'gallery_no')
