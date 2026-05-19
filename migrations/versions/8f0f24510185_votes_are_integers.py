"""votes are integers

Switch civitas_ledger.delta from NUMERIC(3,1) to INTEGER. Earlier draft
allowed 0.5 increments for "votes 4-5 worth half" but the UX confusion
of decimal Votes outweighed the value of the half-credit mechanic.
Simpler model: every awarded vote = 1 Vote, cap 5/day, beyond cap = 0.

Revision ID: 8f0f24510185
Revises: af21d38871f4
Create Date: 2026-05-19
"""
from typing import Sequence, Union

from alembic import op


revision: str = '8f0f24510185'
down_revision: Union[str, None] = 'af21d38871f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing rows: any 0.5 values would round to 0 — but no real
    # users exist yet (only the dev/test rows from my own testing),
    # so straight ALTER with floor is safe.
    op.execute("ALTER TABLE civitas_ledger ALTER COLUMN delta TYPE INTEGER USING floor(delta)::INTEGER;")


def downgrade() -> None:
    op.execute("ALTER TABLE civitas_ledger ALTER COLUMN delta TYPE NUMERIC(3,1);")
