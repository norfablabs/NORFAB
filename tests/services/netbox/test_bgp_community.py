from collections.abc import Iterator
from typing import Any

import pytest

from tests.services.netbox.common import get_pynetbox

pytestmark = [
    pytest.mark.netbox,
    pytest.mark.netbox_sync_bgp_community,
]


class TestSyncBgpCommunity:
    DEVICES = ["fn-ceos-lf-1", "fn-ceos-lf-2"]
    ROUTE_TARGET_VALUES = {"65000:200", "65000:999"}
    COMMUNITY_VALUES = {"65000:100", "65000:300", "65000:999"}
    COMMUNITY_KEYS = [
        "65000:100::BLUE_EXPORT",
        "65000:100::CUSTOMER_EXPORT",
        "65000:300::ORIGIN_SITE",
        "65000:300::SITE_ORIGIN",
    ]

    @pytest.fixture(autouse=True)
    def cleanup_test_communities(self, nfclient: Any) -> Iterator[None]:
        self.nb = get_pynetbox(nfclient)
        created_custom_fields = []
        for field_name in ("community_name", "community_aliases"):
            if self.nb.extras.custom_fields.get(name=field_name) is not None:
                continue
            payload = {
                "name": field_name,
                "label": field_name.replace("_", " ").title(),
                "type": "longtext",
                "object_types": ["ipam.routetarget", "netbox_bgp.community"],
            }
            if float(".".join(self.nb.version.split(".")[:2])) < 4.0:
                payload["content_types"] = payload.pop("object_types")
            created_custom_fields.append(self.nb.extras.custom_fields.create(**payload))
        for field_name in ("devices", "community_devices"):
            if self.nb.extras.custom_fields.get(name=field_name) is not None:
                continue
            payload = {
                "name": field_name,
                "label": field_name.replace("_", " ").title(),
                "type": "multiobject",
                "object_types": ["ipam.routetarget", "netbox_bgp.community"],
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
        for value in self.ROUTE_TARGET_VALUES:
            for route_target in list(self.nb.ipam.route_targets.filter(name=value)):
                route_target.delete()
        for value in self.COMMUNITY_VALUES:
            for community in list(self.nb.plugins.bgp.community.filter(value=value)):
                community.delete()

    @staticmethod
    def _sync(
        nfclient: Any,
        devices: list[str] | None = None,
        **kwargs: object,
    ) -> dict:
        if devices is None and not any(key.startswith("F") for key in kwargs):
            devices = TestSyncBgpCommunity.DEVICES
        sync_kwargs = {"devices": devices, **kwargs} if devices else kwargs
        return nfclient.run_job(
            "netbox",
            "sync_bgp_community",
            workers="any",
            kwargs=sync_kwargs,
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
    def _custom_field_device_ids(record: Any, field_name: str) -> set[int]:
        return {device["id"] for device in record.custom_fields[field_name]}

    def _community_by_description(self, value: str, description: str) -> Any:
        for community in self.nb.plugins.bgp.community.filter(value=value):
            if community.description == description:
                return community
        pytest.fail(
            f"BGP community value '{value}' with description '{description}' not found"
        )

    def test_dry_run_apply_aggregation_and_idempotency(self, nfclient: Any) -> None:
        response = self._sync(
            nfclient, dry_run=True, device_custom_field="community_devices"
        )
        for result in self._successful_results(response):
            assert result["result"]["route_targets"]["create"] == ["65000:200"]
            assert result["result"]["communities"]["create"] == self.COMMUNITY_KEYS
        assert self.nb.ipam.route_targets.get(name="65000:200") is None

        response = self._sync(nfclient, device_custom_field="community_devices")
        for result in self._successful_results(response):
            assert result["result"]["route_targets"]["created"] == ["65000:200"]
            assert result["result"]["communities"]["created"] == self.COMMUNITY_KEYS

        route_target = self.nb.ipam.route_targets.get(name="65000:200")
        blue_export = self._community_by_description("65000:100", "BLUE_EXPORT")
        customer_export = self._community_by_description("65000:100", "CUSTOMER_EXPORT")
        origin_site = self._community_by_description("65000:300", "ORIGIN_SITE")
        site_origin = self._community_by_description("65000:300", "SITE_ORIGIN")
        assert route_target.custom_fields["community_name"] == ("TENANT_BLUE, VPN_BLUE")
        assert blue_export.custom_fields["community_name"] == "BLUE_EXPORT"
        assert customer_export.custom_fields["community_name"] == "CUSTOMER_EXPORT"
        assert origin_site.custom_fields["community_name"] == "ORIGIN_SITE"
        assert site_origin.custom_fields["community_name"] == "SITE_ORIGIN"
        device_ids = {
            self.nb.dcim.devices.get(name=device).id for device in self.DEVICES
        }
        assert (
            self._custom_field_device_ids(route_target, "community_devices")
            == device_ids
        )
        assert self._custom_field_device_ids(blue_export, "community_devices") == {
            self.nb.dcim.devices.get(name="fn-ceos-lf-1").id
        }
        assert self._custom_field_device_ids(customer_export, "community_devices") == {
            self.nb.dcim.devices.get(name="fn-ceos-lf-2").id
        }
        assert self._custom_field_device_ids(origin_site, "community_devices") == {
            self.nb.dcim.devices.get(name="fn-ceos-lf-2").id
        }
        assert self._custom_field_device_ids(site_origin, "community_devices") == {
            self.nb.dcim.devices.get(name="fn-ceos-lf-1").id
        }

        response = self._sync(nfclient, device_custom_field="community_devices")
        for result in self._successful_results(response):
            assert result["result"]["route_targets"]["in_sync"] == ["65000:200"]
            assert result["result"]["communities"]["in_sync"] == self.COMMUNITY_KEYS

    def test_custom_field_name_and_no_deletions(self, nfclient: Any) -> None:
        self.nb.ipam.route_targets.create(
            name="65000:200",
            custom_fields={"community_aliases": "stale"},
        )
        for value, description in (
            ("65000:100", "BLUE_EXPORT"),
            ("65000:100", "CUSTOMER_EXPORT"),
            ("65000:300", "ORIGIN_SITE"),
            ("65000:300", "SITE_ORIGIN"),
        ):
            self.nb.plugins.bgp.community.create(
                value=value,
                description=description,
                custom_fields={"community_aliases": "stale"},
            )
        self.nb.ipam.route_targets.create(name="65000:999")
        self.nb.plugins.bgp.community.create(value="65000:999")

        response = self._sync(
            nfclient,
            community_name_field="community_aliases",
            device_custom_field="community_devices",
        )
        for result in self._successful_results(response):
            assert result["result"]["route_targets"]["updated"] == ["65000:200"]
            assert result["result"]["communities"]["updated"] == self.COMMUNITY_KEYS
            assert result["diff"]["route_targets"]["delete"] == []
            assert result["diff"]["communities"]["delete"] == []

        route_target = self.nb.ipam.route_targets.get(name="65000:200")
        assert route_target.custom_fields["community_aliases"] == (
            "TENANT_BLUE, VPN_BLUE, stale"
        )
        blue_export = self._community_by_description("65000:100", "BLUE_EXPORT")
        customer_export = self._community_by_description("65000:100", "CUSTOMER_EXPORT")
        origin_site = self._community_by_description("65000:300", "ORIGIN_SITE")
        site_origin = self._community_by_description("65000:300", "SITE_ORIGIN")
        assert blue_export.custom_fields["community_aliases"] == "BLUE_EXPORT, stale"
        assert customer_export.custom_fields["community_aliases"] == (
            "CUSTOMER_EXPORT, stale"
        )
        assert origin_site.custom_fields["community_aliases"] == "ORIGIN_SITE, stale"
        assert site_origin.custom_fields["community_aliases"] == "SITE_ORIGIN, stale"
        assert self.nb.ipam.route_targets.get(name="65000:999") is not None
        assert self.nb.plugins.bgp.community.get(value="65000:999") is not None

        response = self._sync(
            nfclient,
            community_name_field="community_aliases",
            device_custom_field="community_devices",
        )
        for result in self._successful_results(response):
            assert result["result"]["route_targets"]["in_sync"] == ["65000:200"]
            assert result["result"]["communities"]["in_sync"] == self.COMMUNITY_KEYS

    def test_custom_field_sync_can_be_disabled(self, nfclient: Any) -> None:
        response = self._sync(
            nfclient,
            community_name_field=False,
            device_custom_field="community_devices",
        )
        for result in self._successful_results(response):
            assert result["result"]["route_targets"]["created"] == ["65000:200"]
            assert result["result"]["communities"]["created"] == self.COMMUNITY_KEYS

        route_target = self.nb.ipam.route_targets.get(name="65000:200")
        blue_export = self._community_by_description("65000:100", "BLUE_EXPORT")
        site_origin = self._community_by_description("65000:300", "SITE_ORIGIN")
        assert route_target.custom_fields.get("community_name") is None
        assert blue_export.custom_fields.get("community_name") is None
        assert site_origin.custom_fields.get("community_name") is None

        response = self._sync(
            nfclient,
            community_name_field=False,
            device_custom_field="community_devices",
        )
        for result in self._successful_results(response):
            assert result["result"]["route_targets"]["in_sync"] == ["65000:200"]
            assert result["result"]["communities"]["in_sync"] == self.COMMUNITY_KEYS

    def test_nornir_filter_resolution(self, nfclient: Any) -> None:
        response = self._sync(
            nfclient,
            devices=[],
            FR="fn-ceos-lf-[12]",
            device_custom_field="community_devices",
        )
        for result in self._successful_results(response):
            assert result["result"]["route_targets"]["created"] == ["65000:200"]
            assert result["result"]["communities"]["created"] == self.COMMUNITY_KEYS

    def test_custom_device_field_name(self, nfclient: Any) -> None:
        self._sync(
            nfclient,
            devices=[self.DEVICES[0]],
            device_custom_field="community_devices",
        )

        route_target = self.nb.ipam.route_targets.get(name="65000:200")
        blue_export = self._community_by_description("65000:100", "BLUE_EXPORT")
        device = self.nb.dcim.devices.get(name=self.DEVICES[0])
        assert self._custom_field_device_ids(route_target, "community_devices") == {
            device.id
        }
        assert self._custom_field_device_ids(blue_export, "community_devices") == {
            device.id
        }

        self._sync(
            nfclient,
            devices=[self.DEVICES[1]],
            device_custom_field="community_devices",
        )
        route_target = self.nb.ipam.route_targets.get(name="65000:200")
        customer_export = self._community_by_description("65000:100", "CUSTOMER_EXPORT")
        assert self._custom_field_device_ids(route_target, "community_devices") == {
            self.nb.dcim.devices.get(name=device).id for device in self.DEVICES
        }
        assert self._custom_field_device_ids(blue_export, "community_devices") == {
            self.nb.dcim.devices.get(name=self.DEVICES[0]).id
        }
        assert self._custom_field_device_ids(customer_export, "community_devices") == {
            self.nb.dcim.devices.get(name=self.DEVICES[1]).id
        }

    def test_missing_device_custom_field_is_ignored(self, nfclient: Any) -> None:
        response = self._sync(nfclient, device_custom_field="does_not_exist")

        for result in self._successful_results(response):
            assert result["result"]["route_targets"]["created"] == ["65000:200"]

    def test_resources_failed_are_reported(self, nfclient: Any) -> None:
        device = self.nb.dcim.devices.get(name="cisco_ios_xr1")
        if device is not None:
            device.delete()
        device = self.nb.dcim.devices.create(
            name="cisco_ios_xr1",
            device_type=self.nb.dcim.device_types.get(model="XVR9000").id,
            role=self.nb.dcim.device_roles.get(name="VirtualRouter").id,
            site=self.nb.dcim.sites.get(name="SALTNORNIR-LAB").id,
            status="active",
        )
        try:
            response = self._sync(
                nfclient,
                devices=["fn-ceos-lf-1", "cisco_ios_xr1"],
                device_custom_field="community_devices",
            )
            for result in response.values():
                assert any(
                    "failed to fetch BGP community data from devices cisco_ios_xr1"
                    in error
                    for error in result["errors"]
                )
                assert result["failed"] is False
                assert result["result"]["route_targets"]["created"] == ["65000:200"]
                assert result["result"]["communities"]["created"] == [
                    "65000:100::BLUE_EXPORT",
                    "65000:300::SITE_ORIGIN",
                ]
        finally:
            device.delete()
