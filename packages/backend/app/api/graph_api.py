"""Owner-scoped graph build status and explicit retry."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.api.source_api import owned_source
from app.core.config import settings
from app.core.db import async_session
from app.core.security import get_current_user
from app.models.graph_task import GraphBuildTask
from app.models.user import User

router = APIRouter(tags=["资料图谱"])


def _status(source_id: str, revision_id: str | None, task: GraphBuildTask | None) -> dict[str, Any]:
    return {
        "source_id": source_id, "revision_id": revision_id,
        "status": task.status if task else ("not_indexed" if revision_id else "not_ready"),
        "attempts": task.attempts if task else 0,
        "relation_count": task.relation_count if task else 0,
        "rejected_count": task.rejected_count if task else 0,
        "error_code": task.error_code if task else None,
    }


@router.get("/sources/{source_id}/graph")
async def graph_status(source_id: uuid.UUID, user: User = Depends(get_current_user)) -> dict[str, Any]:
    async with async_session() as session:
        source = await owned_source(session, str(source_id), user.id)
        if not source.current_revision_id:
            return _status(source.id, None, None)
        task = (await session.execute(select(GraphBuildTask).where(
            GraphBuildTask.source_id == source.id,
            GraphBuildTask.revision_id == source.current_revision_id,
            GraphBuildTask.extractor_version == settings.graph_extractor_version))).scalar_one_or_none()
        return _status(source.id, source.current_revision_id, task)


@router.post("/sources/{source_id}/graph/retry", status_code=202)
async def retry_graph(source_id: uuid.UUID, user: User = Depends(get_current_user)) -> dict[str, Any]:
    async with async_session() as session:
        source = await owned_source(session, str(source_id), user.id, lock=True)
        if source.archived_at or not source.current_revision_id:
            raise HTTPException(409, "资料来源没有可索引的当前版本")
        task = (await session.execute(select(GraphBuildTask).where(
            GraphBuildTask.source_id == source.id,
            GraphBuildTask.revision_id == source.current_revision_id,
            GraphBuildTask.extractor_version == settings.graph_extractor_version)
            .with_for_update())).scalar_one_or_none()
        if task is None or task.status != "failed":
            raise HTTPException(409, "当前图谱任务不能重试")
        task.status = "pending"
        task.error_code = None
        task.lease_until = None
        await session.commit()
        response = _status(source.id, source.current_revision_id, task)
        task_id, next_attempt = task.id, task.attempts + 1
    try:
        from app.api.import_api import get_arq

        await (await get_arq()).enqueue_job("process_graph_build", task_id,
                                           _job_id=f"graph:{task_id}:{next_attempt}")
    except Exception:
        # The durable pending row is discovered by the worker maintenance tick.
        pass
    return response
