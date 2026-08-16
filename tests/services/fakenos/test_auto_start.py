import pprint

import pytest

pytestmark = [
    pytest.mark.fakenos,
    pytest.mark.fakenos_auto_start,
]


class TestAutoStart:
    def test_inventory_networks_auto_start(self, nfclient):
        ret = nfclient.run_job(
            "fakenos",
            "inspect_networks",
            kwargs={"details": False},
        )
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            assert data["failed"] is False, f"{worker_name} failed to inspect networks"
            assert (
                "nornir-cli-ceos-spine-leaf" in data["result"]
            ), f"{worker_name} did not auto-start cEOS network"
            assert (
                "manual-net2" not in data["result"]
            ), f"{worker_name} auto-started disabled network"
