"""Tests for DB connection pool exhaustion under concurrent load.

These tests verify that Empire's SQLAlchemy connection pool can handle
concurrent API requests without leaking connections or triggering
``QueuePool limit reached`` errors.
"""

from __future__ import annotations

import asyncio
import logging
import random
from pathlib import Path

import httpx
import pytest
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR

from empire.test.test_performance.conftest import (
    CONCURRENT_CHECKINS,
    MAX_ERROR_RATE,
    MAX_P99_LATENCY_SECONDS,
    MAX_POOL_ERRORS,
)
from empire.test.test_performance.helpers import (
    RequestResult,
    summarize_results,
    timed_request,
)

log = logging.getLogger(__name__)

pytestmark = [pytest.mark.slow, pytest.mark.mysql]

# Endpoints that hit the database
_DB_ENDPOINTS = [
    "/api/v2/agents",
    "/api/v2/listeners",
    "/api/v2/users/me",
]


@pytest.mark.slow
def test_concurrent_db_requests_no_pool_exhaustion(
    empire_base_url: str,
    auth_header: dict[str, str],
    empire_log_path: str,
):
    """Fire CONCURRENT_CHECKINS simultaneous requests across DB-hitting
    endpoints and verify zero pool exhaustion errors, zero server errors,
    and acceptable latency.
    """

    async def _run() -> list[RequestResult]:
        async with httpx.AsyncClient(base_url=empire_base_url, timeout=30.0) as client:
            tasks = [
                timed_request(
                    client,
                    "GET",
                    _DB_ENDPOINTS[i % len(_DB_ENDPOINTS)],
                    headers=auth_header,
                )
                for i in range(CONCURRENT_CHECKINS)
            ]
            return await asyncio.gather(*tasks)

    results = asyncio.run(_run())

    summary = summarize_results(results)
    log.info("Concurrent DB requests summary: %s", summary)

    # --- Assertions ---
    # Zero connection-level errors
    error_rate = summary["error_rate"]
    assert error_rate <= MAX_ERROR_RATE, (
        f"Error rate {error_rate:.2%} exceeds maximum {MAX_ERROR_RATE:.2%}"
    )

    # Zero 5xx server errors
    server_errors = sum(
        count
        for status, count in summary["status_codes"].items()
        if status >= HTTP_500_INTERNAL_SERVER_ERROR
    )
    assert server_errors == 0, (
        f"Got {server_errors} server errors (5xx): {summary['status_codes']}"
    )

    # p99 latency within budget
    p99 = summary["latency"]["p99"]
    assert p99 <= MAX_P99_LATENCY_SECONDS, (
        f"p99 latency {p99:.3f}s exceeds maximum {MAX_P99_LATENCY_SECONDS}s"
    )

    # No QueuePool errors in server logs
    with Path(empire_log_path).open() as f:
        log_contents = f.read()
    pool_errors = log_contents.count("QueuePool limit")
    assert pool_errors <= MAX_POOL_ERRORS, (
        f"Found {pool_errors} 'QueuePool limit' errors in Empire logs "
        f"(max allowed: {MAX_POOL_ERRORS})"
    )


@pytest.mark.slow
@pytest.mark.parametrize(
    "concurrency",
    [
        50,
        100,
        # The 250 case stresses the pool at ~25x its 8-connection capacity
        # and occasionally times out under CI resource contention (~10% rate
        # observed). Retry up to 2 times before failing — a real regression
        # in connection hold time will still fail all 3 attempts, while
        # transient CI pressure will pass on retry.
        pytest.param(250, marks=pytest.mark.flaky(reruns=2)),
    ],
)
def test_pool_exhaustion_at_concurrency_levels(
    empire_base_url: str,
    auth_header: dict[str, str],
    concurrency: int,
):
    """Fire *concurrency* requests with staggered arrival (realistic jitter)
    and verify zero connection-level errors.
    """
    jitter_seconds = 5.0  # spread requests over this window

    async def _run() -> list[RequestResult]:
        async with httpx.AsyncClient(base_url=empire_base_url, timeout=30.0) as client:

            async def _jittered_request(i: int):
                await asyncio.sleep(random.uniform(0, jitter_seconds))
                return await timed_request(
                    client, "GET", "/api/v2/listeners", headers=auth_header
                )

            tasks = [_jittered_request(i) for i in range(concurrency)]
            return await asyncio.gather(*tasks)

    results = asyncio.run(_run())

    summary = summarize_results(results)
    log.info(
        "Concurrency level %d (jitter=%.1fs) summary: %s",
        concurrency,
        jitter_seconds,
        summary,
    )

    connection_errors = [r for r in results if r.error is not None]
    assert len(connection_errors) == 0, (
        f"Got {len(connection_errors)} connection errors at concurrency "
        f"{concurrency}: {[e.error for e in connection_errors]}"
    )
