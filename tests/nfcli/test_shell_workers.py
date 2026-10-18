import builtins
from unittest.mock import Mock

from picle import App
from picle.models import Outputters

from norfab.clients.nfcli_shell.nfcli_shell_client import (
    NorFabShell,
    ShowNorfabWorkersModel,
)


def test_worker_summary(monkeypatch, capsys):
    client = Mock()
    client.mmi.return_value = {
        "errors": [],
        "results": [
            {"name": "dead", "service": "z", "status": "dead"},
            {"name": "live", "service": "a", "status": "alive"},
        ],
    }
    client.run_job.return_value = {
        "live": {
            "failed": False,
            "result": {
                "process": {
                    "uptime_seconds": 90061,
                    "memory_rss_mbyte": 123.456,
                    "cpu_percent": 2.34,
                },
                "jobs": {"total_jobs": 42},
            },
        }
    }
    monkeypatch.setattr(builtins, "NFCLIENT", client, raising=False)
    rows, outputter, options = ShowNorfabWorkersModel.run(timeout=3)
    assert outputter == Outputters.outputter_tabulate_table
    assert options == {"showindex": False, "tablefmt": "simple"}
    assert rows[0] == {
        "Worker": "live",
        "Service": "a",
        "Status": "alive",
        "Uptime": "1 day, 1:01:01",
        "RAM MB": 123,
        "CPU%": "2.3%",
        "Jobs": 42,
    }
    assert rows[1]["Worker"] == "dead"
    assert rows[1]["RAM MB"] == "—"
    client.run_job.assert_called_once_with(
        "all", "get_stats", workers=["live"], timeout=3
    )
    shell = App(NorFabShell)
    shell.onecmd("show norfab workers")
    output = capsys.readouterr().out
    assert "RAM MB" in output and "live" in output
    assert "max_concurrent_jobs" not in output
    assert "Jobs" in output
    assert "running_jobs" not in output
    assert rows[1]["Jobs"] == "—"

    client.run_job.return_value["live"]["result"]["process"]["cpu_percent"] = 1.0
    client.mmi.return_value["results"] = [
        {"name": "live", "service": "a", "status": "alive"}
    ]
    shell.onecmd("show norfab workers")
    assert "1.0%" in capsys.readouterr().out


def test_empty_workers(monkeypatch):
    client = Mock()
    client.mmi.return_value = {
        "errors": [],
        "results": [{"name": "", "service": "", "status": ""}],
    }
    monkeypatch.setattr(builtins, "NFCLIENT", client, raising=False)
    assert ShowNorfabWorkersModel.run()[0] == []
    client.run_job.assert_not_called()
