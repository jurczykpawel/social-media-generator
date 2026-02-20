"""
SQLite database — users, magic links, credit log.
Zero ORM, just stdlib sqlite3.
"""

import sqlite3
import uuid
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / 'data' / 'app.db'


def get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_db()
    conn.executescript("""
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
    """)
    conn.close()


# --- Users ---

def get_user_by_token(api_token: str) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE api_token = ?", (api_token,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id: str) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_email(email: str) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_user(email: str, credits: int = 0) -> dict:
    user_id = str(uuid.uuid4())
    api_token = secrets.token_urlsafe(32)
    conn = get_db()
    conn.execute(
        "INSERT INTO users (id, email, credits, api_token) VALUES (?, ?, ?, ?)",
        (user_id, email, credits, api_token),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row)


def regenerate_token(user_id: str) -> str:
    new_token = secrets.token_urlsafe(32)
    conn = get_db()
    conn.execute("UPDATE users SET api_token = ? WHERE id = ?", (new_token, user_id))
    conn.commit()
    conn.close()
    return new_token


def update_last_login(user_id: str):
    conn = get_db()
    conn.execute(
        "UPDATE users SET last_login = datetime('now') WHERE id = ?", (user_id,)
    )
    conn.commit()
    conn.close()


# --- Credits ---

def add_credits(user_id: str, amount: int, reason: str):
    conn = get_db()
    conn.execute("UPDATE users SET credits = credits + ? WHERE id = ?", (amount, user_id))
    conn.execute(
        "INSERT INTO credit_log (user_id, delta, reason) VALUES (?, ?, ?)",
        (user_id, amount, reason),
    )
    conn.commit()
    conn.close()


def deduct_credits(user_id: str, amount: int, reason: str) -> bool:
    """Deduct credits atomically. Returns False if insufficient."""
    conn = get_db()
    cursor = conn.execute(
        "UPDATE users SET credits = credits - ? WHERE id = ? AND credits >= ?",
        (amount, user_id, amount),
    )
    if cursor.rowcount == 0:
        conn.close()
        return False
    conn.execute(
        "INSERT INTO credit_log (user_id, delta, reason) VALUES (?, ?, ?)",
        (user_id, -amount, reason),
    )
    conn.commit()
    conn.close()
    return True


def get_credit_log(user_id: str, limit: int = 50) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM credit_log WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --- Magic Links ---

def create_magic_link(email: str) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
    conn = get_db()
    conn.execute(
        "INSERT INTO magic_links (token, email, expires_at) VALUES (?, ?, ?)",
        (token, email, expires_at),
    )
    conn.commit()
    conn.close()
    return token


def verify_magic_link(token: str) -> str | None:
    """Verify and consume magic link. Returns email or None."""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM magic_links WHERE token = ? AND used = 0", (token,)
    ).fetchone()

    if not row:
        conn.close()
        return None

    expires = datetime.fromisoformat(row['expires_at'])
    now = datetime.now(timezone.utc)
    if now > expires:
        conn.close()
        return None

    conn.execute("UPDATE magic_links SET used = 1 WHERE token = ?", (token,))
    conn.commit()
    conn.close()
    return row['email']


def cleanup_expired_links():
    """Remove old magic links."""
    conn = get_db()
    conn.execute("DELETE FROM magic_links WHERE used = 1 OR expires_at < datetime('now')")
    conn.commit()
    conn.close()
