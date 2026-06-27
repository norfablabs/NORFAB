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
    pytest.mark.save,
    pytest.mark.task_containerlab_save,
]


@pytest.mark.task_containerlab_save
class TestSaveTask:
    def test_save(self, nfclient):
        wait_for_containerlab_worker(nfclient)

        ret_deploy = nfclient.run_job(
            "containerlab",
            "deploy",
            kwargs={
                "topology": "nf://containerlab/three-routers-topology.yaml",
                "reconfigure": True,
            },
        )

        ret = nfclient.run_job(
            "containerlab", "save", kwargs={"lab_name": "three-routers-lab"}
        )

        print("Ret deploy:")
        pprint.pprint(ret_deploy)

        print("Ret save:")
        pprint.pprint(ret)

        for w, r in ret.items():
            assert r["failed"] == False, f"{w} - failed to save lab"
            assert (
                r["result"]["three-routers-lab"] == True
            ), f"{w} - failed to save lab three-routers-lab"

    def test_save_nonexistlab(self, nfclient):
        wait_for_containerlab_worker(nfclient)
        ret = nfclient.run_job("containerlab", "save", kwargs={"lab_name": "nonexist"})
        pprint.pprint(ret)

        for w, r in ret.items():
            assert r["failed"] == True, f"{w} - should have failed to save lab"
