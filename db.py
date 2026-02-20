"""
Database layer — supports SQLite (dev) and PostgreSQL (prod).

Backend auto-detected from DATABASE_URL env var:
    postgresql://user:pass@host/dbname  → PostgreSQL (psycopg2)
    sqlite:///path/to/app.db            → SQLite
    (empty)                             → SQLite at data/app.db
"""

import os
import uuid
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATABASE_URL = os.environ.get('DATABASE_URL', '')

# --- Backend detection ---

def _is_postgres() -> bool:
    return DATABASE_URL.startswith('postgresql')


def _get_conn():
    """Get a database connection with dict-like rows."""
    if _is_postgres():
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        return conn
    else:
        import sqlite3
        path = DATABASE_URL.replace('sqlite:///', '') if DATABASE_URL.startswith('sqlite') else ''
        if not path:
            path = str(Path(__file__).parent / 'data' / 'app.db')
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn


def _q(sql: str) -> str:
    """Convert %s placeholders to ? for SQLite."""
    if _is_postgres():
        return sql
    return sql.replace('%s', '?')


def _fetchone(conn, sql: str, params=()) -> dict | None:
    if _is_postgres():
        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        row = cur.fetchone()
        cur.close()
        return dict(row) if row else None
    else:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None


def _fetchall(conn, sql: str, params=()) -> list[dict]:
    if _is_postgres():
        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        rows = cur.fetchall()
        cur.close()
        return [dict(r) for r in rows]
    else:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def _execute(conn, sql: str, params=()) -> int:
    """Execute and return rowcount."""
    if _is_postgres():
        cur = conn.cursor()
        cur.execute(sql, params)
        rc = cur.rowcount
        cur.close()
        return rc
    else:
        cursor = conn.execute(sql, params)
        return cursor.rowcount


# --- Schema ---

_SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS users (
    id          TEXT PRIMARY KEY,
    email       TEXT UNIQUE NOT NULL,
    credits     INTEGER NOT NULL DEFAULT 0,
    api_token   TEXT UNIQUE NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    last_login  TEXT
);
CREATE TABLE IF NOT EXISTS magic_links (
    token       TEXT PRIMARY KEY,
    email       TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    used        INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS credit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL REFERENCES users(id),
    delta       INTEGER NOT NULL,
    reason      TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

_SCHEMA_POSTGRES = """
CREATE TABLE IF NOT EXISTS users (
    id          TEXT PRIMARY KEY,
    email       TEXT UNIQUE NOT NULL,
    credits     INTEGER NOT NULL DEFAULT 0,
    api_token   TEXT UNIQUE NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login  TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS magic_links (
    token       TEXT PRIMARY KEY,
    email       TEXT NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL,
    used        INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS credit_log (
    id          SERIAL PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id),
    delta       INTEGER NOT NULL,
    reason      TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


def init_db():
    """Create tables if they don't exist."""
    conn = _get_conn()
    if _is_postgres():
        cur = conn.cursor()
        cur.execute(_SCHEMA_POSTGRES)
        cur.close()
    else:
        conn.executescript(_SCHEMA_SQLITE)
    conn.commit()
    conn.close()


# --- Users ---

def get_user(user_id: str) -> dict | None:
    conn = _get_conn()
    row = _fetchone(conn, _q("SELECT * FROM users WHERE id = %s"), (user_id,))
    conn.close()
    return row


def get_user_by_token(api_token: str) -> dict | None:
    conn = _get_conn()
    row = _fetchone(conn, _q("SELECT * FROM users WHERE api_token = %s"), (api_token,))
    conn.close()
    return row


def get_user_by_id(user_id: str) -> dict | None:
    return get_user(user_id)


def get_user_by_email(email: str) -> dict | None:
    conn = _get_conn()
    row = _fetchone(conn, _q("SELECT * FROM users WHERE email = %s"), (email,))
    conn.close()
    return row


def create_user(email: str, credits: int = 0) -> dict:
    user_id = str(uuid.uuid4())
    api_token = secrets.token_urlsafe(32)
    conn = _get_conn()
    _execute(conn, _q(
        "INSERT INTO users (id, email, credits, api_token) VALUES (%s, %s, %s, %s)"
    ), (user_id, email, credits, api_token))
    conn.commit()
    row = _fetchone(conn, _q("SELECT * FROM users WHERE id = %s"), (user_id,))
    conn.close()
    return row


def regenerate_token(user_id: str) -> str:
    new_token = secrets.token_urlsafe(32)
    conn = _get_conn()
    _execute(conn, _q("UPDATE users SET api_token = %s WHERE id = %s"), (new_token, user_id))
    conn.commit()
    conn.close()
    return new_token


def update_last_login(user_id: str):
    conn = _get_conn()
    now = datetime.now(timezone.utc).isoformat()
    _execute(conn, _q("UPDATE users SET last_login = %s WHERE id = %s"), (now, user_id))
    conn.commit()
    conn.close()


# --- Credits ---

def add_credits(user_id: str, amount: int, reason: str):
    conn = _get_conn()
    _execute(conn, _q("UPDATE users SET credits = credits + %s WHERE id = %s"), (amount, user_id))
    _execute(conn, _q(
        "INSERT INTO credit_log (user_id, delta, reason) VALUES (%s, %s, %s)"
    ), (user_id, amount, reason))
    conn.commit()
    conn.close()


def deduct_credits(user_id: str, amount: int, reason: str) -> bool:
    """Deduct credits atomically. Returns False if insufficient."""
    conn = _get_conn()
    rc = _execute(conn, _q(
        "UPDATE users SET credits = credits - %s WHERE id = %s AND credits >= %s"
    ), (amount, user_id, amount))
    if rc == 0:
        conn.rollback()
        conn.close()
        return False
    _execute(conn, _q(
        "INSERT INTO credit_log (user_id, delta, reason) VALUES (%s, %s, %s)"
    ), (user_id, -amount, reason))
    conn.commit()
    conn.close()
    return True


def get_credit_log(user_id: str, limit: int = 50) -> list[dict]:
    conn = _get_conn()
    rows = _fetchall(conn, _q(
        "SELECT * FROM credit_log WHERE user_id = %s ORDER BY created_at DESC LIMIT %s"
    ), (user_id, limit))
    conn.close()
    return rows


# --- Magic Links ---

def create_magic_link(email: str) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
    conn = _get_conn()
    _execute(conn, _q(
        "INSERT INTO magic_links (token, email, expires_at) VALUES (%s, %s, %s)"
    ), (token, email, expires_at))
    conn.commit()
    conn.close()
    return token


def verify_magic_link(token: str) -> str | None:
    """Verify and consume magic link. Returns email or None."""
    conn = _get_conn()
    row = _fetchone(conn, _q(
        "SELECT * FROM magic_links WHERE token = %s AND used = 0"
    ), (token,))

    if not row:
        conn.close()
        return None

    expires = datetime.fromisoformat(str(row['expires_at']))
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires:
        conn.close()
        return None

    _execute(conn, _q("UPDATE magic_links SET used = 1 WHERE token = %s"), (token,))
    conn.commit()
    conn.close()
    return row['email']


def cleanup_expired_links():
    """Remove old magic links."""
    conn = _get_conn()
    now = datetime.now(timezone.utc).isoformat()
    _execute(conn, _q("DELETE FROM magic_links WHERE used = 1 OR expires_at < %s"), (now,))
    conn.commit()
    conn.close()
