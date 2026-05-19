"""baseline existing schema

This is the soft-baseline migration. It is INTENTIONALLY a no-op.

Background:
    Alembic is being adopted into an existing project with three Postgres
    instances (prod, staging, local) that already have populated `bills`,
    `votes`, and `rep_contact_forms` tables created by
    src.database.connection.init_db_tables(). The schema was assembled
    over ~15 ad-hoc scripts/add_*.py one-shots.

How to consume:
    On each environment, run `alembic stamp 17abb2617552` exactly once.
    That marks the DB as already at this revision without executing any
    SQL. From that point forward, all schema changes are written as new
    Alembic revisions with real op.execute() / op.create_table() bodies.

Why no-op:
    Re-running the full DDL would either fail (tables already exist) or
    require CREATE TABLE IF NOT EXISTS which doesn't catch schema drift.
    The "soft baseline" pattern is standard for Alembic adoption into
    legacy projects — the alembic_version table starts populated and the
    DDL truth lives in init_db_tables() until init_db_tables() is
    eventually deleted (post the next 3-4 forward migrations).

Future migrations:
    Anything that adds a column, creates a table, or changes an index
    after 2026-05-19 goes through a new Alembic revision. The
    `users`, `magic_links`, `civitas_ledger` tables for the upcoming
    gamification feature will be the first real DDL migration on top
    of this baseline.

Revision ID: 17abb2617552
Revises:
Create Date: 2026-05-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '17abb2617552'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Soft baseline — no-op. Existing schema is the source of truth."""
    pass


def downgrade() -> None:
    """No downgrade — this is the root migration."""
    pass
