import pprint

import pytest

pytestmark = pytest.mark.nfcli


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
