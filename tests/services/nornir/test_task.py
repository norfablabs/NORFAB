import pprint
import pytest

pytestmark = [pytest.mark.nornir, pytest.mark.task, pytest.mark.task_nornir_task]


@pytest.mark.task_nornir_task
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
                    "dummy_subtask": "dummy subtask done",
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
