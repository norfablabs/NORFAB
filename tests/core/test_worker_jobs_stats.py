from pathlib import Path

import pytest

from norfab.core.monitoring import WorkerJobMonitoringStats
from norfab.core.worker import JobDatabase

pytestmark = pytest.mark.core


def test_worker_jobs_stats(tmp_path: Path) -> None:
    path = str(tmp_path / "worker.db")
    db = JobDatabase(path)
    try:
        assert db.jobs_stats() == {"total_jobs": 0, "jobs_by_status": {}}
        with db._transaction(write=True) as conn:
            conn.executemany(
                "INSERT INTO jobs (uuid, client_address, task, status, received_timestamp) VALUES (?, 'client', 'echo', ?, 'now')",
                [
                    (str(i), status)
                    for i, status in enumerate(
                        ["COMPLETED", "COMPLETED", "FAILED", "PENDING", "STARTED"]
                    )
                ],
            )
        expected = {
            "total_jobs": 5,
            "jobs_by_status": {"COMPLETED": 2, "FAILED": 1, "PENDING": 1, "STARTED": 1},
        }
        assert db.jobs_stats() == expected
        assert WorkerJobMonitoringStats.model_validate(db.jobs_stats()).total_jobs == 5
        db.close()
        db = JobDatabase(path)
        assert db.jobs_stats() == expected
        with db._transaction(write=True) as conn:
            conn.execute("DELETE FROM jobs WHERE status = 'COMPLETED'")
        assert db.jobs_stats()["total_jobs"] == 3
        assert db.jobs_stats()["jobs_by_status"].get("COMPLETED", 0) == 0
    finally:
        db.close()
