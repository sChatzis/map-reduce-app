from pydantic import BaseModel, EmailStr, Field
from app.models.enums import UserRole, UserStatus
from typing import Optional

# --- User Data Schemas ---

# Schema for new user registration request
class UserCreate(BaseModel):
    username: str
    password: str = Field(min_length=8, max_length=72)

# Schema for login request
class TokenRequest(BaseModel):
    # Only username and password for login
    username: str
    password: str

# Schema for a user response (data returned to the client)
class UserOut(BaseModel):
    id: int
    username: str
    role: UserRole
    status: UserStatus

    class Config:
        # SQLAlchemy: enables reading data from a DB model
        from_attributes = True

# --- Token Schemas ---

# Schema for the JWT token response after successful login
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

# Schema for the data contained inside the JWT payload
class TokenData(BaseModel):
    username: Optional[str] = None
    user_id: Optional[int] = None
    role: Optional[UserRole] = None
    status: Optional[UserStatus] = None

# Schema to define what data an Admin can update
class UserUpdate(BaseModel):
    role: Optional[UserRole] = None
    status: Optional[UserStatus] = None