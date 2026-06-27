import pprint
import pytest

pytestmark = [pytest.mark.nornir, pytest.mark.jinja2, pytest.mark.task_nornir_jinja2]


@pytest.mark.task_nornir_jinja2
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
