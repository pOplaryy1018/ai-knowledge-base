from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException


def test_task_snapshot_preserves_terminal_state():
    from app.models.import_task import ImportTask
    from app.services.import_tasks import task_event

    task = ImportTask(id="task", status="completed", chunks_count=3, percent=100)
    event = task_event(task)
    assert event["type"] == "complete"
    assert event["total_chunks"] == 3
    task.status, task.error_message = "failed", "queue offline"
    assert task_event(task) == {"type": "error", "error": "queue offline"}


def test_task_access_requires_owner_or_admin():
    from app.models.import_task import ImportTask
    from app.models.user import User
    from app.services.import_tasks import verify_task_access

    task = ImportTask(user_id="alice")
    with pytest.raises(HTTPException) as error:
        verify_task_access(task, User(id="bob", role="user"))
    assert error.value.status_code == 403
    verify_task_access(task, User(id="alice", role="user"))
    verify_task_access(task, User(id="bob", role="super_admin"))


async def test_enqueue_failure_marks_task_retryable(monkeypatch):
    from app.models.import_task import ImportTask
    from app.models.knowledge import KnowledgeFile
    from app.services import import_tasks

    task = ImportTask(id="task", file_id="file", status="pending")
    file = KnowledgeFile(id="file", active_task_id="task", status="pending")
    session = AsyncMock()
    session.get.return_value = task
    result = MagicMock()
    result.scalar_one_or_none.return_value = file
    session.execute.return_value = result
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(import_tasks, "async_session", lambda: ctx)
    queue = AsyncMock(side_effect=ConnectionError("offline"))
    with pytest.raises(HTTPException) as error:
        await import_tasks.enqueue_import(task, file, queue)
    assert error.value.status_code == 503
    assert file.status == task.status == "failed"
    assert file.error_message
    session.commit.assert_awaited_once()


@pytest.mark.parametrize("status", ["processing", "completed"])
async def test_enqueue_response_failure_preserves_started_task(monkeypatch, status):
    from app.models.import_task import ImportTask
    from app.models.knowledge import KnowledgeFile
    from app.services import import_tasks

    task = ImportTask(id="task", file_id="file", status=status)
    file = KnowledgeFile(id="file", active_task_id="task", status=status)
    session = AsyncMock()
    session.get.return_value = task
    result = MagicMock()
    result.scalar_one_or_none.return_value = file
    session.execute.return_value = result
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(import_tasks, "async_session", lambda: ctx)
    with pytest.raises(HTTPException):
        await import_tasks.enqueue_import(task, file, AsyncMock(side_effect=ConnectionError()))
    assert task.status == file.status == status
    session.commit.assert_not_awaited()


async def test_pending_backlog_does_not_timeout(monkeypatch):
    from datetime import datetime, timedelta, timezone

    from app.models.import_task import ImportTask
    from app.models.user import User
    from app.services import import_tasks

    task = ImportTask(id="task", user_id="alice", status="pending", updated_at=datetime.now(timezone.utc) - timedelta(hours=2))
    session = AsyncMock()
    session.get.return_value = task
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(import_tasks, "async_session", lambda: ctx)
    monkeypatch.setattr(import_tasks, "queue_job_exists", AsyncMock(return_value=True))
    assert (await import_tasks.load_task("task", User(id="alice", role="user"))).status == "pending"
    session.commit.assert_not_awaited()


def test_upload_and_cleanup_share_storage_root(tmp_path, monkeypatch):
    from app.api.import_api import UPLOAD_DIR
    from app.services import file_storage

    assert UPLOAD_DIR == file_storage.UPLOAD_ROOT
    monkeypatch.setattr(file_storage, "UPLOAD_ROOT", tmp_path)
    source = tmp_path / "uploaded.txt"
    source.write_text("hello")
    outside = tmp_path.parent / "outside-regression.txt"
    # Outside-root paths must be refused; no file outside the test root is created.
    file_storage.remove_uploads([str(source), str(outside)])
    assert not source.exists()


