import pprint
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from norfab.models import Result
from norfab.workers.netbox_worker import netbox_models
from norfab.workers.netbox_worker.devices_tasks import NetboxDevicesTasks
from norfab.workers.netbox_worker.netbox_worker import (
    RETRYABLE_HTTP_METHODS,
    NetboxWorker,
)
from norfab.workers.netbox_worker.netbox_worker_utilities import (
    sync_diff_has_changes,
)

try:
    from tests.services.netbox.common import (
        delete_all_mac_addresses,
        delete_branch,
        get_pynetbox,
    )
except ModuleNotFoundError as exc:
    if exc.name not in {
        "tests",
        "tests.services",
        "tests.services.netbox",
        "tests.services.netbox.common",
    }:
        raise
    from services.netbox.common import (
        delete_all_mac_addresses,
        delete_branch,
        get_pynetbox,
    )

pytestmark = pytest.mark.netbox


@pytest.mark.parametrize(
    ("diff", "expected"),
    [
        ({}, False),
        ({"create": [], "update": {}, "delete": [], "in_sync": ["item"]}, False),
        ({"device": {"create": [], "update": {}, "delete": []}}, False),
        (
            {
                "vlans": {"global": {"create": [], "update": {}, "delete": []}},
                "interfaces": {
                    "router-1": {"create": [], "update": {}, "delete": []}
                },
            },
            False,
        ),
        ({"device": {"create": ["item"], "update": {}, "delete": []}}, True),
        ({"global": {"create": [], "update": {"item": {}}, "delete": []}}, True),
    ],
)
def test_sync_diff_has_changes(diff: dict, expected: bool) -> None:
    assert sync_diff_has_changes(diff) is expected


def test_sync_diff_has_changes_can_ignore_deletions() -> None:
    diff = {
        "device": {"create": [], "update": {}, "delete": ["Loopback99"]}
    }

    assert sync_diff_has_changes(diff) is True
    assert sync_diff_has_changes(diff, ignore_deletions=True) is False


@pytest.mark.parametrize(
    "model, required_data",
    [
        (netbox_models.SyncDeviceInventoryInput, {}),
        (netbox_models.SyncDeviceInterfacesInput, {}),
        (netbox_models.SyncMacAddressesInput, {}),
        (netbox_models.SyncDeviceIpInput, {}),
        (netbox_models.SyncDevicePrefixesInput, {}),
        (netbox_models.SyncVlansInput, {}),
        (netbox_models.SyncVrfsInput, {}),
        (netbox_models.SyncBgpAsnInput, {}),
        (netbox_models.SyncBgpCommunityInput, {}),
        (netbox_models.SyncBgpPeeringsInput, {}),
        (netbox_models.CreateBgpPeeringInput, {"bulk_create": []}),
        (netbox_models.UpdateBgpPeeringInput, {"bulk_update": []}),
    ],
)
def test_bulk_sync_batch_size_models(model: Any, required_data: dict) -> None:
    assert model.model_validate(required_data).batch_size == 1000
    assert model.model_validate({**required_data, "batch-size": 1}).batch_size == 1
    assert (
        model.model_validate({**required_data, "batch-size": 10_000}).batch_size
        == 10_000
    )
    for value in (0, -1, True, 1.5, "2"):
        with pytest.raises(ValidationError):
            model.model_validate({**required_data, "batch-size": value})


def test_sync_action_summary_supports_string_and_integer_identifiers() -> None:
    summary = netbox_models.SyncActionSummary(
        created=["Ethernet1"],
        updated=[100],
        deleted=[],
        in_sync=[4200000001, "10.0.0.1/32"],
    )

    assert summary.model_dump() == {
        "created": ["Ethernet1"],
        "updated": [100],
        "deleted": [],
        "in_sync": [4200000001, "10.0.0.1/32"],
    }


@pytest.mark.parametrize(
    "model",
    [
        netbox_models.SyncDeviceInventoryResult,
        netbox_models.SyncDeviceInterfacesResult,
        netbox_models.SyncMacAddressesResult,
        netbox_models.SyncDeviceIpResult,
        netbox_models.SyncVrrpResult,
        netbox_models.SyncBgpPeeringsResult,
        netbox_models.SyncBgpAsnResult,
        netbox_models.SyncBgpCommunityResult,
    ],
)
def test_sync_result_models_accept_typed_live_action_maps(model: Any) -> None:
    result = model.model_validate(
        {
            "result": {
                "scope": netbox_models.SyncActionSummary().model_dump(),
            }
        }
    )

    assert result.result.root["scope"].model_dump() == {
        "created": [],
        "updated": [],
        "deleted": [],
        "in_sync": [],
    }


def test_pynetbox_session_uses_retry_adapter() -> None:
    worker = object.__new__(NetboxWorker)
    worker.netbox_retry = Retry(total=0)
    worker._get_instance_params = lambda instance: {
        "url": "https://netbox.example",
        "token": "token",
        "ssl_verify": True,
    }

    nb = worker._get_pynetbox("test")
    adapter = nb.http_session.get_adapter("https://")

    assert type(adapter) is HTTPAdapter
    assert adapter.max_retries is worker.netbox_retry
    assert "POST" not in RETRYABLE_HTTP_METHODS


def test_netbox_inventory_timeout_and_retry_model() -> None:
    config = netbox_models.NetboxConfigModel.model_validate(
        {
            "netbox_connect_timeout": 12,
            "netbox_read_timeout": 345,
            "netbox_retries": 2,
            "netbox_retry_backoff": 1.5,
            "instances": {},
        }
    )

    assert config.netbox_connect_timeout == 12
    assert config.netbox_read_timeout == 345
    assert config.netbox_retries == 2
    assert config.netbox_retry_backoff == 1.5


