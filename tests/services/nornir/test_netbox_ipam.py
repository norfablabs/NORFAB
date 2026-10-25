import pprint
from collections.abc import Iterator
from typing import Any

import pytest

try:
    from tests.services.netbox.common import delete_ips, get_pynetbox
except ModuleNotFoundError as exc:
    if exc.name not in {
        "tests",
        "tests.services",
        "tests.services.netbox",
        "tests.services.netbox.common",
    }:
        raise
    from services.netbox.common import delete_ips, get_pynetbox

pytestmark = pytest.mark.nornir


class TestNBCreateIp:
    @pytest.fixture
    def allocation_pool(self, nfclient: Any) -> Iterator[Any]:
        """Clean the class-owned pool before and after each allocation test."""
        prefix = "198.19.236.0/24"
        nb = get_pynetbox(nfclient)
        assert nb.ipam.prefixes.get(prefix=prefix) is not None, "seed prefix is missing"
        delete_ips(prefix, nfclient)
        try:
            yield nb
        finally:
            delete_ips(prefix, nfclient)

    def test_nb_create_ip_jinja2_template_with_filter(
        self, nfclient: Any, allocation_pool: Any
    ) -> None:
        ret = nfclient.run_job(
            "nornir",
            "cfg",
            workers=["nornir-worker-5"],
            kwargs={
                "on_failed": True,
                "config": "nf://cfg/config_netbox_get_next_ip_j2filter.txt",
                "FC": "fceos5",
                "dry_run": True,
            },
        )

        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is False, f"{worker} failed to run the task"
            assert (
                results["result"]["fceos5"]["dry_run"].count("198.19.236.") == 2
            ), "IPs not allocated"

        allocated = list(
            allocation_pool.ipam.ip_addresses.filter(parent="198.19.236.0/24")
        )
        assert len(allocated) == 2
        assert {
            (ip.assigned_object.device.name, ip.assigned_object.name)
            for ip in allocated
        } == {("fceos5", "eth101"), ("fceos5", "eth102")}

    def test_nb_create_ip_jinja2_template_with_set(
        self, nfclient: Any, allocation_pool: Any
    ) -> None:
        ret = nfclient.run_job(
            "nornir",
            "cfg",
            workers=["nornir-worker-5"],
            kwargs={
                "on_failed": True,
                "config": "nf://cfg/config_netbox_get_next_ip_j2set.txt",
                "FC": "fceos5",
                "dry_run": True,
            },
        )

        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is False, f"{worker} failed to run the task"
            assert (
                results["result"]["fceos5"]["dry_run"].count("198.19.236.") == 2
            ), "IPs not allocated"

        allocated = list(
            allocation_pool.ipam.ip_addresses.filter(parent="198.19.236.0/24")
        )
        assert len(allocated) == 2
        assert {
            (ip.assigned_object.device.name, ip.assigned_object.name)
            for ip in allocated
        } == {("fceos5", "eth101"), ("fceos5", "eth102")}


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
        delete_ips("10.1.0.0/30", nfclient)

        ret = nfclient.run_job(
            "nornir",
            "cfg",
            workers=["nornir-worker-1"],
            kwargs={
                "on_failed": True,
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
        delete_ips("10.1.0.0/30", nfclient)

        ret = nfclient.run_job(
            "nornir",
            "cfg",
            workers=["nornir-worker-1"],
            kwargs={
                "on_failed": True,
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


# ----------------------------------------------------------------------------
# SNMP TASK TESTS
# ----------------------------------------------------------------------------
