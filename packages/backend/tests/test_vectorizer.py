"""Embedding inference must remain serialized while cancelled threads finish."""

import asyncio
import threading

import pytest

from app.services import vectorizer


@pytest.mark.parametrize("cancel_count", [1, 2])
async def test_cancelled_inference_keeps_lock_until_worker_finishes(monkeypatch, cancel_count):
    started = threading.Event()
    release = threading.Event()
    state_lock = threading.Lock()
    active = 0
    peak = 0

    class Model:
        def encode(self, texts, **kwargs):
            nonlocal active, peak
            with state_lock:
                active += 1
                peak = max(peak, active)
            started.set()
            try:
                assert release.wait(timeout=5), "Test did not release inference worker"
                return []
            finally:
                with state_lock:
                    active -= 1

    monkeypatch.setattr(vectorizer, "get_model", lambda: Model())
    monkeypatch.setattr(vectorizer, "_encoding_lock", asyncio.Lock())
    first = asyncio.create_task(vectorizer.encode_texts(["first"]))
    second = None
    try:
        assert await asyncio.to_thread(started.wait, 5)
        first.cancel()
        second = asyncio.create_task(vectorizer.encode_texts(["second"]))
        # Allow cancellation cleanup and the waiting request to enter their await points.
        await asyncio.sleep(0.05)
        if cancel_count == 2:
            first.cancel()
            await asyncio.sleep(0.05)
        release.set()
        results = await asyncio.gather(first, second, return_exceptions=True)
        assert isinstance(results[0], asyncio.CancelledError)
        assert results[1] == []
        assert peak == 1
    finally:
        release.set()
        tasks = [first] if second is None else [first, second]
        await asyncio.gather(*tasks, return_exceptions=True)
