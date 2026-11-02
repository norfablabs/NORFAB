import builtins
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest
from picle import App

from norfab.clients.nfcli_shell import nfcli_shell_client as shell

pytestmark = pytest.mark.nfcli


class TestManTasks:
    @pytest.mark.parametrize("brief", [False, True])
    def test_summary(self, monkeypatch: pytest.MonkeyPatch, brief: bool) -> None:
        schema = {
            "name": "echo",
            "description": "Echo a value.\n\nArgs:\n    value: Input.",
            "inputSchema": {},
        }
        monkeypatch.setattr(
            shell,
            "NFCLIENT",
            Mock(
                run_job=lambda *a, **kw: {
                    "worker": {"failed": False, "service": "dummy", "result": [schema]}
                }
            ),
        )
        expected = (
            {"dummy-service:all-tasks": ["echo"]}
            if brief
            else {"dummy": {"echo": "Echo a value."}}
        )
        assert shell.ManTasks.run(brief=brief) == expected

    @pytest.mark.parametrize("service", [None, "nornir"])
    def test_sources(self, monkeypatch: pytest.MonkeyPatch, service: Any) -> None:
        client = Mock()
        client.run_job.return_value = {
            "b": {"service": "nornir", "failed": False, "result": ["z", "a"]},
            "a": {"service": "nornir", "failed": False, "result": ["a"]},
            "c": {"service": "netbox", "failed": True, "result": None},
        }
        monkeypatch.setattr(shell, "NFCLIENT", client)
        assert shell.ManTasks.source_name(service=service) == ["a", "z"]
        client.run_job.assert_called_with(
            service or "all",
            "list_tasks",
            workers="any",
            timeout=60,
            kwargs={"brief": True},
        )
        assert shell.ManTasks.source_service() == ["nornir"]
        client.run_job.assert_called_with(
            "all", "list_tasks", workers="any", timeout=60, kwargs={"brief": True}
        )

    def test_details(self, monkeypatch: pytest.MonkeyPatch) -> None:
        schema = {
            "name": "echo",
            "description": "Full description",
            "inputSchema": {},
            "outputSchema": {},
            "mcp": {},
        }

        def discover(service: str, task: str, **kwargs: Any) -> dict:
            assert service == "dummy"
            assert task == "list_tasks"
            assert kwargs["kwargs"] == {"name": "echo"}
            return {"worker": {"failed": False, "service": service, "result": [schema]}}

        monkeypatch.setattr(shell, "NFCLIENT", Mock(run_job=discover))
        assert shell.ManTasks.run(service="dummy", name="echo", details=True) == {
            "dummy-service:echo": [schema]
        }

    def test_conflicting_modes(self) -> None:
        with pytest.raises(ValueError, match="brief and details"):
            shell.ManTasks.run(brief=True, details=True)

    @pytest.mark.parametrize("brief", [False, True])
    def test_worker_name_filter(self, nfclient: Any, brief: bool) -> None:
        results = nfclient.run_job(
            "nornir",
            "list_tasks",
            workers="any",
            kwargs={"name": "get_version", "brief": brief},
        )
        assert results
        for result in results.values():
            assert not result["failed"]
            tasks = result["result"]
            assert [t if brief else t["name"] for t in tasks] == ["get_version"]

    def test_worker_unknown_name_brief(self, nfclient: Any) -> None:
        results = nfclient.run_job(
            "nornir",
            "list_tasks",
            workers="any",
            kwargs={"name": "unregistered_task_for_test", "brief": True},
        )
        assert results
        for result in results.values():
            assert result["failed"]
            assert "task not registered" in str(result["errors"])

    @pytest.mark.parametrize("mode", ["", " brief", " details"])
    def test_shell_modes(
        self,
        nfclient: Any,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        mode: str,
    ) -> None:
        monkeypatch.setattr(builtins, "NFCLIENT", nfclient, raising=False)
        monkeypatch.setattr(shell, "NFCLIENT", nfclient)
        app = App(shell.NorFabShell)
        shell.mount_shell_plugins(app, SimpleNamespace(plugins={}))
        app.onecmd("top")
        app.onecmd("man tasks service nornir name get_version" + mode)
        output = capsys.readouterr().out
        assert "get_version" in output
        assert "nornir" in output
        assert ("inputSchema" in output) == (mode == " details")
