import sqlite3
import uuid
from typing import List, Optional

from src.core.security import hash_password, verify_password


def _row_to_user_public(row: sqlite3.Row, roles: List[str]) -> dict:
    """Map user row and roles to public dict."""
    return {
        "id": row["id"],
        "public_id": row["public_id"],
        "email": row["email"],
        "username": row["username"],
        "full_name": row["full_name"],
        "is_active": bool(row["is_active"]),
        "roles": roles,
    }


def get_user_by_email(conn: sqlite3.Connection, email: str) -> Optional[sqlite3.Row]:
    cur = conn.execute("SELECT * FROM users WHERE email = ?", (email.lower(),))
    return cur.fetchone()


def get_user_by_public_id(conn: sqlite3.Connection, public_id: str) -> Optional[sqlite3.Row]:
    cur = conn.execute("SELECT * FROM users WHERE public_id = ?", (public_id,))
    return cur.fetchone()


def get_user_roles(conn: sqlite3.Connection, user_id: int) -> List[str]:
    cur = conn.execute(
        """
        SELECT r.name
        FROM user_roles ur
        JOIN roles r ON r.id = ur.role_id
        WHERE ur.user_id = ?
        ORDER BY r.name
        """,
        (user_id,),
    )
    return [r[0] for r in cur.fetchall()]


def ensure_role_exists(conn: sqlite3.Connection, role_name: str) -> int:
    cur = conn.execute("SELECT id FROM roles WHERE name = ?", (role_name,))
    row = cur.fetchone()
    if row:
        return int(row["id"])
    # Attempt to create role if not existing (for robustness)
    cur = conn.execute(
        "INSERT INTO roles (name, description) VALUES (?, ?)",
        (role_name, f"Autocreated role {role_name}"),
    )
    return cur.lastrowid


def assign_role(conn: sqlite3.Connection, user_id: int, role_name: str) -> None:
    role_id = ensure_role_exists(conn, role_name)
    conn.execute(
        "INSERT OR IGNORE INTO user_roles (user_id, role_id) VALUES (?, ?)",
        (user_id, role_id),
    )


def create_user(
    conn: sqlite3.Connection,
    email: str,
    password: str,
    username: Optional[str],
    full_name: Optional[str],
    role_name: str,
) -> dict:
    existing = get_user_by_email(conn, email)
    if existing:
        raise ValueError("User with this email already exists.")
    public_id = str(uuid.uuid4())
    pwd_hash = hash_password(password)
    with conn:
        cur = conn.execute(
            """
            INSERT INTO users (public_id, email, username, full_name, password_hash, password_algo, is_active)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
            (public_id, email.lower(), username, full_name, pwd_hash, "bcrypt"),
        )
        user_id = cur.lastrowid
        assign_role(conn, user_id, role_name)
    row = get_user_by_email(conn, email)
    roles = get_user_roles(conn, user_id)
    return _row_to_user_public(row, roles)


def authenticate_user(conn: sqlite3.Connection, email: str, password: str) -> Optional[dict]:
    row = get_user_by_email(conn, email)
    if not row:
        return None
    if not verify_password(password, row["password_hash"] or ""):
        return None
    roles = get_user_roles(conn, row["id"])
    return _row_to_user_public(row, roles)
