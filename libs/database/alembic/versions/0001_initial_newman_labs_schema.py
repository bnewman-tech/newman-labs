"""Create the initial Newman Labs database schema.

Revision ID: 0001
Revises:
Create Date: 2026-08-16
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from libs.database.functions import require_disposable_database

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SCHEMAS = (
    "raw",
    "orchestration",
    "document_intelligence",
    "analytics_staging",
    "analytics_houston_signal",
)
MAX_EMBEDDING_DIMENSIONS = 16_000


def upgrade() -> None:
    """Create source-data, ingestion-audit, and document objects."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    for schema in SCHEMAS:
        op.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')

    create_ingestion_run_table()
    create_houston_311_tables()
    create_houston_emergency_center_tables()
    create_document_intelligence_tables()
    grant_web_role_access()


def create_ingestion_run_table() -> None:
    """Create one append-only audit table for every managed source."""
    op.create_table(
        "ingestion_run",
        sa.Column("run_id", sa.Uuid(), primary_key=True),
        sa.Column("source_name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_cursor", sa.Text()),
        sa.Column("extracted_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inserted_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unchanged_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deactivated_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deleted_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("previous_watermark", sa.DateTime(timezone=True)),
        sa.Column("current_watermark", sa.DateTime(timezone=True)),
        sa.Column(
            "warnings",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("error_type", sa.Text()),
        sa.CheckConstraint(
            "status IN ('succeeded', 'failed')",
            name="status",
        ),
        sa.CheckConstraint(
            "extracted_rows >= 0 AND inserted_rows >= 0 "
            "AND updated_rows >= 0 AND unchanged_rows >= 0 "
            "AND deactivated_rows >= 0 AND deleted_rows >= 0",
            name="row_counts_nonnegative",
        ),
        schema="orchestration",
    )
    op.create_index(
        "ix_ingestion_run_source_completed_at",
        "ingestion_run",
        ["source_name", "completed_at"],
        schema="orchestration",
    )


def create_houston_311_tables() -> None:
    """Create the Houston 311 current-state table."""
    op.create_table(
        "houston_311_request",
        sa.Column("case_number", sa.Text(), primary_key=True),
        sa.Column("source_object_id", sa.BigInteger(), nullable=False),
        sa.Column("case_number_365", sa.Text()),
        sa.Column("incident_address", sa.Text()),
        sa.Column("latitude", sa.Double()),
        sa.Column("longitude", sa.Double()),
        sa.Column("status", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("title", sa.Text()),
        sa.Column("case_type", sa.Text()),
        sa.Column("sla_time", sa.Text()),
        sa.Column("service_area", sa.Text()),
        sa.Column("council_district", sa.Text()),
        sa.Column("key_map", sa.Text()),
        sa.Column("department", sa.Text()),
        sa.Column("division", sa.Text()),
        sa.Column("state_code", sa.Text()),
        sa.Column("state_code_name", sa.Text()),
        sa.Column("swm_quadrant", sa.Text()),
        sa.Column("recycling_quadrant", sa.Text()),
        sa.Column("heavy_trash_quadrant", sa.Text()),
        sa.Column("resolution_notes", sa.Text()),
        sa.Column("meaningful_hash", sa.Text(), nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "latitude IS NULL OR latitude BETWEEN -90 AND 90",
            name="latitude_range",
        ),
        sa.CheckConstraint(
            "longitude IS NULL OR longitude BETWEEN -180 AND 180",
            name="longitude_range",
        ),
        sa.CheckConstraint(
            "first_seen_at <= last_seen_at",
            name="observation_order",
        ),
        schema="raw",
    )
    for column in ("created_at", "council_district", "source_object_id"):
        op.create_index(
            f"ix_houston_311_request_{column}",
            "houston_311_request",
            [column],
            schema="raw",
        )


def create_houston_emergency_center_tables() -> None:
    """Create the retained Houston Emergency Center incident table."""
    op.create_table(
        "houston_emergency_center_incident",
        sa.Column("incident_id", sa.Text(), primary_key=True),
        sa.Column("source_incident_id", sa.BigInteger(), nullable=False),
        sa.Column("agency", sa.Text(), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("cross_street", sa.Text()),
        sa.Column("longitude", sa.Double(), nullable=False),
        sa.Column("latitude", sa.Double(), nullable=False),
        sa.Column("key_map", sa.Text()),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("incident_type", sa.Text(), nullable=False),
        sa.Column("alarm_level", sa.Text()),
        sa.Column("reported_unit_count", sa.Integer(), nullable=False),
        sa.Column("units", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("combined_response", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("meaningful_hash", sa.Text(), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "first_seen_at <= last_seen_at",
            name="observation_order",
        ),
        sa.CheckConstraint(
            "(is_active AND ended_at IS NULL) OR (NOT is_active AND ended_at IS NOT NULL)",
            name="lifecycle_state",
        ),
        sa.CheckConstraint(
            "ended_at IS NULL OR ended_at >= opened_at",
            name="end_after_open",
        ),
        sa.CheckConstraint("agency IN ('F', 'P')", name="agency"),
        sa.CheckConstraint("source_incident_id > 0", name="source_id_positive"),
        sa.CheckConstraint(
            "reported_unit_count >= 0",
            name="unit_count_nonnegative",
        ),
        sa.CheckConstraint("latitude BETWEEN -90 AND 90", name="latitude_range"),
        sa.CheckConstraint(
            "longitude BETWEEN -180 AND 180",
            name="longitude_range",
        ),
        sa.UniqueConstraint(
            "agency",
            "source_incident_id",
            "opened_at",
            name="agency_source_incident_opened_at",
        ),
        schema="raw",
    )
    for column in ("agency", "opened_at", "is_active", "key_map"):
        op.create_index(
            f"ix_houston_emergency_center_incident_{column}",
            "houston_emergency_center_incident",
            [column],
            schema="raw",
        )


def create_document_intelligence_tables() -> None:
    """Create document lifecycle, parser artifacts, chunks, and vectors."""
    op.create_table(
        "document",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("storage_bucket", sa.Text(), nullable=False),
        sa.Column("storage_object_key", sa.Text(), nullable=False, unique=True),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("media_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("content_sha256", sa.Text(), nullable=False),
        sa.Column("security_scan", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('stored', 'converted', 'embedded', 'failed', 'deleted')",
            name="status",
        ),
        sa.CheckConstraint("size_bytes > 0", name="size_positive"),
        sa.CheckConstraint(
            "security_scan ->> 'verdict' IN ('allow', 'flag')",
            name="security_approved",
        ),
        schema="document_intelligence",
    )
    op.create_index(
        "ix_document_content_sha256",
        "document",
        ["content_sha256"],
        schema="document_intelligence",
    )
    op.create_index(
        "ix_document_expires_at",
        "document",
        ["expires_at"],
        schema="document_intelligence",
    )

    op.create_table(
        "document_parse",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey(
                "document_intelligence.document.id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("parser_name", sa.Text(), nullable=False),
        sa.Column("parser_version", sa.Text(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("markdown_object_key", sa.Text(), nullable=False, unique=True),
        sa.Column("markdown_sha256", sa.Text(), nullable=False),
        sa.Column(
            "docling_document_object_key",
            sa.Text(),
            nullable=False,
            unique=True,
        ),
        sa.Column("docling_document_sha256", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("page_count > 0", name="page_count_positive"),
        sa.UniqueConstraint(
            "document_id",
            "parser_name",
            "parser_version",
            name="document_parse_identity",
        ),
        schema="document_intelligence",
    )
    op.create_table(
        "document_chunk",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "parse_id",
            sa.Uuid(),
            sa.ForeignKey(
                "document_intelligence.document_parse.id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("contextualized_text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("chunker_name", sa.Text(), nullable=False),
        sa.Column("chunker_version", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.Text(), nullable=False),
        sa.Column(
            "page_numbers",
            postgresql.ARRAY(sa.Integer()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("ordinal >= 0", name="ordinal_nonnegative"),
        sa.CheckConstraint("token_count > 0", name="token_count_positive"),
        sa.UniqueConstraint(
            "parse_id",
            "chunker_name",
            "chunker_version",
            "ordinal",
            name="parse_chunker_ordinal",
        ),
        schema="document_intelligence",
    )

    op.create_table(
        "document_embedding",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "chunk_id",
            sa.Uuid(),
            sa.ForeignKey(
                "document_intelligence.document_chunk.id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("embedding_provider", sa.Text(), nullable=False),
        sa.Column("embedding_model", sa.Text(), nullable=False),
        sa.Column("embedding_model_revision", sa.Text(), nullable=False),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            f"embedding_dimensions BETWEEN 1 AND {MAX_EMBEDDING_DIMENSIONS}",
            name="embedding_dimensions_supported",
        ),
        sa.CheckConstraint(
            "vector_dims(embedding) = embedding_dimensions",
            name="embedding_dimensions_match",
        ),
        sa.UniqueConstraint(
            "chunk_id",
            "embedding_provider",
            "embedding_model",
            "embedding_model_revision",
            "embedding_dimensions",
            name="chunk_embedding_identity",
        ),
        schema="document_intelligence",
    )


def grant_web_role_access() -> None:
    """Grant the public runtime only the reads and document writes it owns."""
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'newman_labs_web') THEN
                GRANT USAGE ON SCHEMA
                    analytics_houston_signal,
                    document_intelligence,
                    orchestration
                    TO newman_labs_web;
                GRANT SELECT ON orchestration.ingestion_run TO newman_labs_web;
                GRANT SELECT, INSERT
                    ON document_intelligence.document,
                       document_intelligence.document_parse
                    TO newman_labs_web;
                GRANT SELECT ON document_intelligence.document_chunk
                    TO newman_labs_web;
                GRANT SELECT ON ALL TABLES IN SCHEMA analytics_houston_signal
                    TO newman_labs_web;
                ALTER DEFAULT PRIVILEGES FOR ROLE neondb_owner
                    IN SCHEMA analytics_houston_signal
                    GRANT SELECT ON TABLES TO newman_labs_web;
            ELSIF current_database() !~ '_(test|verify)$' THEN
                RAISE EXCEPTION 'Required role newman_labs_web does not exist';
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    """Drop Alembic-owned schemas and dependent dbt views."""
    require_disposable_database(database_name=op.get_bind().engine.url.database)
    for schema in reversed(SCHEMAS):
        op.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
