import pprint
import random
import pytest

pytestmark = [pytest.mark.nornir, pytest.mark.cfg, pytest.mark.task_nornir_cfg]


@pytest.mark.task_nornir_cfg
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
        ), "nornir-worker-1 produced more then 1 host result"
        assert (
            len(ret["nornir-worker-2"]["result"]) == 1
        ), "nornir-worker-2 produced more then 1 host result"

        assert (
            "ceos-spine-1" in ret["nornir-worker-1"]["result"]
        ), "nornir-worker-1 no output for ceos-spine-1"
        assert (
            "ceos-leaf-1" in ret["nornir-worker-2"]["result"]
        ), "nornir-worker-2 no output for ceos-leaf-1"

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

        assert len(ret) == 1, "CFG produced more then 1 worker result"
        assert "nornir-worker-1" in ret, "No output for nornir-worker-1"

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
                "ValidationError" in results["errors"][0]
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
