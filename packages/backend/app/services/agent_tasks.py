"""Create owner-isolated durable task identities without committing caller transactions."""

from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.source_reader import capture_source_versions
from app.models.agent_task import AgentTask


def _id(value: str) -> str:
    try:
        return str(UUID(value))
    except (TypeError, ValueError, AttributeError):
        raise HTTPException(status_code=404, detail="任务不存在") from None


async def create_task(session: AsyncSession, *, owner_id: str, question: str, request_key: str) -> AgentTask:
    if (not isinstance(question, str) or not question.strip() or len(question) > 20000
            or not isinstance(request_key, str) or not request_key.strip() or len(request_key) > 200):
        raise ValueError("invalid task request")
    owner_id = _id(owner_id)
    versions = await capture_source_versions(session, owner_id)
    statement = (insert(AgentTask).values(id=str(uuid4()), owner_id=owner_id, request_key=request_key,
                                         question=question, source_versions=versions, status="queued")
                 .on_conflict_do_nothing(index_elements=[AgentTask.owner_id, AgentTask.request_key])
                 .returning(AgentTask.id))
    await session.execute(statement)
    task = (await session.execute(select(AgentTask).where(AgentTask.owner_id == owner_id,
                                                          AgentTask.request_key == request_key))).scalar_one()
    if task.question != question:
        raise HTTPException(status_code=409, detail="请求标识已用于其他任务")
    return task


async def get_owned_task(session: AsyncSession, task_id: str, owner_id: str) -> AgentTask:
    task_id, owner_id = _id(task_id), _id(owner_id)
    task = (await session.execute(select(AgentTask).where(AgentTask.id == task_id,
                                                          AgentTask.owner_id == owner_id))).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task
