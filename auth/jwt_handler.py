"""
JWT Authentication module — token generation, validation, and refresh logic.
Uses RS256 asymmetric signing for secure cross-service token validation.
"""
import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple

import jwt
from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7

# Load from AWS Secrets Manager / KMS in production
_PRIVATE_KEY = "REPLACE_WITH_RSA_PRIVATE_KEY"
_PUBLIC_KEY  = "REPLACE_WITH_RSA_PUBLIC_KEY"

security = HTTPBearer()


def create_access_token(user_id: str, role: str = "user", extra_claims: dict = None) -> str:
    """Create a short-lived JWT access token (RS256)."""
    now = datetime.utcnow()
    payload = {
        "sub": user_id,
        "role": role,
        "type": "access",
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, _PRIVATE_KEY, algorithm="RS256")


def create_refresh_token(user_id: str, session_id: str) -> str:
    """Create a long-lived refresh token tied to a DB session record."""
    now = datetime.utcnow()
    payload = {
        "sub": user_id,
        "session_id": session_id,
        "type": "refresh",
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    }
    return jwt.encode(payload, _PRIVATE_KEY, algorithm="RS256")


def validate_token(token: str, expected_type: str = "access") -> dict:
    """Decode and validate a JWT. Raises HTTP 401 on any failure."""
    try:
        payload = jwt.decode(token, _PUBLIC_KEY, algorithms=["RS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")

    if payload.get("type") != expected_type:
        raise HTTPException(status_code=401, detail=f"Expected {expected_type} token")
    return payload


def create_token_pair(user_id: str, role: str = "user") -> Tuple[str, str, str]:
    """
    Create access + refresh token pair.
    Returns (access_token, refresh_token, session_id).
    """
    session_id = str(uuid.uuid4())
    return (
        create_access_token(user_id, role),
        create_refresh_token(user_id, session_id),
        session_id,
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> dict:
    """FastAPI dependency: validate Bearer token and return payload."""
    return validate_token(credentials.credentials, expected_type="access")


def require_role(role: str):
    """FastAPI dependency factory: ensure user has required role."""
    async def _check(user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") not in (role, "admin"):
            raise HTTPException(status_code=403, detail=f"Role '{role}' required")
        return user
    return _check
