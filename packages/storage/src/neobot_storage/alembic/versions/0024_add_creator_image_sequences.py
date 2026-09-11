"""creator_images 图库编号改为持久化高水位

Revision ID: 0024
Revises: 0023
Create Date: 2026-09-10

0023 把图库编号改成入库时固定，但分配仍用 MAX(gallery_no)+1：
删除当前最大号后会复用它，并发入库还会读到同一个 MAX 撞唯一索引。
这里新增 creator_image_sequences 记录"已发到几号"，并把历史最大值回填为
高水位；之后编号只增不复用（允许空洞）。

注意：迁移只能以"当前存在的最大编号"为种子，无法找回迁移前已经被回收过的
编号，只能保证从此版本起不再回收。
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0024'
down_revision: Union[str, None] = '0023'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'creator_image_sequences',
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('last_no', sa.Integer(), nullable=False, server_default='0'),
        sa.PrimaryKeyConstraint('name'),
    )
    # 以现有最大编号为高水位：只保证从此不再复用，历史空洞无法恢复
    op.execute(
        """
        INSERT INTO creator_image_sequences (name, last_no)
        SELECT 'gallery', COALESCE(MAX(gallery_no), 0) FROM creator_images
        """
    )


def downgrade() -> None:
    op.drop_table('creator_image_sequences')
