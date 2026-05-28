"""Smoke test for the integration harness.

Asserts that:
    - The FastAPI app boots with DB + K8s dependency overrides in place.
    - GET /v1/jobs returns an empty list against a fresh DB.
    - The fake K8s client has not been touched (no orchestration has run).
"""
from typing import Any

from httpx import AsyncClient


async def test_get_jobs_returns_empty_list(client: AsyncClient, fake_k8s: Any) -> None:
    """An empty DB returns ``[]`` from ``GET /v1/jobs`` and does not touch K8s."""
    response = await client.get("/v1/jobs")
    assert response.status_code == 200
    assert response.json() == []
    assert fake_k8s.created_jobs == []


async def test_health_check_responds(client: AsyncClient) -> None:
    """``GET /health`` returns the manager_service status payload."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "manager_service"}
