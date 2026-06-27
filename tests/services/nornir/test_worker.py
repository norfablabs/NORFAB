import pprint

import pytest

pytestmark = [pytest.mark.nornir, pytest.mark.worker, pytest.mark.task_nornir_worker]


@pytest.mark.task_nornir_worker
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
