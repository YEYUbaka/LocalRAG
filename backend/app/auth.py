"""JWT authentication module with strict claim validation."""

from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.security.secrets import build_auth_config, EnvironmentSecretProvider

ALGORITHM_ALLOWLIST = ("HS256",)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

_auth_config = build_auth_config(EnvironmentSecretProvider())


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    config = _auth_config
    now = datetime.now(timezone.utc)
    to_encode = data.copy()
    to_encode.update(
        {
            "iss": config.issuer,
            "aud": config.audience,
            "iat": now,
            "nbf": now,
            "exp": now + (expires_delta or timedelta(minutes=config.access_token_minutes)),
            "type": "access",
        }
    )
    return jwt.encode(to_encode, config.secret, algorithm="HS256")


def decode_token(token: str) -> dict:
    config = _auth_config
    try:
        payload = jwt.decode(
            token,
            config.secret,
            algorithms=list(ALGORITHM_ALLOWLIST),
            issuer=config.issuer,
            audience=config.audience,
            options={
                "verify_iat": True,
                "verify_nbf": True,
                "verify_exp": True,
                "verify_iss": True,
                "verify_aud": True,
                "verify_sub": True,
                "require": ["sub", "iss", "aud", "iat", "nbf", "exp", "type"],
            },
        )
    except JWTError:
        raise HTTPException(status_code=401, detail="无效的认证凭据")
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="无效的认证凭据")
    return payload


def _get_user_id(payload: dict) -> int:
    raw = payload.get("sub")
    try:
        user_id = int(raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="无效的认证凭据")
    if user_id <= 0:
        raise HTTPException(status_code=401, detail="无效的认证凭据")
    return user_id


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """FastAPI dependency: extract and verify user from JWT token."""
    from app.models import User
    from app.main import SessionLocal

    payload = decode_token(credentials.credentials)
    user_id = _get_user_id(payload)

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            raise HTTPException(status_code=401, detail="用户不存在")
        return user
    finally:
        db.close()


async def require_owner(user=Depends(get_current_user)) -> object:
    """FastAPI dependency: only the installation owner may pass.

    Phase 0 defines the owner as the user with the lowest user ID.
    """
    from app.models import User
    from app.main import SessionLocal

    db = SessionLocal()
    try:
        lowest = db.query(User.id).order_by(User.id.asc()).first()
    finally:
        db.close()
    if lowest is None or lowest[0] != user.id:
        raise HTTPException(status_code=403, detail="无权限")
    return user
