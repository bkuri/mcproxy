"""Tests for api_parallel.py - Parallel Execution Support."""

import asyncio
from typing import List
from unittest.mock import MagicMock

import pytest

from api_parallel import (
    ParallelExecutor,
    ParallelResult,
    create_parallel_executor,
    DEFAULT_MAX_CONCURRENCY,
)


class TestParallelResult:
    """Tests for ParallelResult dataclass."""

    def test_parallel_result_fulfilled(self):
        result = ParallelResult(status="fulfilled", result={"data": 42})

        assert result.status == "fulfilled"
        assert result.result == {"data": 42}
        assert result.error is None

    def test_parallel_result_rejected(self):
        result = ParallelResult(status="rejected", error="ValueError: bad input")

        assert result.status == "rejected"
        assert result.result is None
        assert result.error == "ValueError: bad input"


class TestParallelExecutorInit:
    """Tests for ParallelExecutor initialization."""

    def test_default_concurrency(self):
        executor = ParallelExecutor()

        assert executor.max_concurrency == DEFAULT_MAX_CONCURRENCY

    def test_custom_concurrency(self):
        executor = ParallelExecutor(max_concurrency=10)

        assert executor.max_concurrency == 10


class TestParallelExecutorExecute:
    """Tests for ParallelExecutor.execute_parallel()."""

    @pytest.mark.asyncio
    async def test_empty_callables_returns_empty_list(self):
        executor = ParallelExecutor()

        results = await executor.execute_parallel([])

        assert results == []

    @pytest.mark.asyncio
    async def test_single_callable_success(self):
        executor = ParallelExecutor()

        async def returns_42():
            return 42

        results = await executor.execute_parallel([returns_42])

        assert len(results) == 1
        assert results[0].status == "fulfilled"
        assert results[0].result == 42

    @pytest.mark.asyncio
    async def test_single_callable_error(self):
        executor = ParallelExecutor()

        async def raises_error():
            raise ValueError("test error")

        results = await executor.execute_parallel([raises_error])

        assert len(results) == 1
        assert results[0].status == "rejected"
        assert "ValueError" in (results[0].error or "")
        assert "test error" in (results[0].error or "")

    @pytest.mark.asyncio
    async def test_multiple_callables_all_success(self):
        executor = ParallelExecutor()

        async def returns_a():
            return "a"

        async def returns_b():
            return "b"

        async def returns_c():
            return "c"

        results = await executor.execute_parallel([returns_a, returns_b, returns_c])

        assert len(results) == 3
        assert results[0].status == "fulfilled"
        assert results[0].result == "a"
        assert results[1].status == "fulfilled"
        assert results[1].result == "b"
        assert results[2].status == "fulfilled"
        assert results[2].result == "c"

    @pytest.mark.asyncio
    async def test_multiple_callables_mixed_results(self):
        executor = ParallelExecutor()

        async def succeeds():
            return "ok"

        async def fails():
            raise RuntimeError("boom")

        results = await executor.execute_parallel([succeeds, fails, succeeds])

        assert len(results) == 3
        assert results[0].status == "fulfilled"
        assert results[0].result == "ok"
        assert results[1].status == "rejected"
        assert "RuntimeError" in (results[1].error or "")
        assert results[2].status == "fulfilled"
        assert results[2].result == "ok"

    @pytest.mark.asyncio
    async def test_all_settled_pattern_no_fail_fast(self):
        executor = ParallelExecutor()

        async def fails():
            raise ValueError("fail")

        async def succeeds():
            return "ok"

        results = await executor.execute_parallel([fails, succeeds])

        assert len(results) == 2
        assert results[0].status == "rejected"
        assert results[1].status == "fulfilled"

    @pytest.mark.asyncio
    async def test_results_preserve_order(self):
        executor = ParallelExecutor(max_concurrency=1)

        async def returns(i):
            return i

        callables: List = [lambda i=n: returns(i) for n in range(5)]  # type: ignore[misc]

        results = await executor.execute_parallel(callables)  # type: ignore[arg-type]

        for i, result in enumerate(results):
            assert result.status == "fulfilled"
            assert result.result == i


