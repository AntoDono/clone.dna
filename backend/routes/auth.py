"""
Auth router — username/password account creation and login.

Endpoints:
  POST /auth/register — create a new account, returns JWT
  POST /auth/login    — verify credentials, returns JWT

get_current_user() — FastAPI Depends() used by protected routes.
"""

import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel as PydanticModel

from db import db
from models import User

router = APIRouter(prefix="/auth")

SECRET_KEY = os.getenv("SECRET_KEY", "clone-dna-dev-secret-change-in-prod")
ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = 30

_pwd = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
_bearer = HTTPBearer(auto_error=False)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_token(user: User) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=TOKEN_EXPIRE_DAYS)
    return jwt.encode(
        {"sub": user.username, "user_id": user.id, "exp": expire},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def _decode_token(token: str) -> User:
    """Decode a raw JWT string and return the corresponding User row."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int | None = payload.get("user_id")
        if user_id is None:
            raise HTTPException(401, "Invalid token")
    except JWTError:
        raise HTTPException(401, "Invalid or expired token")
    try:
        return User.get_by_id(user_id)
    except User.DoesNotExist:
        raise HTTPException(401, "User not found")


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    token: str | None = None,
) -> User:
    """FastAPI dependency — decodes the Bearer token and returns the User row.

    Accepts the token via Authorization header or ?token= query param (for
    SSE endpoints where EventSource cannot set custom headers).
    Raises 401 if the token is missing, expired, or invalid.
    """
    raw = token or (creds.credentials if creds else None)
    if not raw:
        raise HTTPException(401, "Not authenticated")
    return _decode_token(raw)


# ── Request / response schemas ────────────────────────────────────────────────

class AuthRequest(PydanticModel):
    username: str
    password: str


class AuthResponse(PydanticModel):
    token: str
    username: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/register", response_model=AuthResponse, status_code=201)
def register(body: AuthRequest):
    """Create a new account. Returns a JWT on success."""
    username = body.username.strip()
    if len(username) < 2:
        raise HTTPException(422, "Username must be at least 2 characters")
    if len(body.password) < 4:
        raise HTTPException(422, "Password must be at least 4 characters")

    if User.select().where(User.username == username).exists():
        raise HTTPException(409, "Username already taken")

    with db.atomic():
        user = User.create(
            username=username,
            password_hash=_pwd.hash(body.password),
        )

    return AuthResponse(token=_make_token(user), username=user.username)


@router.post("/login", response_model=AuthResponse)
def login(body: AuthRequest):
    """Verify credentials and return a JWT."""
    try:
        user = User.get(User.username == body.username.strip())
    except User.DoesNotExist:
        raise HTTPException(401, "Invalid username or password")

    if not _pwd.verify(body.password, user.password_hash):
        raise HTTPException(401, "Invalid username or password")

    return AuthResponse(token=_make_token(user), username=user.username)
