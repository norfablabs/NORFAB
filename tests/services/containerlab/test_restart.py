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
    pytest.mark.restart,
    pytest.mark.task_containerlab_restart,
]


@pytest.mark.task_containerlab_restart
class TestRestartTask:
    def test_restart(self, nfclient):
        wait_for_containerlab_worker(nfclient)
        ret = nfclient.run_job(
            "containerlab", "restart_lab", kwargs={"lab_name": "three-routers-lab"}
        )
        pprint.pprint(ret)

        for w, r in ret.items():
            assert r["failed"] == False, f"{w} - failed to restart lab"
            assert (
                r["result"]["three-routers-lab"] == True
            ), f"{w} - failed to restart lab three-routers-lab"

    def test_restart_nonexist_lab(self, nfclient):
        wait_for_containerlab_worker(nfclient)
        ret = nfclient.run_job(
            "containerlab", "restart_lab", kwargs={"lab_name": "nonexist"}
        )
        pprint.pprint(ret)

        for w, r in ret.items():
            assert r["failed"] == True, f"{w} - should have failed to restart lab"
