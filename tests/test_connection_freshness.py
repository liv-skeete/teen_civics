"""Regression tests for the connection-pool freshness optimization.

Background: postgres_connect() used to call _validate_connection() on
every checkout, adding 3 round-trips (~150ms on Railway's cross-region
proxy) to every request. We now skip validation when the connection
was returned to the pool within _VALIDATION_FRESHNESS_WINDOW seconds.

These tests pin the contract so a future "be safer, validate always"
refactor can't silently kill p50 latency again.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from src.database import connection as conn_mod


@pytest.fixture(autouse=True)
def clear_freshness_state():
    """Reset the freshness dict between tests so they don't see each
    other's stamps."""
    with conn_mod._conn_last_used_lock:
        conn_mod._conn_last_used.clear()
    yield
    with conn_mod._conn_last_used_lock:
        conn_mod._conn_last_used.clear()


def test_unstamped_connection_is_not_fresh():
    """A brand-new connection with no last_used record must be treated
    as stale — we have to validate it."""
    conn = MagicMock()
    assert conn_mod._conn_is_fresh(conn) is False


def test_just_stamped_is_fresh():
    """A connection stamped this instant is fresh; the optimization
    short-circuits validation on its next checkout."""
    conn = MagicMock()
    conn_mod._stamp_last_used(conn)
    assert conn_mod._conn_is_fresh(conn) is True


def test_outside_window_is_not_fresh():
    """After more than _VALIDATION_FRESHNESS_WINDOW seconds elapsed,
    the connection must be revalidated. Tested by directly mutating
    the timestamp rather than sleeping for 60s."""
    conn = MagicMock()
    conn_mod._stamp_last_used(conn)
    # Pretend it was stamped just past the freshness window.
    with conn_mod._conn_last_used_lock:
        conn_mod._conn_last_used[id(conn)] = (
            time.monotonic() - conn_mod._VALIDATION_FRESHNESS_WINDOW - 1
        )
    assert conn_mod._conn_is_fresh(conn) is False


def test_forget_clears_record():
    """When a connection is closed/discarded we must drop its
    freshness record so the dict can't grow unbounded as the pool
    rotates."""
    conn = MagicMock()
    conn_mod._stamp_last_used(conn)
    assert len(conn_mod._conn_last_used) == 1

    conn_mod._forget_conn(conn)
    assert len(conn_mod._conn_last_used) == 0
    assert conn_mod._conn_is_fresh(conn) is False


def test_stamp_and_forget_handle_none():
    """None must be silently no-op; helpers are called from release
    paths where conn can be None."""
    conn_mod._stamp_last_used(None)
    conn_mod._forget_conn(None)
    assert conn_mod._conn_is_fresh(None) is False


def test_freshness_window_is_positive():
    """A negative or zero window would defeat the whole point and was
    a tempting wrong constant during development."""
    assert conn_mod._VALIDATION_FRESHNESS_WINDOW > 0
