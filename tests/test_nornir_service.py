import pprint
import pytest
import random

# ----------------------------------------------------------------------------
# NORNIR WORKER TESTS
# ----------------------------------------------------------------------------


class TestNornirWorker:
    def test_get_nornir_inventory(self, nfclient):
        ret = nfclient.run_job("nornir", "get_inventory")
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            assert all(
                k in data["result"] for k in ["hosts", "groups", "defaults"]
            ), f"{worker_name} inventory incomplete"

    def test_get_nornir_hosts(self, nfclient):
        ret = nfclient.run_job("nornir", "get_nornir_hosts")
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            assert isinstance(
                data["result"], list
            ), "{worker_name} did not return a list of hosts"
            assert len(data) > 0 or data == []

    def test_get_nornir_hosts_check_validation(self, nfclient):
        ret = nfclient.run_job("nornir", "get_nornir_hosts", kwargs={"FZ": "spine"})
        pprint.pprint(ret)

        for worker_name, results in ret.items():
            assert results["failed"] == True, f"{worker_name} did not fail"
            assert (
                "ValidationError" in results["errors"][0]
            ), f"{worker_name} did not raise ValidationError"

    def test_get_nornir_version(self, nfclient):
        ret = nfclient.run_job("nornir", "get_version")
        pprint.pprint(ret)

        assert isinstance(ret, dict), f"Expected dictionary but received {type(ret)}"
        for worker_name, version_report in ret.items():
            for package, version in version_report["result"].items():
                assert version != "", f"{worker_name}:{package} version is empty"

    @pytest.mark.skip(reason="TBD")
    def test_get_watchdog_stats(self, nfclient):
        pass

    @pytest.mark.skip(reason="TBD")
    def test_get_watchdog_configuration(self, nfclient):
        pass

    @pytest.mark.skip(reason="TBD")
    def test_get_watchdog_connections(self, nfclient):
        pass


# ----------------------------------------------------------------------------
# NORNIR.CLI FUNCTION TESTS
# ----------------------------------------------------------------------------


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


