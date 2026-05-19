"""users + civitas_ledger

MVP gamification schema. Two tables:
- users: username/password accounts (no email in v1, magic-link in v2)
- civitas_ledger: append-only Votes-currency ledger; balance = SUM(delta)

Revision ID: af21d38871f4
Revises: 17abb2617552
Create Date: 2026-05-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'af21d38871f4'
down_revision: Union[str, None] = '17abb2617552'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")  # gen_random_uuid()
    op.execute("CREATE EXTENSION IF NOT EXISTS citext;")    # case-insensitive username

    op.execute("""
        CREATE TABLE users (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            username          CITEXT UNIQUE NOT NULL,
            password_hash     TEXT NOT NULL,
            created_at        TIMESTAMPTZ DEFAULT NOW(),
            last_login_at     TIMESTAMPTZ,
            voter_id          UUID UNIQUE,
            total_votes_cast  INTEGER DEFAULT 0
        );
    """)
    op.execute("CREATE INDEX idx_users_username ON users(username);")

    op.execute("""
        CREATE TABLE civitas_ledger (
            id              BIGSERIAL PRIMARY KEY,
            user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            delta           NUMERIC(3,1) NOT NULL,
            reason          TEXT NOT NULL,
            source_bill_id  TEXT,
            awarded_at      TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    op.execute("CREATE INDEX idx_civitas_user_date ON civitas_ledger(user_id, awarded_at);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS civitas_ledger;")
    op.execute("DROP TABLE IF EXISTS users;")
