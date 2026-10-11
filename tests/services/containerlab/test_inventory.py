import pprint

import pytest

from norfab.core.client import NFPClient

try:
    from tests.services.containerlab.common import (
        wait_for_containerlab_worker,
        wait_for_netbox_worker,
    )
except ModuleNotFoundError as exc:
    if exc.name not in {
        "tests",
        "tests.services",
        "tests.services.containerlab",
        "tests.services.containerlab.common",
    }:
        raise
    from services.containerlab.common import (
        wait_for_containerlab_worker,
        wait_for_netbox_worker,
    )

pytestmark = [
    pytest.mark.containerlab,
    pytest.mark.containerlab_get_nornir_inventory,
]


class TestGetNornirInventoryTask:
    def test_load_containerlab_inventory_with_netbox(self, nfclient: NFPClient) -> None:
        """Load one read-only device from a prod branch, preserving lab connectivity."""
        wait_for_containerlab_worker(nfclient)
        wait_for_netbox_worker(nfclient)
        lab = "norfab-netbox-inventory-load"
        branch = "norfab-clab-inventory-read"
        try:
            deployed = nfclient.run_job(
                "containerlab",
                "deploy",
                workers="containerlab-worker-1",
                kwargs={
                    "topology": "nf://containerlab/netbox-inventory-load.yaml",
                    "reconfigure": True,
                },
            )["containerlab-worker-1"]
            assert deployed["failed"] is False, deployed["errors"]

            original = nfclient.run_job(
                "containerlab",
                "get_nornir_inventory",
                workers="containerlab-worker-1",
                kwargs={"lab_name": lab},
            )["containerlab-worker-1"]
            assert original["failed"] is False, original["errors"]

            loaded = nfclient.run_job(
                "nornir",
                "nornir_inventory_load_containerlab",
                workers="nornir-worker-1",
                kwargs={
                    "lab_name": lab,
                    "clab_workers": "containerlab-worker-1",
                    "load_netbox_branch": branch,
                    "load_netbox_instance": "prod",
                    "dry_run": True,
                },
            )["nornir-worker-1"]
            assert loaded["failed"] is False, loaded["errors"]
            hosts = loaded["result"]["containerlab-worker-1"]["hosts"]
            assert list(hosts) == ["fceos4"]
            host = hosts["fceos4"]
            for key in (
                "hostname",
                "port",
                "platform",
                "username",
                "password",
                "groups",
            ):
                assert host[key] == original["result"]["hosts"]["fceos4"][key], key
            assert host["data"]["name"] == "fceos4"
            assert all(
                key in host["data"]
                for key in (
                    "interfaces",
                    "connections",
                    "circuits",
                    "bgp_peerings",
                    "config_context",
                )
            )
            assert any(
                interface["ip_addresses"]
                for interface in host["data"]["interfaces"].values()
            )
        finally:
            nfclient.run_job(
                "containerlab",
                "destroy_lab",
                workers="containerlab-worker-1",
                kwargs={"lab_name": lab},
            )
            nfclient.run_job(
                "netbox",
                "delete_branch",
                workers="any",
                kwargs={"branch": branch, "instance": "prod"},
            )

    def test_get_nornir_inventory_by_lab_name(self, nfclient):
        wait_for_containerlab_worker(nfclient)
        ret_deploy = nfclient.run_job(
            "containerlab",
            "deploy",
            kwargs={
                "topology": "nf://containerlab/three-routers-topology.yaml",
                "reconfigure": True,
            },
        )
        ret_inventory = nfclient.run_job(
            "containerlab",
            "get_nornir_inventory",
            kwargs={"lab_name": "three-routers-lab", "groups": ["g1", "g2"]},
        )

        print("Lab deployed:")
        pprint.pprint(ret_deploy)

        print("Lab Nornir Inventory generated:")
        pprint.pprint(ret_inventory)

        for w, r in ret_deploy.items():
            assert r["failed"] == False, f"{w} - failed to re-deploy lab"
            assert r["result"][
                "three-routers-lab"
            ], f"{w} - worker did not re-deploy all three-routers-lab containers"

        for w, r in ret_inventory.items():
            assert r["failed"] == False, f"{w} - failed to get lab Nornir inventory"
            assert all(
                k in r["result"]["hosts"] for k in ["r1", "r2", "r3"]
            ), f"{w} - failed to get inventory for all devices"
            for h, i in r["result"]["hosts"].items():
                assert all(
                    k in i
                    for k in [
                        "groups",
                        "hostname",
                        "password",
                        "platform",
                        "port",
                        "username",
                    ]
                ), f"{w}:{h} - inventory incomplete"
                assert i["groups"] == ["g1", "g2"], f"{w}:{h} - groups content wrong"

    def test_get_nornir_inventory_all_labs(self, nfclient):
        wait_for_containerlab_worker(nfclient)
        ret_deploy = nfclient.run_job(
            "containerlab",
            "deploy",
            kwargs={
                "topology": "nf://containerlab/three-routers-topology.yaml",
                "reconfigure": True,
            },
        )
        ret_inventory = nfclient.run_job(
            "containerlab", "get_nornir_inventory", kwargs={"groups": ["g1", "g2"]}
        )

        print("Lab deployed:")
        pprint.pprint(ret_deploy)

        print("Lab Nornir Inventory generated:")
        pprint.pprint(ret_inventory)

        for w, r in ret_deploy.items():
            assert r["failed"] == False, f"{w} - failed to re-deploy lab"
            assert r["result"][
                "three-routers-lab"
            ], f"{w} - worker did not re-deploy all three-routers-lab containers"

        for w, r in ret_inventory.items():
            assert r["failed"] == False, f"{w} - failed to get lab Nornir inventory"
            assert all(
                k in r["result"]["hosts"] for k in ["r1", "r2", "r3"]
            ), f"{w} - failed to get inventory for all devices"
            for h, i in r["result"]["hosts"].items():
                assert all(
                    k in i
                    for k in [
                        "groups",
                        "hostname",
                        "password",
                        "platform",
                        "port",
                        "username",
                    ]
                ), f"{w}:{h} - inventory incomplete"
                assert i["groups"] == ["g1", "g2"], f"{w}:{h} - groups content wrong"

    def test_get_nornir_inventory_nonexisting_lab_name(self, nfclient):
        wait_for_containerlab_worker(nfclient)
        ret_inventory = nfclient.run_job(
            "containerlab", "get_nornir_inventory", kwargs={"lab_name": "notexist"}
        )

        print("Lab Nornir Inventory generated:")
        pprint.pprint(ret_inventory)

        for w, r in ret_inventory.items():
            assert (
                r["failed"] == True
            ), f"{w} - inventory retrieval for non existing lab should fail"
            assert r["result"] == {
                "hosts": {}
            }, f"{w} - inventory should contain no hosts"
