"""strengthen_home_booking_constraint_and_snapshot_integrity

Revision ID: 44cef7a277a7
Revises: 7f6eb611e707
Create Date: 2026-09-12 21:08:09.149150

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '44cef7a277a7'
down_revision = '7f6eb611e707'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Update check constraint on bookings for HOME branch_id is NULL
    op.drop_constraint('ck_bookings_branch_for_branch_visit', 'bookings', type_='check')
    op.create_check_constraint(
        'ck_bookings_branch_for_branch_visit',
        'bookings',
        "(visit_type = 'BRANCH' AND branch_id IS NOT NULL) OR (visit_type = 'HOME' AND branch_id IS NULL)",
    )

    # 2. Database trigger enforcing conversation_sessions.active_snapshot_id belongs to the same session
    op.execute("""
    CREATE OR REPLACE FUNCTION conversation_sessions_snapshot_integrity_trigger() RETURNS trigger AS $$
    BEGIN
        IF NEW.active_snapshot_id IS NOT NULL THEN
            IF NOT EXISTS (
                SELECT 1 FROM search_snapshots
                WHERE id = NEW.active_snapshot_id AND session_id = NEW.session_id
            ) THEN
                RAISE EXCEPTION 'Cross-session snapshot assignment rejected: snapshot % does not belong to session %',
                    NEW.active_snapshot_id, NEW.session_id;
            END IF;
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    CREATE TRIGGER trg_conversation_sessions_snapshot_integrity
    BEFORE INSERT OR UPDATE OF active_snapshot_id, session_id ON conversation_sessions
    FOR EACH ROW EXECUTE FUNCTION conversation_sessions_snapshot_integrity_trigger();
    """)


def downgrade():
    # 1. Drop trigger and function
    op.execute("""
    DROP TRIGGER IF EXISTS trg_conversation_sessions_snapshot_integrity ON conversation_sessions;
    DROP FUNCTION IF EXISTS conversation_sessions_snapshot_integrity_trigger();
    """)

    # 2. Revert check constraint on bookings
    op.drop_constraint('ck_bookings_branch_for_branch_visit', 'bookings', type_='check')
    op.create_check_constraint(
        'ck_bookings_branch_for_branch_visit',
        'bookings',
        "(visit_type = 'BRANCH' AND branch_id IS NOT NULL) OR (visit_type = 'HOME')",
    )
