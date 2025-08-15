import sqlite3
from typing import Generator

from src.core.config import get_settings


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """
    Ensure required database tables exist. Executes idempotent DDL statements.
    This makes the backend resilient when the database container isn't pre-initialized.
    """
    # Users and roles
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            public_id TEXT UNIQUE,
            email TEXT NOT NULL UNIQUE,
            username TEXT,
            full_name TEXT,
            password_hash TEXT,
            password_algo TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS user_roles (
            user_id INTEGER NOT NULL,
            role_id INTEGER NOT NULL,
            PRIMARY KEY (user_id, role_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

        -- Prescriptions domain
        CREATE TABLE IF NOT EXISTS prescriptions (
            id TEXT PRIMARY KEY,
            number TEXT NOT NULL,
            patient_id INTEGER NOT NULL,
            doctor_id INTEGER NOT NULL,
            pharmacist_id INTEGER,
            drug_name TEXT NOT NULL,
            dosage TEXT,
            quantity INTEGER,
            units TEXT,
            frequency TEXT,
            duration_days INTEGER,
            instructions TEXT,
            issue_date TEXT,
            expires_at TEXT,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT,
            FOREIGN KEY (patient_id) REFERENCES users(id) ON DELETE RESTRICT,
            FOREIGN KEY (doctor_id) REFERENCES users(id) ON DELETE RESTRICT,
            FOREIGN KEY (pharmacist_id) REFERENCES users(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_prescriptions_created_at ON prescriptions(created_at);
        CREATE INDEX IF NOT EXISTS idx_prescriptions_doctor ON prescriptions(doctor_id);
        CREATE INDEX IF NOT EXISTS idx_prescriptions_patient ON prescriptions(patient_id);

        CREATE TABLE IF NOT EXISTS prescription_audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prescription_id TEXT NOT NULL,
            action TEXT NOT NULL,
            actor_user_id INTEGER,
            actor_role TEXT,
            ip_address TEXT,
            user_agent TEXT,
            details TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (prescription_id) REFERENCES prescriptions(id) ON DELETE CASCADE,
            FOREIGN KEY (actor_user_id) REFERENCES users(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_audit_logs_prescription ON prescription_audit_logs(prescription_id);

        CREATE TABLE IF NOT EXISTS prescription_blockchain_refs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prescription_id TEXT NOT NULL,
            chain TEXT NOT NULL,
            network TEXT,
            tx_signature TEXT,
            status TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (prescription_id) REFERENCES prescriptions(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_chain_refs_prescription ON prescription_blockchain_refs(prescription_id);
        """
    )

    # Seed standard roles if empty
    cur = conn.execute("SELECT COUNT(*) AS c FROM roles")
    row = cur.fetchone()
    count = int(row["c"]) if row else 0
    if count == 0:
        # Minimal seed to avoid failures on first user registration
        for r in ("doctor", "pharmacist", "patient", "admin"):
            conn.execute(
                "INSERT OR IGNORE INTO roles (name, description) VALUES (?, ?)",
                (r, f"Default role: {r}"),
            )


def _connect() -> sqlite3.Connection:
    """Create a SQLite3 connection with schema ensured, foreign keys enabled, and Row factory."""
    db_path = get_settings().SQLITE_DB
    # NOTE: sqlite3 will fail if the parent directory does not exist. That is expected,
    # and should be resolved via environment/volume configuration. Once the file is accessible,
    # we auto-initialize the schema below.
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # Ensure schema is present before handling requests
    try:
        _ensure_schema(conn)
    except Exception:
        # In case of concurrent initialization attempts, ignore errors here to avoid blocking requests.
        # Subsequent statements will fail loudly if schema truly cannot be created.
        pass
    return conn


# PUBLIC_INTERFACE
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """
    FastAPI dependency yielding a SQLite3 connection for the duration of the request.

    Yields:
        sqlite3.Connection with row_factory set to sqlite3.Row

    Ensures:
        - Foreign keys are enforced
        - Schema is initialized if missing
        - Connection is closed after request
    """
    conn = _connect()
    try:
        yield conn
    finally:
        try:
            conn.close()
        except Exception:
            pass
