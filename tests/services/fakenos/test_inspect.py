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

pytestmark = [
    pytest.mark.fakenos,
    pytest.mark.inspect,
    pytest.mark.task_fakenos_inspect,
]


@pytest.mark.task_fakenos_inspect
class TestInspectNetworks:
    def test_inspect_networks_all_details(self, nfclient):
        _stop_all_networks(nfclient)
        _start_network(nfclient, "net1", NET1_INVENTORY)
        _start_network(nfclient, "net2", NET2_INVENTORY)

        ret = nfclient.run_job(
            "fakenos",
            "inspect_networks",
            kwargs={"details": True},
        )
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            assert data["failed"] is False, f"{worker_name} failed to inspect networks"
            assert isinstance(
                data["result"], dict
            ), f"{worker_name} result is not a dict"
            for net_name, net_info in data["result"].items():
                assert "pid" in net_info, f"{worker_name}/{net_name} missing 'pid'"
                assert "alive" in net_info, f"{worker_name}/{net_name} missing 'alive'"
                assert "hosts" in net_info, f"{worker_name}/{net_name} missing 'hosts'"
                assert net_info["alive"] is True, f"{worker_name}/{net_name} not alive"

    def test_inspect_networks_no_details(self, nfclient):
        _stop_all_networks(nfclient)
        _start_network(nfclient, "net1", NET1_INVENTORY)
        _start_network(nfclient, "net2", NET2_INVENTORY)

        ret = nfclient.run_job(
            "fakenos",
            "inspect_networks",
            kwargs={"details": False},
        )
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            assert (
                data["failed"] is False
            ), f"{worker_name} failed to inspect networks without details"
            assert isinstance(
                data["result"], list
            ), f"{worker_name} result is not a list"
            assert "net1" in data["result"], f"{worker_name} net1 missing from list"
            assert "net2" in data["result"], f"{worker_name} net2 missing from list"

    def test_inspect_networks_specific_network(self, nfclient):
        _stop_all_networks(nfclient)
        _start_network(nfclient, "net1", NET1_INVENTORY)

        ret = nfclient.run_job(
            "fakenos",
            "inspect_networks",
            kwargs={"network": "net1", "details": True},
        )
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            assert data["failed"] is False, f"{worker_name} failed to inspect net1"
            assert "net1" in data["result"], f"{worker_name} net1 not found in result"
            assert "pid" in data["result"]["net1"], f"{worker_name} net1 missing 'pid'"
            assert (
                "alive" in data["result"]["net1"]
            ), f"{worker_name} net1 missing 'alive'"
            assert (
                "hosts" in data["result"]["net1"]
            ), f"{worker_name} net1 missing 'hosts'"
            assert (
                data["result"]["net1"]["alive"] is True
            ), f"{worker_name} net1 not alive"
            assert (
                len(data["result"]["net1"]["hosts"]) > 0
            ), f"{worker_name} net1 has no hosts"

    def test_inspect_networks_empty(self, nfclient):
        _stop_all_networks(nfclient)

        ret = nfclient.run_job(
            "fakenos",
            "inspect_networks",
            kwargs={"details": False},
        )
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            assert (
                data["failed"] is False
            ), f"{worker_name} failed to inspect empty networks"
            assert (
                data["result"] == []
            ), f"{worker_name} expected empty list but got: {data['result']}"
