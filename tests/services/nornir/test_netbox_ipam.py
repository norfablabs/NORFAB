import pprint
import pytest

try:
    from tests.services.netbox.common import delete_ips
except ModuleNotFoundError as exc:
    if exc.name not in {
        "tests",
        "tests.services",
        "tests.services.netbox",
        "tests.services.netbox.common",
    }:
        raise
    from services.netbox.common import delete_ips

pytestmark = [
    pytest.mark.nornir,
    pytest.mark.netbox_ipam,
    pytest.mark.task_nornir_netbox_ipam,
]


@pytest.mark.task_nornir_netbox_ipam
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
        delete_ips("10.1.0.0/30", nfclient)

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
        delete_ips("10.1.0.0/30", nfclient)

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


# ----------------------------------------------------------------------------
# SNMP TASK TESTS
# ----------------------------------------------------------------------------
