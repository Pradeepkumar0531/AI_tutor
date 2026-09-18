"""PDF embedded images: DocumentImage table with page provenance.

Revision ID: 0008_document_images
Revises: 0007_mastery_engine

- ``uq_materials_project_id`` / ``uq_documents_project_id``: anchors for the
  image composite FKs (same QuestionConcept pattern as 0006).
- ``document_images``: one row per embedded-raster page occurrence
  (id/document/material/project, 1-based page_number, page-local
  image_index, dimensions, mime, size, internal storage_key, sha256),
  composite FKs ``fk_docimg_document_in_project`` /
  ``fk_docimg_material_in_project`` (cross-project links impossible),
  ``uq_docimg_document_page_index`` deterministic identity,
  ``ix_docimg_document_page`` lookup index, sanity CHECKs.
- Binaries are content-addressed in storage (not in this migration);
  duplicate binaries share one object while each page keeps its row.

SQLite needs batch mode for ADD CONSTRAINT on existing tables; new-table
creation is plain on both dialects. Downgrade drops the table/constraints;
extracted binaries in storage are left for best-effort cleanup (never
referenced after the table is gone).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008_document_images"
down_revision: str | None = "0007_mastery_engine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.create_unique_constraint("uq_materials_project_id", "materials", ["project_id", "id"])
        op.create_unique_constraint("uq_documents_project_id", "documents", ["project_id", "id"])
    else:
        with op.batch_alter_table("materials") as batch:
            batch.create_unique_constraint("uq_materials_project_id", ["project_id", "id"])
        with op.batch_alter_table("documents") as batch:
            batch.create_unique_constraint("uq_documents_project_id", ["project_id", "id"])

    op.create_table(
        "document_images",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("material_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("image_index", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("mime_type", sa.String(length=64), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["project_id", "document_id"],
            ["documents.project_id", "documents.id"],
            ondelete="CASCADE",
            name="fk_docimg_document_in_project",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "material_id"],
            ["materials.project_id", "materials.id"],
            ondelete="CASCADE",
            name="fk_docimg_material_in_project",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id", "page_number", "image_index", name="uq_docimg_document_page_index"
        ),
        sa.CheckConstraint("page_number >= 1", name="ck_docimg_page"),
        sa.CheckConstraint("image_index >= 0", name="ck_docimg_index"),
        sa.CheckConstraint("width >= 1", name="ck_docimg_width"),
        sa.CheckConstraint("height >= 1", name="ck_docimg_height"),
        sa.CheckConstraint("file_size >= 0", name="ck_docimg_file_size"),
    )
    op.create_index("ix_docimg_document_page", "document_images", ["document_id", "page_number"])
    op.create_index("ix_document_images_project_id", "document_images", ["project_id"])
    op.create_index("ix_document_images_document_id", "document_images", ["document_id"])
    op.create_index("ix_document_images_material_id", "document_images", ["material_id"])
    op.create_index("ix_document_images_sha256", "document_images", ["sha256"])


def downgrade() -> None:
    op.drop_index("ix_document_images_sha256", table_name="document_images")
    op.drop_index("ix_document_images_material_id", table_name="document_images")
    op.drop_index("ix_document_images_document_id", table_name="document_images")
    op.drop_index("ix_document_images_project_id", table_name="document_images")
    op.drop_index("ix_docimg_document_page", table_name="document_images")
    op.drop_table("document_images")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_constraint("uq_documents_project_id", "documents", type_="unique")
        op.drop_constraint("uq_materials_project_id", "materials", type_="unique")
    else:
        with op.batch_alter_table("documents") as batch:
            batch.drop_constraint("uq_documents_project_id", type_="unique")
        with op.batch_alter_table("materials") as batch:
            batch.drop_constraint("uq_materials_project_id", type_="unique")
