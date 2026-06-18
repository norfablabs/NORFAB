import builtins

from norfab.clients.nfcli_shell.common import ClientRunJobArgs


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
