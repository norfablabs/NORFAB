import pprint

import pytest

pytestmark = [pytest.mark.nornir, pytest.mark.cli, pytest.mark.task_nornir_cli]


@pytest.mark.task_nornir_cli
class TestNornirCli:
    def test_commands_list(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cli",
            workers=["nornir-worker-1", "nornir-worker-2"],
            kwargs={"commands": ["show version", "show clock"]},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert (
                    "show clock" in res and "Traceback" not in res["show clock"]
                ), f"{worker}:{host} show clock output is wrong"
                assert (
                    "show version" in res and "Traceback" not in res["show version"]
                ), f"{worker}:{host} show clock output is wrong"

    def test_commands_dry_run(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cli",
            kwargs={"commands": ["show version", "show clock"], "dry_run": True},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert (
                    "dry_run" in res and res["dry_run"] == "show version\nshow clock"
                ), f"{worker}:{host} dry run output is wrong"

    def test_commands_with_hosts_filters(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cli",
            kwargs={"commands": ["show version", "show clock"], "FC": "spine"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert (
                    "show clock" in res and "Traceback" not in res["show clock"]
                ), f"{worker}:{host} show clock output is wrong"
                assert (
                    "show version" in res and "Traceback" not in res["show version"]
                ), f"{worker}:{host} show clock output is wrong"

    def test_commands_with_worker_target(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cli",
            workers="nornir-worker-1",
            kwargs={"commands": ["show version", "show clock"]},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert (
                    "show clock" in res and "Traceback" not in res["show clock"]
                ), f"{worker}:{host} show clock output is wrong"
                assert (
                    "show version" in res and "Traceback" not in res["show version"]
                ), f"{worker}:{host} show clock output is wrong"

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

    def test_commands_plugin_scrapli(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cli",
            workers="nornir-worker-1",
            kwargs={"commands": ["show version", "show clock"], "plugin": "scrapli"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert (
                    "show clock" in res and "Traceback" not in res["show clock"]
                ), f"{worker}:{host} show clock output is wrong"
                assert (
                    "show version" in res and "Traceback" not in res["show version"]
                ), f"{worker}:{host} show clock output is wrong"

    def test_commands_plugin_napalm(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cli",
            workers="nornir-worker-1",
            kwargs={"commands": ["show version", "show clock"], "plugin": "napalm"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert (
                    "show clock" in res and "Traceback" not in res["show clock"]
                ), f"{worker}:{host} show clock output is wrong"
                assert (
                    "show version" in res and "Traceback" not in res["show version"]
                ), f"{worker}:{host} show clock output is wrong"

    def test_commands_from_file_dry_run(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cli",
            kwargs={
                "commands": "nf://cli/commands.txt",
                "dry_run": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert (
                    "dry_run" in res
                    and res["dry_run"]
                    == "show version\nshow clock\nshow int description"
                ), f"{worker}:{host} output is wrong"

    def test_commands_from_nonexisting_file(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cli",
            workers="nornir-worker-1",
            kwargs={"commands": "nf://cli/commands_non_existing.txt"},
        )
        pprint.pprint(ret)

        assert ret["nornir-worker-1"]["failed"] == True
        assert ret["nornir-worker-1"]["errors"]

    def test_commands_from_file_template(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cli",
            kwargs={
                "commands": "nf://cli/show_interfaces.j2",
                "dry_run": True,
            },
        )
        pprint.pprint(ret)

        found_ceos_spine_1 = False
        found_ceos_spine_2 = False

        for worker, results in ret.items():
            for host, res in results["result"].items():
                if host == "ceos-spine-1":
                    found_ceos_spine_1 = True
                    assert "loopback0" in res["dry_run"]
                    assert "ethernet1" in res["dry_run"]
                elif host == "ceos-spine-2":
                    assert "loopback0" not in res["dry_run"]
                    assert "ethernet1" in res["dry_run"]
                    found_ceos_spine_2 = True

        assert found_ceos_spine_1, "No results for ceos-spine-1"
        assert found_ceos_spine_2, "No results for ceos-spine-2"

    def test_run_ttp(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cli",
            workers="nornir-worker-1",
            kwargs={
                "run_ttp": "nf://ttp/parse_eos_intf.txt",
                "FB": ["ceos-spine-*"],
                "enable": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert "run_ttp" in res, f"{worker}:{host} no run_ttp output"
                for interface in res["run_ttp"]:
                    assert (
                        "interface" in interface
                    ), f"{worker}:{host} run_ttp output is wrong"

    def test_commands_template_with_norfab_client_call(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cli",
            workers="nornir-worker-1",
            kwargs={
                "commands": "nf://cli/test_commands_template_with_norfab_call.j2",
                "dry_run": True,
                "FL": ["ceos-spine-1"],
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert all(
                    k in res["dry_run"]
                    for k in [
                        "nornir-worker-2",
                        "ceos-leaf-1",
                        "nr_test",
                        "eos-leaf-3",
                        "eos-leaf-2",
                    ]
                ), f"{worker}:{host} output is wrong"

    def test_commands_template_with_nornir_worker_call(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cli",
            workers="nornir-worker-1",
            kwargs={
                "commands": "nf://cli/test_commands_template_with_nornir_worker_call.j2",
                "dry_run": True,
                "FL": ["ceos-spine-1", "ceos-spine-2"],
            },
        )
        pprint.pprint(ret, width=150)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert all(
                    k in res["dry_run"]
                    for k in [
                        "updated by norfab 1234",
                        "interface Ethernet",
                        "description",
                    ]
                ), f"{worker}:{host} output is wrong"

    def test_commands_with_tests(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cli",
            workers="nornir-worker-1",
            kwargs={
                "commands": ["show version", "show clock"],
                "tests": [
                    ["show version", "contains", "cEOS"],
                    ["show clock", "contains", "NTP"],
                ],
                "FL": ["ceos-spine-1", "ceos-spine-2"],
                "remove_tasks": False,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert all(
                    k in res
                    for k in [
                        "show clock",
                        "show clock contains NTP..",
                        "show version",
                        "show version contains cEOS..",
                    ]
                )

    @pytest.mark.skip(reason="TBD")
    def test_commands_with_tf_processor(self, nfclient):
        pass

    @pytest.mark.skip(reason="TBD")
    def test_commands_with_diff_processor(self, nfclient):
        pass

    @pytest.mark.skip(reason="TBD")
    def test_commands_with_diff_processor_diff_last(self, nfclient):
        pass

    def test_commands_template_with_job_data_dict(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cli",
            kwargs={
                "job_data": {"commands": ["show version", "show clock"]},
                "FL": ["ceos-spine-1", "ceos-spine-2"],
                "dry_run": True,
                "commands": "nf://cli/template_with_job_data.txt",
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert (
                    "show version" in res["dry_run"] and "show clock" in res["dry_run"]
                ), f"{worker}:{host} output is wrong"

    def test_commands_template_with_job_data_file(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cli",
            kwargs={
                "job_data": "nf://cli/job_data_1.txt",
                "FL": ["ceos-spine-1", "ceos-spine-2"],
                "dry_run": True,
                "commands": "nf://cli/template_with_job_data.txt",
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert (
                    "show version" in res["dry_run"] and "show clock" in res["dry_run"]
                ), f"{worker}:{host} output is wrong"

    def test_commands_template_with_job_data_wrong_file(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cli",
            workers=["nornir-worker-1"],
            kwargs={
                "job_data": "nf://cli/job_data_non_exist.txt",
                "FL": ["ceos-spine-1", "ceos-spine-2"],
                "dry_run": True,
                "commands": "nf://cli/template_with_job_data.txt",
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["errors"]
            assert "FileNotFoundError" in results["errors"][0]

    def test_commands_template_with_job_data_wrong_yaml(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cli",
            workers=["nornir-worker-1"],
            kwargs={
                "job_data": "nf://cli/job_data_wrong_yaml.txt",
                "FL": ["ceos-spine-1", "ceos-spine-2"],
                "dry_run": True,
                "commands": "nf://cli/template_with_job_data.txt",
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["errors"]
            assert "yaml.scanner.ScannerError" in results["errors"][0]


# ----------------------------------------------------------------------------
# NORNIR.TASK FUNCTION TESTS
# ----------------------------------------------------------------------------