class TestNornirTask:
    def test_task_nornir_salt_nr_test(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "task",
            workers=["nornir-worker-1"],
            kwargs={"plugin": "nornir_salt.plugins.tasks.nr_test", "foo": "bar"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert res == {"nr_test": {"foo": "bar"}}

    def test_task_nornir_salt_nr_test_add_details(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "task",
            workers=["nornir-worker-1"],
            kwargs={
                "plugin": "nornir_salt.plugins.tasks.nr_test",
                "foo": "bar",
                "add_details": True,
            },
        )
        pprint.pprint(ret)
        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert res == {
                    "nr_test": {
                        "changed": False,
                        "connection_retry": 0,
                        "diff": "",
                        "exception": None,
                        "failed": False,
                        "result": {"foo": "bar"},
                        "task_retry": 0,
                    }
                }

    def test_task_from_file(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "task",
            workers=["nornir-worker-1"],
            kwargs={"plugin": "nf://nornir_tasks/dummy.py"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert res == {"dummy": True}

    def test_task_from_nonexisting_file(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "task",
            workers=["nornir-worker-1"],
            kwargs={"plugin": "nf://nornir_tasks/_non_existing_.py"},
        )
        pprint.pprint(ret, width=150)

        for worker, results in ret.items():
            assert results["failed"] == True
            assert (
                "nornir-worker-1 - 'nf://nornir_tasks/_non_existing_.py' task plugin download failed"
                in results["errors"][0]
            )
            assert (
                "nornir-worker-1 - 'nf://nornir_tasks/_non_existing_.py' task plugin download failed"
                in results["messages"][0]
            )

    def test_task_from_nonexisting_module(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "task",
            workers=["nornir-worker-1"],
            kwargs={
                "plugin": "nornir_salt.plugins.tasks.non_existing_module",
                "foo": "bar",
            },
        )
        pprint.pprint(ret, width=200)

        for worker, results in ret.items():
            assert results["failed"] == True
            assert (
                "module 'nornir_salt.plugins.tasks' has no attribute 'non_existing_module'"
                in results["errors"][0]
            )
            assert (
                "module 'nornir_salt.plugins.tasks' has no attribute 'non_existing_module'"
                in results["messages"][0]
            )

    def test_task_with_error(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "task",
            workers=["nornir-worker-1"],
            kwargs={"plugin": "nf://nornir_tasks/dummy_with_error.py"},
        )
        pprint.pprint(ret, width=150)

        for worker_name, worker_results in ret.items():
            for hostname, host_results in worker_results["result"].items():
                assert (
                    "Traceback" in host_results["dummy"]
                    and "RuntimeError: dummy error" in host_results["dummy"]
                )

    def test_task_with_subtasks(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "task",
            workers=["nornir-worker-1"],
            kwargs={"plugin": "nf://nornir_tasks/dummy_with_subtasks.py"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert res == {
                    "dummy": "dummy task done",
                    "dummy_subtask": "dummy substask done",
                }

    def test_task_netmiko_send_command(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "task",
            workers=["nornir-worker-1"],
            kwargs={
                "plugin": "nornir_netmiko.tasks.netmiko_send_command",
                "FC": "spine",
                "command_string": "show clock",
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] == False, f"{worker} task failed"
            for host, res in results["result"].items():
                assert (
                    "Timezone" in res["netmiko_send_command"]
                ), f"{worker}:{host} unexpected output"

    def test_task_netmiko_send_command_full_path(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "task",
            workers=["nornir-worker-1"],
            kwargs={
                "plugin": "nornir_netmiko.tasks.netmiko_send_command.netmiko_send_command",
                "FC": "spine",
                "command_string": "show clock",
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] == False, f"{worker} task failed"
            for host, res in results["result"].items():
                assert (
                    "Timezone" in res["netmiko_send_command"]
                ), f"{worker}:{host} unexpected output"


# ----------------------------------------------------------------------------
# NORNIR.CFG FUNCTION TESTS
# ----------------------------------------------------------------------------


class TestNornirCfg:
    def test_config_list(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cfg",
            workers=["nornir-worker-1", "nornir-worker-2"],
            kwargs={"config": ["interface loopback 0", "description RID"]},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert (
                    "netmiko_send_config" in res
                ), f"{worker}:{host} no netmiko_send_config output"
                assert (
                    "Traceback" not in res["netmiko_send_config"]
                ), f"{worker}:{host} cfg output is wrong"

    def test_config_dry_run(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cfg",
            workers=["nornir-worker-1", "nornir-worker-2"],
            kwargs={
                "config": ["interface loopback 0", "description RID"],
                "dry_run": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert "dry_run" in res, f"{worker}:{host} no cfg dry run output"
                assert (
                    res["dry_run"] == "interface loopback 0\ndescription RID"
                ), f"{worker}:{host} cfg dry run output is wrong"

    def test_config_with_hosts_filters(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cfg",
            workers=["nornir-worker-1", "nornir-worker-2"],
            kwargs={
                "config": ["interface loopback 0", "description RID"],
                "FL": ["ceos-leaf-1", "ceos-spine-1"],
                "dry_run": True,
            },
        )
        pprint.pprint(ret)

        assert (
            len(ret["nornir-worker-1"]["result"]) == 1
        ), f"nornir-worker-1 produced more then 1 host result"
        assert (
            len(ret["nornir-worker-2"]["result"]) == 1
        ), f"nornir-worker-2 produced more then 1 host result"

        assert (
            "ceos-spine-1" in ret["nornir-worker-1"]["result"]
        ), f"nornir-worker-1 no output for ceos-spine-1"
        assert (
            "ceos-leaf-1" in ret["nornir-worker-2"]["result"]
        ), f"nornir-worker-2 no output for ceos-leaf-1"

    def test_config_with_worker_target(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cfg",
            workers=["nornir-worker-1"],
            kwargs={
                "config": ["interface loopback 0", "description RID"],
                "dry_run": True,
            },
        )
        pprint.pprint(ret)

        assert len(ret) == 1, f"CFG produced more then 1 worker result"
        assert "nornir-worker-1" in ret, f"No output for nornir-worker-1"

    def test_config_add_details(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cfg",
            workers=["nornir-worker-1", "nornir-worker-2"],
            kwargs={
                "config": ["interface loopback 0", "description RID"],
                "add_details": True,
                "dry_run": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert "dry_run" in res, f"{worker}:{host} no dry_run output"
                assert isinstance(
                    res["dry_run"], dict
                ), f"{worker}:{host} no detailed output produced"
                assert all(
                    k in res["dry_run"]
                    for k in [
                        "changed",
                        "connection_retry",
                        "diff",
                        "exception",
                        "failed",
                        "result",
                        "task_retry",
                    ]
                ), f"{worker}:{host} detailed output incomplete"

    def test_config_to_dict_false(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cfg",
            workers=["nornir-worker-1", "nornir-worker-2"],
            kwargs={
                "config": ["interface loopback 0", "description RID"],
                "to_dict": False,
                "dry_run": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert isinstance(
                results["result"], list
            ), f"{worker} did not return list result"
            for host_res in results["result"]:
                assert (
                    len(host_res) == 3
                ), f"{worker} was expecting 3 items in host result dic, but got more"
                assert all(
                    k in host_res for k in ["name", "result", "host"]
                ), f"{worker} host output incomplete"

    def test_config_to_dict_false_add_details(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cfg",
            workers=["nornir-worker-1", "nornir-worker-2"],
            kwargs={
                "config": ["interface loopback 0", "description RID"],
                "to_dict": False,
                "dry_run": True,
                "add_details": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert isinstance(
                results["result"], list
            ), f"{worker} did not return list result"
            for host_res in results["result"]:
                assert (
                    len(host_res) > 3
                ), f"{worker} was expecting more then 3 items in host result dic, but got less"
                assert all(
                    k in host_res
                    for k in [
                        "changed",
                        "connection_retry",
                        "diff",
                        "exception",
                        "failed",
                        "result",
                        "task_retry",
                        "name",
                        "host",
                    ]
                ), f"{worker} host output incomplete"

    def test_config_wrong_plugin(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cfg",
            workers=["nornir-worker-1", "nornir-worker-2"],
            kwargs={
                "config": ["interface loopback 0", "description RID"],
                "dry_run": True,
                "plugin": "wrong_plugin",
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert (
                "UnsupportedPluginError" in results["errors"][0]
            ), f"{worker} did not raise error"

    def test_config_from_file_dry_run(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cfg",
            workers=["nornir-worker-1", "nornir-worker-2"],
            kwargs={
                "config": "nf://cfg/config_1.txt",
                "dry_run": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert "dry_run" in res, f"{worker}:{host} no cfg dry run output"
                assert (
                    res["dry_run"] == "interface Loopback0\ndescription RID"
                ), f"{worker}:{host} cfg dry run output is wrong"

    def test_config_from_nonexisting_file(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cfg",
            workers=["nornir-worker-1", "nornir-worker-2"],
            kwargs={
                "config": "nf://cfg/config_non_existing.txt",
                "dry_run": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert "FileNotFoundError" in results["errors"][0]

    def test_config_from_file_template(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cfg",
            workers=["nornir-worker-1", "nornir-worker-2"],
            kwargs={
                "config": "nf://cfg/config_2.txt",
                "dry_run": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host_name, res in results["result"].items():
                assert "dry_run" in res, f"{worker}:{host_name} no cfg dry run output"
                assert (
                    "interface Loopback0\ndescription RID for " in res["dry_run"]
                ), f"{worker}:{host_name} cfg dry run output is wrong"
                assert (
                    host_name in res["dry_run"]
                ), f"{worker}:{host_name} cfg dry run output is not rendered"

    def test_config_plugin_napalm(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cfg",
            workers=["nornir-worker-1"],
            kwargs={
                "config": [
                    "interface loopback 123",
                    f"description RID {random.randint(0, 1000)}",
                ],
                "plugin": "napalm",
                "add_details": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert (
                    "napalm_configure" in res
                ), f"{worker}:{host} no napalm_configure output"
                assert (
                    res["napalm_configure"]["result"] is None
                ), f"{worker}:{host} cfg output is wrong"
                assert (
                    res["napalm_configure"]["diff"] is not None
                ), f"{worker}:{host} cfg output no diff"

    def test_config_plugin_scrapli(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cfg",
            workers=["nornir-worker-1"],
            kwargs={
                "config": ["interface loopback 0", "description RID"],
                "plugin": "scrapli",
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert (
                    "scrapli_send_config" in res
                ), f"{worker}:{host} no scrapli_send_config output"
                assert (
                    "Traceback" not in res["scrapli_send_config"]
                ), f"{worker}:{host} cfg output is wrong"

    def test_config_plugin_netmiko(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cfg",
            workers=["nornir-worker-1"],
            kwargs={
                "config": ["interface loopback 0", "description RID"],
                "plugin": "netmiko",
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            for host, res in results["result"].items():
                assert (
                    "netmiko_send_config" in res
                ), f"{worker}:{host} no netmiko_send_config output"
                assert (
                    "Traceback" not in res["netmiko_send_config"]
                ), f"{worker}:{host} cfg output is wrong"

    def test_config_from_file_template_with_include(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cfg",
            workers=["nornir-worker-1", "nornir-worker-2"],
            kwargs={
                "config": "nf://cfg/config_with_includes.txt",
                "dry_run": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] == False, f"{worker} results failed"
            for host, res in results["result"].items():
                assert "dry_run" in res, f"{worker}:{host} no dry_run output"
                assert (
                    "interface Loopback1" in res["dry_run"]
                ), f"{worker}:{host} no config_with_includes.txt config"
                assert (
                    "interface Loopback0" in res["dry_run"]
                ), f"{worker}:{host} no config_with_includes_2.txt config"
                assert (
                    "ntp server 1.1.1.1" in res["dry_run"]
                ), f"{worker}:{host} no config_with_includes_2.txt config"

    def test_config_from_file_template_with_include_non_exist(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cfg",
            workers=["nornir-worker-1", "nornir-worker-2"],
            kwargs={
                "config": "nf://cfg/config_with_includes_non_exist.txt",
                "dry_run": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] == True, f"{worker} results not failed"
            assert "FileNotFoundError" in results["errors"][0]

    def test_config_from_file_template_with_if_and_include(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cfg",
            workers=["nornir-worker-1", "nornir-worker-2"],
            kwargs={
                "config": "nf://cfg/config_with_if_and_includes.txt",
                "dry_run": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] == False, f"{worker} results failed"
            for host, res in results["result"].items():
                assert "dry_run" in res, f"{worker}:{host} no dry_run output"
                assert (
                    "interface Loopback1" in res["dry_run"]
                ), f"{worker}:{host} no config_with_includes.txt config"

    def test_config_from_file_template_with_job_data_dict(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cfg",
            workers=["nornir-worker-1", "nornir-worker-2"],
            kwargs={
                "config": "nf://cfg/config_with_job_data.txt",
                "dry_run": True,
                "job_data": {
                    "commands": ["interface loopback 555", "description foobar"]
                },
            },
        )
        pprint.pprint(ret)
        for worker, results in ret.items():
            assert results["failed"] == False, f"{worker} results failed"
            for host, res in results["result"].items():
                assert (
                    "interface loopback 555" in res["dry_run"]
                    and "description foobar" in res["dry_run"]
                ), f"{worker}:{host} config is wrong"

    def test_config_from_file_template_with_job_data_file(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cfg",
            workers=["nornir-worker-1", "nornir-worker-2"],
            kwargs={
                "config": "nf://cfg/config_with_job_data.txt",
                "dry_run": True,
                "job_data": "nf://cfg/config_job_data_1.txt",
            },
        )
        pprint.pprint(ret)
        for worker, results in ret.items():
            assert results["failed"] == False, f"{worker} results failed"
            for host, res in results["result"].items():
                assert (
                    "interface loopback 555" in res["dry_run"]
                    and "description foobar" in res["dry_run"]
                ), f"{worker}:{host} config is wrong"

    def test_config_from_file_template_with_job_data_wrong_file(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cfg",
            workers=["nornir-worker-1", "nornir-worker-2"],
            kwargs={
                "config": "nf://cfg/config_with_job_data.txt",
                "dry_run": True,
                "job_data": "nf://cfg/config_job_data_non_exist.txt",
            },
        )
        pprint.pprint(ret)
        for worker, results in ret.items():
            assert results["errors"]
            assert "FileNotFoundError" in results["errors"][0]


# ----------------------------------------------------------------------------
# NORNIR.TEST FUNCTION TESTS
# ----------------------------------------------------------------------------


class TestNornirTest:
    def test_nornir_test_suite(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={"suite": "nf://nornir_test_suites/suite_1.txt"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results[
                "failed"
            ], f"{worker} some tests failed, result should be failed as well"
            assert results["result"], f"{worker} returned no test results"
            for host, res in results["result"].items():
                for test_name, test_res in res.items():
                    assert (
                        "Traceback" not in test_res
                    ), f"{worker}:{host}:{test_name} test output contains error"
                    assert test_res in [
                        "PASS",
                        "FAIL",
                    ], f"{worker}:{host}:{test_name} unexpected test result"

    def test_nornir_test_suite_empty_suite(self, nfclient):
        # this test renders empty test for any host except for spine 1
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={
                "suite": "nf://nornir_test_suites/suite_empty_tests.txt",
                "FC": "spine",
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no test results"
            for host, res in results["result"].items():
                for test_name, test_res in res.items():
                    assert (
                        "Traceback" not in test_res
                    ), f"{worker}:{host}:{test_name} test output contains error"
                    assert test_res in [
                        "PASS",
                        "FAIL",
                    ], f"{worker}:{host}:{test_name} unexpected test result"

    def test_nornir_test_suite_with_details(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={
                "suite": "nf://nornir_test_suites/suite_1.txt",
                "add_details": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results[
                "failed"
            ], f"{worker} some tests failed, result should be failed as well"
            assert results["result"], f"{worker} returned no test results"
            for host, res in results["result"].items():
                for test_name, test_res in res.items():
                    assert isinstance(test_res, dict)
                    assert test_res["result"] in [
                        "PASS",
                        "FAIL",
                    ], f"{worker}:{host}:{test_name} unexpected test result"

    def test_nornir_test_suite_list_result(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={"suite": "nf://nornir_test_suites/suite_1.txt", "to_dict": False},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results[
                "failed"
            ], f"{worker} some tests failed, result should be failed as well"
            assert results["result"], f"{worker} returned no test results"
            assert isinstance(
                results["result"], list
            ), f"{worker} did not return list result"
            for host_res in results["result"]:
                assert isinstance(host_res, dict)
                assert host_res["result"] in [
                    "PASS",
                    "FAIL",
                ], f"{worker} unexpected test result - {host_res}"

    def test_nornir_test_suite_list_result_with_details(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={
                "suite": "nf://nornir_test_suites/suite_1.txt",
                "to_dict": False,
                "add_details": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results[
                "failed"
            ], f"{worker} some tests failed, result should be failed as well"
            assert results["result"], f"{worker} returned no test results"
            assert isinstance(
                results["result"], list
            ), f"{worker} did not return list result"
            for host_res in results["result"]:
                assert isinstance(host_res, dict)
                assert host_res["result"] in [
                    "PASS",
                    "FAIL",
                ], f"{worker} unexpected test result - {host_res}"
                assert "exception" in host_res
                assert "diff" in host_res, f"{worker} details added"

    def test_nornir_test_suite_template(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={"suite": "nf://nornir_test_suites/suite_2.txt"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert (
                results["failed"] is False
            ), f"{worker} no tests failed, result should not be failed as well"
            assert results["result"], f"{worker} returned no test results"
            for host, res in results["result"].items():
                for test_name, test_res in res.items():
                    assert (
                        "Traceback" not in test_res
                    ), f"{worker}:{host}:{test_name} test output contains error"
                    assert test_res in [
                        "PASS",
                        "FAIL",
                    ], f"{worker}:{host}:{test_name} unexpected test result"

    def test_nornir_test_suite_subset(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={
                "suite": "nf://nornir_test_suites/suite_1.txt",
                "subset": "check*version",
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no test results"
            for host, res in results["result"].items():
                assert (
                    len(res) == 1
                ), f"{worker}:{host} was expecting results for single test only"
                assert (
                    "check ceos version" in res
                ), f"{worker}:{host} was expecting 'check ceos version' results"

    def test_nornir_test_dry_run(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={
                "suite": "nf://nornir_test_suites/suite_1.txt",
                "dry_run": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no test results"
            for host, res in results["result"].items():
                assert (
                    "tests_dry_run" in res
                ), f"{worker}:{host} no tests_dry_run results"
                assert isinstance(
                    res["tests_dry_run"], list
                ), f"{worker}:{host} was expecting list of tests"
                for i in res["tests_dry_run"]:
                    assert all(
                        k in i for k in ["name", "pattern", "task", "test"]
                    ), f"{worker}:{host} test missing some keys"

    def test_nornir_test_to_dict_true(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={
                "suite": "nf://nornir_test_suites/suite_1.txt",
                "to_dict": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no test results"
            for host, res in results["result"].items():
                for test_name, test_res in res.items():
                    assert (
                        "Traceback" not in test_res
                    ), f"{worker}:{host}:{test_name} test output contains error"
                    assert test_res in [
                        "PASS",
                        "FAIL",
                    ], f"{worker}:{host}:{test_name} unexpected test result"

    def test_nornir_test_to_dict_false(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={
                "suite": "nf://nornir_test_suites/suite_1.txt",
                "to_dict": False,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no test results"
            assert isinstance(results["result"], list)
            for i in results["result"]:
                assert all(
                    k in i for k in ["host", "name", "result"]
                ), f"{worker} test output does not contains all keys"

    def test_nornir_test_remove_tasks_false(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={
                "suite": "nf://nornir_test_suites/suite_1.txt",
                "remove_tasks": False,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no test results"
            for host, res in results["result"].items():
                assert len(res) > 2, f"{worker}:{host} not having tasks output"
                for task_name, task_res in res.items():
                    assert (
                        "Traceback" not in task_res
                    ), f"{worker}:{host}:{test_name} test output contains error"

    def test_nornir_test_failed_only_true(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={
                "suite": "nf://nornir_test_suites/suite_1.txt",
                "failed_only": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no test results"
            for host, res in results["result"].items():
                for test_name, test_res in res.items():
                    assert (
                        "Traceback" not in test_res
                    ), f"{worker}:{host}:{test_name} test output contains error"
                    assert test_res in [
                        "FAIL"
                    ], f"{worker}:{host}:{test_name} unexpected test result"

    def test_nornir_test_suite_non_existing_file(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={"suite": "nf://nornir_test_suites/suite_non_existing.txt"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert (
                "FileNotFoundError" in results["errors"][0]
            ), f"{worker} was expecting download to fail"

    def test_nornir_test_suite_bad_yaml_file(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={"suite": "nf://nornir_test_suites/suite_bad_yaml.txt"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert (
                "YAML load failed" in results["errors"][0]
            ), f"{worker} was expecting YAML load to fail"

    def test_nornir_test_suite_bad_jinja2(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={"suite": "nf://nornir_test_suites/suite_bad_jinja2.txt"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert (
                "Jinja2 template parsing failed" in results["errors"][0]
            ), f"{worker} was expecting Jinja2 rendering to fail"

    def test_nornir_test_suite_custom_functions_files(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={
                "suite": "nf://nornir_test_suites/test_suite_custom_fun.txt",
                "FC": "ceos-spine-",
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no test results"
            for host, res in results["result"].items():
                for test_name in [
                    "test_cust_fun_1",
                    "test_cust_fun_2 show clock NTP",
                    "test_cust_fun_2 show ip int brief NTP",
                    "test_cust_fun_3 Test IP config",
                    "test_cust_fun_3 Test NTP",
                ]:
                    assert (
                        test_name in res
                    ), f"{worker}:{host} missing '{test_name}' results"
                for test_name, test_res in res.items():
                    assert (
                        "Traceback" not in test_res
                    ), f"{worker}:{host}:{test_name} test output contains error"
                    assert test_res in [
                        "FAIL"
                    ], f"{worker}:{host}:{test_name} unexpected test result"

    def test_nornir_test_with_nftask_to_dict_false(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={
                "suite": "nf://nornir_test_suites/test_nornir_test_with_nftask.txt",
                "FC": "ceos-spine-",
                "add_details": True,
                "to_dict": False,
            },
        )
        pprint.pprint(ret)
        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no test results"
            for i in results["result"]:
                assert (
                    i["result"] == "PASS"
                ), f"{worker}:{i['host']}:{i['name']} unexpected test result"

    def test_nornir_test_with_nftask_to_dict_true(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={
                "suite": "nf://nornir_test_suites/test_nornir_test_with_nftask.txt",
                "FC": "ceos-spine-",
                "add_details": True,
                "to_dict": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no test results"
            for host, res in results["result"].items():
                for test_name, test_res in res.items():
                    assert not test_res[
                        "exception"
                    ], f"{worker}:{host}:{test_name} test output contains error"
                    assert (
                        test_res["result"] == "PASS"
                    ), f"{worker}:{host}:{test_name} unexpected test result"

    def test_nornir_test_suite_with_includes_dry_run(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={
                "suite": "nf://nornir_test_suites/test_suite_with_include.txt",
                "FC": "ceos-spine-",
                "dry_run": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no test results"
            for host, res in results["result"].items():
                assert (
                    len(res["tests_dry_run"]) == 3
                ), f"{worker}:{host} not all tests rendered"
                assert res["tests_dry_run"][0]["name"] == "check hostname value"
                assert res["tests_dry_run"][1]["name"] == "check version"
                assert res["tests_dry_run"][2]["name"] == "check loopback0 present"

    def test_nornir_test_suite_with_includes(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={
                "suite": "nf://nornir_test_suites/test_suite_with_include.txt",
                "FC": "ceos-spine-",
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no test results"
            for host, res in results["result"].items():
                for test_name, test_res in res.items():
                    assert test_name in [
                        "check hostname value",
                        "check loopback0 present",
                        "check version",
                    ], f"{worker}:{host}:{test_name} unexpected test result"

    def test_nornir_test_suite_with_job_data_dict(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={
                "suite": "nf://nornir_test_suites/test_nornir_test_suite_with_job_data.txt",
                "FC": "ceos-spine-",
                "job_data": {"some_conditional": True},
                "dry_run": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no test results"
            for host, res in results["result"].items():
                assert (
                    len(res["tests_dry_run"]) == 1
                ), f"{worker}:{host} was expecting only one test item"
                assert (
                    res["tests_dry_run"][0]["name"] == "check ceos version"
                ), f"{worker}:{host} unexpected tes name"

    @pytest.mark.skip(reason="TBD")
    def test_nornir_test_suite_pattern_files(self, nfclient):
        pass

    def test_nornir_test_markdown_brief(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            kwargs={
                "suite": "nf://nornir_test_suites/suite_1.txt",
                "FC": ["spine", "leaf"],
            },
            markdown=True,
        )
        print(ret)
        assert "No hosts test suites available" in ret
        assert "No hosts outputs available" in ret
        assert "No detailed results available" in ret
        assert "No hosts inventory available" in ret
        assert "|Host|Test Name|Result|Exception|" in ret
        assert "Input Arguments (kwargs)" in ret
        assert "Complete Results (JSON)" in ret

    def test_nornir_test_with_extensive(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            kwargs={
                "suite": "nf://nornir_test_suites/suite_1.txt",
                "FC": ["spine", "leaf"],
                "extensive": True,
            },
        )
        pprint.pprint(ret)
        for worker, results in ret.items():
            assert (
                "hosts_inventory" in results["result"]
            ), f"{worker} returned no hosts inventory"
            assert (
                "test_results" in results["result"]
            ), f"{worker} returned no test results"
            assert "suite" in results["result"], f"{worker} returned no tests suite"
            if "worker" in ["nornir-worker-2", "nornir-worker-1"]:
                assert results["result"]["hosts_inventory"]

    def test_nornir_test_markdown_with_extensive(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "test",
            kwargs={
                "suite": "nf://nornir_test_suites/suite_1.txt",
                "FC": ["spine", "leaf"],
                "extensive": True,
            },
            markdown=True,
        )
        print(ret)
        assert "|Host|Test Name|Result|Exception|" in ret
        assert "Input Arguments (kwargs)" in ret
        assert "Complete Results (JSON)" in ret
        assert "Devices Inventory" in ret
        assert "Test suites definitions for each host" in ret
        assert (
            "Expandable sections containing outputs collected during test execution for each host"
            in ret
        )
        assert (
            "Hierarchical expandable sections organized by device, then test name, containing complete test result details"
            in ret
        )


# ----------------------------------------------------------------------------
# NORNIR.NETWORK FUNCTION TESTS
# ----------------------------------------------------------------------------


class TestNornirNetwork:
    def test_nornir_network_ping(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "network",
            workers=["nornir-worker-1"],
            kwargs={"fun": "ping", "FC": "ceos"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no test results"
            for host, res in results["result"].items():
                assert "ping" in res, f"{worker}:{host} did not return ping result"
                assert (
                    "Reply from" in res["ping"]
                ), f"{worker}:{host} ping result is not good"

    def test_nornir_network_ping_with_count(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "network",
            workers=["nornir-worker-1"],
            kwargs={"fun": "ping", "FC": "ceos", "count": 2},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no test results"
            for host, res in results["result"].items():
                assert "ping" in res, f"{worker}:{host} did not return ping result"
                assert (
                    "Reply from" in res["ping"]
                ), f"{worker}:{host} ping result is not good"
                assert (
                    res["ping"].count("Reply from") == 2
                ), f"{worker}:{host} ping result did not get 2 replies"

    @pytest.mark.skip(reason="TBD")
    def test_nornir_network_resolve_dns(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "network",
            workers=["nornir-worker-1"],
            kwargs={"fun": "resolve_dns", "FC": "ceos"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no test results"
            for host, res in results["result"].items():
                assert "ping" in res, f"{worker}:{host} did not return ping result"
                assert (
                    "Reply from" in res["ping"]
                ), f"{worker}:{host} ping result is not good"


# ----------------------------------------------------------------------------
# NORNIR.PARSE FUNCTION TESTS
# ----------------------------------------------------------------------------


class TestNornirParse:
    def test_nornir_parse_wrong_plugin_name(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "parse",
            workers=["nornir-worker-1"],
            kwargs={"plugin": "nonexisting", "method": "get_facts"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"] is None, f"{worker} returned results"
            assert results["failed"] is True, f"{worker} did not fail to run the task"

    def test_nornir_parse_napalm_get_facts(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "parse",
            workers=["nornir-worker-1"],
            kwargs={"plugin": "napalm", "getters": "get_facts"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no results"
            assert results["failed"] is False, f"{worker} failed to run the task"
            for host, res in results["result"].items():
                assert (
                    "napalm_get" in res
                ), f"{worker}:{host} did not return napalm_get result"
                assert res["napalm_get"][
                    "get_facts"
                ], f"{worker}:{host} get facts are empty"

    def test_nornir_parse_napalm_unsupported_getter(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "parse",
            workers=["nornir-worker-1"],
            kwargs={"plugin": "napalm", "getters": "get_ntp_peers"},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no results"
            assert (
                results["failed"] is True
            ), f"{worker} should have failed to run the task"
            for host, res in results["result"].items():
                assert "NotImplementedError" in res["napalm_get"]

    def test_nornir_parse_napalm_multiple_getters(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "parse",
            workers=["nornir-worker-1"],
            kwargs={"plugin": "napalm", "getters": ["get_facts", "get_interfaces"]},
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no results"
            assert results["failed"] is False, f"{worker} failed to run the task"
            for host, res in results["result"].items():
                assert (
                    "napalm_get" in res
                ), f"{worker}:{host} did not return napalm_get result"
                assert res["napalm_get"][
                    "get_interfaces"
                ], f"{worker}:{host} get_interfaces are empty"
                assert res["napalm_get"][
                    "get_facts"
                ], f"{worker}:{host} get_facts are empty"

    def test_nornir_parse_ttp_templates_template_with_commands(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "parse",
            workers=["nornir-worker-1"],
            kwargs={
                "plugin": "ttp",
                "template": "ttp://platform/arista_eos_show_hostname.txt",
                "commands": "show hostname",
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no results"
            assert results["failed"] is False, f"{worker} failed to run the task"
            for host, res in results["result"].items():
                assert (
                    "run_ttp" in res
                ), f"{worker}:{host} did not return TTP parsing result"
                assert res["run_ttp"][
                    0
                ], f"{worker}:{host} TTP parsing results are empty"

    def test_nornir_parse_ttp_templates_template(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "parse",
            workers=["nornir-worker-1"],
            kwargs={
                "plugin": "ttp",
                "template": "ttp://misc/Netbox/parse_arista_eos_config.txt",
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no results"
            assert results["failed"] is False, f"{worker} failed to run the task"
            for host, res in results["result"].items():
                assert (
                    "run_ttp" in res
                ), f"{worker}:{host} did not return TTP parsing result"
                assert res["run_ttp"][
                    0
                ], f"{worker}:{host} TTP parsing results are empty"

    def test_nornir_parse_ttp_file_template(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "parse",
            workers=["nornir-worker-1"],
            kwargs={
                "plugin": "ttp",
                "template": "nf://ttp/parse_eos_intf.txt",
                "enable": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no results"
            assert results["failed"] is False, f"{worker} failed to run the task"
            for host, res in results["result"].items():
                assert (
                    "run_ttp" in res
                ), f"{worker}:{host} did not return TTP parsing result"
                assert res["run_ttp"][
                    0
                ], f"{worker}:{host} TTP parsing results are empty"

    def test_nornir_parse_inline_ttp_template(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "parse",
            workers=["nornir-worker-1"],
            kwargs={
                "plugin": "ttp",
                "template": "Clock source: {{ source }}",
                "commands": "show clock",
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no results"
            assert results["failed"] is False, f"{worker} failed to run the task"
            for host, res in results["result"].items():
                assert (
                    "run_ttp" in res
                ), f"{worker}:{host} did not return TTP parsing result"
                assert res["run_ttp"][
                    0
                ], f"{worker}:{host} TTP parsing results are empty"
                assert (
                    "source" in res["run_ttp"][0]
                ), f"{worker}:{host} TTP parsing results are wrong"

    @pytest.mark.skip(reason="TBD")
    def test_nornir_parse_textfsm_file_template(self, nfclient):
        pass

    @pytest.mark.skip(reason="TBD")
    def test_nornir_parse_textfsm_template(self, nfclient):
        pass


# ----------------------------------------------------------------------------
# NORNIR JINJA2 FILTERS
# ----------------------------------------------------------------------------


class TestNornirJinja2Filters:
    def test_network_hosts(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cli",
            workers=["nornir-worker-1"],
            kwargs={
                "commands": "nf://cli/test_network_hosts.txt",
                "dry_run": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no results"
            assert results["failed"] is False, f"{worker} failed to run the task"
            for host, res in results["result"].items():
                assert "192.168.1.1" in res["dry_run"]
                assert "192.168.1.2" in res["dry_run"]

    def test_network_hosts_with_prefixlen(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "cli",
            workers=["nornir-worker-1"],
            kwargs={
                "commands": "nf://cli/test_network_hosts_with_prefixlen.txt",
                "dry_run": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no results"
            assert results["failed"] is False, f"{worker} failed to run the task"
            for host, res in results["result"].items():
                assert "192.168.1.1/30" in res["dry_run"]
                assert "192.168.1.2/30" in res["dry_run"]


# ----------------------------------------------------------------------------
# NORNIR FILE COPY TESTS
# ----------------------------------------------------------------------------


class TestNornirFileCopy:
    def test_file_copy_dry_run(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "file_copy",
            workers=["nornir-worker-1"],
            kwargs={
                "source_file": "nf://nornir/files/file_copy_test.txt",
                "dry_run": True,
                "FC": "spine",
                "enable": True,
            },
        )

        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no results"
            assert results["failed"] is False, f"{worker} failed to run the task"
            for host, res in results["result"].items():
                assert "spine" in host
                assert "socket_timeout" in res["file_copy_dry_run"]
                assert "source_file" in res["file_copy_dry_run"]
                assert "dest_file" in res["file_copy_dry_run"]

    def test_file_copy(self, nfclient):
        # delete file first
        file_delete = nfclient.run_job(
            "nornir",
            "cli",
            workers=["nornir-worker-1"],
            kwargs={
                "commands": "delete file_copy_test.txt",
                "FC": "spine",
                "enable": True,
            },
        )
        print("File delete result:")
        pprint.pprint(file_delete)

        # copy file
        file_copy = nfclient.run_job(
            "nornir",
            "file_copy",
            workers=["nornir-worker-1"],
            kwargs={
                "source_file": "nf://nornir/files/file_copy_test.txt",
                "FC": "spine",
                "FM": "arista_eos",
            },
        )
        print("File copy result:")
        pprint.pprint(file_copy)

        # verify file copied
        file_dir = nfclient.run_job(
            "nornir",
            "cli",
            workers=["nornir-worker-1"],
            kwargs={"commands": "dir", "FC": "spine", "enable": True},
        )
        print("File dir result:")
        pprint.pprint(file_dir)

        for worker, results in file_delete.items():
            assert results["result"], f"{worker} returned no results"
            assert results["failed"] is False, f"{worker} failed to run the task"

        for worker, results in file_copy.items():
            assert results["result"], f"{worker} returned no results"
            assert results["failed"] is False, f"{worker} failed to run the task"
            for host, res in results["result"].items():
                assert "spine" in host
                assert res["netmiko_file_transfer"] == True

        for worker, results in file_dir.items():
            assert results["result"], f"{worker} returned no results"
            assert results["failed"] is False, f"{worker} failed to run the task"
            for host, res in results["result"].items():
                assert "file_copy_test.txt" in res["dir"], f"{host} - file not copied"

    def test_file_copy_non_existing_file(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "file_copy",
            workers=["nornir-worker-1"],
            kwargs={
                "source_file": "nf://nornir/files/file_not_exist.txt",
                "FC": "spine",
                "FM": "arista_eos",
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"] is None, f"{worker} returned results"
            assert results["failed"] is True, f"{worker} did not fail to run the task"
            assert "fetch file failed" in results["errors"][0]


# ----------------------------------------------------------------------------
# NORNIR RUNTIME INVENTORY TESTS
# ----------------------------------------------------------------------------


class TestNornirRunTimeInventory:
    def test_runtime_inventory_create_host(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "runtime_inventory",
            workers=["nornir-worker-1"],
            kwargs={"action": "create_host", "name": "foobar"},
        )

        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is False, f"{worker} failed to run the task"
            assert results["result"]["foobar"] == True

    def test_runtime_inventory_delete_host(self, nfclient):
        ret_create = nfclient.run_job(
            "nornir",
            "runtime_inventory",
            workers=["nornir-worker-1"],
            kwargs={"action": "create_host", "name": "foobar"},
        )

        ret = nfclient.run_job(
            "nornir",
            "runtime_inventory",
            workers=["nornir-worker-1"],
            kwargs={"action": "delete_host", "name": "foobar"},
        )

        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is False, f"{worker} failed to run the task"
            assert results["result"]["foobar"] == True

    def test_load_containerlab_inventory(self, nfclient):
        # deploy containerlab topology
        ret_deploy = nfclient.run_job(
            "containerlab",
            "deploy",
            workers=["containerlab-worker-1"],
            kwargs={
                "topology": "nf://containerlab/three-routers-topology.yaml",
                "reconfigure": True,
            },
        )
        print("Lab deployed:")
        pprint.pprint(ret_deploy)

        # load inventory
        ret_load = nfclient.run_job(
            "nornir",
            "nornir_inventory_load_containerlab",
            workers=["nornir-worker-1"],
            kwargs={
                "clab_workers": "containerlab-worker-1",
                "lab_name": "three-routers-lab",
            },
        )
        print("Nornir loaded containerlab nodes:")
        pprint.pprint(ret_load)

        # show hosts inventory
        ret_hosts = nfclient.run_job(
            "nornir",
            "get_nornir_hosts",
            workers=["nornir-worker-1"],
        )
        print("Nornir hosts:")
        pprint.pprint(ret_hosts)

        # run command
        ret_run_command = nfclient.run_job(
            "nornir",
            "cli",
            workers=["nornir-worker-1"],
            kwargs={
                "commands": "show version",
                "FL": ["r1", "r2", "r3"],
            },
        )
        print("Nornir run cli command:")
        pprint.pprint(ret_run_command)

        # Refresh nornir
        ret_refresh = nfclient.run_job(
            "nornir",
            "refresh_nornir",
            workers=["nornir-worker-1"],
        )
        print("Nornir refreshed:")
        pprint.pprint(ret_refresh)

        # show hosts inventory
        ret_hosts_after_refresh = nfclient.run_job(
            "nornir",
            "get_nornir_hosts",
            workers=["nornir-worker-1"],
        )
        print("Nornir hosts after refresh:")
        pprint.pprint(ret_hosts_after_refresh)

        assert all(
            h in ret_hosts["nornir-worker-1"]["result"]
            for h in ["ceos-spine-1", "ceos-spine-2", "r1", "r2", "r3"]
        ), f"nornir-worker-1 did not load three-routers-lab devices"
        assert all(
            h in ret_run_command["nornir-worker-1"]["result"]
            for h in ["r1", "r2", "r3"]
        ), f"nornir-worker-1 did not return command output"
        assert all(
            h not in ret_hosts_after_refresh["nornir-worker-1"]["result"]
            for h in ["r1", "r2", "r3"]
        ), f"nornir-worker-1 inventory not refreshed"


# ----------------------------------------------------------------------------
# NORNIR NETBOX CREATE IP TESTS
# ----------------------------------------------------------------------------


class TestNBCreateIp:
    def delete_ips(self, prefix, nfclient):
        resp = nfclient.run_job(
            "netbox",
            "rest",
            workers="any",
            kwargs={
                "method": "get",
                "api": "/ipam/ip-addresses/",
                "params": {"parent": prefix},
            },
        )
        worker, ips = tuple(resp.items())[0]
        # pprint.pprint(ips)
        for ip in ips["result"]["results"]:
            delete_ip = nfclient.run_job(
                "netbox",
                "rest",
                workers="any",
                kwargs={
                    "method": "delete",
                    "api": f"/ipam/ip-addresses/{ip['id']}/",
                },
            )
            # print("delete ip address:")
            # pprint.pprint(delete_ip)

    def test_nb_create_ip_jinja2_template_with_filter(self, nfclient):
        self.delete_ips("10.0.0.0/24", nfclient)

        ret = nfclient.run_job(
            "nornir",
            "cfg",
            workers=["nornir-worker-5"],
            kwargs={
                "config": "nf://cfg/config_netbox_get_next_ip_j2filter.txt",
                "FC": "fceos5",
                "dry_run": True,
            },
        )

        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is False, f"{worker} failed to run the task"
            assert (
                results["result"]["fceos5"]["dry_run"].count("10.0.0.") > 10
            ), "IPs not allocated"

    def test_nb_create_ip_jinja2_template_with_set(self, nfclient):
        self.delete_ips("10.0.0.0/24", nfclient)

        ret = nfclient.run_job(
            "nornir",
            "cfg",
            workers=["nornir-worker-5"],
            kwargs={
                "config": "nf://cfg/config_netbox_get_next_ip_j2set.txt",
                "FC": "fceos5",
                "dry_run": True,
            },
        )

        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is False, f"{worker} failed to run the task"
            assert (
                results["result"]["fceos5"]["dry_run"].count("10.0.0.") > 10
            ), "IPs not allocated"


# ----------------------------------------------------------------------------
# NORNIR NETBOX CREATE PREFIX TESTS
# ----------------------------------------------------------------------------


class TestNBCreatePrefix:
    def delete_prefixes_within(self, prefix, nfclient):
        resp = nfclient.run_job(
            "netbox",
            "rest",
            workers="any",
            kwargs={
                "method": "get",
                "api": "/ipam/prefixes/",
                "params": {"within": prefix},
            },
        )
        worker, prefixes = tuple(resp.items())[0]
        # pprint.pprint(prefixes)
        for pfx in prefixes["result"]["results"]:
            delete_pfx = nfclient.run_job(
                "netbox",
                "rest",
                workers="any",
                kwargs={
                    "method": "delete",
                    "api": f"/ipam/prefixes/{pfx['id']}/",
                },
            )
            # print("delete prefix:")
            # pprint.pprint(delete_pfx)

    def test_nb_create_prefix_jinja2_template_with_filter(self, nfclient):
        self.delete_prefixes_within("10.1.0.0/24", nfclient)

        ret = nfclient.run_job(
            "nornir",
            "cfg",
            workers=["nornir-worker-1"],
            kwargs={
                "config": "nf://cfg/config_netbox_get_next_prefix_j2filter.txt",
                "FC": "spine",
                "dry_run": True,
            },
        )

        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is False, f"{worker} failed to run the task"
            assert (
                "10.1.0.1/30" in results["result"]["ceos-spine-1"]["dry_run"]
            ), "Correct prefix and ip not allocated"
            assert (
                "10.1.0.2/30" in results["result"]["ceos-spine-2"]["dry_run"]
            ), "Correct prefix and ip not allocated"

    def test_nb_create_prefix_jinja2_template_with_set(self, nfclient):
        self.delete_prefixes_within("10.1.0.0/24", nfclient)

        ret = nfclient.run_job(
            "nornir",
            "cfg",
            workers=["nornir-worker-1"],
            kwargs={
                "config": "nf://cfg/config_netbox_get_next_prefix_j2set.txt",
                "FC": "spine",
                "dry_run": True,
            },
        )

        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is False, f"{worker} failed to run the task"
            assert (
                "10.1.0.1/30" in results["result"]["ceos-spine-1"]["dry_run"]
            ), "Correct prefix and ip not allocated"
            assert (
                "10.1.0.2/30" in results["result"]["ceos-spine-2"]["dry_run"]
            ), "Correct prefix and ip not allocated"
