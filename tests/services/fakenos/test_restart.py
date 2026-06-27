import pprint
import pytest

try:
    from tests.services.fakenos.common import (
        NET1_INVENTORY,
        _start_network,
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
        NET1_INVENTORY,
        _start_network,
        _stop_all_networks,
    )

pytestmark = [
    pytest.mark.fakenos,
    pytest.mark.restart,
    pytest.mark.task_fakenos_restart,
]


@pytest.mark.task_fakenos_restart
class TestRestartTask:
    def test_restart_task(self, nfclient):
        _stop_all_networks(nfclient)
        _start_network(nfclient, "net1", NET1_INVENTORY)

        ret = nfclient.run_job(
            "fakenos",
            "restart",
            kwargs={"network": "net1"},
        )
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            assert data["failed"] is False, f"{worker_name} failed to restart net1"
            assert (
                "net1" in data["result"]
            ), f"{worker_name} net1 not found in result after restart"
            assert (
                data["result"]["net1"]["alive"] is True
            ), f"{worker_name} net1 not alive after restart"
            assert (
                len(data["result"]["net1"]["hosts"]) > 0
            ), f"{worker_name} net1 has no hosts after restart"
