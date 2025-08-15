import logging
import sqlite3
import uuid
from typing import List, Optional

from src.core.security import hash_password, verify_password

logger = logging.getLogger("med_backend.users")


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


# PUBLIC_INTERFACE
def ensure_role_exists(conn: sqlite3.Connection, role_name: str) -> int:
    """Ensure the given role exists and return its id.

    Handles races robustly: if another process inserts the same role concurrently,
    we catch the IntegrityError and re-read the role id.

    Args:
        conn: SQLite connection.
        role_name: Name of the role, case-sensitive match.

    Returns:
        Integer role id.
    """
    cur = conn.execute("SELECT id FROM roles WHERE name = ?", (role_name,))
    row = cur.fetchone()
    if row:
        return int(row["id"])
    # Attempt to create role if not existing (for robustness)
    try:
        cur = conn.execute(
            "INSERT INTO roles (name, description) VALUES (?, ?)",
            (role_name, f"Autocreated role {role_name}"),
        )
        return cur.lastrowid
    except sqlite3.IntegrityError as ie:
        # Likely unique constraint due to a race. Re-read and return.
        logger.warning("Role insert race detected for '%s': %s", role_name, ie)
        cur = conn.execute("SELECT id FROM roles WHERE name = ?", (role_name,))
        row = cur.fetchone()
        if not row:
            # If still not found, bubble up with context
            logger.exception("Failed to resolve role '%s' after IntegrityError", role_name)
            raise
        return int(row["id"])


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


# PUBLIC_INTERFACE
def cleanup_ghost_user_records_for_email(conn: sqlite3.Connection, email: str) -> int:
    """Attempt to remove ghost/partial user records for the given email.

    Ghost user definition (conservative):
      - users.email matches
      - AND (password_hash IS NULL OR password_hash == '')
      - AND there are no related rows referencing the user (user_roles, prescriptions, audit logs)
    This avoids deleting legitimate users and preserves referential integrity.

    Args:
        conn: SQLite connection.
        email: Email address to check for ghost records (case-insensitive).

    Returns:
        The number of user rows deleted (0 or more, typically 0 or 1).
    """
    # Find candidate users
    cur = conn.execute(
        "SELECT id, password_hash FROM users WHERE email = ?",
        (email.lower(),),
    )
    rows = cur.fetchall()
    if not rows:
        return 0

    deleted = 0
    for r in rows:
        user_id = int(r["id"])
        pwd_hash = r["password_hash"]
        if pwd_hash not in (None, ""):
            continue  # not a ghost by our definition

        # Check for relations
        has_roles = conn.execute(
            "SELECT 1 FROM user_roles WHERE user_id = ? LIMIT 1", (user_id,)
        ).fetchone() is not None
        has_presc = conn.execute(
            "SELECT 1 FROM prescriptions WHERE patient_id = ? OR doctor_id = ? OR pharmacist_id = ? LIMIT 1",
            (user_id, user_id, user_id),
        ).fetchone() is not None
        has_audit = conn.execute(
            "SELECT 1 FROM prescription_audit_logs WHERE actor_user_id = ? LIMIT 1",
            (user_id,),
        ).fetchone() is not None

        if has_roles or has_presc or has_audit:
            logger.info(
                "Skipping ghost cleanup for user %s (id=%s) due to existing relations: roles=%s, presc=%s, audit=%s",
                email, user_id, has_roles, has_presc, has_audit
            )
            continue

        # Safe to delete
        with conn:
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        deleted += 1
        logger.warning("Deleted ghost user record for email %s (id=%s)", email, user_id)

    return deleted
