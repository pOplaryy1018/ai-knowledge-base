"""认证路由 ── 登录、刷新令牌、获取当前用户"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select

from app.core.db import async_session
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RefreshTokenRequest,
    RegisterRequest,
    RoleInfo,
    TokenRefreshResponse,
    UserInfo,
    UserUpdate,
    VALID_ROLES,
)

router: APIRouter = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest) -> LoginResponse:
    """用户登录：验证用户名密码，返回 JWT 令牌和用户信息"""
    async with async_session() as session:
        result = await session.execute(select(User).where(User.username == req.username))
        user: User | None = result.scalar_one_or_none()

    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    access_token: str = create_access_token(
        user_id=user.id,
        role=user.role,
    )
    refresh_token_value: str = create_refresh_token(user_id=user.id)

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token_value,
        user=UserInfo.model_validate(user),
    )


@router.post("/register", response_model=UserInfo, status_code=201)
async def register(req: RegisterRequest) -> UserInfo:
    """用户自助注册：创建 user 角色账户"""
    async with async_session() as session:
        existing = await session.execute(
            select(User).where(User.username == req.username)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="该用户名已被使用",
            )

        new_user: User = User(
            username=req.username,
            hashed_password=hash_password(req.password),
            role="user",
        )
        session.add(new_user)
        await session.commit()
        await session.refresh(new_user)

    return UserInfo.model_validate(new_user)


@router.post("/refresh", response_model=TokenRefreshResponse)
async def refresh_token(req: RefreshTokenRequest) -> TokenRefreshResponse:
    """刷新 Access Token：使用 Refresh Token 换取新的 Access Token"""
    payload: dict[str, object] = decode_token(req.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh Token 类型错误",
        )

    user_id: object | None = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh Token 无效",
        )

    # 从数据库查询用户获取最新的角色信息
    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user: User | None = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已被删除",
        )

    new_access_token: str = create_access_token(
        user_id=user.id,
        role=user.role,
    )

    return TokenRefreshResponse(access_token=new_access_token)


@router.get("/me", response_model=UserInfo)
async def get_me(current_user: User = Depends(get_current_user)) -> UserInfo:
    """获取当前登录用户信息"""
    return UserInfo.model_validate(current_user)


@router.get("/users", response_model=list[UserInfo])
async def list_users(
    current_user: User = Depends(get_current_user),
) -> list[UserInfo]:
    """管理员获取用户列表（仅 super_admin 可操作）"""
    if current_user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅超级管理员可查看用户列表",
        )

    async with async_session() as session:
        result = await session.execute(
            select(User).order_by(User.created_at.desc())
        )
        users = result.scalars().all()

    return [UserInfo.model_validate(u) for u in users]


@router.post("/users", response_model=UserInfo)
async def create_user(
    username: str,
    password: str,
    role: str = "user",
    current_user: User = Depends(get_current_user),
) -> UserInfo:
    """管理员创建新用户（仅 super_admin 可操作）"""
    if current_user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅超级管理员可创建用户",
        )

    if role not in ("super_admin", "user"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的角色值: {role}，可选: super_admin, user",
        )

    async with async_session() as session:
        # 检查用户名是否已存在
        existing = await session.execute(select(User).where(User.username == username))
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="该用户名已被使用",
            )

        new_user: User = User(
            username=username,
            hashed_password=hash_password(password),
            role=role,
        )
        session.add(new_user)
        await session.commit()
        await session.refresh(new_user)

    return UserInfo.model_validate(new_user)


@router.put("/users/{user_id}", response_model=UserInfo)
async def update_user(
    user_id: str,
    body: UserUpdate,
    current_user: User = Depends(get_current_user),
) -> UserInfo:
    """管理员更新用户角色（仅 super_admin 可操作）"""
    if current_user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅超级管理员可修改用户",
        )

    if body.role not in VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的角色值: {body.role}，可选: {', '.join(sorted(VALID_ROLES))}",
        )

    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user: User | None = result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")

        if user.id == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="不允许修改自己的角色",
            )

        user.role = body.role
        await session.commit()
        await session.refresh(user)

    return UserInfo.model_validate(user)


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: str,
    current_user: User = Depends(get_current_user),
) -> None:
    """管理员硬删除用户（仅 super_admin 可操作）"""
    if current_user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅超级管理员可删除用户",
        )

    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user: User | None = result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")

        if user.id == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="不允许删除自己",
            )

        await session.delete(user)
        await session.commit()


# ── 角色定义（静态元数据 + 动态用户数）──
ROLE_DEFS: dict[str, dict[str, str]] = {
    "super_admin": {
        "label": "超级管理员",
        "description": "拥有所有权限，可管理用户、配置系统、查看全局数据",
        "permissions": "全部",
    },
    "user": {
        "label": "普通用户",
        "description": "可管理自己的知识库、条目，使用 AI 问答",
        "permissions": "知识库管理、条目管理、文档导入、AI 问答",
    },
}


@router.get("/roles", response_model=list[RoleInfo])
async def list_roles(
    current_user: User = Depends(get_current_user),
) -> list[RoleInfo]:
    """获取角色定义列表（含各角色实际用户数）"""
    async with async_session() as session:
        result = await session.execute(
            select(User.role, func.count(User.id)).group_by(User.role)
        )
        role_counts: dict[str, int] = {row[0]: row[1] for row in result.all()}

    roles: list[RoleInfo] = []
    for role_value, definition in ROLE_DEFS.items():
        roles.append(
            RoleInfo(
                role=role_value,
                label=definition["label"],
                description=definition["description"],
                permissions=definition["permissions"],
                user_count=role_counts.get(role_value, 0),
            )
        )
    return roles
