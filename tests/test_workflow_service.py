import pprint
import pytest
import random
import requests
import json


class TestWorkflowWorker:
    def test_get_inventory(self, nfclient):
        ret = nfclient.run_job("workflow", "get_inventory")
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            assert all(
                k in data["result"] for k in ["service"]
            ), f"{worker_name} inventory incomplete"

    def test_get_version(self, nfclient):
        ret = nfclient.run_job("workflow", "get_version")
        pprint.pprint(ret)

        assert isinstance(ret, dict), f"Expected dictionary but received {type(ret)}"
        for worker_name, version_report in ret.items():
            for package, version in version_report["result"].items():
                assert version != "", f"{worker_name}:{package} version is empty"


class TestWorkflowRunTask:
    def test_workflow_1(self, nfclient):
        ret = nfclient.run_job(
            "workflow",
            "run",
            kwargs={
                "workflow": "nf://workflow/test_workflow_1.yaml",
            },
        )
        pprint.pprint(ret)

        assert (
            ret["workflow-worker-1"]["result"]["test_workflow_1"]["step1"][
                "nornir-worker-1"
            ]["failed"]
            is False
        ), "test_workflow_1 step1 nornir-worker-1 failed"
        assert ret["workflow-worker-1"]["result"]["test_workflow_1"]["step1"][
            "nornir-worker-1"
        ]["result"]["ceos-spine-1"][
            "show version"
        ], f"test_workflow_1 step1 nornir-worker-1 ceos-spine-1 show version has no output"
        assert ret["workflow-worker-1"]["result"]["test_workflow_1"]["step1"][
            "nornir-worker-1"
        ]["result"]["ceos-spine-2"][
            "show version"
        ], f"test_workflow_1 step1 nornir-worker-1 ceos-spine-2 show version has no output"
        assert ret["workflow-worker-1"]["result"]["test_workflow_1"]["step1"][
            "nornir-worker-1"
        ]["result"]["ceos-spine-1"][
            "show ip int brief"
        ], f"test_workflow_1 step1 nornir-worker-1 ceos-spine-1 show ip int brief has no output"
        assert ret["workflow-worker-1"]["result"]["test_workflow_1"]["step1"][
            "nornir-worker-1"
        ]["result"]["ceos-spine-2"][
            "show ip int brief"
        ], f"test_workflow_1 step1 nornir-worker-1 ceos-spine-2 show ip int brief has no output"

        assert (
            ret["workflow-worker-1"]["result"]["test_workflow_1"]["step2"][
                "nornir-worker-2"
            ]["failed"]
            is False
        ), "test_workflow_1 step2 nornir-worker-2 failed"
        assert ret["workflow-worker-1"]["result"]["test_workflow_1"]["step2"][
            "nornir-worker-2"
        ]["result"]["ceos-leaf-1"][
            "show hostname"
        ], f"test_workflow_1 step2 nornir-worker-2 ceos-leaf-1 show hostname has no output"
        assert ret["workflow-worker-1"]["result"]["test_workflow_1"]["step2"][
            "nornir-worker-2"
        ]["result"]["ceos-leaf-2"][
            "show hostname"
        ], f"test_workflow_1 step2 nornir-worker-2 ceos-leaf-2 show hostname has no output"
        assert ret["workflow-worker-1"]["result"]["test_workflow_1"]["step2"][
            "nornir-worker-2"
        ]["result"]["ceos-leaf-3"][
            "show hostname"
        ], f"test_workflow_1 step2 nornir-worker-2 ceos-leaf-3 show hostname has no output"
        assert ret["workflow-worker-1"]["result"]["test_workflow_1"]["step2"][
            "nornir-worker-2"
        ]["result"]["ceos-leaf-1"][
            "show ntp status"
        ], f"test_workflow_1 step2 nornir-worker-2 ceos-leaf-1 show ntp status has no output"
        assert ret["workflow-worker-1"]["result"]["test_workflow_1"]["step2"][
            "nornir-worker-2"
        ]["result"]["ceos-leaf-2"][
            "show ntp status"
        ], f"test_workflow_1 step2 nornir-worker-2 ceos-leaf-2 show ntp status has no output"
        assert ret["workflow-worker-1"]["result"]["test_workflow_1"]["step2"][
            "nornir-worker-2"
        ]["result"]["ceos-leaf-3"][
            "show ntp status"
        ], f"test_workflow_1 step2 nornir-worker-2 ceos-leaf-3 show ntp status has no output"

    def test_workflow_run_if_fail_any(self, nfclient):
        ret = nfclient.run_job(
            "workflow",
            "run",
            kwargs={
                "workflow": "nf://workflow/test_workflow_run_if_fail_any.yaml",
            },
        )
        pprint.pprint(ret)

        assert (
            ret["workflow-worker-1"]["result"]["test_workflow_run_if_fail_any"][
                "step3"
            ]["nornir-worker-2"]["status"]
            == "completed"
        ), f"test_workflow_run_if_fail_any step3 should be completed"
        assert (
            ret["workflow-worker-1"]["result"]["test_workflow_run_if_fail_any"][
                "step4"
            ]["all-workers"]["status"]
            == "skipped"
        ), f"test_workflow_run_if_fail_any step4 should be skipped"

    def test_workflow_run_if_pass_any(self, nfclient):
        ret = nfclient.run_job(
            "workflow",
            "run",
            kwargs={
                "workflow": "nf://workflow/test_workflow_run_if_pass_any.yaml",
            },
        )
        pprint.pprint(ret)

        assert (
            ret["workflow-worker-1"]["result"]["test_workflow_run_if_pass_any"][
                "step3-should-run"
            ]["nornir-worker-2"]["status"]
            == "completed"
        ), f"test_workflow_run_if_pass_any step3-should-run should be completed"
        assert (
            ret["workflow-worker-1"]["result"]["test_workflow_run_if_pass_any"][
                "step4-should-not-run"
            ]["all-workers"]["status"]
            == "skipped"
        ), f"test_workflow_run_if_pass_any step4-should-not-run should be skipped"

    def test_workflow_run_if_fail_all(self, nfclient):
        ret = nfclient.run_job(
            "workflow",
            "run",
            kwargs={
                "workflow": "nf://workflow/test_workflow_run_if_fail_all.yaml",
            },
        )
        pprint.pprint(ret)

        assert (
            ret["workflow-worker-1"]["result"]["test_workflow_run_if_fail_all"][
                "step4-should-run"
            ]["nornir-worker-2"]["status"]
            == "completed"
        ), f"test_workflow_run_if_fail_all step4-should-run should be completed"
        assert (
            ret["workflow-worker-1"]["result"]["test_workflow_run_if_fail_all"][
                "step5-should-not-run"
            ]["all-workers"]["status"]
            == "skipped"
        ), f"test_workflow_run_if_pass_any step5-should-not-run should be skipped"

    def test_workflow_run_if_pass_all(self, nfclient):
        ret = nfclient.run_job(
            "workflow",
            "run",
            kwargs={
                "workflow": "nf://workflow/test_workflow_run_if_pass_all.yaml",
            },
        )
        pprint.pprint(ret)

        assert (
            ret["workflow-worker-1"]["result"]["test_workflow_run_if_pass_all"][
                "step4-should-run"
            ]["nornir-worker-2"]["status"]
            == "completed"
        ), f"test_workflow_run_if_pass_all step4-should-run should be completed"
        assert (
            ret["workflow-worker-1"]["result"]["test_workflow_run_if_pass_all"][
                "step5-should-not-run"
            ]["all-workers"]["status"]
            == "skipped"
        ), f"test_workflow_run_if_pass_any step5-should-not-run should be skipped"

    def test_workflow_stop_on_failure_test(self, nfclient):
        ret = nfclient.run_job(
            "workflow",
            "run",
            kwargs={
                "workflow": "nf://workflow/test_workflow_stop_on_failure_test.yaml",
            },
        )
        pprint.pprint(ret)

        assert (
            ret["workflow-worker-1"]["result"]["test_workflow_stop_on_failure_test"][
                "step1"
            ]["nornir-worker-1"]["status"]
            == "completed"
        ), f"test_workflow_stop_on_failure_test step1 should be completed"
        assert (
            ret["workflow-worker-1"]["result"]["test_workflow_stop_on_failure_test"][
                "step2_failed"
            ]["nornir-worker-2"]["failed"]
            == True
        ), f"test_workflow_stop_on_failure_test step2_failed should be failed"
        assert (
            "step3-should-not-run"
            not in ret["workflow-worker-1"]["result"][
                "test_workflow_stop_on_failure_test"
            ]
        ), "step3 should be not in results"

    def test_workflow_run_if_error(self, nfclient):
        ret = nfclient.run_job(
            "workflow",
            "run",
            kwargs={
                "workflow": "nf://workflow/test_workflow_run_if_error.yaml",
            },
        )
        pprint.pprint(ret)

        assert (
            ret["workflow-worker-1"]["result"]["test_workflow_run_if_error"][
                "step1_failed"
            ]["nornir-worker-1"]["status"]
            == "completed"
        ), f"test_workflow_run_if_error step1 should be completed"
        assert (
            ret["workflow-worker-1"]["result"]["test_workflow_run_if_error"]["step2"][
                "all-workers"
            ]["status"]
            == "error"
        ), f"test_workflow_run_if_error step2 status should be error"
        assert (
            "step3"
            not in ret["workflow-worker-1"]["result"]["test_workflow_run_if_error"]
        ), "step3 should be not in results"
