"""email + oauth subject identifiers

Adds the columns needed for email verification and third-party sign-in:
- users.email (CITEXT, UNIQUE, NULL) — required by verification flow,
  nullable so existing username-only accounts keep working until they
  add one.
- users.email_verified_at (TIMESTAMPTZ, NULL) — set when the user
  follows the verification link from their inbox.
- users.google_sub (TEXT, UNIQUE, NULL) — Google OIDC subject identifier.
- users.apple_sub  (TEXT, UNIQUE, NULL) — Apple OIDC subject identifier
  (column reserved now even though wiring is deferred to staging).

Revision ID: f88fa0e69ea9
Revises: 8f0f24510185
Create Date: 2026-05-22
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'f88fa0e69ea9'
down_revision: Union[str, None] = '8f0f24510185'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS email CITEXT;")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMPTZ;")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS google_sub TEXT;")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS apple_sub TEXT;")

    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_unique
        ON users(email) WHERE email IS NOT NULL;
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_sub_unique
        ON users(google_sub) WHERE google_sub IS NOT NULL;
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_apple_sub_unique
        ON users(apple_sub) WHERE apple_sub IS NOT NULL;
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_users_apple_sub_unique;")
    op.execute("DROP INDEX IF EXISTS idx_users_google_sub_unique;")
    op.execute("DROP INDEX IF EXISTS idx_users_email_unique;")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS apple_sub;")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS google_sub;")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS email_verified_at;")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS email;")
