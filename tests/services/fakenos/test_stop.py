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

pytestmark = [pytest.mark.fakenos, pytest.mark.stop, pytest.mark.task_fakenos_stop]


@pytest.mark.task_fakenos_stop
class TestStopTask:
    def test_stop_task_specific_network(self, nfclient):
        _stop_all_networks(nfclient)
        _start_network(nfclient, "net1", NET1_INVENTORY)
        _start_network(nfclient, "net2", NET2_INVENTORY)

        ret = nfclient.run_job(
            "fakenos",
            "stop",
            kwargs={"network": "net1"},
        )
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            assert data["failed"] is False, f"{worker_name} failed to stop net1"
            assert "net1" in data["result"], f"{worker_name} net1 not in stop result"
            assert (
                data["result"]["net1"] == "stopped"
            ), f"{worker_name} unexpected stop message: {data['result']}"

    def test_stop_task_all_networks(self, nfclient):
        _stop_all_networks(nfclient)
        _start_network(nfclient, "net1", NET1_INVENTORY)
        _start_network(nfclient, "net2", NET2_INVENTORY)

        ret = nfclient.run_job("fakenos", "stop")
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            assert data["failed"] is False, f"{worker_name} failed to stop all networks"
            assert isinstance(
                data["result"], dict
            ), f"{worker_name} result is not a dict"
            assert "net1" in data["result"], f"{worker_name} net1 not in stop result"
            assert "net2" in data["result"], f"{worker_name} net2 not in stop result"
            assert (
                data["result"]["net1"] == "stopped"
            ), f"{worker_name} net1 unexpected stop message"
            assert (
                data["result"]["net2"] == "stopped"
            ), f"{worker_name} net2 unexpected stop message"

    def test_stop_task_empty(self, nfclient):
        _stop_all_networks(nfclient)

        ret = nfclient.run_job("fakenos", "stop")
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            assert (
                data["failed"] is False
            ), f"{worker_name} failed to call stop with no networks"
            assert (
                data["result"] == {}
            ), f"{worker_name} expected empty dict but got: {data['result']}"
