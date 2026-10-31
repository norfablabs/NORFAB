"""gNMI integration tests against the cEOS lab through nfclient."""

import builtins
import json
from io import StringIO

import pytest
from picle import App

from norfab.clients.nfcli_shell.nornir.nornir_picle_shell_gnmi import NornirGnmiShell

pytestmark = [pytest.mark.nornir, pytest.mark.nornir_gnmi]


class TestGnmiGet:
    @pytest.mark.parametrize(
        "worker,hosts",
        [
            ("nornir-worker-1", ["ceos-spine-1", "ceos-spine-2"]),
            ("nornir-worker-2", ["ceos-leaf-1", "ceos-leaf-2", "ceos-leaf-3"]),
        ],
    )
    def test_gnmi_get(self, nfclient: object, worker: str, hosts: list[str]) -> None:
        result = nfclient.run_job(
            "nornir",
            "gnmi_get",
            workers=worker,
            kwargs={
                "path": ["/system/config/hostname"],
                "datatype": "config",
                "FL": hosts,
                "on_failed": True,
                "run_connect_retry": 0,
                "run_task_retry": 0,
            },
        )[worker]
        assert result["failed"] is False, result
        assert set(result["result"]) == set(hosts), result
        for host in hosts:
            reply = result["result"][host]["get"]
            assert reply["notification"], reply
            assert any(
                update["val"] == host
                for notification in reply["notification"]
                for update in notification["update"]
            ), reply

    def test_gnmi_get_no_match(self, nfclient: object) -> None:
        result = nfclient.run_job(
            "nornir",
            "gnmi_get",
            workers="nornir-worker-1",
            kwargs={"path": ["/system"], "FL": ["no-such-gnmi-host"]},
        )["nornir-worker-1"]
        assert result["status"] == "no_match", result
        assert result["result"] == {}, result

    @pytest.mark.parametrize(
        "selector",
        [
            "path /system/config/hostname",
            "openconfig-system",
            "openconfig-interfaces",
            "openconfig-lldp",
            "openconfig-platform",
        ],
    )
    def test_gnmi_get_shell(
        self,
        nfclient: object,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        selector: str,
    ) -> None:
        """Run the real shell command through the integration client."""
        monkeypatch.setattr(builtins, "NFCLIENT", nfclient, raising=False)
        output = StringIO()
        shell = App(NornirGnmiShell, stdout=output)
        shell.onecmd(
            f"get workers nornir-worker-1 FL ceos-spine-1 {selector} on-failed"
        )
        captured = capsys.readouterr().out + output.getvalue()
        assert "ceos-spine-1" in captured, captured
        assert "notification" in captured, captured

    @pytest.mark.parametrize(
        "getter,node",
        [
            ("openconfig_system", "system"),
            ("openconfig_interfaces", "interfaces"),
            ("openconfig_lldp", "lldp"),
            ("openconfig_platform", "components"),
        ],
    )
    def test_gnmi_get_shortcuts(self, nfclient: object, getter: str, node: str) -> None:
        result = nfclient.run_job(
            "nornir",
            "gnmi_get",
            workers="nornir-worker-1",
            kwargs={getter: True, "FL": ["ceos-spine-1"], "on_failed": True},
        )["nornir-worker-1"]
        assert result["failed"] is False, result
        notifications = result["result"]["ceos-spine-1"]["get"]["notification"]
        assert notifications, result
        assert node in str(notifications), result


