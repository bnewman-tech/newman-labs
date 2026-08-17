"""Bound managed invoice extraction admission.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-17
"""

import sqlalchemy as sa
from alembic import op

from libs.database.functions import require_disposable_database

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the short-lived global admission ledger."""
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
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'newman_labs_web') THEN
                GRANT SELECT, INSERT, DELETE
                    ON document_intelligence.invoice_extraction_admission
                    TO newman_labs_web;
            ELSIF current_database() !~ '_(test|verify)$' THEN
                RAISE EXCEPTION 'Required role newman_labs_web does not exist';
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    """Drop the admission ledger only in a disposable database."""
    require_disposable_database(database_name=op.get_bind().engine.url.database)
    op.drop_table(
        "invoice_extraction_admission",
        schema="document_intelligence",
    )
