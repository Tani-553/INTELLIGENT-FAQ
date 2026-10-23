"""Small SQLite-backed authentication store for CityCare's local workspaces."""
import os
import sqlite3
from datetime import datetime, timezone

from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USER_DB_PATH = os.environ.get("CITYCARE_USER_DB", os.path.join(BASE_DIR, "citycare_users.db"))
ROLES = ("admin",)


def _connect():
    connection = sqlite3.connect(USER_DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db(legacy_username=None, legacy_password=None):
    """Create the account store and optionally retain the old local demo admin."""
    db = _connect()
    try:
        db.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin')),
            created_at TEXT NOT NULL
        )""")
        if legacy_username and legacy_password:
            found = db.execute("SELECT id FROM users WHERE username = ?", (legacy_username,)).fetchone()
            if not found:
                db.execute("INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
                           (legacy_username, generate_password_hash(legacy_password), "admin", now()))
        db.commit()
    finally:
        db.close()


def now():
    return datetime.now(timezone.utc).isoformat()


def authenticate(username, password):
    if not isinstance(username, str) or not isinstance(password, str):
        return None
    db = _connect()
    try:
        account = db.execute("SELECT id, username, password_hash, role FROM users WHERE username = ?", (username.strip(),)).fetchone()
    finally:
        db.close()
    if not account or not check_password_hash(account["password_hash"], password):
        return None
    return {"id": account["id"], "username": account["username"], "role": account["role"]}


def create_user(username, password, role):
    """Provision accounts from an administrator-controlled process, never public registration."""
    username = (username or "").strip()
    if not username or len(username) > 80 or not username.replace("_", "").replace(".", "").isalnum():
        raise ValueError("Username must contain letters, numbers, dots, or underscores.")
    if role not in ROLES:
        raise ValueError("Unknown role.")
    if not isinstance(password, str) or len(password) < 12:
        raise ValueError("Password must be at least 12 characters.")
    try:
        db = _connect()
        try:
            db.execute("INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
                       (username, generate_password_hash(password), role, now()))
            db.commit()
        finally:
            db.close()
    except sqlite3.IntegrityError as error:
        raise ValueError("Username is already in use.") from error


def list_users():
    db = _connect()
    try:
        return [dict(row) for row in db.execute("SELECT id, username, role, created_at FROM users ORDER BY username")]
    finally:
        db.close()
