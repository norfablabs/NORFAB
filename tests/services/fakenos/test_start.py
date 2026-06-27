import pprint
import pytest

try:
    from tests.services.fakenos.common import (
        NET1_INVENTORY,
        NET2_INVENTORY,
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
        NET2_INVENTORY,
        _start_network,
        _stop_all_networks,
    )

pytestmark = [pytest.mark.fakenos, pytest.mark.start, pytest.mark.task_fakenos_start]


@pytest.mark.task_fakenos_start
class TestStartTask:
    def test_start_task_net1(self, nfclient):
        _stop_all_networks(nfclient)

        ret = _start_network(nfclient, "net1", NET1_INVENTORY)
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            assert data["failed"] is False, f"{worker_name} failed to start net1"
            assert "net1" in data["result"], f"{worker_name} net1 not found in result"
            assert (
                data["result"]["net1"]["alive"] is True
            ), f"{worker_name} net1 process not alive"
            assert (
                len(data["result"]["net1"]["hosts"]) > 0
            ), f"{worker_name} net1 has no hosts"

    def test_start_task_net2(self, nfclient):
        _stop_all_networks(nfclient)

        ret = _start_network(nfclient, "net2", NET2_INVENTORY)
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            assert data["failed"] is False, f"{worker_name} failed to start net2"
            assert "net2" in data["result"], f"{worker_name} net2 not found in result"
            assert (
                data["result"]["net2"]["alive"] is True
            ), f"{worker_name} net2 process not alive"
            assert (
                len(data["result"]["net2"]["hosts"]) > 0
            ), f"{worker_name} net2 has no hosts"

    def test_start_task_both_networks(self, nfclient):
        _stop_all_networks(nfclient)

        _start_network(nfclient, "net1", NET1_INVENTORY)
        ret = _start_network(nfclient, "net2", NET2_INVENTORY)
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            assert (
                data["failed"] is False
            ), f"{worker_name} failed to start net2 alongside net1"
            assert "net2" in data["result"], f"{worker_name} net2 not found in result"
            assert (
                data["result"]["net2"]["alive"] is True
            ), f"{worker_name} net2 process not alive"