class TestSyncAllOrchestration:
    TASKS = [
        ("sync_device_inventory", {"device-1": {}}),
        ("sync_device_prefixes", {"created": [], "updated": [], "in_sync": []}),
        ("sync_device_interfaces", {"device-1": {}}),
        (
            "sync_vrfs",
            {
                "vrfs": {},
                "route_targets": {},
                "routing_policies": {},
                "interfaces": {"device-1": {}, "other-device": {}},
            },
        ),
        (
            "sync_vlans",
            {
                "vlans": {"site:test": {}},
                "interfaces": {"device-1": {}, "other-device": {}},
            },
        ),
        ("sync_mac_addresses", {"device-1": {}}),
        ("sync_device_ip", {"device-1": {}}),
        ("sync_bgp_peerings", {"device-1": {}}),
    ]
    RESULT_CATEGORIES = {
        "sync_device_inventory": "inventory",
        "sync_vlans": "vlans",
        "sync_device_prefixes": "prefixes",
        "sync_vrfs": "vrfs",
        "sync_device_interfaces": "interfaces",
        "sync_mac_addresses": "mac_addresses",
        "sync_device_ip": "ip_addresses",
        "sync_bgp_peerings": "bgp_peerings",
    }

    @classmethod
    def _worker(cls, calls: list[str]) -> SimpleNamespace:
        worker = SimpleNamespace(
            name="netbox-test",
            default_instance="test",
            get_nornir_hosts=lambda kwargs, timeout: [],
        )
        for task_name, task_result in cls.TASKS:
            setattr(
                worker,
                task_name,
                lambda _task_name=task_name, _result=task_result, **kwargs: (
                    calls.append(_task_name) or Result(task=_task_name, result=_result)
                ),
            )
        worker.sync_bgp_community = lambda **kwargs: Result(
            task="sync_bgp_community",
            result={"route_targets": {}, "communities": {}},
        )
        worker.sync_vrrp = lambda **kwargs: Result(
            task="sync_vrrp", result={"device-1": {}}
        )
        return worker

    @staticmethod
    def _job() -> SimpleNamespace:
        return SimpleNamespace(event=lambda *args, **kwargs: None)

    def test_sync_all_task_order(self) -> None:
        calls = []

        result = NetboxDevicesTasks.sync_all(
            self._worker(calls),
            self._job(),
            devices=["device-1"],
            dry_run=True,
        )

        assert calls == [task_name for task_name, _ in self.TASKS]
        assert result.result["device-1"]["vlans"] == {
            "vlans": {"site:test": {}},
            "interfaces": {"device-1": {}},
        }
        assert result.result["device-1"]["vrfs"] == {
            "vrfs": {},
            "route_targets": {},
            "routing_policies": {},
            "interfaces": {"device-1": {}},
        }

    def test_check_sync_keeps_routing_policy_plan(self) -> None:
        worker = self._worker([])
        vrf_plan = {
            "vrfs": {
                "create": [],
                "update": {},
                "delete": [],
            },
            "route_targets": {"create": []},
            "routing_policies": {"create": ["RPL1"]},
            "interfaces": {},
        }
        worker.sync_vrfs = lambda **kwargs: Result(task="sync_vrfs", diff=vrf_plan)

        result = NetboxDevicesTasks.check_device_sync(
            worker,
            self._job(),
            devices=["device-1"],
            check_inventory=False,
            check_interfaces=False,
            check_vlans=False,
            check_prefixes=False,
            check_ip_addresses=False,
            check_bgp_peerings=False,
            check_bgp_communities=False,
            check_vrrp=False,
        )

        assert result.result["device-1"] == {"vrfs": False, "in_sync": False}
        assert result.diff["vrfs"]["routing_policies"]["create"] == ["RPL1"]

    def test_check_sync_detects_route_target_plan(self) -> None:
        worker = self._worker([])
        vrf_plan = {
            "vrfs": {"create": [], "update": {}, "delete": []},
            "route_targets": {"create": ["65000:1"], "update": {}, "delete": []},
            "routing_policies": {"create": [], "update": {}, "delete": []},
            "interfaces": {},
        }
        worker.sync_vrfs = lambda **kwargs: Result(task="sync_vrfs", diff=vrf_plan)

        result = NetboxDevicesTasks.check_device_sync(
            worker,
            self._job(),
            devices=["device-1"],
            check_inventory=False,
            check_interfaces=False,
            check_vlans=False,
            check_prefixes=False,
            check_ip_addresses=False,
            check_bgp_peerings=False,
            check_bgp_communities=False,
            check_vrrp=False,
        )

        assert result.result["device-1"] == {"vrfs": False, "in_sync": False}
        assert result.diff["vrfs"]["route_targets"]["create"] == ["65000:1"]

    @pytest.mark.parametrize(
        "ignore_deletions,create,expected",
        [(False, [], False), (True, [], True), (True, ["Loopback99"], False)],
    )
    def test_check_sync_can_ignore_interface_deletions(
        self, ignore_deletions: bool, create: list[str], expected: bool
    ) -> None:
        worker = self._worker([])
        interface_plan = {
            "device-1": {
                "create": create,
                "update": {},
                "delete": ["StrayIface"],
                "in_sync": [],
            }
        }
        worker.sync_device_interfaces = lambda **kwargs: Result(
            task="sync_device_interfaces", diff=interface_plan
        )

        result = NetboxDevicesTasks.check_device_sync(
            worker,
            self._job(),
            devices=["device-1"],
            check_inventory=False,
            check_vrfs=False,
            check_vlans=False,
            check_prefixes=False,
            check_ip_addresses=False,
            check_bgp_peerings=False,
            check_bgp_communities=False,
            check_vrrp=False,
            ignore_deletions=ignore_deletions,
        )

        assert result.result["device-1"] == {
            "interfaces": expected,
            "in_sync": expected,
        }
        assert result.diff["interfaces"] == interface_plan

    def test_check_sync_detects_bgp_community_plan(self) -> None:
        worker = self._worker([])
        community_plan = {
            "route_targets": {
                "create": ["65000:1"],
                "update": {},
                "delete": [],
                "in_sync": [],
            },
            "communities": {
                "create": [],
                "update": {},
                "delete": [],
                "in_sync": [],
            },
        }
        worker.sync_bgp_community = lambda **kwargs: Result(
            task="sync_bgp_community", diff=community_plan
        )

        result = NetboxDevicesTasks.check_device_sync(
            worker,
            self._job(),
            devices=["device-1"],
            check_inventory=False,
            check_interfaces=False,
            check_vrfs=False,
            check_vlans=False,
            check_prefixes=False,
            check_ip_addresses=False,
            check_bgp_peerings=False,
            check_vrrp=False,
        )

        assert result.result["device-1"] == {
            "bgp_communities": False,
            "in_sync": False,
        }
        assert result.diff["bgp_communities"] == community_plan

    def test_check_sync_detects_per_device_vrrp_plan(self) -> None:
        worker = self._worker([])
        vrrp_plan = {
            "device-1": {
                "create": ["Ethernet1:vrrp2:10"],
                "update": {},
                "delete": [],
                "in_sync": [],
            },
            "device-2": {
                "create": [],
                "update": {},
                "delete": [],
                "in_sync": ["Ethernet1:vrrp2:10"],
            },
        }
        worker.sync_vrrp = lambda **kwargs: Result(task="sync_vrrp", diff=vrrp_plan)

        result = NetboxDevicesTasks.check_device_sync(
            worker,
            self._job(),
            devices=["device-1", "device-2"],
            check_inventory=False,
            check_interfaces=False,
            check_vrfs=False,
            check_vlans=False,
            check_prefixes=False,
            check_ip_addresses=False,
            check_bgp_peerings=False,
            check_bgp_communities=False,
        )

        assert result.result["device-1"] == {"vrrp": False, "in_sync": False}
        assert result.result["device-2"] == {"vrrp": True, "in_sync": True}
        assert result.diff["vrrp"] == vrrp_plan

    @pytest.mark.parametrize("failed_task, failed_result", TASKS)
    def test_sync_all_stops_after_failed_stage(
        self, failed_task: str, failed_result: dict
    ) -> None:
        calls = []
        worker = self._worker(calls)
        setattr(
            worker,
            failed_task,
            lambda _task=failed_task, _result=failed_result, **kwargs: (
                calls.append(_task)
                or Result(
                    task=_task,
                    result=_result,
                    failed=True,
                    errors=["batch failed"],
                )
            ),
        )

        result = NetboxDevicesTasks.sync_all(
            worker,
            self._job(),
            devices=["device-1"],
        )

        assert result.failed
        task_names = [task_name for task_name, _ in self.TASKS]
        assert calls == task_names[: task_names.index(failed_task) + 1]

    @pytest.mark.parametrize("skipped_task", RESULT_CATEGORIES)
    def test_false_sync_kwarg_skips_task_and_continues(self, skipped_task: str) -> None:
        calls = []

        result = NetboxDevicesTasks.sync_all(
            self._worker(calls),
            self._job(),
            devices=["device-1"],
            dry_run=True,
            sync_kwargs={skipped_task: False},
        )

        assert calls == [
            task_name for task_name, _ in self.TASKS if task_name != skipped_task
        ]
        assert self.RESULT_CATEGORIES[skipped_task] not in result.result["device-1"]
        assert set(result.result["device-1"]) == (
            set(self.RESULT_CATEGORIES.values())
            - {self.RESULT_CATEGORIES[skipped_task]}
        )


class TestSyncResourcesFailed:
    DEVICE = "cisco_ios_xr1"
    VLAN_DEVICE = "failed-nornir-device"
    SUCCESS_DEVICE = "fn-ceos-lf-1"

    @pytest.mark.parametrize(
        ("task", "failed_device"),
        [
            ("sync_device_inventory", DEVICE),
            ("sync_vlans", VLAN_DEVICE),
            ("sync_vrrp", VLAN_DEVICE),
            ("sync_device_prefixes", DEVICE),
            ("sync_vrfs", DEVICE),
            ("sync_device_interfaces", DEVICE),
            ("sync_mac_addresses", DEVICE),
            ("sync_device_ip", DEVICE),
            ("sync_bgp_peerings", DEVICE),
            ("sync_bgp_asn", DEVICE),
            ("sync_bgp_community", DEVICE),
        ],
    )
    def test_failed_nornir_resources_are_reported(
        self, nfclient: Any, task: str, failed_device: str
    ) -> None:
        nb = get_pynetbox(nfclient)
        device = nb.dcim.devices.get(name=failed_device)
        if device is not None:
            device.delete()
        device = nb.dcim.devices.create(
            name=failed_device,
            device_type=nb.dcim.device_types.get(
                model=(
                    "Arista cEOS" if failed_device == self.VLAN_DEVICE else "XVR9000"
                )
            ).id,
            role=nb.dcim.device_roles.get(name="VirtualRouter").id,
            site=nb.dcim.sites.get(name="SALTNORNIR-LAB").id,
            status="active",
        )
        try:
            clear_result = nfclient.run_job(
                "nornir", "errdisabled_hosts_clear", workers=["nornir-worker-4"]
            )["nornir-worker-4"]
            assert clear_result["failed"] is False

            response = nfclient.run_job(
                "netbox",
                task,
                workers="any",
                kwargs={
                    "devices": [self.SUCCESS_DEVICE, failed_device],
                    "dry_run": True,
                },
            )

            assert response
            for result in response.values():
                assert failed_device in result["resources_failed"]
                assert result["errors"]
                if task == "sync_vrrp":
                    assert not any(
                        "missing a live VRRP result" in error and failed_device in error
                        for error in result["errors"]
                    )
                assert result["failed"] is False
        finally:
            device.delete()


