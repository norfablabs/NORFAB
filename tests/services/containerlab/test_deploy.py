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
    pytest.mark.deploy,
    pytest.mark.task_containerlab_deploy,
]


@pytest.mark.task_containerlab_deploy
class TestDeployTask:
    def test_deploy(self, nfclient):
        wait_for_containerlab_worker(nfclient)

        # destroy the lab first
        ret_labs = nfclient.run_job("containerlab", "get_running_labs")
        print("Running labs:")
        pprint.pprint(ret_labs)
        for worker_name, res in ret_labs.items():
            if "three-routers-lab" in res["result"]:
                ret_destroy = nfclient.run_job(
                    "containerlab",
                    "destroy_lab",
                    kwargs={"lab_name": "three-routers-lab"},
                    workers=worker_name,
                )

                print("Lab destroyed:")
                pprint.pprint(ret_destroy)

                for w, r in ret_destroy.items():
                    assert r["failed"] == False, f"{w} - failed to destroy lab"
                    assert (
                        r["result"]["three-routers-lab"] == True
                    ), f"{w} - worker did not destroy three-routers-lab lab"

        ret_deploy = nfclient.run_job(
            "containerlab",
            "deploy",
            kwargs={"topology": "nf://containerlab/three-routers-topology.yaml"},
        )

        print("Lab deployed:")
        pprint.pprint(ret_deploy)

        for w, r in ret_deploy.items():
            assert r["failed"] == False, f"{w} - failed to deploy lab"
            assert r["result"][
                "three-routers-lab"
            ], f"{w} - worker did not deploy three-routers-lab"
            assert (
                len(r["result"]["three-routers-lab"]) == 3
            ), f"{w} - worker did not deploy all three-routers-lab containers"

    def test_deploy_reconfigure(self, nfclient):
        wait_for_containerlab_worker(nfclient)

        ret_deploy = nfclient.run_job(
            "containerlab",
            "deploy",
            kwargs={
                "topology": "nf://containerlab/three-routers-topology.yaml",
                "reconfigure": True,
            },
        )

        print("Lab deployed:")
        pprint.pprint(ret_deploy)

        for w, r in ret_deploy.items():
            assert r["failed"] == False, f"{w} - failed to deploy lab"
            assert r["result"][
                "three-routers-lab"
            ], f"{w} - worker did not deploy three-routers-lab"
            assert (
                len(r["result"]["three-routers-lab"]) == 3
            ), f"{w} - worker did not deploy all three-routers-lab containers"

    def test_deploy_node_filter(self, nfclient):
        wait_for_containerlab_worker(nfclient)

        # destroy the lab first
        ret_labs = nfclient.run_job("containerlab", "get_running_labs")
        print("Running labs:")
        pprint.pprint(ret_labs)
        for worker_name, res in ret_labs.items():
            if "three-routers-lab" in res["result"]:
                ret_destroy = nfclient.run_job(
                    "containerlab",
                    "destroy_lab",
                    kwargs={"lab_name": "three-routers-lab"},
                    workers=worker_name,
                )

                print("Lab destroyed:")
                pprint.pprint(ret_destroy)

                for w, r in ret_destroy.items():
                    assert r["failed"] == False, f"{w} - failed to destroy lab"
                    assert (
                        r["result"]["three-routers-lab"] == True
                    ), f"{w} - worker did not destroy three-routers-lab lab"

        ret_deploy = nfclient.run_job(
            "containerlab",
            "deploy",
            kwargs={
                "topology": "nf://containerlab/three-routers-topology.yaml",
                "node_filter": "r1,r2",
            },
        )

        print("Lab destroyed:")
        pprint.pprint(ret_destroy)

        print("Lab deployed:")
        pprint.pprint(ret_deploy)

        for w, r in ret_destroy.items():
            assert r["failed"] == False, f"{w} - failed to destroy lab"
            assert (
                r["result"]["three-routers-lab"] == True
            ), f"{w} - worker did not destroy three-routers-lab lab"

        for w, r in ret_deploy.items():
            assert r["failed"] == False, f"{w} - failed to deploy lab"
            assert r["result"][
                "three-routers-lab"
            ], f"{w} - worker did not deploy three-routers-lab"
            assert (
                len(r["result"]["three-routers-lab"]) == 2
            ), f"{w} - worker did not deplpoy 2 containers"
