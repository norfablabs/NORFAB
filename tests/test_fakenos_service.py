import pprint

NET1_INVENTORY = "nf://fakenos/net1.yaml"
NET2_INVENTORY = "nf://fakenos/net2.yaml"


def _stop_all_networks(nfclient):
    """Stop all running FakeNOS networks on every worker."""
    nfclient.run_job("fakenos", "stop")


def _start_network(nfclient, network, inventory):
    """Start a FakeNOS network and return the raw result."""
    return nfclient.run_job(
        "fakenos",
        "start",
        kwargs={"network": network, "inventory": inventory},
    )


# ----------------------------------------------------------------------------
# FAKENOS WORKER TESTS
# ----------------------------------------------------------------------------


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
                assert (
                    host_data["platform"] == "cisco_ios"
                ), f"{worker_name}/{host_name} unexpected platform"
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