class TestGnmiSet:
    def test_gnmi_set_no_match(self, nfclient: object) -> None:
        result = nfclient.run_job(
            "nornir",
            "gnmi_set",
            workers="nornir-worker-1",
            kwargs={
                "delete": ["/interfaces/interface[name=Loopback9999]"],
                "FL": ["no-such-gnmi-host"],
            },
        )["nornir-worker-1"]
        assert result["status"] == "no_match", result
        assert result["result"] == {}, result

    def test_gnmi_set_operations(self, nfclient: object) -> None:
        """Create only unused test-owned loopbacks, read back changes, and remove them."""
        common = {
            "FL": ["ceos-spine-1"],
            "on_failed": True,
            "run_task_retry": 0,
        }
        names = [f"Loopback{1983 + offset}" for offset in range(3)]
        before = nfclient.run_job(
            "nornir",
            "gnmi_get",
            workers="nornir-worker-1",
            kwargs={**common, "openconfig_interfaces": True, "datatype": "config"},
        )["nornir-worker-1"]
        assert before["failed"] is False, before
        assert all(name not in str(before["result"]) for name in names), before
        paths = [f"openconfig:/interfaces/interface[name={name}]" for name in names]
        try:
            created = nfclient.run_job(
                "nornir",
                "gnmi_set",
                workers="nornir-worker-1",
                kwargs={
                    **common,
                    "update": [
                        [
                            path + "/config",
                            {
                                "name": name,
                                "type": "iana-if-type:softwareLoopback",
                                "description": "norfab-gnmi-created",
                            },
                        ]
                        for path, name in zip(paths, names)
                    ],
                },
            )["nornir-worker-1"]
            assert created["failed"] is False, created
            record = created["result"]["ceos-spine-1"]["set"]
            assert record["response"], record
            readback = nfclient.run_job(
                "nornir",
                "gnmi_get",
                workers="nornir-worker-1",
                kwargs={
                    **common,
                    "path": [path + "/config" for path in paths],
                    "datatype": "config",
                },
            )["nornir-worker-1"]
            assert readback["failed"] is False, readback
            assert "norfab-gnmi-created" in str(readback["result"]), readback
            replaced = nfclient.run_job(
                "nornir",
                "gnmi_set",
                workers="nornir-worker-1",
                kwargs={
                    **common,
                    "replace": [
                        [
                            paths[0] + "/config",
                            {
                                "name": names[0],
                                "type": "iana-if-type:softwareLoopback",
                                "description": "norfab-gnmi-replaced",
                            },
                        ]
                    ],
                },
            )["nornir-worker-1"]
            assert replaced["failed"] is False, replaced
            readback = nfclient.run_job(
                "nornir",
                "gnmi_get",
                workers="nornir-worker-1",
                kwargs={**common, "path": [paths[0] + "/config"], "datatype": "config"},
            )["nornir-worker-1"]
            assert readback["failed"] is False, readback
            assert "norfab-gnmi-replaced" in str(readback["result"]), readback
            combined = nfclient.run_job(
                "nornir",
                "gnmi_set",
                workers="nornir-worker-1",
                kwargs={
                    **common,
                    "prefix": "openconfig:/interfaces",
                    "update": "nf://gnmi/combined_update.yaml",
                    "replace": "nf://gnmi/combined_replace.yaml",
                    "delete": "nf://gnmi/combined_delete.yaml",
                },
            )["nornir-worker-1"]
            assert combined["failed"] is False, combined
            readback = nfclient.run_job(
                "nornir",
                "gnmi_get",
                workers="nornir-worker-1",
                kwargs={**common, "openconfig_interfaces": True, "datatype": "config"},
            )["nornir-worker-1"]
            assert readback["failed"] is False, readback
            assert "norfab-gnmi-combined" in str(readback["result"]), readback
            assert "norfab-gnmi-combined-replace" in str(readback["result"]), readback
            assert names[1] not in str(readback["result"]), readback
        finally:
            cleanup = nfclient.run_job(
                "nornir",
                "gnmi_set",
                workers="nornir-worker-1",
                kwargs={**common, "delete": paths},
            )["nornir-worker-1"]
            assert cleanup["failed"] is False, cleanup
            after = nfclient.run_job(
                "nornir",
                "gnmi_get",
                workers="nornir-worker-1",
                kwargs={**common, "openconfig_interfaces": True, "datatype": "config"},
            )["nornir-worker-1"]
            assert after["failed"] is False, after
            assert all(name not in str(after["result"]) for name in names), after

    @pytest.mark.parametrize("delete_command", ["set delete", "delete path"])
    def test_gnmi_set_shell(
        self,
        nfclient: object,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        delete_command: str,
    ) -> None:
        common = {
            "FL": ["ceos-spine-1"],
            "on_failed": True,
            "run_task_retry": 0,
        }
        name = "Loopback1994"
        path = f"openconfig:/interfaces/interface[name={name}]"
        before = nfclient.run_job(
            "nornir",
            "gnmi_get",
            workers="nornir-worker-1",
            kwargs={**common, "openconfig_interfaces": True, "datatype": "config"},
        )["nornir-worker-1"]
        assert before["failed"] is False, before
        assert name not in str(before["result"]), before
        monkeypatch.setattr(builtins, "NFCLIENT", nfclient, raising=False)
        shell = App(NornirGnmiShell, stdout=StringIO())
        payload = json.dumps(
            [
                [
                    path + "/config",
                    {
                        "name": name,
                        "type": "iana-if-type:softwareLoopback",
                        "description": "norfab-gnmi-shell",
                    },
                ]
            ]
        )
        try:
            shell.onecmd(
                f"set workers nornir-worker-1 FL ceos-spine-1 update {payload} on-failed task-retry 0"
            )
            readback = nfclient.run_job(
                "nornir",
                "gnmi_get",
                workers="nornir-worker-1",
                kwargs={**common, "openconfig_interfaces": True, "datatype": "config"},
            )["nornir-worker-1"]
            assert readback["failed"] is False, readback
            assert "norfab-gnmi-shell" in str(
                readback["result"]
            ), capsys.readouterr().out
            shell.onecmd(
                f"{delete_command.split()[0]} workers nornir-worker-1 FL ceos-spine-1 {delete_command.split()[1]} {path} on-failed task-retry 0"
            )
            readback = nfclient.run_job(
                "nornir",
                "gnmi_get",
                workers="nornir-worker-1",
                kwargs={**common, "openconfig_interfaces": True, "datatype": "config"},
            )["nornir-worker-1"]
            assert readback["failed"] is False, readback
            assert name not in str(readback["result"]), capsys.readouterr().out
        finally:
            cleanup = nfclient.run_job(
                "nornir",
                "gnmi_set",
                workers="nornir-worker-1",
                kwargs={**common, "delete": [path]},
            )["nornir-worker-1"]
            assert cleanup["failed"] is False, cleanup

    @pytest.mark.parametrize("delete_task", ["gnmi_set", "gnmi_delete"])
    def test_gnmi_files(
        self,
        nfclient: object,
        delete_task: str,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        common = {"FL": ["ceos-spine-1"], "on_failed": True, "run_task_retry": 0}
        before = nfclient.run_job(
            "nornir",
            "gnmi_get",
            workers="nornir-worker-1",
            kwargs={**common, "openconfig_interfaces": True, "datatype": "config"},
        )["nornir-worker-1"]
        assert before["failed"] is False, before
        assert "Loopback1997" not in str(before["result"]), before
        monkeypatch.setattr(builtins, "NFCLIENT", nfclient, raising=False)
        shell = App(NornirGnmiShell, stdout=StringIO())
        try:
            shell.onecmd(
                "set workers nornir-worker-1 FL ceos-spine-1 update nf://gnmi/update.yaml on-failed task-retry 0"
            )
            readback = nfclient.run_job(
                "nornir",
                "gnmi_get",
                workers="nornir-worker-1",
                kwargs={**common, "path": "nf://gnmi/get.json", "datatype": "config"},
            )["nornir-worker-1"]
            assert readback["failed"] is False, readback
            assert "norfab-file-update" in str(
                readback["result"]
            ), capsys.readouterr().out
            replaced = nfclient.run_job(
                "nornir",
                "gnmi_set",
                workers="nornir-worker-1",
                kwargs={
                    **common,
                    "replace": "nf://gnmi/replace.json",
                    "target": "ceos-spine-1",
                },
            )["nornir-worker-1"]
            assert replaced["failed"] is False, replaced
            readback = nfclient.run_job(
                "nornir",
                "gnmi_get",
                workers="nornir-worker-1",
                kwargs={**common, "path": "nf://gnmi/get.json", "datatype": "config"},
            )["nornir-worker-1"]
            assert readback["failed"] is False, readback
            assert "norfab-file-replace" in str(readback["result"]), readback
            command, argument = (
                ("set", "delete") if delete_task == "gnmi_set" else ("delete", "path")
            )
            shell.onecmd(
                f"{command} workers nornir-worker-1 FL ceos-spine-1 {argument} nf://gnmi/delete.yaml on-failed task-retry 0"
            )
            after = nfclient.run_job(
                "nornir",
                "gnmi_get",
                workers="nornir-worker-1",
                kwargs={**common, "openconfig_interfaces": True, "datatype": "config"},
            )["nornir-worker-1"]
            assert after["failed"] is False, after
            assert "Loopback1997" not in str(after["result"]), capsys.readouterr().out
        finally:
            cleanup = nfclient.run_job(
                "nornir",
                "gnmi_delete",
                workers="nornir-worker-1",
                kwargs={
                    **common,
                    "path": ["openconfig:/interfaces/interface[name=Loopback1997]"],
                },
            )["nornir-worker-1"]
            assert cleanup["failed"] is False, cleanup


class TestGnmiDelete:
    def test_gnmi_delete_no_match(self, nfclient: object) -> None:
        result = nfclient.run_job(
            "nornir",
            "gnmi_delete",
            workers="nornir-worker-1",
            kwargs={"path": ["/interfaces"], "FL": ["no-such-gnmi-host"]},
        )["nornir-worker-1"]
        assert result["status"] == "no_match", result
        assert result["result"] == {}, result

    def test_gnmi_delete(self, nfclient: object) -> None:
        common = {"FL": ["ceos-spine-1"], "on_failed": True, "run_task_retry": 0}
        path = "openconfig:/interfaces/interface[name=Loopback1996]"
        before = nfclient.run_job(
            "nornir",
            "gnmi_get",
            workers="nornir-worker-1",
            kwargs={**common, "openconfig_interfaces": True, "datatype": "config"},
        )["nornir-worker-1"]
        assert before["failed"] is False, before
        assert "Loopback1996" not in str(before["result"]), before
        try:
            created = nfclient.run_job(
                "nornir",
                "gnmi_set",
                workers="nornir-worker-1",
                kwargs={
                    **common,
                    "update": [
                        [
                            path + "/config",
                            {
                                "name": "Loopback1996",
                                "type": "iana-if-type:softwareLoopback",
                                "description": "norfab-delete-test",
                            },
                        ]
                    ],
                },
            )["nornir-worker-1"]
            assert created["failed"] is False, created
            readback = nfclient.run_job(
                "nornir",
                "gnmi_get",
                workers="nornir-worker-1",
                kwargs={**common, "openconfig_interfaces": True, "datatype": "config"},
            )["nornir-worker-1"]
            assert readback["failed"] is False, readback
            assert "norfab-delete-test" in str(readback["result"]), readback
            deleted = nfclient.run_job(
                "nornir",
                "gnmi_delete",
                workers="nornir-worker-1",
                kwargs={
                    **common,
                    "prefix": "openconfig:/interfaces",
                    "path": ["interface[name=Loopback1996]"],
                },
            )["nornir-worker-1"]
            assert deleted["failed"] is False, deleted
            assert deleted["task"] == "nornir-worker-1:gnmi_delete", deleted
            assert deleted["result"]["ceos-spine-1"]["set"]["response"], deleted
            after = nfclient.run_job(
                "nornir",
                "gnmi_get",
                workers="nornir-worker-1",
                kwargs={**common, "openconfig_interfaces": True, "datatype": "config"},
            )["nornir-worker-1"]
            assert after["failed"] is False, after
            assert "Loopback1996" not in str(after["result"]), after
        finally:
            cleanup = nfclient.run_job(
                "nornir",
                "gnmi_delete",
                workers="nornir-worker-1",
                kwargs={**common, "path": [path]},
            )["nornir-worker-1"]
            assert cleanup["failed"] is False, cleanup


class TestGnmiGetCapabilities:
    @pytest.mark.parametrize(
        "worker,hosts",
        [
            ("nornir-worker-1", {"ceos-spine-1", "ceos-spine-2"}),
            ("nornir-worker-2", {"ceos-leaf-1", "ceos-leaf-2", "ceos-leaf-3"}),
        ],
    )
    def test_gnmi_get_capabilities(
        self, nfclient: object, worker: str, hosts: set[str]
    ) -> None:
        result = nfclient.run_job(
            "nornir",
            "gnmi_get_capabilities",
            workers=worker,
            kwargs={
                "FL": sorted(hosts),
                "on_failed": True,
            },
        )[worker]
        assert result["failed"] is False, result
        assert set(result["result"]) == hosts, result
        for value in result["result"].values():
            reply = value["capabilities"]
            assert reply["gnmi_version"], reply
            assert reply["supported_encodings"], reply
            assert any(
                model["name"] == "openconfig-interfaces"
                for model in reply["supported_models"]
            ), reply

    def test_gnmi_get_capabilities_no_match(self, nfclient: object) -> None:
        result = nfclient.run_job(
            "nornir",
            "gnmi_get_capabilities",
            workers="nornir-worker-1",
            kwargs={"FL": ["no-such-gnmi-host"]},
        )["nornir-worker-1"]
        assert result["status"] == "no_match", result
        assert result["result"] == {}, result

    def test_gnmi_get_capabilities_shell(
        self,
        nfclient: object,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr(builtins, "NFCLIENT", nfclient, raising=False)
        output = StringIO()
        shell = App(NornirGnmiShell, stdout=output)
        shell.onecmd(
            "get-capabilities workers nornir-worker-1 FL ceos-spine-1 on-failed"
        )
        captured = capsys.readouterr().out + output.getvalue()
        assert "openconfig-interfaces" in captured, captured
        assert "supported_encodings" in captured, captured
