from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, HTTPException, Security, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

from src.core.db import get_db
from src.core.security import create_access_token, decode_token
from src.models.schemas import TokenResponse, UserCreate, UserPublic
from src.services.users import (
    authenticate_user,
    create_user,
    get_user_roles,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def _get_current_user_payload(token: Annotated[str, Security(_oauth2_scheme)]) -> dict:
    try:
        payload = decode_token(token)
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


# PUBLIC_INTERFACE
def get_current_user(db=Depends(get_db), payload: dict = Depends(_get_current_user_payload)) -> dict:
    """
    Resolve current user from JWT payload and return a dictionary with user profile and roles.

    Returns:
        Dict with user properties and roles.
    """
    subject = payload.get("sub")
    if not subject:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    # subject is user_id string
    try:
        user_id = int(subject)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject")

    cur = db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    roles = get_user_roles(db, user_id)
    return {
        "id": row["id"],
        "public_id": row["public_id"],
        "email": row["email"],
        "username": row["username"],
        "full_name": row["full_name"],
        "is_active": bool(row["is_active"]),
        "roles": roles,
    }


# PUBLIC_INTERFACE
def require_roles(*required_roles: str):
    """
    Dependency factory to enforce role-based access.

    Usage:
        @router.post(..., dependencies=[Depends(require_roles('doctor'))])
    """

    def _checker(user: dict = Depends(get_current_user)) -> dict:
        roles = set([r.lower() for r in user.get("roles", [])])
        if "admin" in roles:
            return user
        for rr in required_roles:
            if rr.lower() in roles:
                return user
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role permissions")

    return _checker


@router.post(
    "/register",
    response_model=UserPublic,
    summary="Register a user",
    description="Register a new user (doctor, pharmacist, patient, or admin). Requires email and password.",
    responses={201: {"description": "User created"}},
    status_code=201,
)
# PUBLIC_INTERFACE
def register_user(payload: UserCreate, db=Depends(get_db)) -> UserPublic:
    """Register a new user and assign a role. Email must be unique."""
    try:
        user = create_user(
            db,
            email=payload.email,
            password=payload.password,
            username=payload.username,
            full_name=payload.full_name,
            role_name=payload.role,
        )
        return UserPublic(**user)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login to obtain JWT",
    description="Authenticate with email and password. Returns bearer JWT for subsequent calls.",
)
# PUBLIC_INTERFACE
def login(
    form_data: OAuth2PasswordRequestForm = Depends(), db=Depends(get_db)
) -> TokenResponse:
    """Authenticate user and return a JWT token."""
    user = authenticate_user(db, email=form_data.username, password=form_data.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    # subject is internal user id
    cur = db.execute("SELECT id FROM users WHERE email = ?", (form_data.username.lower(),))
    row = cur.fetchone()
    user_id = int(row["id"])
    token = create_access_token(subject=str(user_id), additional_claims={"roles": user["roles"]})
    return TokenResponse(access_token=token, token_type="bearer")


@router.get(
    "/me",
    response_model=UserPublic,
    summary="Get current user profile",
    description="Return the currently authenticated user's profile and roles.",
)
# PUBLIC_INTERFACE
def me(user: dict = Depends(get_current_user)) -> UserPublic:
    """Return the currently authenticated user."""
    return UserPublic(**user)
