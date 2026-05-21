"""安全工具 ── 密码哈希、JWT 令牌生成与验证"""

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select

from app.core.config import settings
from app.core.db import async_session
from app.models.user import User

# ── 密码哈希 ──
pwd_context: CryptContext = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── Bearer Token 提取器 ──
bearer_scheme: HTTPBearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    """对明文密码进行 bcrypt 哈希"""
    return str(pwd_context.hash(password))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证明文密码与哈希值是否匹配"""
    return bool(pwd_context.verify(plain_password, hashed_password))


# ── JWT 令牌 ──


def create_access_token(user_id: str, role: str) -> str:
    """创建 JWT Access Token"""
    expire: datetime = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_access_token_expire_minutes
    )
    payload: dict[str, Any] = {
        "sub": user_id,
        "role": role,
        "type": "access",
        "exp": expire,
    }
    return str(jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm))


def create_refresh_token(user_id: str) -> str:
    """创建 JWT Refresh Token"""
    expire: datetime = datetime.now(timezone.utc) + timedelta(
        days=settings.jwt_refresh_token_expire_days
    )
    payload: dict[str, Any] = {
        "sub": user_id,
        "type": "refresh",
        "exp": expire,
    }
    return str(jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm))


def decode_token(token: str) -> dict[str, Any]:
    """解码 JWT Token，失败时抛出 HTTPException"""
    try:
        result: dict[str, Any] = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        return result
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> User:
    """FastAPI 依赖注入 ── 从 Bearer Token 解析当前用户"""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证令牌",
        )

    payload: dict[str, Any] = decode_token(credentials.credentials)
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 类型错误，请使用 access_token",
        )

    user_id: Any = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 中缺少用户标识",
        )

    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user: User | None = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已被删除",
        )

    return user


async def require_super_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """FastAPI 依赖注入 ── 确保当前用户是超级管理员"""
    if current_user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅超级管理员可执行此操作",
        )
    return current_user
