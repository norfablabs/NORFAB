import pprint

import pytest
from pydantic import ValidationError

from norfab.workers.netbox_worker.devices_tasks import (
    inventory_record_matches_filters,
)
from norfab.workers.netbox_worker.netbox_models import (
    DeviceInventoryRecords,
    InventoryPatternMap,
    SyncAllInput,
    SyncDeviceInventoryInput,
)

try:
    from tests.services.netbox.common import (
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
        get_pynetbox,
    )

pytestmark = [pytest.mark.netbox, pytest.mark.inventory]


@pytest.mark.task_get_nornir_inventory
class TestGetNornirInventory:
    nb_version = None
    device_data_keys = [
        "last_updated",
        "custom_fields",
        "tags",
        "device_type",
        "config_context",
        "tenant",
        "platform",
        "serial",
        "asset_tag",
        "site",
        "location",
        "rack",
        "status",
        "primary_ip4",
        "primary_ip6",
        "airflow",
        "position",
    ]

    def test_with_devices(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_nornir_inventory",
            workers="any",
            kwargs={"devices": ["ceos1", "fceos4", "nonexist"]},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert (
                "ceos1" in res["result"]["hosts"]
            ), f"{worker} returned no results for ceos1"
            assert (
                "fceos4" in res["result"]["hosts"]
            ), f"{worker} returned no results for fceos4"
            for device, data in res["result"]["hosts"].items():
                assert all(
                    k in data for k in ["data", "hostname", "platform"]
                ), f"{worker}:{device} not all data returned"

    def test_with_filters(self, nfclient):

        ret = nfclient.run_job(
            "netbox",
            "get_nornir_inventory",
            workers="any",
            kwargs={
                "filters": [
                    {"name": ["ceos1"]},
                    {"name__ic": "fceos"},
                ]
            },
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert (
                "ceos1" in res["result"]["hosts"]
            ), f"{worker} returned no results for ceos1"
            assert (
                "fceos4" in res["result"]["hosts"]
            ), f"{worker} returned no results for fceos4"
            for device, data in res["result"]["hosts"].items():
                assert all(
                    k in data for k in ["data", "hostname", "platform"]
                ), f"{worker}:{device} not all data returned"

    def test_source_platform_from_config_context(self, nfclient):
        # for iosxr1 platform data encoded in config context
        ret = nfclient.run_job(
            "netbox",
            "get_nornir_inventory",
            workers="any",
            kwargs={"devices": ["iosxr1"]},
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert (
                "iosxr1" in res["result"]["hosts"]
            ), f"{worker} returned no results for iosxr1"
            for device, data in res["result"]["hosts"].items():
                assert all(
                    k in data for k in ["data", "hostname", "platform"]
                ), f"{worker}:{device} not all data returned"

    def test_with_devices_nbdata_is_true(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_nornir_inventory",
            workers="any",
            kwargs={"devices": ["ceos1", "fceos4"], "nbdata": True},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert (
                "ceos1" in res["result"]["hosts"]
            ), f"{worker} returned no results for ceos1"
            assert (
                "fceos4" in res["result"]["hosts"]
            ), f"{worker} returned no results for fceos4"
            for device, data in res["result"]["hosts"].items():
                assert all(
                    k in data for k in ["data", "hostname", "platform"]
                ), f"{worker}:{device} not all device data returned"
                assert all(
                    k in data["data"] for k in self.device_data_keys
                ), f"{worker}:{device} not all nbdata returned"

    def test_with_devices_add_interfaces(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_nornir_inventory",
            workers="any",
            kwargs={"devices": ["ceos1", "fceos4"], "interfaces": True},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert (
                "ceos1" in res["result"]["hosts"]
            ), f"{worker} returned no results for ceos1"
            assert (
                "fceos4" in res["result"]["hosts"]
            ), f"{worker} returned no results for fceos4"
            for device, data in res["result"]["hosts"].items():
                assert data["data"][
                    "interfaces"
                ], f"{worker}:{device} no interfaces data returned"
                for intf_name, intf_data in data["data"]["interfaces"].items():
                    assert all(
                        k in intf_data
                        for k in [
                            "vrf",
                            "mode",
                            "description",
                        ]
                    ), f"{worker}:{device}:{intf_name} not all interface data returned"

    def test_with_devices_add_interfaces_with_ip_and_inventory(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_nornir_inventory",
            workers="any",
            kwargs={
                "devices": ["ceos1", "fceos4"],
                "interfaces": {"ip_addresses": True, "inventory_items": True},
            },
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert (
                "ceos1" in res["result"]["hosts"]
            ), f"{worker} returned no results for ceos1"
            assert (
                "fceos4" in res["result"]["hosts"]
            ), f"{worker} returned no results for fceos4"
            for device, data in res["result"]["hosts"].items():
                assert data["data"][
                    "interfaces"
                ], f"{worker}:{device} no interfaces data returned"
                for intf_name, intf_data in data["data"]["interfaces"].items():
                    assert (
                        "ip_addresses" in intf_data
                    ), f"{worker}:{device}:{intf_name} no ip addresses data returned"
                    assert (
                        "inventory_items" in intf_data
                    ), f"{worker}:{device}:{intf_name} no invetnory data returned"

    def test_with_devices_add_connections(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_nornir_inventory",
            workers="any",
            kwargs={"devices": ["fceos4", "fceos5"], "connections": True},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert (
                "fceos5" in res["result"]["hosts"]
            ), f"{worker} returned no results for fceos5"
            assert (
                "fceos4" in res["result"]["hosts"]
            ), f"{worker} returned no results for fceos4"
            for device, data in res["result"]["hosts"].items():
                assert data["data"][
                    "connections"
                ], f"{worker}:{device} no connections data returned"
                for intf_name, intf_data in data["data"]["connections"].items():
                    assert all(
                        k in intf_data
                        for k in [
                            "remote_interface",
                            "remote_device",
                        ]
                    ), f"{worker}:{device}:{intf_name} not all connection data returned"

    def test_with_devices_add_bgp_peerings(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_nornir_inventory",
            workers="any",
            kwargs={"devices": ["fceos4", "fceos5"], "bgp_peerings": True},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert (
                "fceos5" in res["result"]["hosts"]
            ), f"{worker} returned no results for fceos5"
            assert (
                "fceos4" in res["result"]["hosts"]
            ), f"{worker} returned no results for fceos4"
            for device, data in res["result"]["hosts"].items():
                assert data["data"][
                    "bgp_peerings"
                ], f"{worker}:{device} no bgp_peerings data returned"
                for peering, peering_data in data["data"]["bgp_peerings"].items():
                    assert all(
                        k in peering_data
                        for k in [
                            "id",
                            "name",
                        ]
                    ), f"{worker}:{device}:{peering} not all peerings data returned"


@pytest.mark.task_inventory_models
class TestInventoryPatternMap:
    def test_rejects_nested_inventory_map_wrapper(self):
        with pytest.raises(ValidationError):
            InventoryPatternMap.model_validate(
                {
                    "inventory_map": {
                        "module_types": {},
                        "module_bays": {},
                    }
                }
            )

    def test_rejects_condition_with_multiple_matchers(self):
        with pytest.raises(ValidationError):
            InventoryPatternMap.model_validate(
                {
                    "module_types": {
                        "Cisco": {
                            "TEST": [
                                {
                                    "glob": "TEST*",
                                    "regex": "^TEST$",
                                }
                            ]
                        }
                    }
                }
            )


@pytest.mark.task_inventory_models
class TestDeviceInventoryRecords:
    def test_validates_inventory_records(self):
        records = DeviceInventoryRecords.model_validate(
            [
                {
                    "description": None,
                    "slot": "module 0/RSP0/CPU0",
                    "module": "A9K-RSP440-TR",
                    "serial": "M9YXCZV9QF",
                }
            ]
        )

        assert records.model_dump() == [
            {
                "description": None,
                "slot": "module 0/RSP0/CPU0",
                "module": "A9K-RSP440-TR",
                "serial": "M9YXCZV9QF",
            }
        ]

    @pytest.mark.parametrize(
        "records",
        [
            {},
            [{"slot": "module 0/RSP0/CPU0"}],
            [
                {
                    "description": None,
                    "slot": "module 0/RSP0/CPU0",
                    "module": 123,
                    "serial": None,
                }
            ],
        ],
    )
    def test_rejects_invalid_inventory_records(self, records):
        with pytest.raises(ValidationError):
            DeviceInventoryRecords.model_validate(records)


@pytest.mark.task_inventory_models
class TestSyncDeviceInventoryInput:
    @pytest.mark.parametrize(
        "field",
        [
            "filter_by_module",
            "filter_by_slot",
            "ignore_modules",
            "ignore_slots",
        ],
    )
    def test_inventory_filters_require_pattern_lists(self, field):
        with pytest.raises(ValidationError):
            SyncDeviceInventoryInput.model_validate({field: "A9K-*"})


@pytest.mark.task_inventory_models
class TestSyncAllInput:
    def test_validates_inventory_arguments(self):
        data = SyncAllInput.model_validate(
            {
                "inventory-create-module-types": True,
                "inventory-create-module-bays": True,
                "inventory-map": "nf://netbox/inventory_map.yaml",
                "inventory-transform": "nf://netbox/inventory_transform.py",
                "inventory-filter-by-module": ["A9K-*"],
                "inventory-filter-by-slot": ["module 0/*"],
                "inventory-ignore-modules": ["SFP-*"],
                "inventory-ignore-slots": ["power-module *"],
                "message": "sync all changes",
            }
        )

        assert data.inventory_create_module_types is True
        assert data.inventory_create_module_bays is True
        assert data.inventory_filter_by_module == ["A9K-*"]
        assert data.inventory_ignore_slots == ["power-module *"]
        assert data.message == "sync all changes"

    def test_rejects_inventory_filter_string(self):
        with pytest.raises(ValidationError):
            SyncAllInput.model_validate({"inventory-filter-by-module": "A9K-*"})


@pytest.mark.task_inventory_models
class TestInventoryRecordFilters:
    MODULE = {
        "slot": "module 0/RSP0/CPU0",
        "inventory_type": "module",
        "module_type": "A9K-RSP440-TR",
    }

    def test_matches_module_and_slot_filters(self):
        assert inventory_record_matches_filters(
            self.MODULE,
            filter_by_module=["A9K-RSP*", "SFP-*"],
            filter_by_slot=["module 0/*"],
        )
        assert not inventory_record_matches_filters(
            self.MODULE,
            filter_by_module=["SFP-*"],
            filter_by_slot=["module 0/*"],
        )

    def test_ignore_filters_take_precedence(self):
        assert not inventory_record_matches_filters(
            self.MODULE,
            filter_by_module=["A9K-*"],
            ignore_slots=["module 0/RSP*"],
        )
        assert not inventory_record_matches_filters(
            self.MODULE,
            filter_by_slot=["module 0/*"],
            ignore_modules=["A9K-RSP*"],
        )

    def test_chassis_always_matches(self):
        assert inventory_record_matches_filters(
            {
                "slot": "chassis",
                "inventory_type": "chassis",
                "serial": "JCY98XR393D",
            },
            filter_by_module=["NO-MATCH"],
            filter_by_slot=["NO-MATCH"],
            ignore_modules=["*"],
            ignore_slots=["*"],
        )


@pytest.mark.task_sync_device_inventory
class TestSyncDeviceInventory:
    DEVICE = "fakenos-iosxr1"
    NETWORK = "netbox-inventory-sync"
    FAKENOS_INVENTORY = "nf://fakenos/netbox_inventory.yaml"
    NORNIR_WORKER = "nornir-worker-4"
    CHASSIS_SERIAL = "JCY98XR393D"
    RSP_SLOT = "module 0/RSP0/CPU0"
    RSP_SERIAL = "M9YXCZV9QF"
    RSP_DESCRIPTION = "ASR9K Route Switch Processor with 440G/slot Fabric and 6GB"
    OPTIC_SLOT = "module mau 0/1/0/0"
    OPTIC_SERIAL = "QMXQLS9GKS"
    PART_NUMBER_MATCH_MODEL = "TEST-RSP-PARTNUMBER-MATCH"
    PATTERN_RSP_MODEL = "TEST-PATTERN-RSP"
    PATTERN_OPTIC_MODEL = "TEST-PATTERN-OPTIC"
    PATTERN_FAN_MODEL = "TEST-PATTERN-FAN"
    PATTERN_RSP_SLOT = "mapped pattern RSP bay"
    PATTERN_OPTIC_SLOT = "mapped pattern optic bay"
    PATTERN_FAN_SLOT = "mapped pattern fan bay"
    TRANSFORM_RSP_MODEL = "TEST-TRANSFORMED-RSP"
    TRANSFORM_RSP_SLOT = "mapped transformer RSP bay"
    FILE_MAP_RSP_MODEL = "TEST-FILE-MAPPED-RSP"
    FILE_MAP_RSP_SLOT = "mapped file RSP bay"
    INVENTORY_MAP = "nf://netbox/inventory_map.yaml"
    INVALID_INVENTORY_MAP = "nf://netbox/inventory_map_invalid.yaml"
    INVENTORY_TRANSFORM = "nf://netbox/inventory_transform.py"
    MISSING_INVENTORY_TRANSFORM = "nf://netbox/inventory_transform_missing.py"
    RAISING_INVENTORY_TRANSFORM = "nf://netbox/inventory_transform_raises.py"
    INVALID_INVENTORY_TRANSFORM = "nf://netbox/inventory_transform_invalid.py"
    TEST_MODULE_MODELS = [
        "A9K-RSP440-TR",
        "ASR-9006-FAN-V2",
        "A9K-MOD160-TR",
        "A9K-MPA-8X10GE",
        "SFP-10G-LR",
        "PWR-3KW-AC-V2",
        "TEST-STALE-MOD",
        "TEST-FAN-MOD",
        PART_NUMBER_MATCH_MODEL,
        PATTERN_RSP_MODEL,
        PATTERN_OPTIC_MODEL,
        PATTERN_FAN_MODEL,
        TRANSFORM_RSP_MODEL,
        FILE_MAP_RSP_MODEL,
    ]

    @pytest.fixture(autouse=True)
    def sync_inventory_fixture(self, nfclient):
        self._ensure_netbox_device()
        self._cleanup_netbox()
        self._ensure_netbox_device()
        self._start_fakenos_network(nfclient)
        yield
        self._stop_fakenos_network(nfclient)
        self._cleanup_netbox()

    @staticmethod
    def _value(record, *path):
        value = record
        for key in path:
            if value is None:
                return None
            if isinstance(value, dict):
                value = value.get(key)
            else:
                value = getattr(value, key, None)
        return value

    @classmethod
    def _sync(cls, nfclient, **kwargs):
        return nfclient.run_job(
            "netbox",
            "sync_device_inventory",
            workers="any",
            kwargs={"devices": [cls.DEVICE], "timeout": 120, **kwargs},
            timeout=180,
        )

    @classmethod
    def _start_fakenos_network(cls, nfclient):
        nfclient.run_job("fakenos", "stop", kwargs={"network": cls.NETWORK})
        started = nfclient.run_job(
            "fakenos",
            "start",
            kwargs={"network": cls.NETWORK, "inventory": cls.FAKENOS_INVENTORY},
        )
        for worker, res in started.items():
            assert not res["failed"], f"{worker} failed to start FakeNOS: {res}"

        inventory = nfclient.run_job(
            "fakenos",
            "get_nornir_inventory",
            kwargs={"network": cls.NETWORK},
        )
        hosts = {}
        for worker, res in inventory.items():
            assert not res["failed"], f"{worker} failed to export Nornir inventory"
            hosts.update(res["result"]["hosts"])
        assert cls.DEVICE in hosts, f"{cls.DEVICE} missing from FakeNOS inventory"
        hosts[cls.DEVICE]["platform"] = "cisco_xr"

        runtime = nfclient.run_job(
            "nornir",
            "runtime_inventory",
            workers=[cls.NORNIR_WORKER],
            kwargs={"action": "create_host", "name": cls.DEVICE, **hosts[cls.DEVICE]},
        )
        for worker, res in runtime.items():
            assert not res["failed"], f"{worker} failed to load FakeNOS host: {res}"

    @classmethod
    def _stop_fakenos_network(cls, nfclient):
        nfclient.run_job(
            "nornir",
            "runtime_inventory",
            workers=[cls.NORNIR_WORKER],
            kwargs={"action": "delete_host", "name": cls.DEVICE},
        )
        nfclient.run_job("fakenos", "stop", kwargs={"network": cls.NETWORK})

    @classmethod
    def _ensure_netbox_device(cls):
        nb = get_pynetbox(None)
        device = nb.dcim.devices.get(name=cls.DEVICE)
        if device:
            device.update({"serial": "OLD-FAKENOS-CHASSIS"})
            return

        device_type = nb.dcim.device_types.get(slug="xvr9000")
        role = nb.dcim.device_roles.get(name="VirtualRouter")
        tenant = nb.tenancy.tenants.get(name="SALTNORNIR")
        site = nb.dcim.sites.get(name="SALTNORNIR-LAB")
        rack = nb.dcim.racks.get(name="R201")
        platform = nb.dcim.platforms.get(name="cisco_xr")
        nb.dcim.devices.create(
            name=cls.DEVICE,
            device_type=device_type.id,
            role=role.id,
            tenant=tenant.id,
            site=site.id,
            rack=rack.id,
            position=32,
            face="front",
            platform=platform.id,
            serial="OLD-FAKENOS-CHASSIS",
        )

    @classmethod
    def _cleanup_netbox(cls):
        nb = get_pynetbox(None)
        for module in list(nb.dcim.modules.filter(device=cls.DEVICE)):
            try:
                module.delete()
            except Exception:
                pass

        for module_bay in list(nb.dcim.module_bays.filter(device=cls.DEVICE)):
            try:
                module_bay.delete()
            except Exception:
                pass

        for model in cls.TEST_MODULE_MODELS:
            for module_type in list(nb.dcim.module_types.filter(model=model)):
                try:
                    if cls._value(module_type, "manufacturer", "name") == "Cisco":
                        module_type.delete()
                except Exception:
                    pass

        device = nb.dcim.devices.get(name=cls.DEVICE)
        if device:
            device.update({"serial": "OLD-FAKENOS-CHASSIS"})

    @classmethod
    def _ensure_module_type(cls, model):
        nb = get_pynetbox(None)
        for module_type in nb.dcim.module_types.filter(model=model):
            if cls._value(module_type, "manufacturer", "name") == "Cisco":
                return module_type
        manufacturer = nb.dcim.manufacturers.get(name="Cisco")
        return nb.dcim.module_types.create(
            manufacturer=manufacturer.id,
            model=model,
            part_number=model,
        )

    @classmethod
    def _ensure_module_bay(cls, slot):
        nb = get_pynetbox(None)
        module_bay = nb.dcim.module_bays.get(device=cls.DEVICE, name=slot)
        if module_bay:
            return module_bay
        device = nb.dcim.devices.get(name=cls.DEVICE)
        return nb.dcim.module_bays.create(device=device.id, name=slot, label=slot)

    @classmethod
    def _ensure_module(cls, slot, model, serial, description=""):
        nb = get_pynetbox(None)
        module_bay = cls._ensure_module_bay(slot)
        module_type = cls._ensure_module_type(model)
        device = nb.dcim.devices.get(name=cls.DEVICE)
        for module in list(nb.dcim.modules.filter(device=cls.DEVICE)):
            if cls._value(module, "module_bay", "name") == slot:
                module.delete()
        return nb.dcim.modules.create(
            device=device.id,
            module_bay=module_bay.id,
            module_type=module_type.id,
            status="active",
            serial=serial,
            description=description,
        )

    @classmethod
    def _get_module(cls, slot):
        nb = get_pynetbox(None)
        for module in nb.dcim.modules.filter(device=cls.DEVICE):
            if cls._value(module, "module_bay", "name") == slot:
                return module
        return None

    @staticmethod
    def _unexpected_inventory_errors(errors):
        return [error for error in errors if "ignored inventory record" not in error]

    @staticmethod
    def _result_text(result):
        return "\n".join(result["errors"] + result["messages"])

    def test_sync_device_inventory_dry_run_reports_raw_diff(self, nfclient):
        ret = self._sync(nfclient, dry_run=True)
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert not res["failed"], f"{worker} failed - {res.get('errors')}"
            assert res["dry_run"] is True
            inventory = res["result"][self.DEVICE]
            assert "chassis" in inventory["update"]
            assert (
                inventory["update"]["chassis"]["serial"]["new_value"]
                == self.CHASSIS_SERIAL
            )
            assert self.RSP_SLOT in inventory["create"]

    def test_sync_device_inventory_creates_modules_and_updates_chassis_serial(
        self, nfclient
    ):
        ret = self._sync(
            nfclient,
            create_module_bays=True,
            create_module_types=True,
        )
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert not res["failed"], f"{worker} failed - {res.get('errors')}"
            assert not self._unexpected_inventory_errors(res["errors"])
            inventory = res["result"][self.DEVICE]
            assert set(inventory) == {"created", "updated", "deleted", "in_sync"}
            assert "chassis" in inventory["updated"]
            assert self.RSP_SLOT in inventory["created"]
            assert self.OPTIC_SLOT in inventory["created"]

        nb = get_pynetbox(None)
        device = nb.dcim.devices.get(name=self.DEVICE)
        assert device.serial == self.CHASSIS_SERIAL
        rsp_module = self._get_module(self.RSP_SLOT)
        optic_module = self._get_module(self.OPTIC_SLOT)
        assert rsp_module is not None
        assert rsp_module.serial == self.RSP_SERIAL
        assert optic_module is not None
        assert optic_module.serial == self.OPTIC_SERIAL

    def test_sync_device_inventory_reports_missing_module_bays(self, nfclient):
        ret = self._sync(
            nfclient,
            create_module_bays=False,
            create_module_types=True,
        )
        pprint.pprint(ret, width=200)

        expected_error = f"{self.DEVICE}:{self.RSP_SLOT} - module bay not found"
        for worker, res in ret.items():
            assert not res["failed"], f"{worker} failed - {res.get('errors')}"
            assert res["errors"].count(expected_error) == 1
            inventory = res["result"][self.DEVICE]
            assert self.RSP_SLOT not in inventory["created"]

        assert self._get_module(self.RSP_SLOT) is None

    def test_sync_device_inventory_matches_module_type_by_part_number(self, nfclient):
        nb = get_pynetbox(None)
        manufacturer = nb.dcim.manufacturers.get(name="Cisco")
        nb.dcim.module_types.create(
            manufacturer=manufacturer.id,
            model=self.PART_NUMBER_MATCH_MODEL,
            part_number="A9K-RSP440-TR",
        )

        ret = self._sync(
            nfclient,
            create_module_bays=True,
            create_module_types=False,
        )
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert not res["failed"], f"{worker} failed - {res.get('errors')}"
            inventory = res["result"][self.DEVICE]
            assert self.RSP_SLOT in inventory["created"]

            missing_rsp_type = (
                f"{self.DEVICE}:{self.RSP_SLOT} - module type 'Cisco "
                "A9K-RSP440-TR' not found"
            )
            assert missing_rsp_type not in res["errors"]

        rsp_module = self._get_module(self.RSP_SLOT)
        assert rsp_module is not None
        assert self._value(rsp_module, "module_type", "model") == (
            self.PART_NUMBER_MATCH_MODEL
        )

    def test_sync_device_inventory_pattern_mapping(self, nfclient):
        nb = get_pynetbox(None)
        device = nb.dcim.devices.get(name=self.DEVICE)
        manufacturer = device.device_type.manufacturer.name
        device_type = device.device_type.model
        inventory_map = {
            "module_types": {
                manufacturer: {
                    self.PATTERN_RSP_MODEL: [{"glob": "A9K-RSP440-*"}],
                    self.PATTERN_OPTIC_MODEL: [{"regex": "^SFP-10G-LR$"}],
                    self.PATTERN_FAN_MODEL: [{"eval": "value == 'ASR-9006-FAN-V2'"}],
                }
            },
            "module_bays": {
                manufacturer: {
                    device_type: {
                        self.PATTERN_RSP_SLOT: [{"glob": "module 0/RSP0/*"}],
                        self.PATTERN_OPTIC_SLOT: [{"regex": "^module mau 0/1/0/0$"}],
                        self.PATTERN_FAN_SLOT: [
                            {"eval": "value == 'fantray 0/FT0/SP'"}
                        ],
                    }
                }
            },
        }

        ret = self._sync(
            nfclient,
            create_module_bays=True,
            create_module_types=True,
            inventory_map=inventory_map,
        )
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert not res["failed"], f"{worker} failed - {res.get('errors')}"
            assert not self._unexpected_inventory_errors(res["errors"])
            created = res["result"][self.DEVICE]["created"]
            assert self.PATTERN_RSP_SLOT in created
            assert self.PATTERN_OPTIC_SLOT in created
            assert self.PATTERN_FAN_SLOT in created

        expected_modules = {
            self.PATTERN_RSP_SLOT: self.PATTERN_RSP_MODEL,
            self.PATTERN_OPTIC_SLOT: self.PATTERN_OPTIC_MODEL,
            self.PATTERN_FAN_SLOT: self.PATTERN_FAN_MODEL,
        }
        for slot, model in expected_modules.items():
            module = self._get_module(slot)
            assert module is not None
            assert self._value(module, "module_type", "model") == model

        assert self._get_module(self.RSP_SLOT) is None
        assert self._get_module(self.OPTIC_SLOT) is None

    def test_sync_device_inventory_filters_normalized_module_and_slot(self, nfclient):
        nb = get_pynetbox(None)
        device = nb.dcim.devices.get(name=self.DEVICE)
        manufacturer = device.device_type.manufacturer.name
        device_type = device.device_type.model
        inventory_map = {
            "module_types": {
                manufacturer: {
                    self.PATTERN_RSP_MODEL: [{"glob": "A9K-RSP440-*"}],
                    self.PATTERN_OPTIC_MODEL: [{"glob": "SFP-10G-LR"}],
                }
            },
            "module_bays": {
                manufacturer: {
                    device_type: {
                        self.PATTERN_RSP_SLOT: [{"glob": "module 0/RSP0/*"}],
                        self.PATTERN_OPTIC_SLOT: [{"glob": "module mau 0/1/0/0"}],
                    }
                }
            },
        }

        ret = self._sync(
            nfclient,
            dry_run=True,
            inventory_map=inventory_map,
            filter_by_module=["TEST-PATTERN-*"],
            filter_by_slot=["mapped pattern RSP *"],
        )
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert not res["failed"], f"{worker} failed - {res.get('errors')}"
            inventory = res["result"][self.DEVICE]
            assert self.PATTERN_RSP_SLOT in inventory["create"]
            assert self.PATTERN_OPTIC_SLOT not in inventory["create"]
            assert self.RSP_SLOT not in inventory["create"]
            assert self.OPTIC_SLOT not in inventory["create"]

    def test_sync_device_inventory_ignores_modules_and_slots(self, nfclient):
        self._ensure_module(
            self.OPTIC_SLOT,
            "SFP-10G-LR",
            serial=self.OPTIC_SERIAL,
        )

        ret = self._sync(
            nfclient,
            dry_run=True,
            process_deletions=True,
            ignore_modules=["SFP-*"],
            ignore_slots=["fantray *"],
        )
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert not res["failed"], f"{worker} failed - {res.get('errors')}"
            inventory = res["result"][self.DEVICE]
            assert self.RSP_SLOT in inventory["create"]
            assert self.OPTIC_SLOT not in inventory["create"]
            assert self.OPTIC_SLOT not in inventory["update"]
            assert self.OPTIC_SLOT not in inventory["delete"]
            assert "fantray 0/FT0/SP" not in inventory["create"]

    def test_sync_device_inventory_loads_mapping_from_file(self, nfclient):
        ret = self._sync(
            nfclient,
            create_module_bays=True,
            create_module_types=True,
            inventory_map=self.INVENTORY_MAP,
        )
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert not res["failed"], f"{worker} failed - {res.get('errors')}"
            assert not self._unexpected_inventory_errors(res["errors"])
            assert self.FILE_MAP_RSP_SLOT in res["result"][self.DEVICE]["created"]

        module = self._get_module(self.FILE_MAP_RSP_SLOT)
        assert module is not None
        assert self._value(module, "module_type", "model") == self.FILE_MAP_RSP_MODEL
        assert self._get_module(self.RSP_SLOT) is None

    def test_sync_device_inventory_rejects_invalid_mapping_file(self, nfclient):
        ret = self._sync(nfclient, inventory_map=self.INVALID_INVENTORY_MAP)
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert res["failed"], f"{worker} accepted invalid inventory mapping"
            assert "exactly one of glob, regex, or eval is required" in (
                self._result_text(res)
            )

    def test_sync_device_inventory_python_transformer(self, nfclient):
        ret = self._sync(
            nfclient,
            create_module_bays=True,
            create_module_types=True,
            inventory_transform=self.INVENTORY_TRANSFORM,
        )
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert not res["failed"], f"{worker} failed - {res.get('errors')}"
            assert not self._unexpected_inventory_errors(res["errors"])
            created = res["result"][self.DEVICE]["created"]
            assert self.TRANSFORM_RSP_SLOT in created

        module = self._get_module(self.TRANSFORM_RSP_SLOT)
        assert module is not None
        assert self._value(module, "module_type", "model") == (self.TRANSFORM_RSP_MODEL)
        assert self._get_module(self.RSP_SLOT) is None

    def test_sync_device_inventory_rejects_missing_transform_function(self, nfclient):
        ret = self._sync(
            nfclient,
            inventory_transform=self.MISSING_INVENTORY_TRANSFORM,
        )
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert res["failed"], f"{worker} accepted transformer without transform"
            assert "KeyError: 'transform'" in self._result_text(res)

    def test_sync_device_inventory_handles_transformer_exception(self, nfclient):
        ret = self._sync(
            nfclient,
            inventory_transform=self.RAISING_INVENTORY_TRANSFORM,
        )
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert res["failed"], f"{worker} did not fail after transformer exception"
            result_text = self._result_text(res)
            assert "inventory transformer failed" in result_text
            assert f"{self.DEVICE} transformer failure" in result_text

    def test_sync_device_inventory_rejects_invalid_transformer_data(self, nfclient):
        ret = self._sync(
            nfclient,
            inventory_transform=self.INVALID_INVENTORY_TRANSFORM,
        )
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert res["failed"], f"{worker} accepted invalid transformer data"
            result_text = self._result_text(res)
            assert "inventory transformer failed" in result_text
            assert "DeviceInventoryRecords" in result_text
            assert "Field required" in result_text

    def test_sync_device_inventory_second_run_is_in_sync(self, nfclient):
        first = self._sync(
            nfclient,
            create_module_bays=True,
            create_module_types=True,
        )
        for worker, res in first.items():
            assert not res["failed"], f"{worker} first sync failed - {res}"

        ret = self._sync(
            nfclient,
            create_module_bays=True,
            create_module_types=True,
        )
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert not res["failed"], f"{worker} failed - {res.get('errors')}"
            assert not self._unexpected_inventory_errors(res["errors"])
            inventory = res["result"][self.DEVICE]
            assert not inventory["created"]
            assert not inventory["updated"]
            assert "chassis" in inventory["in_sync"]
            assert self.RSP_SLOT in inventory["in_sync"]
            assert self.OPTIC_SLOT in inventory["in_sync"]

    def test_sync_device_inventory_updates_existing_module(self, nfclient):
        self._ensure_module(
            self.RSP_SLOT,
            "A9K-RSP440-TR",
            serial="OLD-RSP-SERIAL",
            description="old description",
        )

        ret = self._sync(
            nfclient,
            create_module_bays=True,
            create_module_types=True,
        )
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert not res["failed"], f"{worker} failed - {res.get('errors')}"
            assert not self._unexpected_inventory_errors(res["errors"])
            assert self.RSP_SLOT in res["result"][self.DEVICE]["updated"]

        module = self._get_module(self.RSP_SLOT)
        assert module.serial == self.RSP_SERIAL
        assert module.description == self.RSP_DESCRIPTION

    def test_sync_device_inventory_deletion_controls(self, nfclient):
        stale_slot = "module stale"
        self._ensure_module(stale_slot, "TEST-STALE-MOD", serial="STALE123")

        first = self._sync(
            nfclient,
            create_module_bays=True,
            create_module_types=True,
        )
        for worker, res in first.items():
            assert not res["failed"], f"{worker} failed - {res.get('errors')}"
            assert not self._unexpected_inventory_errors(res["errors"])
            assert stale_slot in res["diff"][self.DEVICE]["delete"]
            assert stale_slot not in res["result"][self.DEVICE]["deleted"]
        assert self._get_module(stale_slot) is not None

        ret = self._sync(
            nfclient,
            create_module_bays=True,
            create_module_types=True,
            process_deletions=True,
        )
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert not res["failed"], f"{worker} failed - {res.get('errors')}"
            assert not self._unexpected_inventory_errors(res["errors"])
            assert stale_slot in res["result"][self.DEVICE]["deleted"]
        assert self._get_module(stale_slot) is None

    def test_sync_device_inventory_incomplete_live_record_suppresses_delete(
        self, nfclient
    ):
        fan_slot = "fan0 0/FT0/SP"
        self._ensure_module(fan_slot, "TEST-FAN-MOD", serial="FAN123")

        ret = self._sync(
            nfclient,
            create_module_bays=True,
            create_module_types=True,
            process_deletions=True,
        )
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert not res["failed"], f"{worker} failed - {res.get('errors')}"
            assert not self._unexpected_inventory_errors(res["errors"])
            inventory = res["result"][self.DEVICE]
            assert fan_slot not in inventory["deleted"]
            expected_error = f"{self.DEVICE}:{fan_slot} - ignored inventory record"
            assert any(error.startswith(expected_error) for error in res["errors"])
        assert self._get_module(fan_slot) is not None
