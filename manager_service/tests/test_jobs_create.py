"""Endpoint tests for ``POST /v1/jobs`` — num_mappers / num_reducers contract.

Covers:
    - defaults (4 / 2) and explicit values are accepted and echoed back
    - ``>= 1`` violation surfaces as a 400 from the endpoint layer
    - genuine type errors stay at Pydantic's 422 (proves the 400/422 split)
    - MAP task count follows the actual split result, not the request

Two real collaborators are patched so the test never needs uploads:
    - ``app.utils.utility.split_input_file_to_chunks`` — the endpoint's
      chunker. Returning a fixed list keeps the test independent of MinIO
      contents.
    - ``app.services.job_service.file_exists`` — the per-path precondition
      check inside ``job_add``. Forced to ``True`` so the input/mapper/
      reducer keys in the payload do not need to exist in MinIO.
"""
from typing import Any
from unittest.mock import patch

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import TaskType
from app.models.task import Task


VALID_PAYLOAD: dict[str, Any] = {
    "input_files":  "in/file.txt",
    "output_path":  "out/file.txt",
    "mapper_code":  "code/mapper.py",
    "reducer_code": "code/reducer.py",
    "user_id":      1,
}


@patch("app.services.job_service.file_exists", return_value=True)
@patch("app.utils.utility.split_input_file_to_chunks")
async def test_creates_job_with_defaults(
    mock_split: Any,
    mock_file_exists: Any,
    client: AsyncClient,
) -> None:
    """Omitting num_mappers / num_reducers yields the spec defaults 4 / 2."""
    mock_split.return_value = ["c0", "c1", "c2", "c3"]

    response = await client.post("/v1/jobs", json=VALID_PAYLOAD)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["num_mappers"] == 4
    assert body["num_reducers"] == 2


@patch("app.services.job_service.file_exists", return_value=True)
@patch("app.utils.utility.split_input_file_to_chunks")
async def test_creates_job_with_custom_values(
    mock_split: Any,
    mock_file_exists: Any,
    client: AsyncClient,
) -> None:
    """Explicit M=8 / R=3 are stored and echoed back unchanged."""
    mock_split.return_value = [f"c{i}" for i in range(8)]

    response = await client.post(
        "/v1/jobs",
        json={**VALID_PAYLOAD, "num_mappers": 8, "num_reducers": 3},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["num_mappers"] == 8
    assert body["num_reducers"] == 3


async def test_rejects_num_mappers_zero(client: AsyncClient) -> None:
    """num_mappers=0 violates ``>= 1`` and returns 400 from the endpoint."""
    response = await client.post(
        "/v1/jobs",
        json={**VALID_PAYLOAD, "num_mappers": 0},
    )

    assert response.status_code == 400
    assert "num_mappers" in response.json()["detail"]


async def test_rejects_num_reducers_zero(client: AsyncClient) -> None:
    """num_reducers=0 violates ``>= 1`` and returns 400."""
    response = await client.post(
        "/v1/jobs",
        json={**VALID_PAYLOAD, "num_reducers": 0},
    )

    assert response.status_code == 400
    assert "num_reducers" in response.json()["detail"]


async def test_rejects_num_mappers_negative(client: AsyncClient) -> None:
    """Negative num_mappers also returns 400 (range, not type, violation)."""
    response = await client.post(
        "/v1/jobs",
        json={**VALID_PAYLOAD, "num_mappers": -1},
    )

    assert response.status_code == 400


async def test_wrong_type_returns_422_not_400(client: AsyncClient) -> None:
    """A non-integer num_mappers is a Pydantic type error → 422.

    Range violations (``>= 1``) are app-level 400; genuine type errors stay
    422. Guards the separation so the two failure modes don't collapse.
    """
    response = await client.post(
        "/v1/jobs",
        json={**VALID_PAYLOAD, "num_mappers": "abc"},
    )

    assert response.status_code == 422


@patch("app.services.job_service.file_exists", return_value=True)
@patch("app.utils.utility.split_input_file_to_chunks")
async def test_map_task_count_matches_actual_split_length(
    mock_split: Any,
    mock_file_exists: Any,
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """When the split returns fewer chunks than requested, MAP task count
    follows the split — not the request.

    Guards the ``actual_mappers = len(map_inputs)`` fix in ``add_job``:
    without it, ``generate_map_output_paths(..., num_mappers)`` would emit
    8 paths against 3 input splits, and ``task_add_batch`` would reject the
    length mismatch by returning ``[]`` (silently dropping all MAP tasks).
    """
    mock_split.return_value = ["p0", "p1", "p2"]  # 3 chunks, request asked for 8

    response = await client.post(
        "/v1/jobs",
        json={**VALID_PAYLOAD, "num_mappers": 8, "num_reducers": 2},
    )

    assert response.status_code == 201, response.text
    job_id = response.json()["job_id"]

    result = await db_session.execute(
        select(Task).where(Task.job_id == job_id, Task.type == TaskType.MAP)
    )
    map_tasks = result.scalars().all()
    assert len(map_tasks) == 3
