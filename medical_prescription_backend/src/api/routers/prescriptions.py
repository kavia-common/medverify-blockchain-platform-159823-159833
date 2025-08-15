from fastapi import APIRouter, Depends, HTTPException, Request, status

from src.api.routers.auth import get_current_user, require_roles
from src.core.db import get_db
from src.models.schemas import (
    PrescriptionCreate,
    PrescriptionListResponse,
    PrescriptionOut,
    VerifyRequest,
)
from src.services.prescriptions import (
    create_prescription,
    get_prescription_by_id,
    list_prescriptions_for_user,
    verify_prescription,
)

router = APIRouter(prefix="/prescriptions", tags=["Prescriptions"])


@router.post(
    "",
    response_model=PrescriptionOut,
    summary="Create a new prescription",
    description="Doctors can create and issue a new prescription. Optionally records a stubbed Solana reference.",
    responses={
        201: {"description": "Prescription created"},
        400: {"description": "Bad request"},
        403: {"description": "Forbidden"},
    },
    status_code=201,
)
# PUBLIC_INTERFACE
def create_new_prescription(
    payload: PrescriptionCreate,
    request: Request,
    db=Depends(get_db),
    user: dict = Depends(require_roles("doctor")),
) -> PrescriptionOut:
    """
    Create and issue a prescription linked to a patient by email or public_id.

    Only users with 'doctor' role (or 'admin') can call this endpoint.
    """
    try:
        out = create_prescription(
            db,
            doctor_user_id=user["id"],
            doctor_role="doctor" if "doctor" in user.get("roles", []) else "admin",
            patient_email=payload.patient_email,
            patient_public_id=payload.patient_public_id,
            drug_name=payload.drug_name,
            dosage=payload.dosage,
            quantity=payload.quantity,
            units=payload.units,
            frequency=payload.frequency,
            duration_days=payload.duration_days,
            instructions=payload.instructions,
            expires_at=payload.expires_at.isoformat() if payload.expires_at else None,
            issue_on_chain=payload.issue_on_chain,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("User-Agent"),
        )
        return PrescriptionOut(**out)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))


@router.get(
    "",
    response_model=PrescriptionListResponse,
    summary="List prescriptions for the current user",
    description="Returns prescriptions based on user role: doctors see their own issued, pharmacists see issued/verified/filled, patients see their own.",
)
# PUBLIC_INTERFACE
def list_my_prescriptions(db=Depends(get_db), user: dict = Depends(get_current_user)) -> PrescriptionListResponse:
    """List prescriptions scoped by the current user's roles."""
    items = list_prescriptions_for_user(db, user_id=user["id"], roles=user.get("roles", []))
    return PrescriptionListResponse(items=[PrescriptionOut(**i) for i in items])


@router.get(
    "/{prescription_id}",
    response_model=PrescriptionOut,
    summary="Get prescription by ID",
    description="Return prescription details. Patients can only access their own; doctors and pharmacists can access relevant ones.",
)
# PUBLIC_INTERFACE
def get_prescription(
    prescription_id: str, db=Depends(get_db), user: dict = Depends(get_current_user)
) -> PrescriptionOut:
    """Return a specific prescription if the user has permissions."""
    try:
        row = get_prescription_by_id(db, prescription_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prescription not found")

    roles = set([r.lower() for r in user.get("roles", [])])
    # Access control: admin can always access, doctor if they created, pharmacist if status allows, patient if their own
    if "admin" not in roles:
        if "doctor" in roles and row["doctor_id"] == user["id"]:
            pass
        elif "pharmacist" in roles and row["status"] in ("ISSUED", "VERIFIED", "FILLED"):
            pass
        elif row["patient_id"] == user["id"]:
            pass
        else:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    from src.services.prescriptions import _get_chain_ref  # local import to avoid exposure
    sig, net = _get_chain_ref(db, prescription_id)
    d = dict(row)
    d["chain_tx_signature"] = sig
    d["chain_network"] = net
    return PrescriptionOut(**d)


@router.post(
    "/{prescription_id}/verify",
    response_model=PrescriptionOut,
    summary="Verify a prescription",
    description="Pharmacists can mark a prescription as VERIFIED. Optionally (stub) verify with on-chain reference.",
    responses={
        200: {"description": "Prescription verified"},
        403: {"description": "Forbidden"},
        404: {"description": "Not found"},
    },
)
# PUBLIC_INTERFACE
def verify(
    prescription_id: str,
    payload: VerifyRequest,
    request: Request,
    db=Depends(get_db),
    user: dict = Depends(require_roles("pharmacist")),
) -> PrescriptionOut:
    """Verify a prescription, updating its status and recording an audit log."""
    try:
        out = verify_prescription(
            db,
            prescription_id=prescription_id,
            pharmacist_user_id=user["id"],
            pharmacist_role="pharmacist",
            verify_on_chain=payload.verify_on_chain,
            mark_verified=payload.mark_verified,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("User-Agent"),
        )
        return PrescriptionOut(**out)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prescription not found")
