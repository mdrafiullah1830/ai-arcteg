"""Authentication: register, login, profile, user admin."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserOut
from app.schemas.common import OkResponse, Paged

router = APIRouter(tags=["auth"])


@router.post("/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    # First account to exist becomes ADMIN so the system is never locked out.
    if db.query(User).count() == 0:
        role = "ADMIN"
    else:
        role = payload.role
    user = User(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=role,
    )
    db.add(user)
    db.commit()
    token = create_access_token(user.email, user.role)
    return TokenResponse(access_token=token, role=user.role, name=user.name, email=user.email)


@router.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.query(User).filter(User.email == payload.email).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    token = create_access_token(user.email, user.role)
    return TokenResponse(access_token=token, role=user.role, name=user.name, email=user.email)


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.get("/users", response_model=Paged[UserOut])
def list_users(
    limit: int = 50,
    offset: int = 0,
    _: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
) -> Paged[UserOut]:
    total = db.query(User).count()
    items = db.query(User).order_by(User.id).offset(offset).limit(limit).all()
    return Paged[UserOut].model_validate(
        {"items": items, "total": total, "limit": limit, "offset": offset}
    )


@router.delete("/users/{user_id}", response_model=OkResponse)
def delete_user(
    user_id: int,
    current: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
) -> OkResponse:
    if user_id == current.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot delete your own account")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    db.delete(user)
    db.commit()
    return OkResponse(detail="User deleted")
