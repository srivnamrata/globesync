"""Enforce canonical project ownership for pipeline records.

Revision ID: 20260903_13
Revises: 20260903_12
Create Date: 2026-09-03
"""

from alembic import op


revision = "20260903_13"
down_revision = "20260903_12"
branch_labels = None
depends_on = None


PROJECT_SCOPED_TABLES = (
    "media_files",
    "transcripts",
    "translations",
    "generated_audios",
    "lipsync_jobs",
    "export_jobs",
)

PROJECT_REFERENCE_TABLES = PROJECT_SCOPED_TABLES + ("voice_profiles",)


def _assert_existing_scope_is_consistent() -> None:
    """Stop rather than silently altering historical ownership data."""
    connection = op.get_bind()
    for table_name in PROJECT_REFERENCE_TABLES:
        orphan_count = connection.exec_driver_sql(
            f"""
            SELECT count(*)
            FROM {table_name} AS child
            LEFT JOIN projects AS project ON project.id = child.project_id
            WHERE child.project_id IS NOT NULL AND project.id IS NULL
            """
        ).scalar_one()
        if orphan_count:
            raise RuntimeError(
                f"Cannot add {table_name}.project_id foreign key: "
                f"{orphan_count} row(s) reference a missing project. Repair the records first."
            )

    for table_name in PROJECT_SCOPED_TABLES:
        cross_workspace_count = connection.exec_driver_sql(
            f"""
            SELECT count(*)
            FROM {table_name} AS child
            JOIN projects AS project ON project.id = child.project_id
            WHERE child.workspace_id IS NOT NULL
              AND child.workspace_id IS DISTINCT FROM project.workspace_id
            """
        ).scalar_one()
        if cross_workspace_count:
            raise RuntimeError(
                f"Cannot add {table_name}.project_id foreign key: "
                f"{cross_workspace_count} row(s) have a project from another workspace. Repair the records first."
            )


def upgrade() -> None:
    _assert_existing_scope_is_consistent()
    for table_name in PROJECT_REFERENCE_TABLES:
        op.create_foreign_key(
            f"fk_{table_name}_project_id_projects",
            table_name,
            "projects",
            ["project_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    for table_name in reversed(PROJECT_REFERENCE_TABLES):
        op.drop_constraint(
            f"fk_{table_name}_project_id_projects",
            table_name,
            type_="foreignkey",
        )
