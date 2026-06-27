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
    pytest.mark.inventory,
    pytest.mark.task_fakenos_get_nornir_inventory,
]


@pytest.mark.task_fakenos_get_nornir_inventory
class TestGetNornirInventory:
    def test_get_nornir_inventory_single_network(self, nfclient):
        _stop_all_networks(nfclient)
        _start_network(nfclient, "net1", NET1_INVENTORY)

        ret = nfclient.run_job(
            "fakenos",
            "get_nornir_inventory",
            kwargs={"network": "net1"},
        )
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            assert (
                data["failed"] is False
            ), f"{worker_name} failed to get nornir inventory"
            assert (
                "hosts" in data["result"]
            ), f"{worker_name} result missing 'hosts' key"
            hosts = data["result"]["hosts"]
            assert len(hosts) > 0, f"{worker_name} no hosts in inventory"
            for host_name, host_data in hosts.items():
                assert (
                    host_data["hostname"] == "127.0.0.1"
                ), f"{worker_name}/{host_name} unexpected hostname"
                assert (
                    host_data["port"] is not None
                ), f"{worker_name}/{host_name} port is None"
                assert (
                    host_data["username"] == "admin"
                ), f"{worker_name}/{host_name} unexpected username"
                assert (
                    host_data["password"] == "admin"
                ), f"{worker_name}/{host_name} unexpected password"
                assert host_data["platform"] in [
                    "cisco_xr",
                    "arista_eos",
                ], f"{worker_name}/{host_name} unexpected platform"
                assert isinstance(
                    host_data["groups"], list
                ), f"{worker_name}/{host_name} groups is not a list"

    def test_get_nornir_inventory_all_networks(self, nfclient):
        _stop_all_networks(nfclient)
        _start_network(nfclient, "net1", NET1_INVENTORY)
        _start_network(nfclient, "net2", NET2_INVENTORY)

        ret = nfclient.run_job(
            "fakenos",
            "get_nornir_inventory",
        )
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            assert (
                data["failed"] is False
            ), f"{worker_name} failed to get nornir inventory for all networks"
            assert (
                "hosts" in data["result"]
            ), f"{worker_name} result missing 'hosts' key"
            hosts = data["result"]["hosts"]
            assert len(hosts) > 0, f"{worker_name} no hosts in inventory"
            # verify at least one net1 host (arista-eos-router*) is present
            net1_hosts = [h for h in hosts if h.startswith("arista-eos-router")]
            assert (
                len(net1_hosts) > 0
            ), f"{worker_name} no net1 hosts (arista-eos-router*) found"
            # verify net2 host is present
            assert (
                "xr1" in hosts
            ), f"{worker_name} net2 host 'xr1' not found in inventory"

    def test_get_nornir_inventory_with_groups(self, nfclient):
        _stop_all_networks(nfclient)
        _start_network(nfclient, "net1", NET1_INVENTORY)

        ret = nfclient.run_job(
            "fakenos",
            "get_nornir_inventory",
            kwargs={"network": "net1", "groups": ["lab", "eos"]},
        )
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            assert (
                data["failed"] is False
            ), f"{worker_name} failed to get nornir inventory with groups"
            hosts = data["result"]["hosts"]
            for host_name, host_data in hosts.items():
                assert (
                    "lab" in host_data["groups"]
                ), f"{worker_name}/{host_name} missing group 'lab'"
                assert (
                    "eos" in host_data["groups"]
                ), f"{worker_name}/{host_name} missing group 'eos'"

    def test_get_nornir_inventory_no_networks_running(self, nfclient):
        _stop_all_networks(nfclient)

        ret = nfclient.run_job(
            "fakenos",
            "get_nornir_inventory",
        )
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            assert (
                data["failed"] is False
            ), f"{worker_name} should not fail when no networks are running"
            assert (
                data["result"]["hosts"] == {}
            ), f"{worker_name} expected empty hosts dict"

    def test_get_nornir_inventory_network_not_found(self, nfclient):
        _stop_all_networks(nfclient)

        ret = nfclient.run_job(
            "fakenos",
            "get_nornir_inventory",
            kwargs={"network": "nonexistent-network"},
        )
        pprint.pprint(ret)

        for worker_name, data in ret.items():
            assert (
                data["failed"] is True
            ), f"{worker_name} should fail for nonexistent network"
