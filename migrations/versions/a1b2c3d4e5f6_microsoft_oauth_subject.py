"""microsoft oauth subject identifier

Adds users.microsoft_sub (TEXT, UNIQUE, NULL) for Microsoft OIDC
sign-in (multi-tenant /common endpoint — covers both personal MSAs
and Azure AD work/school accounts). Mirrors google_sub / apple_sub
in f88fa0e69ea9.

Revision ID: a1b2c3d4e5f6
Revises: f88fa0e69ea9
Create Date: 2026-05-23
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f88fa0e69ea9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS microsoft_sub TEXT;")
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_microsoft_sub_unique
        ON users(microsoft_sub) WHERE microsoft_sub IS NOT NULL;
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_users_microsoft_sub_unique;")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS microsoft_sub;")
