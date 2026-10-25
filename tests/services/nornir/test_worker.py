import pprint

import pytest

pytestmark = pytest.mark.nornir


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

    def test_errdisabled_hosts_list(self, nfclient):
        ret = nfclient.run_job("nornir", "errdisabled_hosts_list")

        for worker_name, data in ret.items():
            assert data["failed"] is False, worker_name
            assert isinstance(data["result"], list), worker_name

    def test_errdisabled_hosts_clear(self, nfclient):
        ret = nfclient.run_job("nornir", "errdisabled_hosts_clear")

        for worker_name, data in ret.items():
            assert data["failed"] is False, worker_name
            assert isinstance(data["result"], list), worker_name

    def test_get_stats(self, nfclient):
        """Return worker monitoring and retained job counters."""
        ret = nfclient.run_job("nornir", "get_stats", workers=["nornir-worker-1"])
        result = ret["nornir-worker-1"]
        assert not result["failed"], result
        stats = result["result"]
        assert stats["name"] == "nornir-worker-1"
        assert stats["service"] == "nornir"
        assert stats["nornir_hosts"] > 0
        assert stats["process"]["memory_rss_mbyte"] > 0
        assert stats["jobs"]["total_jobs"] >= 1

    def test_get_watchdog_configuration(self, nfclient):
        """Return watchdog timing and the default disabled idle timeout."""
        ret = nfclient.run_job(
            "nornir", "get_watchdog_configuration", workers=["nornir-worker-1"]
        )
        result = ret["nornir-worker-1"]
        assert not result["failed"], result
        for key in (
            "watchdog_interval",
            "failed_hosts_recovery_timeout",
        ):
            assert isinstance(result["result"][key], (int, float))
            assert result["result"][key] >= 0
        assert result["result"]["connections_idle_timeout"] is None

    def test_get_watchdog_connections(self, nfclient):
        """Return connection tracking records, including an empty mapping."""
        ret = nfclient.run_job(
            "nornir", "get_watchdog_connections", workers=["nornir-worker-1"]
        )
        result = ret["nornir-worker-1"]
        assert not result["failed"], result
        connections = result["result"]["connections"]
        assert isinstance(connections, dict)
        for plugins in connections.values():
            assert isinstance(plugins, dict)
            for stats in plugins.values():
                assert {"last_use", "last_keepalive", "keepalive_count"} <= stats.keys()
                assert stats["keepalive_count"] >= 0


# ----------------------------------------------------------------------------
# NORNIR.CLI FUNCTION TESTS
# ----------------------------------------------------------------------------
