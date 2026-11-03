import builtins
import logging
from unittest.mock import Mock

import pytest
from picle.models import Outputters

from norfab.clients.nfcli_shell.norfab_jobs_shell import NorFabJobsShellCommands

pytestmark = pytest.mark.nfcli


@pytest.mark.parametrize("details", [False, True])
@pytest.mark.parametrize("found", [False, True])
def test_job_uuid_lookup(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    details: bool,
    found: bool,
) -> None:
    job = {
        "uuid": "job-id",
        "service": "dummy",
        "task": "get_version",
        "status": "COMPLETED",
        "created_at": "2026-11-03 10:00:00",
        "completed_timestamp": "2026-11-03 10:00:01",
    }
    client = Mock()
    client.job_db.get_job.return_value = job if found else None
    monkeypatch.setattr(builtins, "NFCLIENT", client, raising=False)

    with caplog.at_level(logging.ERROR):
        rows, outputter = NorFabJobsShellCommands.run(uuid="job-id", details=details)

    client.job_db.get_job.assert_called_once_with("job-id")
    assert outputter == (
        Outputters.outputter_nested if details else Outputters.outputter_rich_table
    )
    if not found:
        assert rows == []
        assert "job 'job-id' not found" in caplog.text
    else:
        assert not caplog.records
        assert rows == (
            [job]
            if details
            else [
                {
                    "uuid": "job-id",
                    "service": "dummy",
                    "task": "get_version",
                    "status": "COMPLETED",
                    "created": job["created_at"],
                    "completed": job["completed_timestamp"],
                }
            ]
        )
