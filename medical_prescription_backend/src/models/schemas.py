from datetime import date
from typing import List, Literal, Optional

from pydantic import BaseModel, EmailStr, Field


class TokenResponse(BaseModel):
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field("bearer", description="Type of token, typically 'bearer'")


class UserBase(BaseModel):
    email: EmailStr = Field(..., description="User email address")
    username: Optional[str] = Field(None, description="Optional username")
    full_name: Optional[str] = Field(None, description="Full name of the user")


class UserCreate(UserBase):
    password: str = Field(..., min_length=8, description="Password for the user")
    role: Literal["doctor", "pharmacist", "patient", "admin"] = Field(
        "doctor", description="Role to assign to the new user"
    )


class UserLogin(BaseModel):
    email: EmailStr = Field(..., description="Email of the user")
    password: str = Field(..., description="Password of the user")


class UserPublic(BaseModel):
    id: int = Field(..., description="Internal numeric user ID")
    public_id: Optional[str] = Field(None, description="Public UUID reference")
    email: EmailStr = Field(..., description="Email")
    username: Optional[str] = Field(None, description="Username")
    full_name: Optional[str] = Field(None, description="Full name")
    is_active: bool = Field(..., description="Active flag")
    roles: List[str] = Field(default_factory=list, description="Roles assigned to the user")


class PrescriptionCreate(BaseModel):
    patient_email: Optional[EmailStr] = Field(
        None, description="Email of the patient to link to the prescription"
    )
    patient_public_id: Optional[str] = Field(
        None, description="Public UUID of the patient, alternative to email"
    )
    drug_name: str = Field(..., description="Name of the prescribed drug")
    dosage: Optional[str] = Field(None, description="Dosage details")
    quantity: Optional[int] = Field(None, description="Number of units")
    units: Optional[str] = Field(None, description="Units (e.g., tablets, ml)")
    frequency: Optional[str] = Field(None, description="Frequency (e.g., 2x/day)")
    duration_days: Optional[int] = Field(None, description="Duration in days")
    instructions: Optional[str] = Field(None, description="Additional instructions")
    expires_at: Optional[date] = Field(None, description="Expiration date for the prescription")
    issue_on_chain: bool = Field(
        False, description="If true, record a reference on Solana (stubbed integration)"
    )


class PrescriptionOut(BaseModel):
    id: str = Field(..., description="UUID of prescription")
    number: str = Field(..., description="Human-readable prescription number")
    patient_id: int = Field(..., description="Patient user ID")
    doctor_id: int = Field(..., description="Doctor user ID")
    pharmacist_id: Optional[int] = Field(None, description="Pharmacist user ID if filled/verified")
    drug_name: str = Field(..., description="Drug name")
    dosage: Optional[str] = Field(None, description="Dosage")
    quantity: Optional[int] = Field(None, description="Quantity")
    units: Optional[str] = Field(None, description="Units")
    frequency: Optional[str] = Field(None, description="Frequency")
    duration_days: Optional[int] = Field(None, description="Duration in days")
    instructions: Optional[str] = Field(None, description="Instructions")
    issue_date: Optional[str] = Field(None, description="Issue date string")
    expires_at: Optional[str] = Field(None, description="Expiration date string")
    status: str = Field(..., description="Status of prescription")
    created_at: Optional[str] = Field(None, description="Creation timestamp")
    updated_at: Optional[str] = Field(None, description="Last update timestamp")
    chain_tx_signature: Optional[str] = Field(None, description="Blockchain tx signature if recorded")
    chain_network: Optional[str] = Field(None, description="Blockchain network")


class PrescriptionListResponse(BaseModel):
    items: List[PrescriptionOut] = Field(..., description="List of prescriptions")


class VerifyRequest(BaseModel):
    verify_on_chain: bool = Field(
        False, description="If true, attempt (stub) verification via Solana metadata"
    )
    mark_verified: bool = Field(
        True, description="If true, update status to VERIFIED and record audit log"
    )
