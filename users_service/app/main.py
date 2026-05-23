from __future__ import annotations

import hashlib
import os
from datetime import date, datetime, timedelta, timezone
from enum import Enum

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from prometheus_fastapi_instrumentator import Instrumentator

from cmas_shared.observability import CorrelationIdMiddleware, configure_logging

from .database import get_db
from .models import UserORM

configure_logging("users_service")

app = FastAPI(
    title="Users Service",
    description="Сервис управления пользователями и ролями",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Correlation-ID"],
)
app.add_middleware(CorrelationIdMiddleware, service_name="users_service")

Instrumentator().instrument(app).expose(app)

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-key-change-me")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")


class UserRole(str, Enum):
    student = "student"
    commandant = "commandant"
    admin = "admin"


class UserBase(BaseModel):
    full_name: str
    phone: str
    birth_date: date
    email: str
    role: UserRole = UserRole.student


class UserCreate(BaseModel):
    full_name: str = Field(..., min_length=2)
    phone: str = Field(..., pattern=r"^\+?[0-9]{10,15}$")
    birth_date: date
    email: str = Field(..., pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    role: UserRole = UserRole.student
    password: str = Field(..., min_length=6)


class UserOut(UserBase):
    id: int
    room_id: int | None = None


class LoginIn(BaseModel):
    email: str = Field(..., pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(..., min_length=1)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class AssignRoomIn(BaseModel):
    room_id: int | None = None


def _hash_password(password: str) -> str:
    normalized = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return pwd_context.hash(normalized)


def _verify_password(plain_password: str, hashed_password: str) -> bool:
    normalized = hashlib.sha256(plain_password.encode("utf-8")).hexdigest()
    return pwd_context.verify(normalized, hashed_password)


def _create_access_token(user: UserORM) -> tuple[str, int]:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return token, int(timedelta(minutes=JWT_EXPIRE_MINUTES).total_seconds())


def _to_user_out(user: UserORM) -> UserOut:
    return UserOut(
        id=user.id,
        full_name=user.full_name,
        phone=user.phone,
        birth_date=user.birth_date,
        email=user.email,
        role=UserRole(user.role),
        room_id=user.room_id,
    )


def _get_user_by_email(db: Session, email: str) -> UserORM | None:
    return db.query(UserORM).filter(UserORM.email == email.lower()).first()


async def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> UserORM:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
    )
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        raise credentials_exception

    user = db.query(UserORM).filter(UserORM.id == user_id).first()
    if not user:
        raise credentials_exception
    return user


@app.get("/")
async def root():
    return {"service": "Users Service", "status": "running"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(
    payload: UserCreate,
    db: Session = Depends(get_db),
) -> UserOut:
    if _get_user_by_email(db, payload.email):
        raise HTTPException(status_code=409, detail="User with this email already exists")

    user = UserORM(
        full_name=payload.full_name,
        phone=payload.phone,
        birth_date=payload.birth_date,
        email=payload.email.lower(),
        role=payload.role.value,
        room_id=None,
        password_hash=_hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _to_user_out(user)


@app.post("/login", response_model=TokenOut)
async def login(payload: LoginIn, db: Session = Depends(get_db)) -> TokenOut:
    user = _get_user_by_email(db, payload.email)
    if not user or not _verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token, expires_in = _create_access_token(user)
    return TokenOut(access_token=token, expires_in=expires_in, user=_to_user_out(user))


@app.get("/users", response_model=list[UserOut])
async def list_users(
    room_id: int | None = None,
    _: UserORM = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[UserOut]:
    q = db.query(UserORM)
    if room_id is not None:
        q = q.filter(UserORM.room_id == room_id)
    users = q.order_by(UserORM.id.asc()).all()
    return [_to_user_out(user) for user in users]


@app.get("/users/{user_id}", response_model=UserOut)
async def get_user(
    user_id: int, _: UserORM = Depends(get_current_user), db: Session = Depends(get_db)
) -> UserOut:
    user = db.query(UserORM).filter(UserORM.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _to_user_out(user)


@app.put("/users/{user_id}/room", response_model=UserOut)
async def assign_room(
    user_id: int,
    payload: AssignRoomIn,
    _: UserORM = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserOut:
    user = db.query(UserORM).filter(UserORM.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.room_id = payload.room_id
    db.commit()
    db.refresh(user)
    return _to_user_out(user)
