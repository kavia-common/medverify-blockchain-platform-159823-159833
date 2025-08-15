import sqlite3
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from src.core.config import get_settings
from src.integrations.solana import record_prescription_on_chain
from src.services.users import get_user_by_email, get_user_by_public_id


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    return d


def _get_chain_ref(conn: sqlite3.Connection, prescription_id: str) -> Tuple[Optional[str], Optional[str]]:
    cur = conn.execute(
        """
        SELECT tx_signature, network
        FROM prescription_blockchain_refs
        WHERE prescription_id = ?
        ORDER BY id DESC LIMIT 1
        """,
        (prescription_id,),
    )
    ref = cur.fetchone()
    if not ref:
        return None, None
    return ref["tx_signature"], ref["network"]


def _add_audit_log(
    conn: sqlite3.Connection,
    prescription_id: str,
    action: str,
    actor_user_id: int,
    actor_role: str,
    details: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    conn.execute(
        """
        INSERT INTO prescription_audit_logs (prescription_id, action, actor_user_id, actor_role, ip_address, user_agent, details)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (prescription_id, action, actor_user_id, actor_role, ip_address, user_agent, details),
    )


def _find_patient_id(
    conn: sqlite3.Connection, patient_email: Optional[str], patient_public_id: Optional[str]
) -> int:
    if patient_email:
        row = get_user_by_email(conn, patient_email)
        if not row:
            raise ValueError("Patient with the specified email was not found.")
        return int(row["id"])
    if patient_public_id:
        row = get_user_by_public_id(conn, patient_public_id)
        if not row:
            raise ValueError("Patient with the specified public_id was not found.")
        return int(row["id"])
    raise ValueError("Must provide patient_email or patient_public_id.")


def create_prescription(
    conn: sqlite3.Connection,
    doctor_user_id: int,
    doctor_role: str,
    *,
    patient_email: Optional[str],
    patient_public_id: Optional[str],
    drug_name: str,
    dosage: Optional[str],
    quantity: Optional[int],
    units: Optional[str],
    frequency: Optional[str],
    duration_days: Optional[int],
    instructions: Optional[str],
    expires_at: Optional[str],
    issue_on_chain: bool,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new prescription row, optionally recording a stub on-chain reference."""
    prescription_id = str(uuid.uuid4())
    number = f"RX-{prescription_id.split('-')[0].upper()}"
    patient_id = _find_patient_id(conn, patient_email, patient_public_id)
    issue_date = datetime.utcnow().strftime("%Y-%m-%d")
    with conn:
        conn.execute(
            """
            INSERT INTO prescriptions (
                id, number, patient_id, doctor_id, pharmacist_id,
                drug_name, dosage, quantity, units, frequency, duration_days,
                instructions, issue_date, expires_at, status
            )
            VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ISSUED')
            """,
            (
                prescription_id,
                number,
                patient_id,
                doctor_user_id,
                drug_name,
                dosage,
                quantity,
                units,
                frequency,
                duration_days,
                instructions,
                issue_date,
                expires_at,
            ),
        )
        _add_audit_log(
            conn,
            prescription_id,
            action="ISSUED",
            actor_user_id=doctor_user_id,
            actor_role=doctor_role,
            details="Prescription issued by doctor",
            ip_address=ip_address,
            user_agent=user_agent,
        )

        chain_sig = None
        chain_network = None
        if issue_on_chain:
            # Stubbed blockchain call
            network = get_settings().SOLANA_NETWORK
            result = record_prescription_on_chain(
                prescription_id,
                {
                    "number": number,
                    "patient_id": patient_id,
                    "doctor_id": doctor_user_id,
                    "drug_name": drug_name,
                },
                network=network,
            )
            chain_sig = result.get("tx_signature")
            chain_network = result.get("network")
            conn.execute(
                """
                INSERT INTO prescription_blockchain_refs (prescription_id, chain, network, tx_signature, status)
                VALUES (?, 'solana', ?, ?, 'processed')
                """,
                (prescription_id, chain_network, chain_sig),
            )

    row = get_prescription_by_id(conn, prescription_id)
    out = _row_to_dict(row)
    out["chain_tx_signature"] = chain_sig
    out["chain_network"] = chain_network
    return out


def get_prescription_by_id(conn: sqlite3.Connection, prescription_id: str) -> sqlite3.Row:
    cur = conn.execute("SELECT * FROM prescriptions WHERE id = ?", (prescription_id,))
    row = cur.fetchone()
    if not row:
        raise ValueError("Prescription not found.")
    return row


def list_prescriptions_for_user(
    conn: sqlite3.Connection, user_id: int, roles: List[str]
) -> List[Dict[str, Any]]:
    q = "SELECT * FROM prescriptions"
    params: Tuple[Any, ...] = ()
    # Determine scope: doctors see their issued, pharmacists see ISSUED/VERIFIED/FILLED, patients see theirs
    if "admin" in roles:
        pass  # no filter
    elif "doctor" in roles:
        q += " WHERE doctor_id = ?"
        params = (user_id,)
    elif "pharmacist" in roles:
        # Show all issued or verified or filled
        q += " WHERE status IN ('ISSUED','VERIFIED','FILLED')"
    else:
        # patient
        q += " WHERE patient_id = ?"
        params = (user_id,)
    q += " ORDER BY created_at DESC"
    cur = conn.execute(q, params)
    rows = cur.fetchall()
    out: List[Dict[str, Any]] = []
    for r in rows:
        d = _row_to_dict(r)
        sig, net = _get_chain_ref(conn, d["id"])
        d["chain_tx_signature"] = sig
        d["chain_network"] = net
        out.append(d)
    return out


def verify_prescription(
    conn: sqlite3.Connection,
    prescription_id: str,
    pharmacist_user_id: int,
    pharmacist_role: str,
    verify_on_chain: bool,
    mark_verified: bool,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Dict[str, Any]:
    # Optionally "verify" via stubbed chain verification
    chain_ok = True
    sig, net = _get_chain_ref(conn, prescription_id)
    if verify_on_chain:
        # In a real integration, fetch on-chain data and validate. Here we just ensure a signature exists.
        chain_ok = sig is not None

    if mark_verified:
        with conn:
            conn.execute(
                """
                UPDATE prescriptions
                SET status = 'VERIFIED', pharmacist_id = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (pharmacist_user_id, prescription_id),
            )
            _add_audit_log(
                conn,
                prescription_id,
                action="VERIFIED",
                actor_user_id=pharmacist_user_id,
                actor_role=pharmacist_role,
                details=f"verify_on_chain={verify_on_chain}, chain_ok={chain_ok}",
                ip_address=ip_address,
                user_agent=user_agent,
            )
    row = get_prescription_by_id(conn, prescription_id)
    d = _row_to_dict(row)
    d["chain_tx_signature"] = sig
    d["chain_network"] = net
    return d
