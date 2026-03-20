from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.db.database import get_db
from app.models.user import DBUser
from app.schemas.user import UserCreate, TokenRequest, Token, UserOut, UserUpdate
from app.core.security import get_password_hash, verify_password, create_access_token, get_active_user, get_admin_user_payload, get_current_user
from app.models.enums import UserStatus, UserRole

router = APIRouter()


# --- Sign Up ---
@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register_user(user_in: UserCreate, db: Session = Depends(get_db)):
    """
        Registers a new user.
        Account status is set to PENDING_APPROVAL, requiring Admin activation.
    """
    if db.query(DBUser).filter(
            or_(DBUser.username == user_in.username)
    ).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already exists"
        )

    # Hash the password
    hashed_password = get_password_hash(user_in.password)

    # Create the new user
    new_user = DBUser(
        username=user_in.username,
        password=hashed_password,
        role=UserRole.USER,
        status=UserStatus.PENDING_APPROVAL
    )

    # Saving to database
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user


# --- Get all users ---
@router.get("/", response_model=list[UserOut], dependencies=[Depends(get_current_user)])
def read_all_users(db: Session = Depends(get_db)):
    users = db.query(DBUser).all()
    return users


# --- Get specific user by ID (Admin only) ---
@router.get("/{user_id}", response_model=UserOut)
def read_user(
        user_id: int,
        db: Session = Depends(get_db),
        current_user: dict = Depends(get_current_user)
):
    user = db.query(DBUser).filter(DBUser.id == user_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Security check: Admin can do this
    user_role = current_user.get("role")
    if user_role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to view users")

    return user


# --- Update Users Status (Admin only) ---
@router.patch("/{user_id}", response_model=UserOut, dependencies=[Depends(get_admin_user_payload)])
def update_user_status(
        user_id: int,
        user_update: UserUpdate,
        db: Session = Depends(get_db)
):
    user = db.query(DBUser).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Update fields provided in the request
    update_data = user_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(user, key, value)

    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# --- Log In ---
@router.post("/login", response_model=Token)
def login(form_data: TokenRequest, db: Session = Depends(get_db)):
    """
        Authenticates the user and returns a JWT access token if credentials are valid
        and the account status is ACTIVE.
    """
    # Retrieve user
    user = db.query(DBUser).filter_by(username=form_data.username).first()

    # Check credentials
    if not user or not verify_password(form_data.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if user is approved so to allow log in or not
    if user.status != UserStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account is {user.status.value}. Access denied. Requires admin approval."
        )

    # Create JWT
    access_token = create_access_token(
        data={
            "sub": user.username,
            "user_id": user.id,
            "role": user.role.value,
            "status": user.status.value
        }
    )

    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserOut, status_code=status.HTTP_200_OK)
def get_me(current_user: DBUser = Depends(get_active_user)):
    """
        Retrieve the current user's information. Requires a valid, active JWT token.
    """
    # The user is authenticated and active
    return current_user


# --- Delete User ---
@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(get_admin_user_payload)])
def delete_user(user_id: int, db: Session = Depends(get_db)):
    """
    Only Admin can delete a user account.
    """
    user = db.query(DBUser).filter_by(id=user_id).first()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    db.delete(user)
    db.commit()
