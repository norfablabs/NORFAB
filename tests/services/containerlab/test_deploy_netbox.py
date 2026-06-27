import pprint
import pytest

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
    pytest.mark.netbox,
    pytest.mark.task_containerlab_deploy_netbox,
]


@pytest.mark.task_containerlab_deploy_netbox
class TestDeployNetboxTask:
    def test_deploy_netbox(self, nfclient):
        wait_for_containerlab_worker(nfclient)
        wait_for_netbox_worker(nfclient)

        # destroy the lab first
        ret_labs = nfclient.run_job("containerlab", "get_running_labs")
        print("Running labs:")
        pprint.pprint(ret_labs)
        for worker_name, res in ret_labs.items():
            if "foobar" in res["result"]:
                ret_destroy = nfclient.run_job(
                    "containerlab",
                    "destroy_lab",
                    kwargs={"lab_name": "foobar"},
                    workers=worker_name,
                )

                print("Lab destroyed:")
                pprint.pprint(ret_destroy)

                for w, r in ret_destroy.items():
                    assert r["failed"] == False, f"{w} - failed to destroy lab"
                    assert (
                        r["result"]["foobar"] == True
                    ), f"{w} - worker did not destroy foobar lab"

        ret_deploy = nfclient.run_job(
            "containerlab",
            "deploy_netbox",
            kwargs={"lab_name": "foobar", "devices": ["fceos4", "fceos5"]},
        )

        print("Lab deployed from Netbox:")
        pprint.pprint(ret_deploy)

        for w, r in ret_deploy.items():
            assert r["failed"] == False, f"{w} - failed to deploy lab"
            assert (
                len(r["result"]["foobar"]) == 2
            ), f"{w} - worker did not deploy foobar containers"

    def test_deploy_netbox_reconfigure(self, nfclient):
        wait_for_containerlab_worker(nfclient)
        wait_for_netbox_worker(nfclient)
        ret_deploy = nfclient.run_job(
            "containerlab",
            "deploy_netbox",
            kwargs={
                "lab_name": "foobar",
                "devices": ["fceos4", "fceos5"],
                "reconfigure": True,
            },
        )

        print("Lab deployed from Netbox:")
        pprint.pprint(ret_deploy)

        for w, r in ret_deploy.items():
            assert r["failed"] == False, f"{w} - failed to deploy lab"
            assert (
                len(r["result"]["foobar"]) == 2
            ), f"{w} - worker did not deploy foobar containers"

    def test_deploy_netbox_node_filter(self, nfclient):
        wait_for_containerlab_worker(nfclient)
        wait_for_netbox_worker(nfclient)

        # destroy the lab first
        ret_labs = nfclient.run_job("containerlab", "get_running_labs")
        print("Running labs:")
        pprint.pprint(ret_labs)
        for worker_name, res in ret_labs.items():
            if "foobar" in res["result"]:
                ret_destroy = nfclient.run_job(
                    "containerlab",
                    "destroy_lab",
                    kwargs={"lab_name": "foobar"},
                    workers=worker_name,
                )

                print("Lab destroyed:")
                pprint.pprint(ret_destroy)

                for w, r in ret_destroy.items():
                    assert r["failed"] == False, f"{w} - failed to destroy lab"
                    assert (
                        r["result"]["foobar"] == True
                    ), f"{w} - worker did not destroy foobar lab"

        ret_deploy = nfclient.run_job(
            "containerlab",
            "deploy_netbox",
            kwargs={
                "lab_name": "foobar",
                "devices": ["fceos4", "fceos5"],
                "node_filter": "fceos4",
            },
        )

        print("Lab deployed from Netbox:")
        pprint.pprint(ret_deploy)

    def test_deploy_netbox_with_nb_filters(self, nfclient):
        wait_for_containerlab_worker(nfclient)
        wait_for_netbox_worker(nfclient)

        # destroy the lab first
        ret_labs = nfclient.run_job("containerlab", "get_running_labs")
        print("Running labs:")
        pprint.pprint(ret_labs)
        for worker_name, res in ret_labs.items():
            if "foobar" in res["result"]:
                ret_destroy = nfclient.run_job(
                    "containerlab",
                    "destroy_lab",
                    kwargs={"lab_name": "foobar"},
                    workers=worker_name,
                )

                print("Lab destroyed:")
                pprint.pprint(ret_destroy)

                for w, r in ret_destroy.items():
                    assert r["failed"] == False, f"{w} - failed to destroy lab"
                    assert (
                        r["result"]["foobar"] == True
                    ), f"{w} - worker did not destroy foobar lab"

        ret_deploy = nfclient.run_job(
            "containerlab",
            "deploy_netbox",
            kwargs={
                "lab_name": "foobar",
                "filters": [
                    {
                        "tenant__name": "NORFAB",
                        "name__ic": "spine",
                    }
                ],
            },
        )

        print("Lab deployed from Netbox:")
        pprint.pprint(ret_deploy)

        for w, r in ret_deploy.items():
            assert r["failed"] == False, f"{w} - failed to deploy lab"
            assert (
                len(r["result"]["foobar"]) == 2
            ), f"{w} - worker did not deploy correct number of foobar lab containers"
