from datetime import datetime, timedelta, UTC
from passlib.context import CryptContext
from jose import jwt, JWTError
from fastapi import HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer, HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.user import DBUser
from app.models.enums import UserStatus, UserRole
from app.core.config import settings

# Password hashing configuration
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Redirect for authentication (login endpoint)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/users/login")

# --- Password Hashing ---

"""Checks if the plain password matches the hashed password."""


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


"""Hashes a password."""


def get_password_hash(password: str) -> str:
    truncated_password = password[:72]
    encoded_password = truncated_password.encode("utf-8")
    return pwd_context.hash(encoded_password)


# --- JWT Token Management ---

"""Creates a JWT for a user."""


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})

    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.ALGORITHM
    )
    return encoded_jwt


"""Decodes and validates a JWT."""


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        return payload
    except JWTError:
        # Raise exception if the token is invalid or expired
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


"""
    Decodes the JWT and returns the payload data (user_id, role, status).
    Raises HTTPException if the token is invalid, expired, or malformed.
"""


def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )

        if 'user_id' not in payload or 'role' not in payload or 'status' not in payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token payload is missing required parameters.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


"""
    Retrieves the user from the database and checks if they are ACTIVE.
"""


def get_active_user(
        db: Session = Depends(get_db),
        payload: dict = Depends(get_current_user)
) -> DBUser:
    user_id = payload.get("user_id")
    user = db.query(DBUser).filter(DBUser.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check only active users can access protected routes
    if user.status != UserStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not active. Administrator is responsible for this."
        )

    return user


"""
Function that checks if the user has the 'ADMIN' role.
"""


def get_admin_user_payload(payload: dict = Depends(get_current_user)) -> dict:

    role = payload.get("role")

    if role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operation requires administrator privileges."
        )
    return payload
