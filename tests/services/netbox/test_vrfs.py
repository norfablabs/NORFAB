from collections.abc import Iterator
from typing import Any

import pytest

from tests.services.netbox.common import get_pynetbox

pytestmark = [
    pytest.mark.netbox,
    pytest.mark.netbox_sync_vrfs,
]


class TestSyncVrfs:
    DEVICE_1 = "fn-ceos-lf-1"
    DEVICE_2 = "fn-ceos-lf-2"
    VRF_NAMES = {"CONTROL_PLANE", "TENANT_A", "TENANT_B"}
    ROUTE_TARGET_NAMES = {
        "65000:101",
        "65000:201",
        "65000:202",
        "65000:301",
        "65000:302",
        "65000:303",
        "65000:999",
    }

    @pytest.fixture(autouse=True)
    def cleanup_test_vrfs(self, nfclient: Any) -> Iterator[None]:
        self.nb = get_pynetbox(nfclient)
        created_custom_fields = []
        for field_name in ("devices", "vrf_devices"):
            if self.nb.extras.custom_fields.get(name=field_name) is not None:
                continue
            payload = {
                "name": field_name,
                "label": field_name.replace("_", " ").title(),
                "type": "multiobject",
                "object_types": ["ipam.vrf"],
                "related_object_type": "dcim.device",
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
            assert result["result"]["global"]["create"] == sorted(self.VRF_NAMES)
            assert result["result"]["global"]["update"] == {}
            assert result["result"]["global"]["delete"] == []
        assert self.nb.ipam.vrfs.get(name="TENANT_A") is None
        assert self.nb.ipam.route_targets.get(name="65000:201") is None

        first_sync = self._sync(nfclient, [self.DEVICE_1])
        for result in self._successful_results(first_sync):
            assert result["result"]["global"]["created"] == sorted(self.VRF_NAMES)

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

        second_sync = self._sync(nfclient, [self.DEVICE_1])
        for result in self._successful_results(second_sync):
            actions = result["result"]["global"]
            assert actions["created"] == []
            assert actions["updated"] == []
            assert actions["in_sync"] == sorted(self.VRF_NAMES)

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
            assert "TENANT_A" in result["result"]["global"]["updated"]
            changes = result["diff"]["global"]["update"]["TENANT_A"]
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

    def test_multiple_devices_are_aggregated_with_description_precedence(
        self, nfclient: Any
    ) -> None:
        response = self._sync(nfclient, [self.DEVICE_1, self.DEVICE_2])

        for result in self._successful_results(response):
            assert result["result"]["global"]["created"] == sorted(self.VRF_NAMES)
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
            assert result["result"]["global"]["created"] == sorted(self.VRF_NAMES)
        tenant_b = self.nb.ipam.vrfs.get(name="TENANT_B")
        device = self.nb.dcim.devices.get(name=self.DEVICE_1)
        assert self._custom_field_device_ids(tenant_b, "vrf_devices") == {device.id}

    def test_existing_vrf_with_empty_device_custom_field(self, nfclient: Any) -> None:
        self.nb.ipam.vrfs.create(name="TENANT_A")

        response = self._sync(nfclient, [self.DEVICE_1])

        for result in self._successful_results(response):
            assert "TENANT_A" in result["result"]["global"]["updated"]
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
            assert result["result"]["global"]["created"] == sorted(self.VRF_NAMES)
        tenant_a = self.nb.ipam.vrfs.get(name="TENANT_A")
        assert "does_not_exist" not in tenant_a.custom_fields

    def test_unmatched_netbox_vrf_is_not_deleted(self, nfclient: Any) -> None:
        self.nb.ipam.vrfs.create(name="KEEP_ME")
        try:
            response = self._sync(nfclient, [self.DEVICE_1])
            for result in self._successful_results(response):
                assert result["result"]["global"]["deleted"] == []
                assert result["diff"]["global"]["delete"] == []
            assert self.nb.ipam.vrfs.get(name="KEEP_ME") is not None
        finally:
            self.nb.ipam.vrfs.get(name="KEEP_ME").delete()
