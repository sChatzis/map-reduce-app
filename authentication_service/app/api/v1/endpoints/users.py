from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.user import DBUser
from app.schemas.user import UserCreate, TokenRequest, Token, UserOut, UserUpdate
from app.core.security import get_password_hash, verify_password, create_access_token, get_active_user, get_admin_user_payload, get_current_user
from app.models.enums import UserStatus, UserRole

router = APIRouter()


# --- Sign Up ---
@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register_user(user_in: UserCreate, db: Session = Depends(get_db)):
    """Registers a new user. Account status is PENDING_APPROVAL until admin activates it."""
    if db.query(DBUser).filter(DBUser.username == user_in.username).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )

    hashed_password = get_password_hash(user_in.password)
    new_user = DBUser(
        username=user_in.username,
        password=hashed_password,
        role=UserRole.USER,
        status=UserStatus.PENDING_APPROVAL
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


# --- Get current user (MUST be before /{user_id}) ---
@router.get("/me", response_model=UserOut, status_code=status.HTTP_200_OK)
def get_me(current_user: DBUser = Depends(get_active_user)):
    """Retrieve the current user's information. Requires a valid, active JWT token."""
    return current_user


# --- Log In ---
@router.post("/login", response_model=Token)
def login(form_data: TokenRequest, db: Session = Depends(get_db)):
    """Authenticates the user and returns a JWT access token."""
    user = db.query(DBUser).filter_by(username=form_data.username).first()

    if not user or not verify_password(form_data.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.status != UserStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account is {user.status.value}. Access denied. Requires admin approval."
        )

    access_token = create_access_token(
        data={
            "sub": user.username,
            "user_id": user.id,
            "role": user.role.value,
            "status": user.status.value
        }
    )
    return {"access_token": access_token, "token_type": "bearer"}


# --- Get all users (Admin only) ---
@router.get("/", response_model=list[UserOut], dependencies=[Depends(get_admin_user_payload)])
def read_all_users(db: Session = Depends(get_db)):
    return db.query(DBUser).all()


# --- Get specific user by ID (Admin only) ---
@router.get("/{user_id}", response_model=UserOut, dependencies=[Depends(get_admin_user_payload)])
def read_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(DBUser).filter(DBUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


# --- Update User Status (Admin only) ---
@router.patch("/{user_id}", response_model=UserOut, dependencies=[Depends(get_admin_user_payload)])
def update_user_status(user_id: int, user_update: UserUpdate, db: Session = Depends(get_db)):
    user = db.query(DBUser).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    update_data = user_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(user, key, value)

    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# --- Delete User (Admin only) ---
@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(get_admin_user_payload)])
def delete_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(DBUser).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    db.delete(user)
    db.commit()
