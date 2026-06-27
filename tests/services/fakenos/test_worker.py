import pprint
import pytest

try:
    from tests.services.fakenos.common import (
        _stop_all_networks,
    )
except ModuleNotFoundError as exc:
    if exc.name not in {
        "tests",
        "tests.services",
        "tests.services.fakenos",
        "tests.services.fakenos.common",
    }:
        raise
    from services.fakenos.common import (
        _stop_all_networks,
    )

pytestmark = [pytest.mark.fakenos, pytest.mark.worker, pytest.mark.task_fakenos_worker]


@pytest.mark.task_fakenos_worker
class TestFakenosWorker:
    def test_get_inventory(self, nfclient):
        _stop_all_networks(nfclient)

        ret = nfclient.run_job("fakenos", "get_inventory")
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            assert data["failed"] is False, f"{worker_name} failed to run get_inventory"
            assert (
                "service" in data["result"]
            ), f"{worker_name} inventory missing 'service' key"

    def test_get_version(self, nfclient):
        _stop_all_networks(nfclient)

        ret = nfclient.run_job("fakenos", "get_version")
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            assert data["failed"] is False, f"{worker_name} failed to run get_version"
            assert isinstance(
                data["result"], dict
            ), f"{worker_name} result is not a dict"
            for pkg, version in data["result"].items():
                assert version != "", f"{worker_name}: {pkg} version is empty"
