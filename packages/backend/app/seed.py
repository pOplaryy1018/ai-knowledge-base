"""数据库种子脚本 ── 创建初始超级管理员用户"""

import asyncio
import os

from sqlalchemy import select

from app.core.db import async_session
from app.core.security import hash_password
from app.models import User

# 默认管理员密码，通过环境变量 SEED_ADMIN_PASSWORD 覆盖
_SEED_ADMIN_PASSWORD = os.getenv("SEED_ADMIN_PASSWORD", "devpassword")


async def seed_admin() -> None:
    """检查是否存在管理员账户，不存在则创建"""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.role == "super_admin")
        )
        existing: User | None = result.scalar_one_or_none()

        if existing:
            print(f"[seed] 超级管理员已存在: {existing.username}")
            return

        admin: User = User(
            username="admin",
            hashed_password=hash_password(_SEED_ADMIN_PASSWORD),
            role="super_admin",
        )
        session.add(admin)
        await session.commit()
        print("[seed] 初始超级管理员已创建:")
        print("       用户名: admin")
        print(f"       密码: {_SEED_ADMIN_PASSWORD}")
        print(f"      角色: {admin.role}")
        print(f"       ID: {admin.id}")


if __name__ == "__main__":
    asyncio.run(seed_admin())
