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
    pytest.mark.worker,
    pytest.mark.task_containerlab_worker,
]


@pytest.mark.task_containerlab_worker
class TestWorker:
    def test_get_inventory(self, nfclient):
        wait_for_containerlab_worker(nfclient)
        ret = nfclient.run_job("containerlab", "get_inventory")
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            assert all(
                k in data["result"] for k in ["service"]
            ), f"{worker_name} inventory incomplete"

    def test_get_version(self, nfclient):
        wait_for_containerlab_worker(nfclient)
        ret = nfclient.run_job("containerlab", "get_version")
        pprint.pprint(ret)

        assert isinstance(ret, dict), f"Expected dictionary but received {type(ret)}"
        for worker_name, version_report in ret.items():
            for package, version in version_report["result"].items():
                assert version != "", f"{worker_name}:{package} version is empty"

    def test_get_running_labs(self, nfclient):
        wait_for_containerlab_worker(nfclient)
        ret = nfclient.run_job("containerlab", "get_running_labs")
        pprint.pprint(ret)

        assert isinstance(ret, dict), f"Expected dictionary but received {type(ret)}"
        for w, r in ret.items():
            assert r["failed"] == False, f"{w} - failed to get running labs"
            assert r["result"], f"{w} - result is empty"