class TestConcurrencyLimit:
    """Tests for concurrency limiting."""

    @pytest.mark.asyncio
    async def test_concurrency_limit_enforced(self):
        executor = ParallelExecutor(max_concurrency=2)

        concurrent_count = 0
        max_concurrent = 0
        lock = asyncio.Lock()

        async def track_concurrency():
            nonlocal concurrent_count, max_concurrent
            async with lock:
                concurrent_count += 1
                max_concurrent = max(max_concurrent, concurrent_count)

            await asyncio.sleep(0.05)

            async with lock:
                concurrent_count -= 1

            return "done"

        callables: List = [track_concurrency for _ in range(10)]

        results = await executor.execute_parallel(callables)

        assert max_concurrent <= 2
        assert len(results) == 10
        for r in results:
            assert r.status == "fulfilled"

    @pytest.mark.asyncio
    async def test_concurrency_one_runs_sequentially(self):
        executor = ParallelExecutor(max_concurrency=1)

        execution_order: List = []

        async def record_execution(i):
            execution_order.append(f"start_{i}")
            await asyncio.sleep(0.01)
            execution_order.append(f"end_{i}")
            return i

        callables: List = [lambda i=n: record_execution(i) for n in range(3)]  # type: ignore[misc]

        results = await executor.execute_parallel(callables)  # type: ignore[arg-type]

        assert execution_order == [
            "start_0",
            "end_0",
            "start_1",
            "end_1",
            "start_2",
            "end_2",
        ]

    @pytest.mark.asyncio
    async def test_high_concurrency_allows_parallel(self):
        executor = ParallelExecutor(max_concurrency=10)

        start_time = asyncio.get_event_loop().time()

        async def short_delay():
            await asyncio.sleep(0.05)
            return "done"

        callables: List = [short_delay for _ in range(5)]

        results = await executor.execute_parallel(callables)

        elapsed = asyncio.get_event_loop().time() - start_time

        assert elapsed < 0.2
        assert len(results) == 5


class TestMaxConcurrencySetter:
    """Tests for max_concurrency property."""

    def test_setter_updates_value(self):
        executor = ParallelExecutor(max_concurrency=5)

        executor.max_concurrency = 10

        assert executor.max_concurrency == 10

    def test_setter_rejects_zero(self):
        executor = ParallelExecutor()

        with pytest.raises(ValueError, match="at least 1"):
            executor.max_concurrency = 0

    def test_setter_rejects_negative(self):
        executor = ParallelExecutor()

        with pytest.raises(ValueError, match="at least 1"):
            executor.max_concurrency = -5


class TestCreateParallelExecutor:
    """Tests for factory function."""

    def test_creates_executor_with_defaults(self):
        executor = create_parallel_executor()

        assert isinstance(executor, ParallelExecutor)
        assert executor.max_concurrency == DEFAULT_MAX_CONCURRENCY

    def test_creates_executor_with_custom_concurrency(self):
        executor = create_parallel_executor(max_concurrency=20)

        assert executor.max_concurrency == 20


class TestIntegration:
    """Integration tests for parallel execution."""

    @pytest.mark.asyncio
    async def test_parallel_with_different_return_types(self):
        executor = ParallelExecutor()

        async def return_dict():
            return {"key": "value"}

        async def return_list():
            return [1, 2, 3]

        async def return_none():
            return None

        async def return_string():
            return "hello"

        results = await executor.execute_parallel(
            [
                return_dict,
                return_list,
                return_none,
                return_string,
            ]
        )

        assert results[0].result == {"key": "value"}
        assert results[1].result == [1, 2, 3]
        assert results[2].result is None
        assert results[3].result == "hello"

    @pytest.mark.asyncio
    async def test_parallel_with_exception_types(self):
        executor = ParallelExecutor()

        async def raise_value_error():
            raise ValueError("value error")

        async def raise_type_error():
            raise TypeError("type error")

        async def raise_runtime_error():
            raise RuntimeError("runtime error")

        results = await executor.execute_parallel(
            [
                raise_value_error,
                raise_type_error,
                raise_runtime_error,
            ]
        )

        assert "ValueError" in (results[0].error or "")
        assert "TypeError" in (results[1].error or "")
        assert "RuntimeError" in (results[2].error or "")

    @pytest.mark.asyncio
    async def test_parallel_cancellation_propagation(self):
        executor = ParallelExecutor(max_concurrency=1)

        call_count = 0

        async def count_calls():
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)
            return call_count

        callables: List = [count_calls for _ in range(3)]

        results = await executor.execute_parallel(callables)

        assert call_count == 3
        assert all(r.status == "fulfilled" for r in results)