def test_explicit_delete_cleans_tracked_legacy_source(tmp_path, monkeypatch):
    from app.services import file_storage

    legacy = tmp_path / "legacy"
    legacy.mkdir()
    source = legacy / "old.txt"
    source.write_text("old document")
    outside = tmp_path / "keep.txt"
    outside.write_text("unrelated")
    monkeypatch.setattr(file_storage, "UPLOAD_ROOT", tmp_path / "current")
    monkeypatch.setattr(file_storage, "LEGACY_UPLOAD_ROOT", legacy)
    file_storage.remove_uploads([str(source), str(outside)])
    assert not source.exists()
    assert outside.read_text() == "unrelated"

async def test_confirmed_lost_pending_job_fails_task_and_file_atomically(monkeypatch):
    from datetime import datetime, timedelta, timezone

    from app.models.import_task import ImportTask
    from app.models.knowledge import KnowledgeFile
    from app.models.user import User
    from app.services import import_tasks

    task = ImportTask(id="task", file_id="file", user_id="alice", status="pending", updated_at=datetime.now(timezone.utc) - timedelta(seconds=901))
    file = KnowledgeFile(id="file", active_task_id="task", status="pending")
    session = AsyncMock()
    session.get.return_value = task
    result = MagicMock()
    result.scalar_one_or_none.return_value = file
    session.execute.return_value = result
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(import_tasks, "async_session", lambda: ctx)
    queue_job_exists = AsyncMock(return_value=False)
    monkeypatch.setattr(import_tasks, "queue_job_exists", queue_job_exists)
    commit_states = []

    async def commit():
        commit_states.append((task.status, file.status, task.error_message, file.error_message))

    session.commit.side_effect = commit
    loaded = await import_tasks.load_task("task", User(id="alice", role="user"))
    assert loaded is task
    queue_job_exists.assert_awaited_once_with("task")
    session.commit.assert_awaited_once()
    assert commit_states == [("failed", "failed", "任务丢失或处理超时，请重试", "任务丢失或处理超时，请重试")]


@pytest.mark.parametrize("active_task_id", ["task", "replacement-task"])
async def test_finish_import_locks_parent_before_file_and_commits_only_active_task(monkeypatch, active_task_id):
    from sqlalchemy.dialects import postgresql

    from app.models.import_task import ImportTask
    from app.models.knowledge import KnowledgeBase, KnowledgeFile
    from app.services import import_tasks, vectorizer

    task = ImportTask(id="task", file_id="file", status="processing", chunks_count=0)
    file = KnowledgeFile(id="file", knowledge_base_id="kb", active_task_id=active_task_id, status="processing", chunks_count=0)
    kb = KnowledgeBase(id="kb")
    session = AsyncMock()
    session.get.return_value = task
    executed = []
    responses = iter(["kb", kb, file, None])

    async def execute(statement):
        executed.append(str(statement.compile(dialect=postgresql.dialect())))
        result = MagicMock()
        result.scalar_one_or_none.return_value = next(responses)
        return result

    session.execute.side_effect = execute
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(import_tasks, "async_session", lambda: ctx)
    stored = AsyncMock(return_value=2)
    monkeypatch.setattr(vectorizer, "store_chunks", stored)
    commit_states = []

    async def commit():
        commit_states.append((task.status, file.status, task.chunks_count, file.chunks_count))

    session.commit.side_effect = commit
    chunks, vectors, metadata = ["chunk"], [[1.0]], {"filename": "document.txt"}
    result = await import_tasks.finish_import("task", chunks, vectors, metadata)
    lock_sql = [sql for sql in executed if "FOR UPDATE" in sql]
    assert len(lock_sql) == 2
    assert "FROM knowledge_bases" in lock_sql[0]
    assert "FROM knowledge_files" in lock_sql[1]
    if active_task_id == "replacement-task":
        assert result is None
        stored.assert_not_awaited()
        session.commit.assert_not_awaited()
        assert not any(sql.startswith("DELETE") for sql in executed)
        assert task.status == file.status == "processing"
        assert task.chunks_count == file.chunks_count == 0
        return
    assert result == 2
    assert any(sql.startswith("DELETE FROM knowledge_items") for sql in executed)
    stored.assert_awaited_once_with("kb", chunks, vectors, file_id="file", source_metadata_base=metadata, session=session)
    session.commit.assert_awaited_once()
    assert commit_states == [("completed", "completed", 2, 2)]
    assert task.percent == 100
    assert task.error_message is file.error_message is None
