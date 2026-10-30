"""gNMI integration tests against the cEOS lab through nfclient."""

import builtins
from io import StringIO

import pytest
from picle import App

from norfab.clients.nfcli_shell.nornir.nornir_picle_shell_gnmi import NornirGnmiShell

pytestmark = [pytest.mark.nornir, pytest.mark.nornir_gnmi]


@pytest.mark.parametrize(
    "worker,hosts",
    [
        ("nornir-worker-1", ["ceos-spine-1", "ceos-spine-2"]),
        ("nornir-worker-2", ["ceos-leaf-1", "ceos-leaf-2", "ceos-leaf-3"]),
    ],
)
@pytest.mark.parametrize("to_dict", [True, False])
def test_gnmi_get(
    nfclient: object, worker: str, hosts: list[str], to_dict: bool
) -> None:
    result = nfclient.run_job(
        "nornir",
        "gnmi_get",
        workers=worker,
        kwargs={
            "path": ["openconfig-system:system/config/hostname"],
            "datatype": "config",
            "encoding": "json_ietf",
            "FL": hosts,
            "on_failed": True,
            "to_dict": to_dict,
            "add_details": True,
            "run_connect_retry": 0,
            "run_task_retry": 0,
        },
    )[worker]
    assert result["failed"] is False, result
    if to_dict:
        assert set(result["result"]) == set(hosts), result
        records = [result["result"][host]["get"] for host in hosts]
    else:
        records = result["result"]
        assert {record["host"] for record in records} == set(hosts), result
        assert all(record["name"] == "get" for record in records), result
    for record in records:
        assert record["failed"] is False, record
        assert record["result"]["notification"], record
        assert any(
            update["val"] in hosts
            for notification in record["result"]["notification"]
            for update in notification["update"]
        ), record


def test_gnmi_get_no_match(nfclient: object) -> None:
    result = nfclient.run_job(
        "nornir",
        "gnmi_get",
        workers="nornir-worker-1",
        kwargs={"path": ["/system"], "FL": ["no-such-gnmi-host"]},
    )["nornir-worker-1"]
    assert result["status"] == "no_match", result
    assert result["result"] == {}, result


@pytest.mark.parametrize(
    "kwargs",
    [{}, {"path": []}, {"path": [""]}, {"path": ["/system"], "datatype": "invalid"}],
)
def test_gnmi_get_invalid_arguments(nfclient: object, kwargs: dict) -> None:
    result = nfclient.run_job(
        "nornir",
        "gnmi_get",
        workers="nornir-worker-1",
        kwargs=kwargs,
    )["nornir-worker-1"]
    assert result["failed"] is True, result
    assert "ValidationError" in str(result), result


def test_gnmi_get_shell(
    nfclient: object,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Run the real shell command through the integration client."""
    monkeypatch.setattr(builtins, "NFCLIENT", nfclient, raising=False)
    output = StringIO()
    shell = App(NornirGnmiShell, stdout=output)
    shell.onecmd(
        "get workers nornir-worker-1 FL no-such-gnmi-host path /system verbose-result"
    )
    captured = capsys.readouterr().out + output.getvalue()
    assert "no_match" in captured, captured
