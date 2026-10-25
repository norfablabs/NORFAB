import pprint
from typing import Any

import pytest

pytestmark = pytest.mark.nfcli


class TestNetboxCreateAsn:
    def test_dry_run_with_sites(
        self, picle_shell: Any, capsys: pytest.CaptureFixture[str]
    ) -> None:
        shell, _ = picle_shell
        shell.onecmd("top")
        shell.onecmd(
            "netbox create asn asn 4200999702 rir lab "
            "sites SALTNORNIR-LAB,SALTNORNIR-LAB2 dry-run"
        )

        output = capsys.readouterr().out
        assert "4200999702" in output
        assert "create" in output


class TestShowCommands:
    def test_show_broker(self, picle_shell, capsys):
        shell, _ = picle_shell
        shell.onecmd("top")
        shell.onecmd("show norfab broker status")
        shell.onecmd("show norfab broker statistics")

        captured = capsys.readouterr()
        assert "broker_private_key_file" in captured.out
        assert "schema_version" in captured.out

    def test_show_client(self, picle_shell, capsys):
        shell, _ = picle_shell
        shell.onecmd("top")
        shell.onecmd("show norfab client status")
        shell.onecmd("show norfab client statistics")

        captured = capsys.readouterr()
        assert "client_private_key_file" in captured.out
        assert "PICLE Shell" in captured.out
        assert "schema_version" in captured.out

    @pytest.mark.skip(reason="TBD")
    def test_show_version(self):
        pass

    def test_show_workers(self, picle_shell, capsys):
        shell, _ = picle_shell
        shell.onecmd("top")
        shell.onecmd("show norfab workers status")
        shell.onecmd("show norfab workers statistics")

        captured = capsys.readouterr()
        assert "worker_private_key_file" in captured.out
        assert "schema_version" in captured.out

    @pytest.mark.skip(reason="TBD")
    def test_show_workers_by_status(self):
        pass


class TestNornirShowCommands:
    @pytest.mark.skip(reason="TBD")
    def test_show_hosts(self):
        pass

    @pytest.mark.skip(reason="TBD")
    def test_show_inventory(self):
        pass

    @pytest.mark.skip(reason="TBD")
    def test_show_version(self):
        pass

    def test_show_errdisabled_hosts(self, picle_shell, capsys):
        shell, _ = picle_shell
        shell.onecmd("top")
        shell.onecmd("show nornir errdisabled-hosts")

        captured = capsys.readouterr()
        assert "nornir-worker" in captured.out

    def test_clear_errdisabled_hosts(self, picle_shell, capsys):
        shell, _ = picle_shell
        shell.onecmd("top")
        shell.onecmd("nornir clear errdisabled-hosts")

        captured = capsys.readouterr()
        assert "nornir-worker" in captured.out


class TestNornirCli:
    @pytest.mark.skip(reason="TBD")
    def test_commands_list(self):
        pass

    @pytest.mark.skip(reason="TBD")
    def test_commands_dry_run(self):
        pass

    @pytest.mark.skip(reason="TBD")
    def test_commands_with_hosts_filters(self, nfclient):
        pass

    @pytest.mark.skip(reason="TBD")
    def test_commands_with_worker_target(self, nfclient):
        pass

    @pytest.mark.skip(reason="TBD")
    def test_commands_add_details(self, nfclient):
        pass

    @pytest.mark.skip(reason="TBD")
    def test_commands_to_dict_false(self, nfclient):
        pass

    @pytest.mark.skip(reason="TBD")
    def test_commands_to_dict_false_add_details(self, nfclient):
        pass

    @pytest.mark.skip(reason="TBD")
    def test_commands_wrong_plugin(self, nfclient):
        pass

    @pytest.mark.skip(reason="TBD")
    def test_commands_plugin_scrapli(self, nfclient):
        pass

    @pytest.mark.skip(reason="TBD")
    def test_commands_plugin_napalm(self, nfclient):
        pass

    @pytest.mark.skip(reason="TBD")
    def test_commands_from_file_dry_run(self, nfclient):
        pass

    @pytest.mark.skip(reason="TBD")
    def test_commands_from_nonexisting_file(self, nfclient):
        pass

    @pytest.mark.skip(reason="TBD")
    def test_commands_from_file_template(self, nfclient):
        pass

    @pytest.mark.skip(reason="TBD")
    def test_commands_table(self):
        pass

    @pytest.mark.skip(reason="TBD")
    def test_commands_table_headers(self):
        pass

    @pytest.mark.skip(reason="TBD")
    def test_commands_table_reverse(self):
        pass

    @pytest.mark.skip(reason="TBD")
    def test_commands_table_sortby(self):
        pass