@pytest.mark.netbox_sync_mac_addresses
class TestSyncMacAddresses:
    # MAC addresses present in interfaces_parse_data.json per device:
    #   fn-ceos-sp-1  : 02:00:00:11:00:09 on Ethernet9  (description TEST_SYNC_ROUTED_WITH_MAC)
    #   fn-ceos-sp-2  : 02:00:00:12:00:09 on Ethernet9  (description TEST_SYNC_ROUTED_WITH_MAC)
    #   fn-ceos-lf-1   : 12:34:12:34:12:34 on Ethernet1  (description P2P to fn-ceos-sp-1 Ethernet2)
    #                   02:00:00:01:00:06 on Ethernet6  (description TEST_SYNC_ROUTED_WITH_MAC)
    #   fn-ceos-lf-2   : 02:00:00:02:00:06 on Ethernet6  (description TEST_SYNC_ROUTED_WITH_MAC)
    #   fn-ceos-lf-3   : 02:00:00:03:00:06 on Ethernet6  (description TEST_SYNC_ROUTED_WITH_MAC)

    ALL_DEVICES = [
        "fn-ceos-sp-1",
        "fn-ceos-sp-2",
        "fn-ceos-lf-1",
        "fn-ceos-lf-2",
        "fn-ceos-lf-3",
    ]
    SPINE_DEVICES = ["fn-ceos-sp-1", "fn-ceos-sp-2"]
    RESULT_KEYS = {"created", "updated", "in_sync"}

    # MAC addresses per device from parse data
    SPINE1_MAC = "02:00:00:11:00:09"
    SPINE1_INTF = "Ethernet9"
    SPINE2_MAC = "02:00:00:12:00:09"
    SPINE2_INTF = "Ethernet9"
    LEAF1_MAC_ETH1 = "12:34:12:34:12:34"
    LEAF1_INTF_ETH1 = "Ethernet1"
    LEAF1_MAC_ETH6 = "02:00:00:01:00:06"
    LEAF1_INTF_ETH6 = "Ethernet6"
    LEAF2_MAC = "02:00:00:02:00:06"
    LEAF2_INTF = "Ethernet6"
    LEAF3_MAC = "02:00:00:03:00:06"
    LEAF3_INTF = "Ethernet6"

    # All TEST_SYNC_ROUTED_WITH_MAC MACs (description matches TEST_SYNC_*)
    TEST_SYNC_MACS = {
        "02:00:00:11:00:09",
        "02:00:00:12:00:09",
        "02:00:00:01:00:06",
        "02:00:00:02:00:06",
        "02:00:00:03:00:06",
    }

    # ------------------------------------------------------------------ #
    # Class-level helpers                                                  #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _cleanup(nfclient, devices):
        """Delete all MAC addresses assigned to any interface on the given devices."""
        delete_all_mac_addresses(nfclient, devices)

    @staticmethod
    def _sync(nfclient, devices, **extra_kwargs):
        """Run sync_mac_addresses and return the result dict."""
        return nfclient.run_job(
            "netbox",
            "sync_mac_addresses",
            workers="any",
            kwargs={"devices": devices, **extra_kwargs},
        )

    @staticmethod
    def _get_intf_id(nfclient, device, name):
        """Return the NetBox ID of the given device interface."""
        resp = nfclient.run_job(
            "netbox",
            "rest",
            workers="any",
            kwargs={
                "method": "get",
                "api": "dcim/interfaces",
                "params": {"device": device, "name": name},
            },
        )
        worker, result = tuple(resp.items())[0]
        return result["result"]["results"][0]["id"]

    @staticmethod
    def _create_nb_mac(nfclient, mac, intf_id=None):
        """Create a MAC address entry in NetBox, optionally assigned to an interface."""
        payload = {"mac_address": mac}
        if intf_id is not None:
            payload["assigned_object_type"] = "dcim.interface"
            payload["assigned_object_id"] = intf_id
        nfclient.run_job(
            "netbox",
            "rest",
            workers="any",
            kwargs={
                "method": "post",
                "api": "/dcim/mac-addresses/",
                "json": payload,
            },
        )

    @staticmethod
    def _get_nb_macs(nfclient, device, interface):
        """Return a list of pynetbox MAC address records for the given device interface."""
        pynb = get_pynetbox(nfclient)
        return list(pynb.dcim.mac_addresses.filter(device=device, interface=interface))

    # ------------------------------------------------------------------ #
    # Basic smoke tests                                                    #
    # ------------------------------------------------------------------ #

    def test_sync_mac_addresses(self, nfclient):
        """Clean MACs from both spines then sync. Both spine MACs must be created;
        result must carry the correct RESULT_KEYS per device."""
        self._cleanup(nfclient, self.SPINE_DEVICES)

        ret = self._sync(nfclient, self.SPINE_DEVICES, batch_size=1)
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            for device in self.SPINE_DEVICES:
                assert (
                    device in res["result"]
                ), f"{worker} returned no result for {device}"
            for device, device_data in res["result"].items():
                assert (
                    self.RESULT_KEYS <= device_data.keys()
                ), f"{worker}:{device} missing keys in result, got: {set(device_data)}"
                assert device_data[
                    "created"
                ], f"{worker}:{device} no MACs created after cleanup"

    def test_sync_mac_addresses_all_devices(self, nfclient):
        """Clean MACs from all 5 devices then sync. Each device must have at least
        one MAC created."""
        self._cleanup(nfclient, self.ALL_DEVICES)

        ret = self._sync(nfclient, self.ALL_DEVICES)
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            for device in self.ALL_DEVICES:
                assert (
                    device in res["result"]
                ), f"{worker} returned no result for {device}"
            for device, device_data in res["result"].items():
                assert (
                    self.RESULT_KEYS <= device_data.keys()
                ), f"{worker}:{device} missing keys in result"
                assert device_data[
                    "created"
                ], f"{worker}:{device} no MACs created after cleanup"

    def test_sync_mac_addresses_dry_run(self, nfclient):
        """Clean MACs from both spines then dry_run. Result keys must be the same
        RESULT_KEYS and 'created' must be non-empty (no actual NB writes)."""
        self._cleanup(nfclient, self.SPINE_DEVICES)

        ret = self._sync(nfclient, self.SPINE_DEVICES, dry_run=True)
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            for device in self.SPINE_DEVICES:
                assert (
                    device in res["result"]
                ), f"{worker} returned no result for {device}"
            for device, device_data in res["result"].items():
                assert (
                    self.RESULT_KEYS <= device_data.keys()
                ), f"{worker}:{device} dry-run result missing keys, got: {set(device_data)}"
                assert device_data[
                    "created"
                ], f"{worker}:{device} dry-run created list is empty after cleanup"

        # Verify dry-run made no writes - MACs must still be absent from NetBox
        pynb = get_pynetbox(nfclient)
        macs_in_nb = list(
            pynb.dcim.mac_addresses.filter(
                mac_address=[self.SPINE1_MAC, self.SPINE2_MAC]
            )
        )
        assert (
            not macs_in_nb
        ), f"dry-run wrote MACs to NetBox: {[m.mac_address for m in macs_in_nb]}"

    def test_sync_mac_addresses_already_in_sync(self, nfclient):
        """Sync spines, then sync again. The second run must report all MACs as
        in_sync with nothing created or updated."""
        self._cleanup(nfclient, self.SPINE_DEVICES)

        # First sync: create MACs
        setup = self._sync(nfclient, self.SPINE_DEVICES)
        for worker, res in setup.items():
            assert not res["failed"], f"Setup sync failed for {worker}: {res['errors']}"
            assert res["result"]["fn-ceos-sp-1"][
                "created"
            ], f"{worker} no MACs created during setup sync"

        # Second sync: everything must be in_sync
        ret = self._sync(nfclient, self.SPINE_DEVICES)
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            for device, device_data in res["result"].items():
                assert not device_data[
                    "created"
                ], f"{worker}:{device} unexpected creates on second sync: {device_data['created']}"
                assert not device_data[
                    "updated"
                ], f"{worker}:{device} unexpected updates on second sync: {device_data['updated']}"
                assert device_data[
                    "in_sync"
                ], f"{worker}:{device} in_sync list empty on second sync"

    # ------------------------------------------------------------------ #
    # Create scenarios                                                     #
    # ------------------------------------------------------------------ #

    def test_sync_mac_addresses_create(self, nfclient):
        """Clean MACs from spine-1 then sync. Verify the MAC on Ethernet9 is created
        and the NetBox record matches the expected MAC value and interface assignment.
        """
        self._cleanup(nfclient, ["fn-ceos-sp-1"])

        ret = self._sync(nfclient, ["fn-ceos-sp-1"])
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            device_data = res["result"]["fn-ceos-sp-1"]
            assert (
                self.SPINE1_MAC in device_data["created"]
            ), f"{worker} {self.SPINE1_MAC} not in created list"

        # Validate the MAC record in NetBox
        nb_macs = self._get_nb_macs(nfclient, "fn-ceos-sp-1", self.SPINE1_INTF)
        assert (
            nb_macs
        ), f"{self.SPINE1_MAC} not found in NetBox for fn-ceos-sp-1:{self.SPINE1_INTF}"
        mac_values = [m.mac_address.lower() for m in nb_macs]
        assert (
            self.SPINE1_MAC in mac_values
        ), f"Expected MAC {self.SPINE1_MAC} not found in NetBox; got {mac_values}"
        nb_mac = next(m for m in nb_macs if m.mac_address.lower() == self.SPINE1_MAC)
        assert (
            nb_mac.assigned_object is not None
        ), f"{self.SPINE1_MAC} has no assigned_object in NetBox"
        assert (
            nb_mac.assigned_object.name == self.SPINE1_INTF
        ), f"{self.SPINE1_MAC} assigned to wrong interface: got {nb_mac.assigned_object.name!r}"

    def test_sync_mac_addresses_create_leaf1_two_macs(self, nfclient):
        """fn-ceos-lf-1 has two interfaces with MACs in live data (Ethernet1 and Ethernet6).
        Clean all leaf-1 MACs then sync. Both MACs must be created and correctly assigned.
        """
        self._cleanup(nfclient, ["fn-ceos-lf-1"])

        ret = self._sync(nfclient, ["fn-ceos-lf-1"])
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            device_data = res["result"]["fn-ceos-lf-1"]
            assert (
                self.LEAF1_MAC_ETH1 in device_data["created"]
            ), f"{worker} {self.LEAF1_MAC_ETH1} not in created list"
            assert (
                self.LEAF1_MAC_ETH6 in device_data["created"]
            ), f"{worker} {self.LEAF1_MAC_ETH6} not in created list"

        # Validate Ethernet1 MAC record
        nb_macs_eth1 = self._get_nb_macs(nfclient, "fn-ceos-lf-1", self.LEAF1_INTF_ETH1)
        assert (
            nb_macs_eth1
        ), f"{self.LEAF1_MAC_ETH1} not found in NetBox for fn-ceos-lf-1:{self.LEAF1_INTF_ETH1}"
        assert any(
            m.mac_address.lower() == self.LEAF1_MAC_ETH1 for m in nb_macs_eth1
        ), f"Expected MAC {self.LEAF1_MAC_ETH1} not found on fn-ceos-lf-1:{self.LEAF1_INTF_ETH1}"

        # Validate Ethernet6 MAC record
        nb_macs_eth6 = self._get_nb_macs(nfclient, "fn-ceos-lf-1", self.LEAF1_INTF_ETH6)
        assert (
            nb_macs_eth6
        ), f"{self.LEAF1_MAC_ETH6} not found in NetBox for fn-ceos-lf-1:{self.LEAF1_INTF_ETH6}"
        assert any(
            m.mac_address.lower() == self.LEAF1_MAC_ETH6 for m in nb_macs_eth6
        ), f"Expected MAC {self.LEAF1_MAC_ETH6} not found on fn-ceos-lf-1:{self.LEAF1_INTF_ETH6}"

    # ------------------------------------------------------------------ #
    # Update scenarios                                                     #
    # ------------------------------------------------------------------ #

    def test_sync_mac_addresses_update_unassigned(self, nfclient):
        """Pre-create the spine-1 MAC in NetBox without assigning it to any interface,
        then sync. The MAC must be updated (assigned to Ethernet9) rather than created.
        """
        self._cleanup(nfclient, ["fn-ceos-sp-1"])

        # Pre-create MAC unassigned (no assigned_object_id)
        self._create_nb_mac(nfclient, self.SPINE1_MAC, intf_id=None)

        ret = self._sync(nfclient, ["fn-ceos-sp-1"])
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            device_data = res["result"]["fn-ceos-sp-1"]
            assert (
                self.SPINE1_MAC in device_data["updated"]
            ), f"{worker} {self.SPINE1_MAC} not in updated list - expected update of unassigned MAC"
            assert (
                self.SPINE1_MAC not in device_data["created"]
            ), f"{worker} {self.SPINE1_MAC} incorrectly listed as created"

        # Validate the MAC is now assigned to the correct interface
        nb_macs = self._get_nb_macs(nfclient, "fn-ceos-sp-1", self.SPINE1_INTF)
        assert (
            nb_macs
        ), f"{self.SPINE1_MAC} not found on fn-ceos-sp-1:{self.SPINE1_INTF} after update"
        nb_mac = next(
            (m for m in nb_macs if m.mac_address.lower() == self.SPINE1_MAC), None
        )
        assert (
            nb_mac is not None
        ), f"{self.SPINE1_MAC} value not found on fn-ceos-sp-1:{self.SPINE1_INTF}"
        assert (
            nb_mac.assigned_object is not None
        ), f"{self.SPINE1_MAC} still has no assigned_object after update"
        assert (
            nb_mac.assigned_object.name == self.SPINE1_INTF
        ), f"{self.SPINE1_MAC} assigned to wrong interface after update: got {nb_mac.assigned_object.name!r}"

    def test_sync_mac_addresses_update_unassigned_dry_run(self, nfclient):
        """Pre-create spine-1 MAC unassigned in NB. Dry-run sync must list it under
        'updated', and the MAC must remain unassigned after the dry-run."""
        self._cleanup(nfclient, ["fn-ceos-sp-1"])
        self._create_nb_mac(nfclient, self.SPINE1_MAC, intf_id=None)

        ret = self._sync(nfclient, ["fn-ceos-sp-1"], dry_run=True)
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            device_data = res["result"]["fn-ceos-sp-1"]
            assert (
                self.SPINE1_MAC in device_data["updated"]
            ), f"{worker} {self.SPINE1_MAC} not in updated list for dry-run"

        # Dry-run must not have made any changes - MAC must remain unassigned
        pynb = get_pynetbox(nfclient)
        nb_entry = pynb.dcim.mac_addresses.get(mac_address=self.SPINE1_MAC)
        assert nb_entry is not None, f"{self.SPINE1_MAC} gone from NetBox after dry-run"
        assert (
            nb_entry.assigned_object is None
        ), f"Dry-run unexpectedly assigned {self.SPINE1_MAC} to {nb_entry.assigned_object!r}"

    # ------------------------------------------------------------------ #
    # Duplicate MAC scenarios                                              #
    # ------------------------------------------------------------------ #

    def test_sync_mac_addresses_duplicate_mac_different_interface(self, nfclient):
        """Pre-assign the spine-1 MAC to a different interface (Ethernet1) in NetBox,
        then run sync. The sync must report an error because the MAC is already
        assigned to a different interface, and must NOT create or update the MAC."""
        self._cleanup(nfclient, ["fn-ceos-sp-1"])

        # Assign the MAC to a *different* interface (Ethernet1, not Ethernet9)
        intf_id = self._get_intf_id(nfclient, "fn-ceos-sp-1", "Ethernet1")
        self._create_nb_mac(nfclient, self.SPINE1_MAC, intf_id=intf_id)

        ret = self._sync(nfclient, ["fn-ceos-sp-1"])
        pprint.pprint(ret)
        for worker, res in ret.items():
            # Errors must be reported for the conflicting MAC
            assert (
                len(res["errors"]) > 0
            ), f"{worker} expected errors for MAC assigned to different interface, got none"
            device_data = res["result"]["fn-ceos-sp-1"]
            # The MAC must NOT appear in created or updated
            assert (
                self.SPINE1_MAC not in device_data["created"]
            ), f"{worker} {self.SPINE1_MAC} incorrectly created despite interface conflict"
            assert (
                self.SPINE1_MAC not in device_data["updated"]
            ), f"{worker} {self.SPINE1_MAC} incorrectly updated despite interface conflict"

        # Validate the MAC is still assigned to Ethernet1 (not moved to Ethernet9)
        nb_macs_eth1 = self._get_nb_macs(nfclient, "fn-ceos-sp-1", "Ethernet1")
        assert any(
            m.mac_address.lower() == self.SPINE1_MAC for m in nb_macs_eth1
        ), f"{self.SPINE1_MAC} no longer on fn-ceos-sp-1:Ethernet1 after conflict sync"
        nb_macs_eth9 = self._get_nb_macs(nfclient, "fn-ceos-sp-1", self.SPINE1_INTF)
        assert not any(
            m.mac_address.lower() == self.SPINE1_MAC for m in nb_macs_eth9
        ), f"{self.SPINE1_MAC} was incorrectly duplicated onto fn-ceos-sp-1:{self.SPINE1_INTF}"

        # Cleanup
        self._cleanup(nfclient, ["fn-ceos-sp-1"])

    def test_sync_mac_addresses_duplicate_mac_same_interface(self, nfclient):
        """Pre-assign the spine-2 MAC to the correct interface (Ethernet9) in NetBox
        to simulate a MAC that already exists as a duplicate entry from a prior run.
        The sync must report it as in_sync without creating duplicates."""
        self._cleanup(nfclient, ["fn-ceos-sp-2"])

        # Pre-assign MAC to the correct interface - simulates an existing correct entry
        intf_id = self._get_intf_id(nfclient, "fn-ceos-sp-2", self.SPINE2_INTF)
        self._create_nb_mac(nfclient, self.SPINE2_MAC, intf_id=intf_id)

        ret = self._sync(nfclient, ["fn-ceos-sp-2"])
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            device_data = res["result"]["fn-ceos-sp-2"]
            assert (
                self.SPINE2_MAC in device_data["in_sync"]
            ), f"{worker} {self.SPINE2_MAC} not in in_sync list - expected in_sync for pre-assigned MAC"
            assert (
                self.SPINE2_MAC not in device_data["created"]
            ), f"{worker} {self.SPINE2_MAC} incorrectly listed as created"
            assert (
                self.SPINE2_MAC not in device_data["updated"]
            ), f"{worker} {self.SPINE2_MAC} incorrectly listed as updated"

        # Validate only one MAC entry exists for this interface (no duplicates added)
        nb_macs = self._get_nb_macs(nfclient, "fn-ceos-sp-2", self.SPINE2_INTF)
        matching = [m for m in nb_macs if m.mac_address.lower() == self.SPINE2_MAC]
        assert len(matching) == 1, (
            f"Expected exactly 1 entry for {self.SPINE2_MAC} on fn-ceos-sp-2:{self.SPINE2_INTF}, "
            f"got {len(matching)}"
        )

    # ------------------------------------------------------------------ #
    # Filter scenarios                                                     #
    # ------------------------------------------------------------------ #

    def test_sync_mac_addresses_filter_by_name(self, nfclient):
        """Clean all spine MACs then sync with filter_by_name='Ethernet9'.
        Only Ethernet9 MACs must be created; no MACs from other interfaces."""
        self._cleanup(nfclient, self.SPINE_DEVICES)

        ret = self._sync(
            nfclient, self.SPINE_DEVICES, dry_run=True, filter_by_name="Ethernet9"
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            all_macs = []
            for device_data in res["result"].values():
                all_macs.extend(device_data["created"])
                all_macs.extend(device_data["updated"])
                all_macs.extend(device_data["in_sync"])
            # Both Ethernet9 MACs must be planned for creation
            assert (
                self.SPINE1_MAC in all_macs
            ), f"{worker} spine-1 Ethernet9 MAC {self.SPINE1_MAC} not in plan after filter_by_name='Ethernet9'"
            assert (
                self.SPINE2_MAC in all_macs
            ), f"{worker} spine-2 Ethernet9 MAC {self.SPINE2_MAC} not in plan after filter_by_name='Ethernet9'"
            # Non-Ethernet9 MACs from leaf-1 must NOT appear
            assert (
                self.LEAF1_MAC_ETH1 not in all_macs
            ), f"{worker} leaf-1 Ethernet1 MAC {self.LEAF1_MAC_ETH1} leaked through filter_by_name='Ethernet9'"

    def test_sync_mac_addresses_filter_by_description(self, nfclient):
        """Clean all MACs from all devices then dry_run with filter_by_description='TEST_SYNC_*'.
        Only MACs on TEST_SYNC interfaces must appear in the plan.
        The non-TEST_SYNC MAC on leaf-1:Ethernet1 must not appear."""
        self._cleanup(nfclient, self.ALL_DEVICES)

        ret = self._sync(
            nfclient,
            self.ALL_DEVICES,
            dry_run=True,
            filter_by_description="TEST_SYNC_*",
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            all_macs = []
            for device_data in res["result"].values():
                all_macs.extend(device_data["created"])
                all_macs.extend(device_data["updated"])
                all_macs.extend(device_data["in_sync"])
            # All TEST_SYNC MACs must be in the plan
            missing = self.TEST_SYNC_MACS - set(all_macs)
            assert not missing, f"{worker} TEST_SYNC MACs missing from plan: {missing}"
            # Non-TEST_SYNC MAC (leaf-1 Ethernet1, description is a P2P label) must not appear
            assert (
                self.LEAF1_MAC_ETH1 not in all_macs
            ), f"{worker} non-TEST_SYNC MAC {self.LEAF1_MAC_ETH1} leaked through filter_by_description"

    def test_sync_mac_addresses_filter_by_mac(self, nfclient):
        """Clean spine-1 MACs then dry_run with filter_by_mac matching only spine-1's MAC.
        Only the matching MAC must appear; spine-2's MAC must be absent."""
        self._cleanup(nfclient, self.SPINE_DEVICES)

        ret = self._sync(
            nfclient,
            self.SPINE_DEVICES,
            dry_run=True,
            filter_by_mac="02:00:00:11:*",
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            all_macs = []
            for device_data in res["result"].values():
                all_macs.extend(device_data["created"])
                all_macs.extend(device_data["updated"])
                all_macs.extend(device_data["in_sync"])
            assert (
                self.SPINE1_MAC in all_macs
            ), f"{worker} spine-1 MAC {self.SPINE1_MAC} missing from plan with filter_by_mac='02:00:00:11:*'"
            assert (
                self.SPINE2_MAC not in all_macs
            ), f"{worker} spine-2 MAC {self.SPINE2_MAC} leaked through filter_by_mac='02:00:00:11:*'"

    # ------------------------------------------------------------------ #
    # Edge-case scenarios                                                  #
    # ------------------------------------------------------------------ #

    def test_sync_mac_addresses_duplicate_mac_unassigned_and_conflicting(
        self, nfclient
    ):
        """Regression test for the nb_macs dict-overwrite bug.

        Scenario: NetBox contains two entries for the same MAC on spine-1:
          - entry A: assigned to Ethernet1 (wrong interface - conflicts with live Ethernet9)
          - entry B: unassigned (no assigned_object)

        Depending on NetBox's iteration order, the old dict-comprehension could pick up
        entry B last and silently discard the conflicting entry A, causing the sync to
        update the unassigned entry instead of raising an error.

        With the fix, the assigned (conflicting) entry always wins.  The sync must
        report an error and NOT silently move or update the MAC."""
        self._cleanup(nfclient, ["fn-ceos-sp-1"])

        # Create entry A: MAC assigned to Ethernet1 (conflicts with live data pointing to Ethernet9)
        wrong_intf_id = self._get_intf_id(nfclient, "fn-ceos-sp-1", "Ethernet1")
        self._create_nb_mac(nfclient, self.SPINE1_MAC, intf_id=wrong_intf_id)

        # Create entry B: same MAC but unassigned (no interface)
        self._create_nb_mac(nfclient, self.SPINE1_MAC, intf_id=None)

        ret = self._sync(nfclient, ["fn-ceos-sp-1"])
        pprint.pprint(ret)
        for worker, res in ret.items():
            # Must report an error - the assigned conflicting entry must win over the unassigned one
            assert len(res["errors"]) > 0, (
                f"{worker} expected conflict error but got none - "
                f"the unassigned entry may have silently overwritten the conflicting one"
            )
            device_data = res["result"]["fn-ceos-sp-1"]
            # The MAC must NOT be silently updated/created
            assert (
                self.SPINE1_MAC not in device_data["created"]
            ), f"{worker} {self.SPINE1_MAC} incorrectly created despite conflict"
            assert self.SPINE1_MAC not in device_data["updated"], (
                f"{worker} {self.SPINE1_MAC} incorrectly updated despite conflict - "
                f"unassigned entry swallowed the conflicting assigned entry"
            )

        # Cleanup both NB entries
        self._cleanup(nfclient, ["fn-ceos-sp-1"])

    def test_sync_mac_addresses_non_existing_device(self, nfclient):
        """Sync against a device name that does not exist in NetBox.
        The task must fail and report an error."""
        ret = self._sync(nfclient, ["nonexistent-device-12345"])
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert (
                len(res["errors"]) > 0
            ), f"{worker} should have errors for nonexistent device"

    def test_sync_mac_addresses_with_branch(self, nfclient):
        """Clean spine MACs, delete the test branch, then sync into a new branch.
        Result must carry RESULT_KEYS and at least one MAC must be created."""
        branch = "sync_mac_addresses_branch_1"
        delete_branch(branch, nfclient)
        self._cleanup(nfclient, self.SPINE_DEVICES)

        ret = self._sync(nfclient, self.SPINE_DEVICES, branch=branch)
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            for device in self.SPINE_DEVICES:
                assert (
                    device in res["result"]
                ), f"{worker} returned no result for {device}"
            for device, device_data in res["result"].items():
                assert (
                    self.RESULT_KEYS <= device_data.keys()
                ), f"{worker}:{device} missing keys in branch-run result"


@pytest.mark.netbox_check_device_sync
class TestCheckDeviceSync:
    """Test suite for check_device_sync task."""

    DEVICES = ["fn-ceos-sp-1", "fn-ceos-sp-2"]
    # Expected per-device sub-categories when all checks are enabled
    ALL_CATEGORIES = {
        "inventory",
        "interfaces",
        "vrfs",
        "vlans",
        "prefixes",
        "ip_addresses",
        "bgp_peerings",
        "bgp_communities",
        "vrrp",
    }

    def test_check_device_sync_result_structure(self, nfclient):
        """Result has a dict per device with every enabled sync category."""
        ret = nfclient.run_job(
            "netbox",
            "check_device_sync",
            workers="any",
            kwargs={"devices": self.DEVICES},
        )
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert not res["failed"], f"{worker} failed - {res.get('errors')}"
            for device in self.DEVICES:
                assert device in res["result"], f"{worker} missing {device} in result"
                device_data = res["result"][device]
                assert (
                    self.ALL_CATEGORIES <= device_data.keys()
                ), f"{worker}:{device} missing categories: {self.ALL_CATEGORIES - device_data.keys()}"
                assert (
                    "in_sync" in device_data
                ), f"{worker}:{device} missing top-level 'in_sync' key"
                assert isinstance(
                    device_data["in_sync"], bool
                ), f"{worker}:{device} top-level 'in_sync' is not a bool"
                assert device_data["in_sync"] == all(
                    device_data[category] for category in self.ALL_CATEGORIES
                ), f"{worker}:{device} top-level 'in_sync' does not match categories"
                for category in self.ALL_CATEGORIES:
                    assert isinstance(
                        device_data[category], bool
                    ), f"{worker}:{device}:{category} is not a bool"

    def test_check_device_sync_diff_structure(self, nfclient):
        """Result.diff contains sub-task data keyed by category name."""
        ret = nfclient.run_job(
            "netbox",
            "check_device_sync",
            workers="any",
            kwargs={"devices": self.DEVICES},
        )
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert not res["failed"], f"{worker} failed - {res.get('errors')}"
            assert isinstance(res["diff"], dict), f"{worker} diff should be a dict"
            for category in self.ALL_CATEGORIES:
                assert (
                    category in res["diff"]
                ), f"{worker} diff missing '{category}' key"
                assert isinstance(
                    res["diff"][category], dict
                ), f"{worker} diff['{category}'] should be a dict"

    def test_check_device_sync_no_writes_to_netbox(self, nfclient):
        """check_device_sync must never write to NetBox."""
        pynb = get_pynetbox(nfclient)
        nb_device = pynb.dcim.devices.get(name="fn-ceos-sp-1")
        serial_before = nb_device.serial

        nfclient.run_job(
            "netbox",
            "check_device_sync",
            workers="any",
            kwargs={"devices": ["fn-ceos-sp-1"]},
        )

        nb_device = pynb.dcim.devices.get(name="fn-ceos-sp-1")
        assert (
            nb_device.serial == serial_before
        ), "check_device_sync modified NetBox serial - writes must not occur"

    def test_check_device_sync_selective_interfaces_only(self, nfclient):
        """Only interfaces category returned when other checks disabled."""
        ret = nfclient.run_job(
            "netbox",
            "check_device_sync",
            workers="any",
            kwargs={
                "devices": self.DEVICES,
                "check_inventory": False,
                "check_interfaces": True,
                "check_vrfs": False,
                "check_vlans": False,
                "check_prefixes": False,
                "check_ip_addresses": False,
                "check_bgp_peerings": False,
                "check_bgp_communities": False,
                "check_vrrp": False,
            },
        )
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert not res["failed"], f"{worker} failed - {res.get('errors')}"
            for device in self.DEVICES:
                assert device in res["result"], f"{worker} missing {device} in result"
                device_data = res["result"][device]
                assert (
                    "interfaces" in device_data
                ), f"{worker}:{device} missing interfaces"
                assert (
                    "inventory" not in device_data
                ), f"{worker}:{device} inventory should not be present"
                assert "vlans" not in device_data
                assert "prefixes" not in device_data
                assert (
                    "ip_addresses" not in device_data
                ), f"{worker}:{device} ip_addresses should not be present"
                assert (
                    "bgp_peerings" not in device_data
                ), f"{worker}:{device} bgp_peerings should not be present"
            assert "interfaces" in res["diff"], f"{worker} diff missing interfaces"
            assert (
                "inventory" not in res["diff"]
            ), f"{worker} diff should not have inventory"
            assert "vlans" not in res["diff"]
            assert "prefixes" not in res["diff"]

    def test_check_device_sync_selective_ip_only(self, nfclient):
        """Only the IP address category is returned."""
        ret = nfclient.run_job(
            "netbox",
            "check_device_sync",
            workers="any",
            kwargs={
                "devices": self.DEVICES,
                "check_inventory": False,
                "check_interfaces": False,
                "check_vrfs": False,
                "check_vlans": False,
                "check_prefixes": False,
                "check_ip_addresses": True,
                "check_bgp_peerings": False,
                "check_bgp_communities": False,
                "check_vrrp": False,
            },
        )
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert not res["failed"], f"{worker} failed - {res.get('errors')}"
            for device in self.DEVICES:
                device_data = res["result"][device]
                assert (
                    "inventory" not in device_data
                ), f"{worker}:{device} inventory should not be present"
                assert (
                    "interfaces" not in device_data
                ), f"{worker}:{device} interfaces should not be present"
                assert (
                    "ip_addresses" in device_data
                ), f"{worker}:{device} missing ip_addresses"
                assert (
                    "bgp_peerings" not in device_data
                ), f"{worker}:{device} bgp_peerings should not be present"

    def test_check_device_sync_selective_inventory_only(self, nfclient):
        """Inventory check can be explicitly enabled while other checks are disabled."""
        ret = nfclient.run_job(
            "netbox",
            "check_device_sync",
            workers="any",
            kwargs={
                "devices": self.DEVICES,
                "check_inventory": True,
                "check_interfaces": False,
                "check_vrfs": False,
                "check_vlans": False,
                "check_prefixes": False,
                "check_ip_addresses": False,
                "check_bgp_peerings": False,
                "check_bgp_communities": False,
                "check_vrrp": False,
            },
        )
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert not res["failed"], f"{worker} failed - {res.get('errors')}"
            assert "inventory" in res["diff"], f"{worker} diff missing inventory"
            for device in self.DEVICES:
                device_data = res["result"][device]
                assert set(device_data) == {
                    "inventory",
                    "in_sync",
                }, f"{worker}:{device} returned unexpected categories"
                assert isinstance(device_data["inventory"], bool)
                assert device_data["in_sync"] == device_data["inventory"]

    def test_check_device_sync_with_nornir_filter(self, nfclient):
        """Devices resolved via the FakeNOS spine name filter."""
        ret = nfclient.run_job(
            "netbox",
            "check_device_sync",
            workers="any",
            kwargs={"FB": ["fn-ceos-sp-*"]},
        )
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert not res["failed"], f"{worker} failed - {res.get('errors')}"
            for device in self.DEVICES:
                assert (
                    device in res["result"]
                ), f"{worker} device {device} missing from filter-resolved result"

    def test_check_device_sync_empty_devices(self, nfclient):
        """Empty devices list with no filters must fail with an error."""
        ret = nfclient.run_job(
            "netbox",
            "check_device_sync",
            workers="any",
            kwargs={"devices": []},
        )
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert res["failed"], f"{worker} should fail when no devices specified"
            assert res["errors"], f"{worker} should report errors"


@pytest.mark.netbox_sync_all
class TestSyncAll:
    """Verify sync_all calls all eight sync tasks in sequence.

    Each test performs a full cleanup before and after via setup_method/teardown_method
    and uses out-of-band pynetbox queries to verify NetBox state directly.
    """

    SPINE_DEVICES = ["fn-ceos-sp-1", "fn-ceos-sp-2"]
    ALL_CATEGORIES = {
        "inventory",
        "vlans",
        "prefixes",
        "interfaces",
        "mac_addresses",
        "ip_addresses",
        "bgp_peerings",
    }
    NETBOX_SERIALS = {
        "fn-ceos-sp-1": "FN-FNS12345678",
        "fn-ceos-sp-2": "FN-FNS123456789",
    }
    LIVE_SERIALS = {
        "fn-ceos-sp-1": "AF0396AF41960AB215A1BDB718EA1CDA",
        "fn-ceos-sp-2": "88E1CBB406FA6F8C132AD50609BE3053",
    }

    # Known TEST_SYNC items from interfaces_parse_data.json for spine devices
    SPINE1_TEST_INTF = (
        "Loopback10"  # TEST_SYNC_LOOPBACK_IPV4 - created by sync_device_interfaces
    )
    SPINE1_TEST_MAC = "02:00:00:11:00:09"  # created by sync_mac_addresses on Ethernet9
    SPINE1_TEST_IP = "10.3.15.33/30"  # created by sync_device_ip on Ethernet9

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    def setup_method(self):
        """Clean all sync-managed data from NetBox before each test."""
        self._do_cleanup()

    def teardown_method(self):
        """Clean all sync-managed data from NetBox after each test."""
        self._do_cleanup()

    @staticmethod
    def _do_cleanup():
        """Remove TEST_SYNC interfaces, all MACs, TEST_SYNC IPs and BGP sessions
        for spine devices using pynetbox directly."""
        nb = get_pynetbox(None)
        devices = ["fn-ceos-sp-1", "fn-ceos-sp-2"]
        # BGP sessions
        for device in devices:
            for session in list(nb.plugins.bgp.session.filter(device=device)):
                session.delete()
            nb.dcim.devices.get(name=device).update(
                {"serial": TestSyncAll.NETBOX_SERIALS[device]}
            )
        # TEST_SYNC IP addresses
        for parent_prefix in ["10.3.0.0/16", "2001:beef::/32"]:
            for ip in nb.ipam.ip_addresses.filter(parent=parent_prefix):
                ip.delete()
        # MAC addresses - delete by device filter (assigned MACs) and by known
        # MAC address values to catch unassigned/orphaned MACs left by other tests
        for device in devices:
            for mac in nb.dcim.mac_addresses.filter(device=device):
                mac.delete()
        for mac_addr in ["02:00:00:11:00:09", "02:00:00:12:00:09"]:
            for mac in nb.dcim.mac_addresses.filter(mac_address=mac_addr):
                mac.delete()
        # TEST_SYNC interfaces - delete children before parents to avoid 409 conflicts.
        # Exclude 'Ethernet9': pre-existing interface updated by sync; needed by TestSyncMacAddresses.
        for device in devices:
            intfs = list(
                nb.dcim.interfaces.filter(device=device, description__ic="TEST_SYNC")
            )
            children = [i for i in intfs if i.parent]
            parents = [i for i in intfs if not i.parent]
            for intf in children + parents:
                intf.delete()
        print("sync_all cleanup complete")

    # ------------------------------------------------------------------ #
    # Class-level helpers                                                  #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _sync(nfclient, devices, **extra_kwargs):
        """Run sync_all and return the result dict."""
        extra_kwargs.setdefault("sync_kwargs", {"sync_vrfs": False})
        return nfclient.run_job(
            "netbox",
            "sync_all",
            workers="any",
            kwargs={"devices": devices, **extra_kwargs},
        )

    @staticmethod
    def _get_nb_intf(device, name):
        """Fetch a single interface record from NetBox. Returns None if not found."""
        return get_pynetbox(None).dcim.interfaces.get(device=device, name=name)

    @staticmethod
    def _get_nb_macs(device, interface):
        """Return list of MAC address records for the given device interface."""
        return list(
            get_pynetbox(None).dcim.mac_addresses.filter(
                device=device, interface=interface
            )
        )

    @staticmethod
    def _get_nb_ips(device, interface):
        """Return list of IP address records for the given device interface."""
        return list(
            get_pynetbox(None).ipam.ip_addresses.filter(
                device=device, interface=interface
            )
        )

    # ------------------------------------------------------------------ #
    # Basic smoke tests                                                    #
    # ------------------------------------------------------------------ #

    def test_sync_all_result_structure(self, nfclient):
        """All enabled categories are present per device in dry-run mode."""
        ret = self._sync(nfclient, self.SPINE_DEVICES, dry_run=True)
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert not res["failed"], f"{worker} failed - {res.get('errors')}"
            for device in self.SPINE_DEVICES:
                assert device in res["result"], f"{worker} missing {device} in result"
                device_data = res["result"][device]
                assert self.ALL_CATEGORIES <= device_data.keys(), (
                    f"{worker}:{device} missing categories: "
                    f"{self.ALL_CATEGORIES - device_data.keys()}"
                )
                for category in self.ALL_CATEGORIES:
                    assert isinstance(device_data[category], dict), (
                        f"{worker}:{device}:{category} result should be a dict, "
                        f"got {type(device_data[category])}"
                    )
                assert set(device_data["vlans"]["interfaces"]) <= {device}

    def test_sync_all_dry_run_no_writes(self, nfclient):
        """dry_run=True must not write any sync-all stage changes."""
        self._sync(nfclient, self.SPINE_DEVICES, dry_run=True)

        nb = get_pynetbox(None)
        for device, serial in self.NETBOX_SERIALS.items():
            assert nb.dcim.devices.get(name=device).serial == serial
        # Interface must not exist
        intf = nb.dcim.interfaces.get(device="fn-ceos-sp-1", name=self.SPINE1_TEST_INTF)
        assert (
            intf is None
        ), f"dry_run wrote interface {self.SPINE1_TEST_INTF!r} to NetBox"
        # MAC must not exist
        macs = list(
            nb.dcim.mac_addresses.filter(
                device="fn-ceos-sp-1", mac_address=self.SPINE1_TEST_MAC
            )
        )
        assert not macs, f"dry_run wrote MAC {self.SPINE1_TEST_MAC!r} to NetBox"
        # IP must not exist
        ips = list(
            nb.ipam.ip_addresses.filter(
                address=self.SPINE1_TEST_IP, device="fn-ceos-sp-1"
            )
        )
        assert not ips, f"dry_run wrote IP {self.SPINE1_TEST_IP!r} to NetBox"

    # ------------------------------------------------------------------ #
    # Live run - creates in NetBox                                         #
    # ------------------------------------------------------------------ #

    def test_sync_all_updates_device_inventory_in_netbox(self, nfclient):
        """sync_all updates device serials through sync_device_inventory."""
        ret = self._sync(nfclient, self.SPINE_DEVICES)
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert not res["failed"], f"{worker} failed - {res.get('errors')}"
            for device in self.SPINE_DEVICES:
                inventory = res["result"][device]["inventory"]
                assert "chassis" in inventory["updated"]

        nb = get_pynetbox(None)
        for device, serial in self.LIVE_SERIALS.items():
            assert nb.dcim.devices.get(name=device).serial == serial

    def test_sync_all_creates_interfaces_in_netbox(self, nfclient):
        """After cleanup, sync_all must create TEST_SYNC interfaces in NetBox;
        Loopback10 must appear with correct description."""
        ret = self._sync(nfclient, self.SPINE_DEVICES)
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert not res["failed"], f"{worker} failed - {res.get('errors')}"
            for device in self.SPINE_DEVICES:
                assert device in res["result"], f"{worker} missing {device}"
                intf_data = res["result"][device].get("interfaces", {})
                assert intf_data.get(
                    "created"
                ), f"{worker}:{device} no interfaces created after cleanup"

        # Out-of-band: verify Loopback10 exists in NetBox with correct description
        nb_intf = self._get_nb_intf("fn-ceos-sp-1", self.SPINE1_TEST_INTF)
        assert (
            nb_intf is not None
        ), f"{self.SPINE1_TEST_INTF} not found in NetBox after sync_all"
        assert (
            nb_intf.description == "TEST_SYNC_LOOPBACK_IPV4"
        ), f"{self.SPINE1_TEST_INTF} description mismatch: got {nb_intf.description!r}"
        assert (
            nb_intf.type.value == "virtual"
        ), f"{self.SPINE1_TEST_INTF} type mismatch: got {nb_intf.type.value!r}"

    def test_sync_all_creates_mac_addresses_in_netbox(self, nfclient):
        """After cleanup, sync_all must create MAC addresses in NetBox;
        spine-1 MAC must appear on Ethernet9."""
        ret = self._sync(nfclient, self.SPINE_DEVICES)
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert not res["failed"], f"{worker} failed - {res.get('errors')}"
            mac_data = res["result"]["fn-ceos-sp-1"].get("mac_addresses", {})
            assert mac_data.get(
                "created"
            ), f"{worker}:fn-ceos-sp-1 no MACs created after cleanup"

        # Out-of-band: verify spine-1 MAC exists on Ethernet9
        macs = self._get_nb_macs("fn-ceos-sp-1", "Ethernet9")
        mac_addresses = [str(m.mac_address).lower() for m in macs]
        assert self.SPINE1_TEST_MAC in mac_addresses, (
            f"MAC {self.SPINE1_TEST_MAC!r} not found on fn-ceos-sp-1:Ethernet9 "
            f"after sync_all; found: {mac_addresses}"
        )

    def test_sync_all_creates_ip_addresses_in_netbox(self, nfclient):
        """After cleanup, sync_all must create IP addresses in NetBox;
        spine-1 Ethernet9 IP must appear."""
        ret = self._sync(nfclient, self.SPINE_DEVICES)
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert not res["failed"], f"{worker} failed - {res.get('errors')}"
            ip_data = res["result"]["fn-ceos-sp-1"].get("ip_addresses", {})
            assert ip_data.get(
                "created"
            ), f"{worker}:fn-ceos-sp-1 no IPs created after cleanup"

        # Out-of-band: verify spine-1 Ethernet9 IP exists in NetBox
        ips = self._get_nb_ips("fn-ceos-sp-1", "Ethernet9")
        ip_addresses = [str(ip.address) for ip in ips]
        assert self.SPINE1_TEST_IP in ip_addresses, (
            f"IP {self.SPINE1_TEST_IP!r} not found on fn-ceos-sp-1:Ethernet9 "
            f"after sync_all; found: {ip_addresses}"
        )

    # ------------------------------------------------------------------ #
    # Idempotency                                                          #
    # ------------------------------------------------------------------ #

    def test_sync_all_idempotent(self, nfclient):
        """Second sync_all run reports all managed data in sync."""
        # First run - creates everything
        first = self._sync(nfclient, self.SPINE_DEVICES)
        for worker, res in first.items():
            assert not res[
                "failed"
            ], f"First sync_all failed for {worker}: {res.get('errors')}"

        # Second run - must be fully in_sync for interfaces/MACs/IPs
        ret = self._sync(nfclient, self.SPINE_DEVICES)
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert not res["failed"], f"{worker} failed - {res.get('errors')}"
            for device in self.SPINE_DEVICES:
                intf_data = res["result"][device].get("interfaces", {})
                mac_data = res["result"][device].get("mac_addresses", {})
                ip_data = res["result"][device].get("ip_addresses", {})
                inventory_data = res["result"][device].get("inventory", {})
                assert not inventory_data.get("created")
                assert not inventory_data.get("updated")
                assert "chassis" in inventory_data.get("in_sync", [])
                assert not intf_data.get("created"), (
                    f"{worker}:{device} unexpected interface creates on 2nd run: "
                    f"{intf_data.get('created')}"
                )
                assert not mac_data.get("created"), (
                    f"{worker}:{device} unexpected MAC creates on 2nd run: "
                    f"{mac_data.get('created')}"
                )
                assert not ip_data.get("created"), (
                    f"{worker}:{device} unexpected IP creates on 2nd run: "
                    f"{ip_data.get('created')}"
                )
                assert intf_data.get(
                    "in_sync"
                ), f"{worker}:{device} no interfaces in_sync on 2nd run"
                assert mac_data.get(
                    "in_sync"
                ), f"{worker}:{device} no MACs in_sync on 2nd run"
                assert ip_data.get(
                    "in_sync"
                ), f"{worker}:{device} no IPs in_sync on 2nd run"

    # ------------------------------------------------------------------ #
    # Filtering                                                            #
    # ------------------------------------------------------------------ #

    def test_sync_all_with_nornir_filter(self, nfclient):
        """Devices resolved by name filter must include both FakeNOS spines."""
        ret = nfclient.run_job(
            "netbox",
            "sync_all",
            workers="any",
            kwargs={
                "FB": ["fn-ceos-sp-*"],
                "dry_run": True,
                "sync_kwargs": {"sync_vrfs": False},
            },
        )
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert not res["failed"], f"{worker} failed - {res.get('errors')}"
            for device in self.SPINE_DEVICES:
                assert (
                    device in res["result"]
                ), f"{worker} device {device!r} missing from filter-resolved result"

    @pytest.mark.parametrize(
        "sync_kwargs",
        [
            {
                "sync_vlans": False,
                "sync_device_prefixes": False,
                "sync_vrfs": False,
                "sync_device_interfaces": {"filter_by_name": "Loopback10"},
            },
            "nf://netbox/sync_all_kwargs.yaml",
        ],
    )
    def test_sync_all_accepts_inline_or_file_sync_kwargs(self, nfclient, sync_kwargs):
        """Per-task arguments can be supplied inline or through File Sharing."""
        ret = self._sync(
            nfclient,
            ["fn-ceos-sp-1"],
            dry_run=True,
            sync_kwargs=sync_kwargs,
        )
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert not res["failed"], f"{worker} failed - {res.get('errors')}"
            interfaces = res["result"]["fn-ceos-sp-1"]["interfaces"]
            interface_changes = (
                list(interfaces.get("create", []))
                + list(interfaces.get("update", {}))
                + list(interfaces.get("delete", []))
                + list(interfaces.get("in_sync", []))
            )
            assert interface_changes
            assert all(name == "Loopback10" for name in interface_changes)

    # ------------------------------------------------------------------ #
    # Error cases                                                          #
    # ------------------------------------------------------------------ #

    def test_sync_all_empty_devices(self, nfclient):
        """Empty devices list with no filters must fail with an error."""
        ret = nfclient.run_job(
            "netbox",
            "sync_all",
            workers="any",
            kwargs={"devices": []},
        )
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert res["failed"], f"{worker} should fail when no devices specified"
            assert res["errors"], f"{worker} should report errors"
