"""Remove invoice extraction admission persistence.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-17
"""

import sqlalchemy as sa
from alembic import op

from libs.database.functions import require_disposable_database

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Remove the unused database-backed upload quota."""
    op.drop_table(
        "invoice_extraction_admission",
        schema="document_intelligence",
    )


def downgrade() -> None:
    """Recreate the retired quota table only in a disposable database."""
    require_disposable_database(database_name=op.get_bind().engine.url.database)
    op.create_table(
        "invoice_extraction_admission",
        sa.Column("request_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "admitted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema="document_intelligence",
    )
    op.create_index(
        "ix_invoice_extraction_admission_admitted_at",
        "invoice_extraction_admission",
        ["admitted_at"],
        schema="document_intelligence",
    )
