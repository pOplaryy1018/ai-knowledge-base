"""认证相关 Pydantic 请求/响应模型"""

from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """登录请求体"""
    username: str = Field(..., min_length=3, description="用户名")
    password: str = Field(..., min_length=6, description="登录密码")


class RefreshTokenRequest(BaseModel):
    """刷新 Token 请求体"""
    refresh_token: str = Field(..., description="刷新令牌")


class UserInfo(BaseModel):
    """用户公开信息响应"""
    id: str
    username: str
    role: str
    created_at: datetime

    model_config = {"from_attributes": True}


class RegisterRequest(BaseModel):
    """用户注册请求体（默认注册为 user 角色）"""
    username: str = Field(..., min_length=3, description="用户名")
    password: str = Field(..., min_length=6, description="登录密码")


class LoginResponse(BaseModel):
    """登录成功响应"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserInfo


class TokenRefreshResponse(BaseModel):
    """刷新 Token 响应"""
    access_token: str
    token_type: str = "bearer"


class RoleInfo(BaseModel):
    """角色定义信息（含实际用户数）"""
    role: str
    label: str
    description: str
    permissions: str
    user_count: int


VALID_ROLES: set[str] = {"super_admin", "user"}


class UserUpdate(BaseModel):
    """管理员更新用户（仅允许修改角色）"""
    role: str = Field(..., description="新角色")
