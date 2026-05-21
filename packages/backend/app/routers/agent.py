"""Agent 管理路由 ── CRUD"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func

from app.core.db import async_session
from app.models.agent import Agent
from app.models.user import User
from app.core.security import get_current_user, require_super_admin
from app.schemas.chat import (
    AgentCreate,
    AgentUpdate,
    AgentResponse,
    AgentListResponse,
)

router: APIRouter = APIRouter(prefix="/agents", tags=["Agent 管理"])


@router.post("", response_model=AgentResponse, status_code=201)
async def create_agent(
    body: AgentCreate,
    _user: User = Depends(require_super_admin),
) -> AgentResponse:
    """创建 Agent"""
    async with async_session() as session:
        agent = Agent(
            name=body.name,
            description=body.description,
            knowledge_ids=body.knowledge_ids,
            prompt_template=body.prompt_template,
        )
        session.add(agent)
        await session.commit()
        await session.refresh(agent)
        return AgentResponse.model_validate(agent)


@router.get("", response_model=AgentListResponse)
async def list_agents(
    page: int = 1,
    size: int = 20,
    current_user: User = Depends(get_current_user),
) -> AgentListResponse:
    """获取 Agent 列表"""
    async with async_session() as session:
        count_result = await session.execute(select(func.count(Agent.id)))
        total: int = count_result.scalar() or 0

        result = await session.execute(
            select(Agent)
            .order_by(Agent.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        agents = result.scalars().all()
        return AgentListResponse(
            total=total,
            items=[AgentResponse.model_validate(a) for a in agents],
        )


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: str,
    current_user: User = Depends(get_current_user),
) -> AgentResponse:
    """获取 Agent 详情"""
    async with async_session() as session:
        result = await session.execute(select(Agent).where(Agent.id == agent_id))
        agent = result.scalar_one_or_none()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent 不存在")
        return AgentResponse.model_validate(agent)


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: str,
    body: AgentUpdate,
    _user: User = Depends(require_super_admin),
) -> AgentResponse:
    """更新 Agent"""
    async with async_session() as session:
        result = await session.execute(select(Agent).where(Agent.id == agent_id))
        agent = result.scalar_one_or_none()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent 不存在")

        update_data = body.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(agent, key, value)

        await session.commit()
        await session.refresh(agent)
        return AgentResponse.model_validate(agent)


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(
    agent_id: str,
    _user: User = Depends(require_super_admin),
) -> None:
    """删除 Agent"""
    async with async_session() as session:
        result = await session.execute(select(Agent).where(Agent.id == agent_id))
        agent = result.scalar_one_or_none()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent 不存在")
        await session.delete(agent)
        await session.commit()
