"""Long-term database and auth substrate for Genesis.

JSON remains the runtime source of truth for full organism bodies and decision
graph traversal. This module owns the durable control plane: users, sessions,
audit events, and queryable mirrors of organisms/decisions. It supports local
SQLite for development and Postgres/Supabase for hosted production.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from backend.shared.config import settings

_CONN: Any | None = None
_CONN_KEY = ""
_ENGINE = ""


TABLES = ["users", "sessions", "organism_records", "decision_records", "audit_events"]


def _now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _database_engine(url: str | None = None) -> str:
    value = url or settings.DATABASE_URL
    if value in {":memory:", "sqlite:///:memory:", "sqlite+aiosqlite:///:memory:"}:
        return "sqlite"
    if value.startswith(("sqlite:///", "sqlite+aiosqlite:///")):
        return "sqlite"
    if value.startswith(("postgres://", "postgresql://", "postgresql+psycopg://")):
        return "postgres"
    raise RuntimeError("DATABASE_URL must be sqlite:///..., sqlite+aiosqlite:///..., postgres://..., or postgresql://...")


def _database_path() -> Path:
    url = settings.DATABASE_URL
    if url in {":memory:", "sqlite:///:memory:", "sqlite+aiosqlite:///:memory:"}:
        return Path(":memory:")
    if url.startswith("sqlite+aiosqlite:///"):
        return Path(url.removeprefix("sqlite+aiosqlite:///")).resolve()
    if url.startswith("sqlite:///"):
        return Path(url.removeprefix("sqlite:///")).resolve()
    raise RuntimeError("DATABASE_URL is not a SQLite URL")


def _redacted_database_url(url: str | None = None) -> str:
    value = url or settings.DATABASE_URL
    if _database_engine(value) != "postgres":
        return value
    parsed = urlparse(value.replace("postgres://", "postgresql://", 1))
    if not parsed.password:
        return value
    netloc = parsed.hostname or ""
    if parsed.username:
        netloc = f"{parsed.username}:***@{netloc}"
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    return urlunparse(parsed._replace(netloc=netloc))


def _postgres_url() -> str:
    url = settings.DATABASE_URL
    if url.startswith("postgres://"):
        return "postgresql://" + url.removeprefix("postgres://")
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url.removeprefix("postgresql+psycopg://")
    return url


def _sql(sql: str) -> str:
    return sql.replace("?", "%s") if _ENGINE == "postgres" else sql


def _as_dict(row: Any) -> dict:
    return dict(row or {})


def _first_value(row: Any) -> Any:
    if isinstance(row, dict):
        return next(iter(row.values()))
    return row[0]


def _json_value(value: dict) -> Any:
    if _ENGINE == "postgres":
        from psycopg.types.json import Jsonb
        return Jsonb(value)
    return json.dumps(value, sort_keys=True)


def _json_payload(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _connect() -> Any:
    global _CONN, _CONN_KEY, _ENGINE
    engine = _database_engine()
    key = settings.DATABASE_URL
    if _CONN is not None and _CONN_KEY == key:
        return _CONN
    if _CONN is not None:
        _CONN.close()
    _ENGINE = engine
    if engine == "sqlite":
        path = _database_path()
        sqlite_key = str(path)
        if sqlite_key != ":memory:":
            path.parent.mkdir(parents=True, exist_ok=True)
        _CONN = sqlite3.connect(sqlite_key, check_same_thread=False)
        _CONN.row_factory = sqlite3.Row
        _CONN.execute("PRAGMA journal_mode=WAL")
        _CONN.execute("PRAGMA foreign_keys=ON")
    else:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except Exception as exc:  # pragma: no cover - depends on deployment packaging
            raise RuntimeError("psycopg is required for Postgres/Supabase DATABASE_URL values") from exc
        _CONN = psycopg.connect(_postgres_url(), row_factory=dict_row, connect_timeout=10)
    _CONN_KEY = key
    _create_schema(_CONN)
    return _CONN


def _create_schema(conn: Any) -> None:
    if _ENGINE == "postgres":
        statements = [
            """
            CREATE TABLE IF NOT EXISTS users (
              id TEXT PRIMARY KEY,
              username TEXT UNIQUE NOT NULL,
              display_name TEXT NOT NULL,
              password_hash TEXT NOT NULL,
              role TEXT NOT NULL DEFAULT 'operator',
              created_at TEXT NOT NULL,
              last_login_at TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS sessions (
              id TEXT PRIMARY KEY,
              user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              token_hash TEXT UNIQUE NOT NULL,
              created_at TEXT NOT NULL,
              expires_at TEXT NOT NULL,
              revoked_at TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS organism_records (
              id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              state TEXT NOT NULL,
              goal TEXT NOT NULL,
              born_at TEXT,
              updated_at TEXT NOT NULL,
              payload_json JSONB NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS decision_records (
              id TEXT PRIMARY KEY,
              organism_id TEXT NOT NULL,
              timestamp TEXT,
              action_name TEXT,
              is_dream INTEGER NOT NULL DEFAULT 0,
              payload_json JSONB NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS audit_events (
              id TEXT PRIMARY KEY,
              actor TEXT NOT NULL,
              action TEXT NOT NULL,
              target TEXT NOT NULL,
              status TEXT NOT NULL,
              created_at TEXT NOT NULL,
              payload_json JSONB NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_sessions_token_hash ON sessions(token_hash)",
            "CREATE INDEX IF NOT EXISTS idx_sessions_active ON sessions(expires_at, revoked_at)",
            "CREATE INDEX IF NOT EXISTS idx_decision_records_organism ON decision_records(organism_id)",
            "CREATE INDEX IF NOT EXISTS idx_audit_events_created_at ON audit_events(created_at)",
        ]
        for statement in statements:
            conn.execute(statement)
        conn.commit()
        return

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
          id TEXT PRIMARY KEY,
          username TEXT UNIQUE NOT NULL,
          display_name TEXT NOT NULL,
          password_hash TEXT NOT NULL,
          role TEXT NOT NULL DEFAULT 'operator',
          created_at TEXT NOT NULL,
          last_login_at TEXT
        );

        CREATE TABLE IF NOT EXISTS sessions (
          id TEXT PRIMARY KEY,
          user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          token_hash TEXT UNIQUE NOT NULL,
          created_at TEXT NOT NULL,
          expires_at TEXT NOT NULL,
          revoked_at TEXT
        );

        CREATE TABLE IF NOT EXISTS organism_records (
          id TEXT PRIMARY KEY,
          name TEXT NOT NULL,
          state TEXT NOT NULL,
          goal TEXT NOT NULL,
          born_at TEXT,
          updated_at TEXT NOT NULL,
          payload_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS decision_records (
          id TEXT PRIMARY KEY,
          organism_id TEXT NOT NULL,
          timestamp TEXT,
          action_name TEXT,
          is_dream INTEGER NOT NULL DEFAULT 0,
          payload_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_events (
          id TEXT PRIMARY KEY,
          actor TEXT NOT NULL,
          action TEXT NOT NULL,
          target TEXT NOT NULL,
          status TEXT NOT NULL,
          created_at TEXT NOT NULL,
          payload_json TEXT NOT NULL
        );
        """
    )
    conn.commit()


def init() -> dict:
    _create_schema(_connect())
    return status()


def _row_count(table: str) -> int:
    conn = _connect()
    return int(_first_value(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()))


def status() -> dict:
    engine = _database_engine()
    try:
        conn = _connect()
        tables = {name: _row_count(name) for name in TABLES}
        database = {
            "engine": engine,
            "url": _redacted_database_url(),
            "connected": True,
            "tables": tables,
        }
        if engine == "sqlite":
            database["path"] = str(_database_path())
            database["journal_mode"] = _first_value(conn.execute("PRAGMA journal_mode").fetchone())
        else:
            database["host"] = urlparse(_postgres_url()).hostname or ""
            database["provider"] = "supabase" if "supabase" in (database["host"] or "").lower() else "postgres"
        return {
            "version": "organism-long-term-db-auth-v2",
            "database": database,
            "auth": {
                "mode": "session_or_static_token",
                "api_token_required": settings.GENESIS_REQUIRE_API_TOKEN,
                "static_token_configured": bool(settings.GENESIS_API_TOKEN),
                "users": tables["users"],
                "active_sessions": active_session_count(),
            },
            "readiness": "ready",
            "updated_at": _now(),
        }
    except Exception as exc:
        return {
            "version": "organism-long-term-db-auth-v2",
            "database": {"engine": engine, "url": _redacted_database_url(), "connected": False},
            "auth": {"mode": "session_or_static_token", "api_token_required": settings.GENESIS_REQUIRE_API_TOKEN},
            "readiness": "needs_attention",
            "error": str(exc),
            "updated_at": _now(),
        }


def _hash_password(password: str, *, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 210_000)
    return "pbkdf2_sha256$210000$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def _verify_password(password: str, stored: str) -> bool:
    try:
        algo, rounds, salt_b64, digest_b64 = stored.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64.encode())
        expected = base64.b64decode(digest_b64.encode())
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(rounds))
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def bootstrap_user(username: str, password: str, display_name: str = "", role: str = "owner") -> dict:
    username = username.strip().lower()
    if len(username) < 3:
        raise ValueError("username must be at least 3 characters")
    if len(password) < 10:
        raise ValueError("password must be at least 10 characters")
    conn = _connect()
    if _row_count("users") > 0:
        raise ValueError("bootstrap is closed because a user already exists")
    user = {
        "id": "usr_" + secrets.token_hex(8),
        "username": username,
        "display_name": display_name.strip() or username,
        "password_hash": _hash_password(password),
        "role": role,
        "created_at": _now(),
    }
    conn.execute(
        _sql("INSERT INTO users (id, username, display_name, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?, ?)"),
        (user["id"], user["username"], user["display_name"], user["password_hash"], user["role"], user["created_at"]),
    )
    conn.commit()
    write_audit(actor=user["id"], action="auth.bootstrap", target=user["id"], status="ok", payload={"username": username})
    return _public_user(user)


def login(username: str, password: str, ttl_hours: int = 24) -> dict | None:
    conn = _connect()
    row = conn.execute(_sql("SELECT * FROM users WHERE username = ?"), (username.strip().lower(),)).fetchone()
    row_data = _as_dict(row)
    if not row_data or not _verify_password(password, row_data["password_hash"]):
        write_audit(actor=username.strip().lower() or "unknown", action="auth.login", target="session", status="denied")
        return None
    token = "gst_" + secrets.token_urlsafe(32)
    session = {
        "id": "sess_" + secrets.token_hex(8),
        "user_id": row_data["id"],
        "token_hash": _hash_token(token),
        "created_at": _now(),
        "expires_at": (datetime.utcnow() + timedelta(hours=ttl_hours)).replace(microsecond=0).isoformat() + "Z",
    }
    conn.execute(
        _sql("INSERT INTO sessions (id, user_id, token_hash, created_at, expires_at) VALUES (?, ?, ?, ?, ?)"),
        (session["id"], session["user_id"], session["token_hash"], session["created_at"], session["expires_at"]),
    )
    conn.execute(_sql("UPDATE users SET last_login_at = ? WHERE id = ?"), (_now(), row_data["id"]))
    conn.commit()
    write_audit(actor=row_data["id"], action="auth.login", target=session["id"], status="ok")
    return {"token": token, "session": _public_session(session), "user": _public_user(row_data)}


def validate_session_token(token: str) -> dict | None:
    if not token:
        return None
    conn = _connect()
    row = conn.execute(
        _sql("""
        SELECT sessions.*, users.username, users.display_name, users.role
        FROM sessions
        JOIN users ON users.id = sessions.user_id
        WHERE sessions.token_hash = ? AND sessions.revoked_at IS NULL AND sessions.expires_at > ?
        """),
        (_hash_token(token), _now()),
    ).fetchone()
    if not row:
        return None
    row_data = _as_dict(row)
    return {
        "session": _public_session(row_data),
        "user": {
            "id": row_data["user_id"],
            "username": row_data["username"],
            "display_name": row_data["display_name"],
            "role": row_data["role"],
        },
    }


def revoke_session(token: str) -> bool:
    conn = _connect()
    cur = conn.execute(
        _sql("UPDATE sessions SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL"),
        (_now(), _hash_token(token)),
    )
    conn.commit()
    return cur.rowcount > 0


def active_session_count() -> int:
    conn = _connect()
    return int(
        _first_value(conn.execute(
            _sql(
            "SELECT COUNT(*) FROM sessions WHERE revoked_at IS NULL AND expires_at > ?",
            ),
            (_now(),),
        ).fetchone())
    )


def upsert_organism(org: Any) -> None:
    payload = org.model_dump(mode="json") if hasattr(org, "model_dump") else dict(org)
    intent = payload.get("intent") or {}
    conn = _connect()
    conn.execute(
        _sql("""
        INSERT INTO organism_records (id, name, state, goal, born_at, updated_at, payload_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          name=excluded.name,
          state=excluded.state,
          goal=excluded.goal,
          born_at=excluded.born_at,
          updated_at=excluded.updated_at,
          payload_json=excluded.payload_json
        """),
        (
            payload.get("id", ""),
            payload.get("name") or payload.get("id", ""),
            str(payload.get("state", "unknown")),
            intent.get("goal", ""),
            str(payload.get("born_at") or ""),
            _now(),
            _json_value(payload),
        ),
    )
    conn.commit()


def upsert_decision(decision: Any) -> None:
    payload = decision.model_dump(mode="json") if hasattr(decision, "model_dump") else dict(decision)
    conn = _connect()
    conn.execute(
        _sql("""
        INSERT INTO decision_records (id, organism_id, timestamp, action_name, is_dream, payload_json)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          organism_id=excluded.organism_id,
          timestamp=excluded.timestamp,
          action_name=excluded.action_name,
          is_dream=excluded.is_dream,
          payload_json=excluded.payload_json
        """),
        (
            payload.get("id", ""),
            payload.get("organism_id", ""),
            str(payload.get("timestamp") or ""),
            (payload.get("action") or {}).get("name", ""),
            1 if payload.get("is_dream") else 0,
            _json_value(payload),
        ),
    )
    conn.commit()


def list_organism_payloads() -> list[dict]:
    """Return durable organism mirrors ordered like the runtime JSON store."""
    conn = _connect()
    rows = conn.execute(
        "SELECT payload_json FROM organism_records ORDER BY born_at DESC, updated_at DESC"
    ).fetchall()
    return [_json_payload(_as_dict(row).get("payload_json")) for row in rows]


def get_organism_payload(organism_id: str) -> dict | None:
    conn = _connect()
    row = conn.execute(
        _sql("SELECT payload_json FROM organism_records WHERE id = ?"),
        (organism_id,),
    ).fetchone()
    if not row:
        return None
    return _json_payload(_as_dict(row).get("payload_json"))


def list_decision_payloads(organism_id: str) -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        _sql(
            "SELECT payload_json FROM decision_records WHERE organism_id = ? ORDER BY timestamp ASC"
        ),
        (organism_id,),
    ).fetchall()
    return [_json_payload(_as_dict(row).get("payload_json")) for row in rows]


def delete_organism_mirror(organism_id: str) -> None:
    conn = _connect()
    conn.execute(_sql("DELETE FROM decision_records WHERE organism_id = ?"), (organism_id,))
    conn.execute(_sql("DELETE FROM organism_records WHERE id = ?"), (organism_id,))
    conn.commit()


def write_audit(actor: str, action: str, target: str, status: str, payload: dict | None = None) -> dict:
    event = {
        "id": "aud_" + secrets.token_hex(8),
        "actor": actor or "system",
        "action": action,
        "target": target or "unknown",
        "status": status,
        "created_at": _now(),
        "payload_json": payload or {},
    }
    conn = _connect()
    conn.execute(
        _sql("INSERT INTO audit_events (id, actor, action, target, status, created_at, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?)"),
        (
            event["id"],
            event["actor"],
            event["action"],
            event["target"],
            event["status"],
            event["created_at"],
            _json_value(event["payload_json"]),
        ),
    )
    conn.commit()
    return {**event, "payload": payload or {}}


def _public_user(row: dict) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "role": row.get("role", "operator"),
        "created_at": row.get("created_at"),
        "last_login_at": row.get("last_login_at"),
    }


def _public_session(row: dict) -> dict:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
        "revoked_at": row.get("revoked_at"),
    }
