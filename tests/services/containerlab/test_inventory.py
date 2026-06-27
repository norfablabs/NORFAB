import pprint
import pytest

try:
    from tests.services.containerlab.common import (
        wait_for_containerlab_worker,
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
    )

pytestmark = [
    pytest.mark.containerlab,
    pytest.mark.inventory,
    pytest.mark.task_containerlab_get_nornir_inventory,
]


@pytest.mark.task_containerlab_get_nornir_inventory
class TestGetNornirInventoryTask:
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
