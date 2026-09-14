"""initial persistence schema

Revision ID: 0001
Revises:
Create Date: 2026-01-01 00:00:00

Creates clinical_trial_protocols, patient_profiles, assessment_runs and
assessment_traces. Fully idempotent against a fresh database.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clinical_trial_protocols",
        sa.Column("trial_id", sa.String(length=64), nullable=False),
        sa.Column("protocol_metadata", sa.Text(), nullable=True),
        sa.Column("source_document", sa.String(length=512), nullable=True),
        sa.Column("source_page_count", sa.Integer(), nullable=True),
        sa.Column("criteria", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("trial_id"),
    )

    op.create_table(
        "patient_profiles",
        sa.Column("patient_profile_id", sa.String(length=128), nullable=False),
        sa.Column("profile_json", sa.Text(), nullable=True),
        sa.Column("source_type", sa.String(length=64), nullable=True),
        sa.Column("source_document", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("patient_profile_id"),
    )

    op.create_table(
        "assessment_runs",
        sa.Column("assessment_id", sa.String(length=36), nullable=False),
        sa.Column("trial_id", sa.String(length=64), nullable=False),
        sa.Column("patient_profile_id", sa.String(length=128), nullable=False),
        sa.Column("reference_date", sa.String(length=10), nullable=True),
        sa.Column("workflow_status", sa.String(length=24), nullable=False),
        sa.Column("final_decision", sa.String(length=24), nullable=True),
        sa.Column("current_step", sa.String(length=32), nullable=True),
        sa.Column("warnings_json", sa.Text(), nullable=True),
        sa.Column("errors_json", sa.Text(), nullable=True),
        sa.Column("snapshot_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("assessment_id"),
    )
    op.create_index("ix_assessment_runs_trial_id", "assessment_runs", ["trial_id"])
    op.create_index("ix_assessment_runs_patient_profile_id", "assessment_runs", ["patient_profile_id"])
    op.create_index("ix_assessment_runs_workflow_status", "assessment_runs", ["workflow_status"])

    op.create_table(
        "assessment_traces",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("assessment_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_assessment_traces_assessment_id", "assessment_traces", ["assessment_id"])


def downgrade() -> None:
    op.drop_index("ix_assessment_traces_assessment_id", table_name="assessment_traces")
    op.drop_table("assessment_traces")
    op.drop_index("ix_assessment_runs_workflow_status", table_name="assessment_runs")
    op.drop_index("ix_assessment_runs_patient_profile_id", table_name="assessment_runs")
    op.drop_index("ix_assessment_runs_trial_id", table_name="assessment_runs")
    op.drop_table("assessment_runs")
    op.drop_table("patient_profiles")
    op.drop_table("clinical_trial_protocols")