class TestNornirDiagram:
    @pytest.mark.skip(reason="TBD")
    def test_nornir_diagram(self):
        pass


class TestDummyPluginShell:
    def test_dummy_show_version(self, picle_shell, capsys):
        shell, mock_stdout = picle_shell
        shell.onecmd("top")  # go to top
        shell.onecmd("dummy show version")

        captured = capsys.readouterr()
        pprint.pprint(captured.out)

        assert all(
            k in captured.out
            for k in [
                "dummy-worker-1:get_version",
                "result",
                "norfab",
                "platform",
                "python",
            ]
        )

    def test_dummy_show_inventory(self, picle_shell, capsys):
        shell, mock_stdout = picle_shell
        shell.onecmd("top")  # go to top
        shell.onecmd("dummy show inventory")

        captured = capsys.readouterr()
        pprint.pprint(captured.out)

        assert all(
            k in captured.out
            for k in [
                "dummy-worker-1:get_inventory",
                "result",
                "service",
                "data",
                "more",
            ]
        )


class TestNornirNetconfGet:
    @pytest.mark.parametrize("plugin", ["ncclient", "scrapli"])
    def test_get(
        self, picle_shell: Any, capsys: pytest.CaptureFixture[str], plugin: str
    ) -> None:
        shell, _ = picle_shell
        shell.onecmd("top")
        shell.onecmd(
            f"nornir netconf get plugin {plugin} workers nornir-worker-1 "
            "FL ceos-spine-1 on-failed filter-subtree nf://netconf/get_system.xml"
        )
        output = capsys.readouterr().out
        assert "ceos-spine-1" in output
        assert "<hostname>ceos-spine-1</hostname>" in output

    @pytest.mark.parametrize("plugin", ["ncclient", "scrapli"])
    @pytest.mark.parametrize(
        "getter",
        [
            "ietf-interfaces",
            "openconfig-interfaces",
            "openconfig-lldp",
            "openconfig-bgp",
            "openconfig-system",
            "ietf-routing",
            "ietf-hardware",
        ],
    )
    def test_getters(
        self,
        picle_shell: Any,
        capsys: pytest.CaptureFixture[str],
        plugin: str,
        getter: str,
    ) -> None:
        host = "csr1k-r1"
        worker = "nornir-worker-6"
        shell, _ = picle_shell
        shell.onecmd("top")
        shell.onecmd(
            f"nornir netconf get {getter} plugin {plugin} "
            f"workers {worker} FL {host} on-failed"
        )
        output = capsys.readouterr().out
        assert host in output
        assert "rpc-reply" in output
        assert "Traceback" not in output, output
        assert "rpc-error" not in output, output
        assert "<data" in output, output


class TestNornirNetconfXmlProcessors:
    @pytest.mark.parametrize("command", ["get", "get-config"])
    def test_xmltodict(
        self, picle_shell: Any, capsys: pytest.CaptureFixture[str], command: str
    ) -> None:
        shell, _ = picle_shell
        shell.onecmd("top")
        shell.onecmd(
            f"nornir netconf {command} xmltodict xpath (//hostname)[1] "
            "plugin ncclient workers nornir-worker-1 FL ceos-spine-1 on-failed"
        )
        output = capsys.readouterr().out
        assert "hostname:" in output
        assert "ceos-spine-1" in output
        assert "<hostname" not in output
        assert "Traceback" not in output
