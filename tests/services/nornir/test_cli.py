import pprint
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.nornir,
    pytest.mark.nornir_cli,
]


def _assert_cli_commands_ok(worker, host, res):
    assert (
        "show clock" in res and "Traceback" not in res["show clock"]
    ), f"{worker}:{host} show clock output is wrong"
    assert (
        "show version" in res and "Traceback" not in res["show version"]
    ), f"{worker}:{host} show version output is wrong"


def _assert_cli_details(details):
    assert isinstance(details, dict), "detailed output was not produced"
    assert all(
        k in details
        for k in [
            "changed",
            "connection_retry",
            "diff",
            "exception",
            "failed",
            "result",
            "task_retry",
        ]
    ), "detailed output incomplete"


class TestNornirCli:
    @pytest.mark.nornir_fakenos
    def test_commands_stop_after_nonexistent_host_failure(self, nfclient):
        host_name = "non-existent-host"
        healthy_host_name = "fn-ceos-sp-1"
        commands = ["show version", "show clock", "show hostname"]

        nfclient.run_job(
            "nornir",
            "runtime_inventory",
            workers=["nornir-worker-4"],
            kwargs={
                "action": "create_host",
                "name": host_name,
                "hostname": "non-existent.invalid",
                "platform": "arista_eos",
                "username": "admin",
                "password": "admin",
            },
        )

        try:
            ret = nfclient.run_job(
                "nornir",
                "cli",
                workers=["nornir-worker-4"],
                kwargs={
                    "on_failed": True,
                    "commands": commands,
                    "FL": [host_name, healthy_host_name],
                    "run_connect_retry": 0,
                    "run_connect_timeout": 2,
                },
            )
            pprint.pprint(ret)

            result = ret["nornir-worker-4"]
            host_result = result["result"][host_name]
            healthy_host_result = result["result"][healthy_host_name]

            assert result["failed"] is True
            assert result["resources"] == sorted([host_name, healthy_host_name])
            assert result["resources_failed"] == [host_name]
            assert list(host_result) == ["netmiko_send_commands"]
            assert all(command not in host_result for command in commands)
            assert "connection to device failed" in host_result["netmiko_send_commands"]
            assert all(
                command in healthy_host_result
                and "Traceback" not in healthy_host_result[command]
                for command in commands
            )

            errdisabled = nfclient.run_job(
                "nornir",
                "errdisabled_hosts_list",
                workers=["nornir-worker-4"],
            )["nornir-worker-4"]["result"]
            errdisabled_host = next(
                item for item in errdisabled if item["host"] == host_name
            )

            assert errdisabled_host["errdisabled_at"]
            assert 0 < errdisabled_host["recovery_time_left"] <= 60
            assert "connection to device failed" in errdisabled_host["reason"]

            skipped_ret = nfclient.run_job(
                "nornir",
                "cli",
                workers=["nornir-worker-4"],
                kwargs={
                    "on_failed": False,
                    "commands": commands,
                    "dry_run": True,
                    "FL": [host_name, healthy_host_name],
                },
            )["nornir-worker-4"]

            assert skipped_ret["failed"] is False
            assert skipped_ret["resources"] == [healthy_host_name]
            assert list(skipped_ret["result"]) == [healthy_host_name]

            clear_ret = nfclient.run_job(
                "nornir",
                "errdisabled_hosts_clear",
                workers=["nornir-worker-4"],
            )["nornir-worker-4"]

            assert clear_ret["failed"] is False
            assert clear_ret["result"] == [host_name]

            errdisabled = nfclient.run_job(
                "nornir",
                "errdisabled_hosts_list",
                workers=["nornir-worker-4"],
            )["nornir-worker-4"]["result"]
            assert all(item["host"] != host_name for item in errdisabled)

            recovered_ret = nfclient.run_job(
                "nornir",
                "cli",
                workers=["nornir-worker-4"],
                kwargs={
                    "on_failed": False,
                    "commands": commands,
                    "dry_run": True,
                    "FL": [host_name, healthy_host_name],
                },
            )["nornir-worker-4"]

            assert recovered_ret["failed"] is False
            assert recovered_ret["resources"] == sorted([host_name, healthy_host_name])
            assert set(recovered_ret["result"]) == {
                host_name,
                healthy_host_name,
            }
        finally:
            nfclient.run_job(
                "nornir",
                "errdisabled_hosts_clear",
                workers=["nornir-worker-4"],
            )
            nfclient.run_job(
                "nornir",
                "runtime_inventory",
                workers=["nornir-worker-4"],
                kwargs={"action": "delete_host", "name": host_name},
            )

    @pytest.mark.nornir_fakenos
    def test_commands_list(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cli",
            workers=["nornir-worker-4"],
            kwargs={
                "on_failed": True,
                "commands": ["show version", "show clock"],
                "FL": [
                    "fn-ceos-sp-1",
                    "fn-ceos-sp-2",
                    "fn-ceos-lf-1",
                    "fn-ceos-lf-2",
                    "fn-ceos-lf-3",
                ],
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                _assert_cli_commands_ok(worker, host, res)

    @pytest.mark.nornir_fakenos
    def test_commands_dry_run(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cli",
            workers=["nornir-worker-4"],
            kwargs={
                "on_failed": True,
                "commands": ["show version", "show clock"],
                "dry_run": True,
                "FL": ["fn-ceos-sp-1"],
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert (
                    "dry_run" in res and res["dry_run"] == "show version\nshow clock"
                ), f"{worker}:{host} dry run output is wrong"

    @pytest.mark.nornir_fakenos
    def test_commands_with_hosts_filters(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cli",
            workers=["nornir-worker-4"],
            kwargs={
                "on_failed": True,
                "commands": ["show version", "show clock"],
                "FC": "fn-ceos-sp",
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert "fn-ceos-sp" in host, f"{worker}:{host} host filter is wrong"
                _assert_cli_commands_ok(worker, host, res)

    @pytest.mark.nornir_fakenos
    def test_commands_with_worker_target(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cli",
            workers="nornir-worker-4",
            kwargs={
                "on_failed": True,
                "commands": ["show version", "show clock"],
                "FL": ["fn-ceos-sp-1"],
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                _assert_cli_commands_ok(worker, host, res)

    @pytest.mark.nornir_fakenos
    def test_commands_add_details(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cli",
            workers=["nornir-worker-4"],
            kwargs={
                "on_failed": True,
                "commands": ["show version", "show clock"],
                "FL": ["fn-ceos-sp-1"],
                "add_details": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is False, f"{worker} failed to run cli task"
            for host, res in results["result"].items():
                _assert_cli_details(res["show version"])
                _assert_cli_details(res["show clock"])
                assert (
                    "cEOS" in res["show version"]["result"]
                ), f"{worker}:{host} show version output is wrong"

    @pytest.mark.nornir_fakenos
    def test_commands_to_dict_false(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cli",
            workers=["nornir-worker-4"],
            kwargs={
                "on_failed": True,
                "commands": ["show version", "show clock"],
                "FL": ["fn-ceos-sp-1"],
                "to_dict": False,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is False, f"{worker} failed to run cli task"
            assert isinstance(
                results["result"], list
            ), f"{worker} did not return list result"
            assert len(results["result"]) == 2, f"{worker} returned wrong item count"
            for host_res in results["result"]:
                assert all(
                    k in host_res for k in ["name", "result", "host"]
                ), f"{worker} host output incomplete"
                assert host_res["host"] == "fn-ceos-sp-1"
                assert host_res["name"] in ["show version", "show clock"]
                assert "Traceback" not in host_res["result"]

    @pytest.mark.nornir_fakenos
    def test_commands_to_dict_false_add_details(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cli",
            workers=["nornir-worker-4"],
            kwargs={
                "on_failed": True,
                "commands": ["show version", "show clock"],
                "FL": ["fn-ceos-sp-1"],
                "to_dict": False,
                "add_details": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is False, f"{worker} failed to run cli task"
            assert isinstance(
                results["result"], list
            ), f"{worker} did not return list result"
            assert len(results["result"]) == 2, f"{worker} returned wrong item count"
            for host_res in results["result"]:
                assert host_res["host"] == "fn-ceos-sp-1"
                assert host_res["name"] in ["show version", "show clock"]
                _assert_cli_details(host_res)

    @pytest.mark.nornir_fakenos
    def test_commands_wrong_plugin(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cli",
            workers=["nornir-worker-4"],
            kwargs={
                "on_failed": True,
                "commands": ["show version"],
                "FL": ["fn-ceos-sp-1"],
                "plugin": "wrong_plugin",
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["errors"], f"{worker} did not raise error"
            assert (
                "ValidationError" in results["errors"][0]
            ), f"{worker} did not raise validation error"

    @pytest.mark.nornir_fakenos
    def test_commands_plugin_scrapli(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cli",
            workers=["nornir-worker-4"],
            kwargs={
                "on_failed": True,
                "commands": ["show version", "show clock"],
                "plugin": "scrapli",
                "FL": ["fn-ceos-sp-1"],
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                _assert_cli_commands_ok(worker, host, res)

    def test_commands_plugin_napalm(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cli",
            workers="nornir-worker-1",
            kwargs={
                "on_failed": True,
                "commands": ["show version", "show clock"],
                "plugin": "napalm",
            },
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

    @pytest.mark.nornir_fakenos
    def test_commands_inline_template_per_host_dry_run(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cli",
            workers=["nornir-worker-4"],
            kwargs={
                "on_failed": True,
                "commands": "show hostname {{ host.name }}",
                "dry_run": True,
                "FL": ["fn-ceos-sp-1", "fn-ceos-sp-2"],
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert (
                    res["dry_run"] == f"show hostname {host}"
                ), f"{worker}:{host} per-host command rendering is wrong"

    @pytest.mark.nornir_fakenos
    def test_commands_from_file_dry_run(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cli",
            workers=["nornir-worker-4"],
            kwargs={
                "on_failed": True,
                "commands": "nf://cli/commands.txt",
                "dry_run": True,
                "FL": ["fn-ceos-sp-1"],
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

    @pytest.mark.nornir_fakenos
    def test_commands_from_nonexisting_file(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cli",
            workers="nornir-worker-4",
            kwargs={
                "on_failed": True,
                "commands": "nf://cli/commands_non_existing.txt",
            },
        )
        pprint.pprint(ret)

        assert ret["nornir-worker-4"]["failed"] == True
        assert ret["nornir-worker-4"]["errors"]

    @pytest.mark.nornir_fakenos
    def test_commands_from_file_template(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cli",
            workers=["nornir-worker-4"],
            kwargs={
                "on_failed": True,
                "commands": "nf://cli/show_interfaces.j2",
                "dry_run": True,
                "FL": ["fn-ceos-sp-1", "fn-ceos-sp-2"],
            },
        )
        pprint.pprint(ret)

        found_fn_ceos_sp_1 = False
        found_fn_ceos_sp_2 = False

        for worker, results in ret.items():
            for host, res in results["result"].items():
                if host == "fn-ceos-sp-1":
                    found_fn_ceos_sp_1 = True
                    assert "loopback0" in res["dry_run"]
                    assert "ethernet1" in res["dry_run"]
                elif host == "fn-ceos-sp-2":
                    assert "loopback0" not in res["dry_run"]
                    assert "ethernet1" in res["dry_run"]
                    found_fn_ceos_sp_2 = True

        assert found_fn_ceos_sp_1, "No results for fn-ceos-sp-1"
        assert found_fn_ceos_sp_2, "No results for fn-ceos-sp-2"

    @pytest.mark.nornir_fakenos
    def test_commands_from_dynamic_file_template_per_host(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cli",
            workers=["nornir-worker-4"],
            kwargs={
                "on_failed": True,
                "commands": "nf://cli/{{ host.name }}_commands.j2",
                "dry_run": True,
                "FL": ["fn-ceos-sp-1", "fn-ceos-sp-2"],
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert (
                    f"show dynamic command for {host}" in res["dry_run"]
                ), f"{worker}:{host} dynamic command template fetch is wrong"
                assert (
                    f"show rendered command for {host}" in res["dry_run"]
                ), f"{worker}:{host} dynamic command template rendering is wrong"

    @pytest.mark.nornir_fakenos
    def test_run_ttp(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cli",
            workers="nornir-worker-4",
            kwargs={
                "on_failed": True,
                "run_ttp": "nf://ttp/parse_eos_intf.txt",
                "FB": ["fn-ceos-sp-*"],
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

    @pytest.mark.nornir_fakenos
    def test_commands_template_with_norfab_client_call(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cli",
            workers="nornir-worker-4",
            kwargs={
                "on_failed": True,
                "commands": "nf://cli/test_commands_template_with_norfab_call.j2",
                "dry_run": True,
                "FL": ["fn-ceos-sp-1"],
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert all(
                    k in res["dry_run"]
                    for k in [
                        "nornir-worker-4",
                        "fn-ceos-lf-1",
                        "nr_test",
                        "fn-ceos-lf-3",
                        "fn-ceos-lf-2",
                    ]
                ), f"{worker}:{host} output is wrong"

    @pytest.mark.nornir_fakenos
    def test_commands_template_with_nornir_worker_call(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cli",
            workers="nornir-worker-4",
            kwargs={
                "on_failed": True,
                "commands": "nf://cli/test_commands_template_with_nornir_worker_call.j2",
                "dry_run": True,
                "FL": ["fn-ceos-sp-1", "fn-ceos-sp-2"],
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

    @pytest.mark.nornir_fakenos
    def test_commands_with_tests(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cli",
            workers="nornir-worker-4",
            kwargs={
                "on_failed": True,
                "commands": ["show version", "show clock"],
                "tests": [
                    ["show version", "contains", "cEOS"],
                    ["show clock", "contains", "local"],
                ],
                "FL": ["fn-ceos-sp-1", "fn-ceos-sp-2"],
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
                        "show clock contains local..",
                        "show version",
                        "show version contains cEOS..",
                    ]
                )

    @pytest.mark.nornir_fakenos
    def test_commands_with_tf_processor(self, nfclient):
        tf = "test_commands_with_tf_processor"
        ret = nfclient.run_job(
            "nornir",
            "cli",
            workers=["nornir-worker-4"],
            kwargs={
                "on_failed": True,
                "commands": ["show version"],
                "FL": ["fn-ceos-sp-1"],
                "tf": tf,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is False, f"{worker} failed to run cli task"
            for host, res in results["result"].items():
                assert (
                    "show version" in res and "cEOS" in res["show version"]
                ), f"{worker}:{host} show version output is wrong"

        tf_path = (
            Path("nf_tests_inventory")
            / "__norfab__"
            / "files"
            / "worker"
            / "nornir-worker-4"
            / "tf"
        )
        index_file = tf_path / "tf_index_nornir-worker-4.json"
        assert index_file.exists(), "ToFileProcessor did not create index file"
        assert any(
            tf_path.glob(f"{tf}__*__fn-ceos-sp-1.txt")
        ), "ToFileProcessor did not save host output file"

    @pytest.mark.nornir_fakenos
    def test_commands_with_diff_processor(self, nfclient):
        diff = "test_commands_with_diff_processor"
        nfclient.run_job(
            "nornir",
            "cli",
            workers=["nornir-worker-4"],
            kwargs={
                "on_failed": True,
                "commands": ["show version"],
                "FL": ["fn-ceos-sp-1"],
                "tf": diff,
            },
        )

        ret = nfclient.run_job(
            "nornir",
            "cli",
            workers=["nornir-worker-4"],
            kwargs={
                "on_failed": True,
                "commands": ["show version"],
                "FL": ["fn-ceos-sp-1"],
                "diff": diff,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is False, f"{worker} failed to run cli task"
            for host, res in results["result"].items():
                assert (
                    res["show version"] is True
                ), f"{worker}:{host} diff output is wrong"

    @pytest.mark.nornir_fakenos
    def test_commands_with_diff_processor_diff_last(self, nfclient):
        diff = "test_commands_with_diff_processor_diff_last"
        for _ in range(2):
            nfclient.run_job(
                "nornir",
                "cli",
                workers=["nornir-worker-4"],
                kwargs={
                    "on_failed": True,
                    "commands": ["show version"],
                    "FL": ["fn-ceos-sp-1"],
                    "tf": diff,
                },
            )

        ret = nfclient.run_job(
            "nornir",
            "cli",
            workers=["nornir-worker-4"],
            kwargs={
                "on_failed": True,
                "commands": ["show version"],
                "FL": ["fn-ceos-sp-1"],
                "diff": diff,
                "diff_last": 2,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is False, f"{worker} failed to run cli task"
            for host, res in results["result"].items():
                assert (
                    res["show version"] is True
                ), f"{worker}:{host} diff_last output is wrong"

    @pytest.mark.nornir_fakenos
    def test_commands_template_with_job_data_dict(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cli",
            workers=["nornir-worker-4"],
            kwargs={
                "on_failed": True,
                "job_data": {"commands": ["show version", "show clock"]},
                "FL": ["fn-ceos-sp-1", "fn-ceos-sp-2"],
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

    @pytest.mark.nornir_fakenos
    def test_commands_template_with_job_data_file(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cli",
            workers=["nornir-worker-4"],
            kwargs={
                "on_failed": True,
                "job_data": "nf://cli/job_data_1.txt",
                "FL": ["fn-ceos-sp-1", "fn-ceos-sp-2"],
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

    @pytest.mark.nornir_fakenos
    def test_commands_template_with_job_data_wrong_file(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cli",
            workers=["nornir-worker-4"],
            kwargs={
                "on_failed": True,
                "job_data": "nf://cli/job_data_non_exist.txt",
                "FL": ["fn-ceos-sp-1", "fn-ceos-sp-2"],
                "dry_run": True,
                "commands": "nf://cli/template_with_job_data.txt",
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["errors"]
            assert "FileNotFoundError" in results["errors"][0]

    @pytest.mark.nornir_fakenos
    def test_commands_template_with_job_data_wrong_yaml(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cli",
            workers=["nornir-worker-4"],
            kwargs={
                "on_failed": True,
                "job_data": "nf://cli/job_data_wrong_yaml.txt",
                "FL": ["fn-ceos-sp-1", "fn-ceos-sp-2"],
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
