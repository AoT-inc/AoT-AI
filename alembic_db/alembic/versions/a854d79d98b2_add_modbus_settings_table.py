"""Add modbus_settings table

Revision ID: a854d79d98b2
Revises: 5966b3569c89
Create Date: 2025-02-25 19:02:29.663381

"""
import sys
import os

sys.path.append(os.path.abspath(os.path.join(__file__, "../../../..")))

from alembic_db.alembic_post_utils import write_revision_post_alembic

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a854d79d98b2'
down_revision = '5966b3569c89'
branch_labels = None
depends_on = None


def upgrade():
    # write_revision_post_alembic(revision)

    pass


def downgrade():
    pass
