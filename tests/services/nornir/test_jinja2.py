import pprint

import pytest

pytestmark = pytest.mark.nornir


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

    def test_nb_filter_config_template(self, nfclient):
        """Render interface configuration using data read from NetBox."""
        ret = nfclient.run_job(
            "nornir",
            "cfg",
            workers=["nornir-worker-1"],
            kwargs={
                "config": "nf://cfg/config_netbox_filter_interface.txt",
                "FL": ["ceos-spine-1"],
                "dry_run": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no results"
            assert results["failed"] is False, f"{worker} failed to render config"
            rendered = results["result"]["ceos-spine-1"]["dry_run"]
            assert "interface Loopback0" in rendered
            assert "description RID" in rendered

    def test_nb_filter_test_suite_template(self, nfclient):
        """Render one test per device interface read from NetBox."""
        ret = nfclient.run_job(
            "nornir",
            "test",
            workers=["nornir-worker-1"],
            kwargs={
                "suite": "nf://nornir_test_suites/test_suite_netbox_filter_interfaces.txt",
                "FL": ["ceos-spine-1"],
                "dry_run": True,
            },
        )
        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["result"], f"{worker} returned no results"
            assert results["failed"] is False, f"{worker} failed to render suite"
            rendered_tests = results["result"]["ceos-spine-1"]["tests_dry_run"]
            tests_by_name = {test["name"]: test for test in rendered_tests}
            assert len(rendered_tests) == 2
            for interface_name in ("Ethernet2", "Loopback0"):
                test_name = f"Check {interface_name} status"
                assert test_name in tests_by_name
