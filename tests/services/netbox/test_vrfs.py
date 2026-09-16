from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest

from norfab.workers.netbox_worker.netbox_worker import NetboxWorker
from norfab.workers.netbox_worker.vrf_tasks import NetboxVrfsTasks
from tests.services.netbox.common import get_pynetbox

pytestmark = [
    pytest.mark.netbox,
    pytest.mark.netbox_sync_vrfs,
]


class TestSyncVrfs:
    DEVICE_1 = "fn-ceos-lf-1"
    DEVICE_2 = "fn-ceos-lf-2"
    VRF_NAMES = {"CONTROL_PLANE", "TENANT_A", "TENANT_B"}
    CONTROL_PLANE_INTERFACES = {"Ethernet1.101", "Ethernet2.101", "Loopback101"}
    ROUTE_TARGET_NAMES = {
        "65000:101",
        "65000:201",
        "65000:202",
        "65000:301",
        "65000:302",
        "65000:303",
        "65000:999",
    }
    DEVICE_1_ROUTE_TARGETS = {
        "65000:101",
        "65000:201",
        "65000:202",
        "65000:301",
        "65000:302",
    }
    ROUTING_POLICY_NAMES = {
        "CONTROL_PLANE_IMPORT",
        "CONTROL_PLANE_EXPORT",
        "TENANT_A_IMPORT",
        "TENANT_A_EXPORT",
        "TENANT_B_IMPORT",
        "TENANT_B_EXPORT",
        "TENANT_A_EXTRA",
        "TENANT_A_IPV6_IMPORT_TEST",
        "TENANT_A_IPV6_EXPORT_TEST",
    }
    DEVICE_1_ROUTING_POLICIES = ROUTING_POLICY_NAMES - {
        "TENANT_A_EXTRA",
        "TENANT_A_IPV6_IMPORT_TEST",
        "TENANT_A_IPV6_EXPORT_TEST",
    }

    @pytest.fixture(autouse=True)
    def cleanup_test_vrfs(self, nfclient: Any) -> Iterator[None]:
        self.nb = get_pynetbox(nfclient)
        created_custom_fields = []
        for field_name in (
            "devices",
            "vrf_devices",
            "rpl_import_ipv4",
            "rpl_import_ipv6",
            "rpl_export_ipv4",
            "rpl_export_ipv6",
            "alternate_rpl_import_ipv4",
        ):
            if self.nb.extras.custom_fields.get(name=field_name) is not None:
                continue
            payload = {
                "name": field_name,
                "label": field_name.replace("_", " ").title(),
                "type": "multiobject",
                "object_types": ["ipam.vrf"],
                "related_object_type": (
                    "dcim.device"
                    if field_name in ("devices", "vrf_devices")
                    else "netbox_bgp.routingpolicy"
                ),
            }
            if float(".".join(self.nb.version.split(".")[:2])) < 4.0:
                payload["content_types"] = payload.pop("object_types")
                payload["object_type"] = payload.pop("related_object_type")
            created_custom_fields.append(self.nb.extras.custom_fields.create(**payload))
        self._delete_test_data()
        yield
        self._delete_test_data()
        for custom_field in created_custom_fields:
            custom_field.delete()

    def _delete_test_data(self) -> None:
        for name in self.VRF_NAMES:
            for vrf in list(self.nb.ipam.vrfs.filter(name=name)):
                vrf.delete()
        for name in self.ROUTE_TARGET_NAMES:
            for route_target in list(self.nb.ipam.route_targets.filter(name=name)):
                route_target.delete()
        for name in self.ROUTING_POLICY_NAMES:
            for policy in list(self.nb.plugins.bgp.routing_policy.filter(name=name)):
                policy.delete()

    @staticmethod
    def _sync(nfclient: Any, devices: list[str], **kwargs: object) -> dict:
        return nfclient.run_job(
            "netbox",
            "sync_vrfs",
            workers="any",
            kwargs={"devices": devices, **kwargs},
        )

    @staticmethod
    def _successful_results(response: dict) -> list[dict]:
        assert response
        results = []
        for worker, result in response.items():
            assert result["failed"] is False, f"{worker} failed: {result}"
            assert result["errors"] == [], f"{worker} returned errors: {result}"
            results.append(result)
        return results

    @staticmethod
    def _custom_field_device_ids(vrf: Any, field_name: str) -> set[int]:
        values = (vrf.custom_fields or {}).get(field_name) or []
        return {
            int(
                value.get("id")
                if isinstance(value, dict)
                else getattr(value, "id", value)
            )
            for value in values
        }

    def _custom_field_policy_names(self, vrf: Any, field_name: str) -> set[str]:
        values = (vrf.custom_fields or {}).get(field_name) or []
        return {
            self.nb.plugins.bgp.routing_policy.get(id=value["id"]).name
            for value in values
        }

    def _stub_worker(
        self, records: list[dict], plugin_installed: bool
    ) -> SimpleNamespace:
        return SimpleNamespace(
            name="netbox-test",
            default_instance="test",
            is_url=lambda value: False,
            _get_pynetbox=lambda *args, **kwargs: self.nb,
            has_plugin=lambda *args, **kwargs: plugin_installed,
            bulk_filter=lambda endpoint, **kwargs: list(endpoint.filter(**kwargs)),
            make_diff=lambda source, target: NetboxWorker.make_diff(
                None, source, target
            ),
            client=SimpleNamespace(
                run_job=lambda *args, **kwargs: {
                    "nornir-test": {
                        "failed": False,
                        "result": {self.DEVICE_1: records},
                    }
                }
            ),
        )

    @staticmethod
    def _stub_job() -> SimpleNamespace:
        return SimpleNamespace(event=lambda *args, **kwargs: None)

    @staticmethod
    def _ipv6_record() -> dict:
        return {
            "name": "TENANT_A",
            "description": "Tenant A services",
            "interfaces": [],
            "address_families": {
                "ipv4": {
                    "rt_import": [],
                    "rt_export": [],
                    "route_policy_import": None,
                    "route_policy_export": None,
                },
                "ipv6": {
                    "rt_import": [],
                    "rt_export": [],
                    "route_policy_import": "TENANT_A_IPV6_IMPORT_TEST",
                    "route_policy_export": "TENANT_A_IPV6_EXPORT_TEST",
                },
            },
        }

    def test_ipv6_routing_policies_from_getter(self, nfclient: Any) -> None:
        worker = self._stub_worker([self._ipv6_record()], plugin_installed=True)
        preview = NetboxVrfsTasks.sync_vrfs(
            worker, self._stub_job(), devices=[self.DEVICE_1], dry_run=True
        )
        assert set(preview.result["routing_policies"]["create"]) == {
            "TENANT_A_IPV6_IMPORT_TEST",
            "TENANT_A_IPV6_EXPORT_TEST",
        }
        changes = preview.result["vrfs"]["create"]
        assert changes == ["TENANT_A"]
        assert (
            self.nb.plugins.bgp.routing_policy.get(name="TENANT_A_IPV6_IMPORT_TEST")
            is None
        )

        applied = NetboxVrfsTasks.sync_vrfs(
            worker, self._stub_job(), devices=[self.DEVICE_1]
        )
        assert set(applied.result["routing_policies"]["created"]) == {
            "TENANT_A_IPV6_IMPORT_TEST",
            "TENANT_A_IPV6_EXPORT_TEST",
        }
        tenant_a = self.nb.ipam.vrfs.get(name="TENANT_A")
        assert self._custom_field_policy_names(tenant_a, "rpl_import_ipv6") == {
            "TENANT_A_IPV6_IMPORT_TEST"
        }
        assert self._custom_field_policy_names(tenant_a, "rpl_export_ipv6") == {
            "TENANT_A_IPV6_EXPORT_TEST"
        }

    def test_missing_bgp_plugin_ignores_policies(self, nfclient: Any) -> None:
        worker = self._stub_worker([self._ipv6_record()], plugin_installed=False)
        preview = NetboxVrfsTasks.sync_vrfs(
            worker, self._stub_job(), devices=[self.DEVICE_1], dry_run=True
        )
        assert preview.errors == []
        assert preview.result["vrfs"]["create"] == ["TENANT_A"]
        assert preview.result["routing_policies"] == {
            "create": [],
            "update": {},
            "delete": [],
            "in_sync": [],
        }

    def test_preserve_description_modes(self, nfclient: Any) -> None:
        self.nb.ipam.vrfs.create(name="TENANT_B", description="NetBox empty-live")

        self._successful_results(self._sync(nfclient, [self.DEVICE_1]))
        assert self.nb.ipam.vrfs.get(name="TENANT_B").description == (
            "NetBox empty-live"
        )

        self._successful_results(
            self._sync(nfclient, [self.DEVICE_1], preserve_description=False)
        )
        assert self.nb.ipam.vrfs.get(name="TENANT_B").description == ""

        tenant_a = self.nb.ipam.vrfs.get(name="TENANT_A")
        tenant_a.description = "NetBox curated"
        tenant_a.save()
        self._successful_results(
            self._sync(nfclient, [self.DEVICE_1], preserve_description=True)
        )
        assert self.nb.ipam.vrfs.get(name="TENANT_A").description == "NetBox curated"

        self._successful_results(
            self._sync(nfclient, [self.DEVICE_1], preserve_description=False)
        )
        assert self.nb.ipam.vrfs.get(name="TENANT_A").description == (
            "Tenant A services"
        )

    def test_dry_run_create_apply_and_exact_match(self, nfclient: Any) -> None:
        dry_run = self._sync(nfclient, [self.DEVICE_1], dry_run=True)
        for result in self._successful_results(dry_run):
            assert result["result"]["vrfs"]["create"] == sorted(self.VRF_NAMES)
            assert result["result"]["vrfs"]["update"] == {}
            assert result["result"]["vrfs"]["delete"] == []
            assert (
                set(result["result"]["route_targets"]["create"])
                == self.DEVICE_1_ROUTE_TARGETS
            )
            assert result["result"]["route_targets"]["update"] == {}
            assert result["result"]["route_targets"]["delete"] == []
            assert result["result"]["route_targets"]["in_sync"] == []
            assert (
                set(result["result"]["routing_policies"]["create"])
                == self.DEVICE_1_ROUTING_POLICIES
            )
            assert result["result"]["routing_policies"]["update"] == {}
            assert result["result"]["routing_policies"]["delete"] == []
            assert result["result"]["routing_policies"]["in_sync"] == []
            assert (
                set(result["result"]["interfaces"][self.DEVICE_1]["update"])
                == self.CONTROL_PLANE_INTERFACES
            )
        assert self.nb.ipam.vrfs.get(name="TENANT_A") is None
        assert self.nb.ipam.route_targets.get(name="65000:201") is None
        assert self.nb.plugins.bgp.routing_policy.get(name="TENANT_A_IMPORT") is None

        first_sync = self._sync(nfclient, [self.DEVICE_1], batch_size=1)
        for result in self._successful_results(first_sync):
            assert result["result"]["vrfs"]["created"] == sorted(self.VRF_NAMES)
            assert (
                set(result["result"]["route_targets"]["created"])
                == self.DEVICE_1_ROUTE_TARGETS
            )
            assert (
                set(result["diff"]["route_targets"]["create"])
                == self.DEVICE_1_ROUTE_TARGETS
            )
            assert result["result"]["route_targets"]["updated"] == []
            assert result["result"]["route_targets"]["deleted"] == []
            assert result["result"]["route_targets"]["in_sync"] == []
            assert (
                set(result["result"]["routing_policies"]["created"])
                == self.DEVICE_1_ROUTING_POLICIES
            )
            assert (
                set(result["diff"]["routing_policies"]["create"])
                == self.DEVICE_1_ROUTING_POLICIES
            )
            assert result["result"]["routing_policies"]["updated"] == []
            assert result["result"]["routing_policies"]["deleted"] == []
            assert result["result"]["routing_policies"]["in_sync"] == []
            assert (
                set(result["result"]["interfaces"][self.DEVICE_1]["updated"])
                == self.CONTROL_PLANE_INTERFACES
            )

        tenant_a = self.nb.ipam.vrfs.get(name="TENANT_A")
        assert tenant_a.description == "Tenant A services"
        assert sorted(target.name for target in tenant_a.import_targets) == [
            "65000:201",
            "65000:301",
        ]
        assert sorted(target.name for target in tenant_a.export_targets) == [
            "65000:201",
            "65000:302",
        ]
        device = self.nb.dcim.devices.get(name=self.DEVICE_1)
        assert self._custom_field_device_ids(tenant_a, "devices") == {device.id}
        assert self._custom_field_policy_names(tenant_a, "rpl_import_ipv4") == {
            "TENANT_A_IMPORT"
        }
        assert self._custom_field_policy_names(tenant_a, "rpl_export_ipv4") == {
            "TENANT_A_EXPORT"
        }
        assert self._custom_field_policy_names(tenant_a, "rpl_import_ipv6") == set()
        assert self._custom_field_policy_names(tenant_a, "rpl_export_ipv6") == set()

        second_sync = self._sync(nfclient, [self.DEVICE_1])
        for result in self._successful_results(second_sync):
            actions = result["result"]["vrfs"]
            assert actions["created"] == []
            assert actions["updated"] == []
            assert actions["in_sync"] == sorted(self.VRF_NAMES)
            assert result["result"]["route_targets"] == {
                "created": [],
                "updated": [],
                "deleted": [],
                "in_sync": [],
            }
            assert result["result"]["routing_policies"] == {
                "created": [],
                "updated": [],
                "deleted": [],
                "in_sync": [],
            }
            assert (
                set(result["result"]["interfaces"][self.DEVICE_1]["in_sync"])
                == self.CONTROL_PLANE_INTERFACES
            )

    def test_extends_route_targets_and_updates_description(self, nfclient: Any) -> None:
        existing_target = self.nb.ipam.route_targets.create(name="65000:999")
        self.nb.ipam.route_targets.create(name="65000:201")
        existing_device = self.nb.dcim.devices.get(name=self.DEVICE_2)
        self.nb.ipam.vrfs.create(
            name="TENANT_A",
            description="stale description",
            import_targets=[existing_target.id],
            export_targets=[existing_target.id],
            custom_fields={"devices": [existing_device.id]},
        )

        response = self._sync(nfclient, [self.DEVICE_1])

        for result in self._successful_results(response):
            assert "TENANT_A" in result["result"]["vrfs"]["updated"]
            assert set(
                result["result"]["route_targets"]["created"]
            ) == self.DEVICE_1_ROUTE_TARGETS - {"65000:201"}
            changes = result["diff"]["vrfs"]["update"]["TENANT_A"]
            assert sorted(changes["import_targets"]["new_value"]) == [
                "65000:201",
                "65000:301",
                "65000:999",
            ]
            assert sorted(changes["export_targets"]["new_value"]) == [
                "65000:201",
                "65000:302",
                "65000:999",
            ]
        tenant_a = self.nb.ipam.vrfs.get(name="TENANT_A")
        assert tenant_a.description == "Tenant A services"
        assert sorted(target.name for target in tenant_a.import_targets) == [
            "65000:201",
            "65000:301",
            "65000:999",
        ]
        assert sorted(target.name for target in tenant_a.export_targets) == [
            "65000:201",
            "65000:302",
            "65000:999",
        ]
        assert len(list(self.nb.ipam.route_targets.filter(name="65000:201"))) == 1
        selected_device = self.nb.dcim.devices.get(name=self.DEVICE_1)
        assert self._custom_field_device_ids(tenant_a, "devices") == {
            existing_device.id,
            selected_device.id,
        }

    def test_routing_policies_are_additive(self, nfclient: Any) -> None:
        existing = self.nb.plugins.bgp.routing_policy.create(name="TENANT_A_EXTRA")
        self.nb.ipam.vrfs.create(
            name="TENANT_A",
            custom_fields={"rpl_import_ipv4": [existing.id]},
        )

        for result in self._successful_results(self._sync(nfclient, [self.DEVICE_1])):
            changes = result["diff"]["vrfs"]["update"]["TENANT_A"]
            assert set(changes["rpl_import_ipv4"]["new_value"]) == {
                "TENANT_A_EXTRA",
                "TENANT_A_IMPORT",
            }
        tenant_a = self.nb.ipam.vrfs.get(name="TENANT_A")
        assert self._custom_field_policy_names(tenant_a, "rpl_import_ipv4") == {
            "TENANT_A_EXTRA",
            "TENANT_A_IMPORT",
        }

    def test_multiple_devices_are_aggregated_with_description_precedence(
        self, nfclient: Any
    ) -> None:
        response = self._sync(nfclient, [self.DEVICE_1, self.DEVICE_2])

        for result in self._successful_results(response):
            assert result["result"]["vrfs"]["created"] == sorted(self.VRF_NAMES)
        control_plane = self.nb.ipam.vrfs.get(name="CONTROL_PLANE")
        expected_device_ids = {
            self.nb.dcim.devices.get(name=self.DEVICE_1).id,
            self.nb.dcim.devices.get(name=self.DEVICE_2).id,
        }
        assert self._custom_field_device_ids(control_plane, "devices") == (
            expected_device_ids
        )
        assert control_plane.description == "Control plane VRF for ceos-leaf-1"
        tenant_a = self.nb.ipam.vrfs.get(name="TENANT_A")
        assert self._custom_field_policy_names(tenant_a, "rpl_import_ipv6") == set()
        assert sorted(target.name for target in tenant_a.import_targets) == [
            "65000:201",
            "65000:301",
            "65000:303",
        ]
        assert sorted(target.name for target in tenant_a.export_targets) == [
            "65000:201",
            "65000:302",
        ]
        tenant_b = self.nb.ipam.vrfs.get(name="TENANT_B")
        assert tenant_b.description == "Tenant B services"

    def test_custom_device_field_name(self, nfclient: Any) -> None:
        response = self._sync(
            nfclient,
            [self.DEVICE_1],
            device_custom_field="vrf_devices",
        )

        for result in self._successful_results(response):
            assert result["result"]["vrfs"]["created"] == sorted(self.VRF_NAMES)
        tenant_b = self.nb.ipam.vrfs.get(name="TENANT_B")
        device = self.nb.dcim.devices.get(name=self.DEVICE_1)
        assert self._custom_field_device_ids(tenant_b, "vrf_devices") == {device.id}

    def test_custom_routing_policy_field_name(self, nfclient: Any) -> None:
        response = self._sync(
            nfclient,
            [self.DEVICE_1],
            rpl_import_ipv4="alternate_rpl_import_ipv4",
        )
        self._successful_results(response)
        tenant_a = self.nb.ipam.vrfs.get(name="TENANT_A")
        assert self._custom_field_policy_names(
            tenant_a, "alternate_rpl_import_ipv4"
        ) == {"TENANT_A_IMPORT"}
        assert self._custom_field_policy_names(tenant_a, "rpl_import_ipv4") == set()

    def test_existing_vrf_with_empty_device_custom_field(self, nfclient: Any) -> None:
        self.nb.ipam.vrfs.create(name="TENANT_A")

        response = self._sync(nfclient, [self.DEVICE_1])

        for result in self._successful_results(response):
            assert "TENANT_A" in result["result"]["vrfs"]["updated"]
        tenant_a = self.nb.ipam.vrfs.get(name="TENANT_A")
        device = self.nb.dcim.devices.get(name=self.DEVICE_1)
        assert self._custom_field_device_ids(tenant_a, "devices") == {device.id}

    def test_missing_device_custom_field_is_ignored(self, nfclient: Any) -> None:
        response = self._sync(
            nfclient,
            [self.DEVICE_1],
            device_custom_field="does_not_exist",
        )

        for result in self._successful_results(response):
            assert result["result"]["vrfs"]["created"] == sorted(self.VRF_NAMES)
        tenant_a = self.nb.ipam.vrfs.get(name="TENANT_A")
        assert "does_not_exist" not in tenant_a.custom_fields

    def test_unmatched_netbox_vrf_is_not_deleted(self, nfclient: Any) -> None:
        self.nb.ipam.vrfs.create(name="KEEP_ME")
        try:
            response = self._sync(nfclient, [self.DEVICE_1])
            for result in self._successful_results(response):
                assert result["result"]["vrfs"]["deleted"] == []
                assert result["diff"]["vrfs"]["delete"] == []
            assert self.nb.ipam.vrfs.get(name="KEEP_ME") is not None
        finally:
            self.nb.ipam.vrfs.get(name="KEEP_ME").delete()
