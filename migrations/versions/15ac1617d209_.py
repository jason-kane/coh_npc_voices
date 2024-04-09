"""empty message

Revision ID: 15ac1617d209
Revises: 90328d2e3ef5
Create Date: 2024-04-08 19:11:52.230371

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '15ac1617d209'
down_revision: Union[str, None] = '90328d2e3ef5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
