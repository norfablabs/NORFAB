import pprint

import pytest

pytestmark = [pytest.mark.nornir, pytest.mark.network, pytest.mark.task_nornir_network]


@pytest.mark.task_nornir_network
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
