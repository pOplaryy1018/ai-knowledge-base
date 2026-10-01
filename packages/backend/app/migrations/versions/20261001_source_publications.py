"""Separate publication history from immutable revision content."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "20261001_source_publications"
down_revision = "20261001_asset_cleanup"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("source_publications",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("source_id", UUID(as_uuid=False), sa.ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("revision_id", UUID(as_uuid=False), sa.ForeignKey("source_revisions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("previous_publication_id", UUID(as_uuid=False), sa.ForeignKey("source_publications.id", ondelete="RESTRICT")),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source_id", "sequence", name="uq_source_publication_sequence"))
    op.create_index("ix_source_publications_source_id", "source_publications", ["source_id"])
    op.add_column("sources", sa.Column("current_publication_id", UUID(as_uuid=False)))
    op.create_foreign_key("fk_sources_current_publication", "sources", "source_publications", ["current_publication_id"], ["id"], ondelete="SET NULL")
    op.add_column("sources", sa.Column("config", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column("sources", sa.Column("last_sync_manifest", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column("source_revisions", sa.Column("commit", sa.String(64)))
    op.add_column("source_revisions", sa.Column("manifest", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column("source_change_events", sa.Column("publication_id", UUID(as_uuid=False)))
    # Server-side backfill works identically in online and offline migrations.
    # Preserve existing event IDs and evidence; only attach release identities.
    op.execute(sa.text("""
DO $$
DECLARE
    source_row record;
    event_row record;
    previous_id uuid;
    new_publication_id uuid;
    head_id uuid;
    release_sequence integer;
BEGIN
    FOR source_row IN SELECT id, current_revision_id FROM sources LOOP
        previous_id := NULL;
        head_id := NULL;
        release_sequence := 0;
        FOR event_row IN
            SELECT id, new_revision_id, created_at FROM source_change_events
            WHERE source_id = source_row.id ORDER BY created_at, id
        LOOP
            release_sequence := release_sequence + 1;
            new_publication_id := gen_random_uuid();
            INSERT INTO source_publications
                (id, source_id, revision_id, previous_publication_id, sequence, created_at, updated_at)
            VALUES (new_publication_id, source_row.id, event_row.new_revision_id,
                    previous_id, release_sequence, event_row.created_at, event_row.created_at);
            UPDATE source_change_events SET publication_id = new_publication_id
                WHERE id = event_row.id;
            previous_id := new_publication_id;
            IF event_row.new_revision_id = source_row.current_revision_id THEN
                head_id := new_publication_id;
            END IF;
        END LOOP;
        IF source_row.current_revision_id IS NOT NULL AND head_id IS NULL THEN
            head_id := gen_random_uuid();
            INSERT INTO source_publications
                (id, source_id, revision_id, previous_publication_id, sequence)
            VALUES (head_id, source_row.id, source_row.current_revision_id,
                    previous_id, release_sequence + 1);
        END IF;
        UPDATE sources SET current_publication_id = head_id WHERE id = source_row.id;
    END LOOP;
END $$;
"""))
    op.alter_column("source_change_events", "publication_id", nullable=False)
    op.create_foreign_key("fk_source_change_publication", "source_change_events", "source_publications", ["publication_id"], ["id"], ondelete="RESTRICT")
    op.drop_constraint("uq_source_change_revision", "source_change_events", type_="unique")
    op.create_unique_constraint("uq_source_change_publication", "source_change_events", ["publication_id"])

def downgrade() -> None:
    # Repeated revisions cannot fit the first-stage uniqueness contract. Refuse loss.
    op.execute(sa.text("""
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM source_change_events GROUP BY source_id, new_revision_id
               HAVING count(*) > 1) THEN
        RAISE EXCEPTION 'Cannot downgrade repeated publications without losing history';
    END IF;
END $$;
"""))
    op.drop_constraint("uq_source_change_publication", "source_change_events", type_="unique")
    op.create_unique_constraint("uq_source_change_revision", "source_change_events", ["source_id","new_revision_id"])
    op.drop_column("source_change_events", "publication_id")
    op.drop_column("sources", "current_publication_id")
    op.drop_column("sources", "config")
    op.drop_column("sources", "last_sync_manifest")
    op.drop_column("source_revisions", "commit")
    op.drop_column("source_revisions", "manifest")
    op.drop_table("source_publications")
