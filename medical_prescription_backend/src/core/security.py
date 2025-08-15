from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import jwt
from passlib.context import CryptContext

from src.core.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# PUBLIC_INTERFACE
def verify_password(plain_password: str, password_hash: str) -> bool:
    """Verify a plain text password against a stored password hash."""
    try:
        return pwd_context.verify(plain_password, password_hash)
    except Exception:
        return False


# PUBLIC_INTERFACE
def hash_password(password: str) -> str:
    """Hash a plain text password using the configured algorithm."""
    return pwd_context.hash(password)


# PUBLIC_INTERFACE
def create_access_token(subject: str, additional_claims: Optional[Dict[str, Any]] = None) -> str:
    """
    Create a signed JWT access token.

    Args:
        subject: Unique identifier for the subject (e.g., user_id as string).
        additional_claims: Optional extra claims to embed into the token payload.

    Returns:
        A signed JWT token string.
    """
    settings = get_settings()
    expire_minutes = settings.MED_API_ACCESS_TOKEN_EXPIRE_MINUTES
    expire = datetime.now(tz=timezone.utc) + timedelta(minutes=expire_minutes)
    to_encode: Dict[str, Any] = {"sub": subject, "exp": expire}
    if additional_claims:
        to_encode.update(additional_claims)
    token = jwt.encode(to_encode, settings.MED_API_SECRET_KEY, algorithm=settings.MED_API_ALGORITHM)
    return token


# PUBLIC_INTERFACE
def decode_token(token: str) -> Dict[str, Any]:
    """
    Decode and validate a JWT access token.

    Returns:
        The decoded payload as a dictionary.

    Raises:
        jwt.ExpiredSignatureError, jwt.InvalidTokenError on invalid tokens.
    """
    settings = get_settings()
    return jwt.decode(token, settings.MED_API_SECRET_KEY, algorithms=[settings.MED_API_ALGORITHM])
