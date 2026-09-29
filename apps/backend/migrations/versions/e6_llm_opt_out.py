"""DeepSeek reads assistant free text by default; store the explicit opt-out.

Revision ID: e6_llm_opt_out
Revises: e5_dialog_state
"""

from alembic import op
import sqlalchemy as sa


revision = "e6_llm_opt_out"
down_revision = "e5_dialog_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("profiles", sa.Column("chat_llm_opt_out_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade is unavailable; restore a verified backup")
