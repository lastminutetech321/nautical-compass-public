"""
db_config.py — Nautical Compass database configuration layer.

This module is the single source of truth for how the application connects
to its database.  It reads the DATABASE_URL environment variable and returns
the appropriate connection depending on the backend in use.

Supported backends
------------------
* SQLite  (default, no env var required)
  - Used automatically when DATABASE_URL is unset or starts with "sqlite"
  - Preserves all existing behaviour with zero code changes in main.py
* PostgreSQL
  - Activated by setting DATABASE_URL to a valid postgres:// or
    postgresql:// connection string
  - Requires psycopg2-binary (already in requirements.txt)

Environment variables
---------------------
DATABASE_URL
    Full connection string.  Examples:
      sqlite:///./nautical_compass.db          ← SQLite (default)
      postgresql://user:pass@host:5432/dbname  ← Postgres

DB_BACKEND
    Read-only diagnostic key set by this module.  Do NOT set it manually.
    Possible values: "sqlite" | "postgres"

Usage
-----
    from db_config import get_db_connection, DB_BACKEND

    with get_db_connection() as conn:
        conn.execute("SELECT 1")

    # Check which backend is active (useful for logging / health endpoint)
    print(DB_BACKEND)   # "sqlite" or "postgres"

Migration notes
---------------
* SQLite fallback is ALWAYS preserved.  Postgres is only activated when
  DATABASE_URL is explicitly set to a postgres:// URI.
* This module does NOT remove or alter any existing sqlite3 calls in
  main.py.  Those calls will be refactored in a later migration phase
  once the Postgres path is verified end-to-end.
* The get_db_connection() helper is provided so future callers can be
  migrated incrementally, one function at a time.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

# ---------------------------------------------------------------------------
# Backend detection
# ---------------------------------------------------------------------------

_DATABASE_URL: str = os.getenv("DATABASE_URL", "").strip()

# Determine active backend from the URL prefix.
# If DATABASE_URL is empty or starts with "sqlite", fall back to SQLite.
if _DATABASE_URL.startswith("postgres://") or _DATABASE_URL.startswith("postgresql://"):
    DB_BACKEND: str = "postgres"
else:
    DB_BACKEND = "sqlite"

# ---------------------------------------------------------------------------
# SQLite helpers (unchanged from original main.py logic)
# ---------------------------------------------------------------------------

_SQLITE_PATH: Path = Path(
    os.getenv("SQLITE_DB_PATH", "nautical_compass.db")
)


def _sqlite_connection() -> sqlite3.Connection:
    """Return a raw sqlite3 connection with Row factory enabled."""
    conn = sqlite3.connect(_SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Postgres helpers
# ---------------------------------------------------------------------------

def _postgres_connection():
    """Return a raw psycopg2 connection.

    psycopg2 is imported lazily so that the module can still be loaded in
    SQLite-only environments where psycopg2 is not installed.
    """
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError as exc:
        raise RuntimeError(
            "psycopg2-binary is required for Postgres connections.  "
            "Install it with: pip install psycopg2-binary"
        ) from exc

    conn = psycopg2.connect(_DATABASE_URL)
    # Use DictCursor so rows behave like dicts (similar to sqlite3.Row)
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    return conn


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@contextmanager
def get_db_connection() -> Generator:
    """Context manager that yields an open database connection.

    The connection is committed and closed automatically on exit.
    On error the transaction is rolled back before re-raising.

    Example::

        from db_config import get_db_connection

        with get_db_connection() as conn:
            conn.execute("SELECT 1")
    """
    if DB_BACKEND == "postgres":
        conn = _postgres_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        # SQLite — mirrors the original `with db_conn() as conn:` pattern
        conn = _sqlite_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def get_db_backend() -> str:
    """Return the active backend identifier: 'sqlite' or 'postgres'."""
    return DB_BACKEND


def get_database_url() -> str:
    """Return the effective DATABASE_URL (redacted password for logging)."""
    if not _DATABASE_URL:
        return f"sqlite:///{_SQLITE_PATH}"
    # Redact password from URL before returning for safe logging
    try:
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(_DATABASE_URL)
        if parsed.password:
            safe = parsed._replace(
                netloc=f"{parsed.username}:***@{parsed.hostname}"
                + (f":{parsed.port}" if parsed.port else "")
            )
            return urlunparse(safe)
    except Exception:
        pass
    return _DATABASE_URL
\\\\\\\\\\
