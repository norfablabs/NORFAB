import builtins

import pytest
from pydantic import ValidationError

from norfab.clients.nfcli_shell.nfcli_shell_client import (
    LogLevel,
    ShowNorfabLoggingModel,
)
from norfab.clients.nfcli_shell.common import ClientRunJobArgs
from norfab.clients.nfcli_shell.nornir.nornir_picle_shell_cfg import NornirCfgShell
from norfab.clients.nfcli_shell.nornir.nornir_picle_shell_inventory import (
    InventoryCreateHostFromNetboxModel,
)

pytestmark = pytest.mark.nfcli


class FakeNFClient:
    def __init__(self, files):
        self.files = files

    def run_job(self, service, task, kwargs):
        assert service == "filesharing"
        assert task == "walk"
        assert kwargs == {"url": "nf://"}
        return {
            "filesharing-worker-1": {
                "result": self.files,
            }
        }


class FakeLoggingNFClient:
    def __init__(self):
        self.calls = []

    def mmi(self, service, task, **kwargs):
        self.calls.append(("mmi", service, task, kwargs))
        return {
            "errors": [],
            "results": [
                {
                    "ts": "2026-07-25T10:00:00+10:00",
                    "level": "ERROR",
                    "role": "broker",
                    "name": "NFPBroker",
                    "logger": "norfab.core.broker",
                    "message": "Broker log",
                }
            ],
        }

    def run_job(self, service, task, workers, kwargs, timeout):
        self.calls.append(("run_job", service, task, workers, kwargs, timeout))
        return {
            "nornir-worker-1": {
                "failed": False,
                "result": [
                    {
                        "ts": "2026-07-25T10:00:01+10:00",
                        "level": "ERROR",
                        "role": "worker",
                        "name": "nornir-worker-1",
                        "logger": "norfab.core.worker",
                        "message": "Worker log",
                    }
                ],
            }
        }


def test_show_norfab_logging_uses_single_service_and_supported_filters(monkeypatch):
    nfclient = FakeLoggingNFClient()
    monkeypatch.setattr(builtins, "NFCLIENT", nfclient, raising=False)

    output = ShowNorfabLoggingModel.run(
        service="nornir",
        workers=["nornir-worker-1"],
        level=LogLevel.ERROR,
        last=10,
    )

    assert len(output.splitlines()) == 2
    assert nfclient.calls[0][3]["kwargs"] == {"last": 10, "level": "ERROR"}
    assert nfclient.calls[1] == (
        "run_job",
        "nornir",
        "get_logs",
        ["nornir-worker-1"],
        {"last": 10, "level": "ERROR"},
        600,
    )


def test_show_norfab_logging_rejects_service_list_and_removed_filters():
    with pytest.raises(ValidationError):
        ShowNorfabLoggingModel(service=["nornir", "netbox"])

    assert "task" not in ShowNorfabLoggingModel.model_fields
    assert "job_uuid" not in ShowNorfabLoggingModel.model_fields
    assert "role" not in ShowNorfabLoggingModel.model_fields
    assert "name" not in ShowNorfabLoggingModel.model_fields


def test_walk_norfab_files_returns_root_entries(monkeypatch):
    monkeypatch.setattr(
        builtins,
        "NFCLIENT",
        FakeNFClient(
            [
                "nf://agents/client_agent_interface_health_checker.yaml",
                "nf://cli/interfaces_status.txt",
                "nf://inventory.yaml.old1",
                "nf://nornir_test_suites/suite_bad_yaml.txt",
            ]
        ),
        raising=False,
    )

    assert ClientRunJobArgs.walk_norfab_files() == [
        "nf://agents/",
        "nf://cli/",
        "nf://inventory.yaml.old1",
        "nf://nornir_test_suites/",
    ]


def test_walk_norfab_files_returns_entries_matching_choice(monkeypatch):
    monkeypatch.setattr(
        builtins,
        "NFCLIENT",
        FakeNFClient(
            [
                "nf://agents/client_agent_interface_health_checker.yaml",
                "nf://agents/nested/check.yaml",
                "nf://cli/interfaces_status.txt",
                "nf://inventory.yaml.old1",
            ]
        ),
        raising=False,
    )

    assert ClientRunJobArgs.walk_norfab_files("nf://ag") == ["nf://agents/"]
    assert ClientRunJobArgs.walk_norfab_files("nf://agents/") == [
        "nf://agents/client_agent_interface_health_checker.yaml",
        "nf://agents/nested/",
    ]


def test_nornir_cfg_config_source_returns_entries_matching_choice(monkeypatch):
    monkeypatch.setattr(
        builtins,
        "NFCLIENT",
        FakeNFClient(
            [
                "nf://cfg/base.txt",
                "nf://cfg/templates/hostname.txt",
                "nf://cli/interfaces_status.txt",
            ]
        ),
        raising=False,
    )

    assert NornirCfgShell.source_config("nf://cfg/") == [
        "nf://cfg/base.txt",
        "nf://cfg/templates/",
        "load-terminal",
    ]


def test_nornir_inventory_create_host_from_netbox_shell_submission(monkeypatch):
    calls = []

    def fake_run_future_job(*args, **kwargs):
        calls.append((args, kwargs))
        return {
            "nornir-worker-1": {
                "failed": False,
                "errors": [],
                "messages": [],
                "result": {"created": ["leaf-1"], "updated": [], "missing": []},
            }
        }

    monkeypatch.setattr(
        "norfab.clients.nfcli_shell.nornir.nornir_picle_shell_inventory.run_future_job",
        fake_run_future_job,
    )
    monkeypatch.setattr(
        "norfab.clients.nfcli_shell.nornir.nornir_picle_shell_inventory.log_error_or_result",
        lambda result, **kwargs: result,
    )

    InventoryCreateHostFromNetboxModel.run(
        devices="leaf-1",
        groups="lab",
        workers="nornir-worker-1",
        netbox_workers="any",
    )

    args, kwargs = calls[0]
    assert args[:2] == ("nornir", "create_host_from_netbox")
    assert kwargs["workers"] == "nornir-worker-1"
    assert kwargs["kwargs"]["devices"] == ["leaf-1"]
    assert kwargs["kwargs"]["groups"] == ["lab"]
    assert kwargs["kwargs"]["netbox_workers"] == "any"
