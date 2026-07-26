import pprint
import pytest

pytestmark = [
    pytest.mark.nornir,
    pytest.mark.runtime_inventory,
    pytest.mark.task_nornir_runtime_inventory,
]


@pytest.mark.task_nornir_runtime_inventory
class TestNornirRunTimeInventory:
    def test_runtime_inventory_create_host(self, nfclient):
        ret = nfclient.run_job(
            "nornir",
            "runtime_inventory",
            workers=["nornir-worker-1"],
            kwargs={"action": "create_host", "name": "foobar"},
        )

        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is False, f"{worker} failed to run the task"
            assert results["result"]["foobar"] == True

    def test_runtime_inventory_delete_host(self, nfclient):
        ret_create = nfclient.run_job(
            "nornir",
            "runtime_inventory",
            workers=["nornir-worker-1"],
            kwargs={"action": "create_host", "name": "foobar"},
        )

        ret = nfclient.run_job(
            "nornir",
            "runtime_inventory",
            workers=["nornir-worker-1"],
            kwargs={"action": "delete_host", "name": "foobar"},
        )

        pprint.pprint(ret)

        for worker, results in ret.items():
            assert results["failed"] is False, f"{worker} failed to run the task"
            assert results["result"]["foobar"] == True

    def test_load_containerlab_inventory(self, nfclient):
        # deploy containerlab topology
        ret_deploy = nfclient.run_job(
            "containerlab",
            "deploy",
            workers=["containerlab-worker-1"],
            kwargs={
                "topology": "nf://containerlab/three-routers-topology.yaml",
                "reconfigure": True,
            },
        )
        print("Lab deployed:")
        pprint.pprint(ret_deploy)

        # load inventory
        ret_load = nfclient.run_job(
            "nornir",
            "nornir_inventory_load_containerlab",
            workers=["nornir-worker-1"],
            kwargs={
                "clab_workers": "containerlab-worker-1",
                "lab_name": "three-routers-lab",
            },
        )
        print("Nornir loaded containerlab nodes:")
        pprint.pprint(ret_load)

        # show hosts inventory
        ret_hosts = nfclient.run_job(
            "nornir",
            "get_nornir_hosts",
            workers=["nornir-worker-1"],
        )
        print("Nornir hosts:")
        pprint.pprint(ret_hosts)

        # run command
        ret_run_command = nfclient.run_job(
            "nornir",
            "cli",
            workers=["nornir-worker-1"],
            kwargs={
                "commands": "show version",
                "FL": ["r1", "r2", "r3"],
            },
        )
        print("Nornir run cli command:")
        pprint.pprint(ret_run_command)

        # Refresh nornir
        ret_refresh = nfclient.run_job(
            "nornir",
            "refresh_nornir",
            workers=["nornir-worker-1"],
        )
        print("Nornir refreshed:")
        pprint.pprint(ret_refresh)

        # show hosts inventory
        ret_hosts_after_refresh = nfclient.run_job(
            "nornir",
            "get_nornir_hosts",
            workers=["nornir-worker-1"],
        )
        print("Nornir hosts after refresh:")
        pprint.pprint(ret_hosts_after_refresh)

        assert all(
            h in ret_hosts["nornir-worker-1"]["result"]
            for h in ["ceos-spine-1", "ceos-spine-2", "r1", "r2", "r3"]
        ), "nornir-worker-1 did not load three-routers-lab devices"
        assert all(
            h in ret_run_command["nornir-worker-1"]["result"]
            for h in ["r1", "r2", "r3"]
        ), "nornir-worker-1 did not return command output"
        assert all(
            h not in ret_hosts_after_refresh["nornir-worker-1"]["result"]
            for h in ["r1", "r2", "r3"]
        ), "nornir-worker-1 inventory not refreshed"

    def test_create_host_from_netbox_one_device(self, nfclient):
        nfclient.run_job("nornir", "refresh_nornir", workers=["nornir-worker-1"])

        ret = nfclient.run_job(
            "nornir",
            "create_host_from_netbox",
            workers=["nornir-worker-1"],
            kwargs={"devices": ["fceos4"], "netbox_workers": "any"},
        )
        pprint.pprint(ret)

        results = ret["nornir-worker-1"]
        assert results["failed"] is False
        assert results["result"]["created"] == ["fceos4"]
        assert results["result"]["updated"] == []
        assert results["result"]["missing"] == []

    def test_create_host_from_netbox_multiple_devices(self, nfclient):
        nfclient.run_job("nornir", "refresh_nornir", workers=["nornir-worker-1"])

        ret = nfclient.run_job(
            "nornir",
            "create_host_from_netbox",
            workers=["nornir-worker-1"],
            kwargs={"devices": ["fceos4", "fceos5"], "netbox_workers": "any"},
        )
        pprint.pprint(ret)

        results = ret["nornir-worker-1"]
        assert results["failed"] is False
        assert sorted(results["result"]["created"]) == ["fceos4", "fceos5"]
        assert results["result"]["updated"] == []
        assert results["result"]["missing"] == []

    def test_create_host_from_netbox_dry_run_does_not_change_inventory(self, nfclient):
        nfclient.run_job("nornir", "refresh_nornir", workers=["nornir-worker-1"])

        ret = nfclient.run_job(
            "nornir",
            "create_host_from_netbox",
            workers=["nornir-worker-1"],
            kwargs={
                "devices": ["fceos4"],
                "netbox_workers": "any",
                "dry_run": True,
            },
        )
        ret_hosts = nfclient.run_job(
            "nornir",
            "get_nornir_hosts",
            workers=["nornir-worker-1"],
        )
        pprint.pprint(ret)
        pprint.pprint(ret_hosts)

        results = ret["nornir-worker-1"]
        assert results["failed"] is False
        assert results["dry_run"] is True
        assert results["result"]["created"] == ["fceos4"]
        assert "fceos4" not in ret_hosts["nornir-worker-1"]["result"]

    def test_create_host_from_netbox_reports_updated_host(self, nfclient):
        nfclient.run_job("nornir", "refresh_nornir", workers=["nornir-worker-1"])
        nfclient.run_job(
            "nornir",
            "runtime_inventory",
            workers=["nornir-worker-1"],
            kwargs={"action": "create_host", "name": "fceos4", "hostname": "scratch"},
        )

        ret = nfclient.run_job(
            "nornir",
            "create_host_from_netbox",
            workers=["nornir-worker-1"],
            kwargs={"devices": ["fceos4"], "netbox_workers": "any"},
        )
        pprint.pprint(ret)

        results = ret["nornir-worker-1"]
        assert results["failed"] is False
        assert results["result"]["created"] == []
        assert results["result"]["updated"] == ["fceos4"]

    def test_create_host_from_netbox_reports_missing_and_creates_valid(self, nfclient):
        nfclient.run_job("nornir", "refresh_nornir", workers=["nornir-worker-1"])

        ret = nfclient.run_job(
            "nornir",
            "create_host_from_netbox",
            workers=["nornir-worker-1"],
            kwargs={
                "devices": ["fceos4", "norfab-missing-device"],
                "netbox_workers": "any",
            },
        )
        pprint.pprint(ret)

        results = ret["nornir-worker-1"]
        assert results["failed"] is False
        assert results["result"]["created"] == ["fceos4"]
        assert results["result"]["missing"] == ["norfab-missing-device"]


