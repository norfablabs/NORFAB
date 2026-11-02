import builtins
from typing import Any
from unittest.mock import Mock

import pytest
from picle import App
from pydantic import create_model

from norfab.clients.nfcli_shell.common import ClientRunJobArgs
from norfab.clients.nfcli_shell.containerlab.containerlab_picle_shell import (
    DestroyCommand,
)
from norfab.clients.nfcli_shell.fakenos.fakenos_picle_shell import FakeNOSStopCommand
from norfab.clients.nfcli_shell.filesharing.filesharing_picle_shell import (
    CloneGitRemoteModel,
)
from norfab.clients.nfcli_shell.norfab_jobs_shell import NorFabJobsShellCommands
from norfab.clients.nfcli_shell.nornir.nornir_picle_shell_cli import NornirCliShell
from norfab.clients.nfcli_shell.nornir.nornir_picle_shell_inventory import (
    InventoryLoadContainerlabModel,
)
from norfab.clients.nfcli_shell.nornir.nornir_picle_shell_task import NornirTaskShell
from norfab.clients.nfcli_shell.workers.workers_picle_shell import ListWorkersJobsModel

pytestmark = pytest.mark.nfcli


def complete(app: App, line: str) -> list[str]:
    return [
        item.strip() for item in app.completedefault("", line, len(line), len(line))
    ]


class TestCompletion:
    @pytest.mark.parametrize(
        "model,field,service,task",
        [
            (DestroyCommand, "lab-name", "containerlab", "get_running_labs"),
            (FakeNOSStopCommand, "network", "fakenos", "inspect_networks"),
            (NornirCliShell, "FL", "nornir", "get_nornir_hosts"),
        ],
    )
    def test_live_worker_scope(
        self,
        monkeypatch: pytest.MonkeyPatch,
        model: Any,
        field: str,
        service: str,
        task: str,
    ) -> None:
        client = Mock()
        client.run_job.return_value = {
            "good": {"failed": False, "result": ["z", "a", "a"]},
            "bad": {"failed": True, "result": None},
            "empty": {"failed": False, "result": None},
        }
        monkeypatch.setattr(builtins, "NFCLIENT", client, raising=False)
        app = App(create_model("Root", command=(model, None)))
        line = f"command workers worker-1 {field} "
        assert complete(app, line) == ["a", "z"]
        complete(app, line)
        assert client.run_job.call_count == 2
        client.run_job.assert_called_with(service, task, workers="worker-1")

    def test_service_scoped_workers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = Mock()
        client.mmi.return_value = {"results": [{"name": "worker-1"}]}
        monkeypatch.setattr(builtins, "NFCLIENT", client, raising=False)
        app = App(create_model("Root", command=(ListWorkersJobsModel, None)))
        assert "worker-1" in complete(app, "command service nornir workers ")
        complete(app, "command service nornir workers ")
        assert client.mmi.call_count == 2
        client.mmi.assert_called_with(
            "mmi.service.broker", "show_workers", kwargs={"service": "nornir"}
        )

    def test_remote_names(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = Mock()
        client.run_job.return_value = {
            "w": {"failed": False, "result": [{"name": "repo"}]}
        }
        monkeypatch.setattr(builtins, "NFCLIENT", client, raising=False)
        app = App(create_model("Root", command=(CloneGitRemoteModel, None)))
        assert "repo" in complete(app, "command workers node-1 name ")
        client.run_job.assert_called_with(
            "filesharing", "get_remotes", workers="node-1"
        )

    def test_job_sources(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = Mock()
        monkeypatch.setattr(builtins, "NFCLIENT", client, raising=False)
        app = App(create_model("Root", command=(ListWorkersJobsModel, None)))
        client.run_job.return_value = {
            "w": {"failed": False, "result": ["get_version"]}
        }
        assert "get_version" in complete(
            app, "command service nornir workers node-1 task "
        )
        complete(app, "command service nornir workers node-1 task ")
        assert client.run_job.call_count == 1
        client.run_job.assert_called_with(
            "nornir", "list_tasks", workers="node-1", kwargs={"brief": True}
        )
        client.run_job.return_value = {
            "w": {"failed": False, "result": [{"uuid": "job-id"}]}
        }
        assert "job-id" in complete(
            app, "command service nornir workers node-1 task get_version uuid "
        )
        client.run_job.assert_called_with(
            "nornir",
            "job_list",
            workers="node-1",
            kwargs={"task": "get_version", "last": 100},
        )

    def test_inventory_lab_scope(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = Mock()
        client.run_job.return_value = {"node": {"failed": False, "result": ["lab"]}}
        monkeypatch.setattr(builtins, "NFCLIENT", client, raising=False)
        app = App(create_model("Root", command=(InventoryLoadContainerlabModel, None)))
        assert "lab" in complete(app, "command clab-workers node-1 lab-name ")
        client.run_job.assert_called_once_with(
            "containerlab", "get_running_labs", workers="node-1"
        )

    def test_file_completion_stays_live(self, monkeypatch: pytest.MonkeyPatch) -> None:
        source = Mock(side_effect=[["nf://old.py"], ["nf://new.py"]])
        monkeypatch.setattr(ClientRunJobArgs, "walk_norfab_files", source)
        app = App(create_model("Root", command=(NornirTaskShell, None)))
        assert complete(app, "command plugin ") == ["nf://old.py"]
        assert complete(app, "command plugin ") == ["nf://new.py"]
        assert source.call_count == 2

    def test_local_job_uuid(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = Mock()
        client.job_db.fetch_jobs.return_value = [{"uuid": "job-id"}]
        monkeypatch.setattr(builtins, "NFCLIENT", client, raising=False)
        app = App(create_model("Root", command=(NorFabJobsShellCommands, None)))
        line = "command service nornir task get_version workers-completed node-1 uuid "
        assert "job-id" in complete(app, line)
        complete(app, line)
        assert client.job_db.fetch_jobs.call_count == 2
        client.job_db.fetch_jobs.assert_called_with(
            service="nornir", task="get_version", workers_completed=["node-1"], last=100
        )
