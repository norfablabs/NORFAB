from collections.abc import Iterator
from typing import Any

import pytest

from tests.services.netbox.common import get_pynetbox

pytestmark = [
    pytest.mark.netbox,
    pytest.mark.netbox_bgp_community_sync,
]


class TestBgpCommunitySync:
    DEVICES = ["fn-ceos-lf-1", "fn-ceos-lf-2"]
    ROUTE_TARGET_VALUES = {"65000:200", "65000:999"}
    COMMUNITY_VALUES = {"65000:100", "65000:300", "65000:999"}

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
            devices = TestBgpCommunitySync.DEVICES
        sync_kwargs = {"devices": devices, **kwargs} if devices else kwargs
        return nfclient.run_job(
            "netbox",
            "bgp_community_sync",
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

    def test_dry_run_apply_aggregation_and_idempotency(self, nfclient: Any) -> None:
        response = self._sync(nfclient, dry_run=True)
        for result in self._successful_results(response):
            assert result["result"]["route_targets"]["create"] == ["65000:200"]
            assert result["result"]["communities"]["create"] == [
                "65000:100",
                "65000:300",
            ]
        assert self.nb.ipam.route_targets.get(name="65000:200") is None

        response = self._sync(nfclient)
        for result in self._successful_results(response):
            assert result["result"]["route_targets"]["created"] == ["65000:200"]
            assert result["result"]["communities"]["created"] == [
                "65000:100",
                "65000:300",
            ]

        route_target = self.nb.ipam.route_targets.get(name="65000:200")
        standard = self.nb.plugins.bgp.community.get(value="65000:100")
        site_origin = self.nb.plugins.bgp.community.get(value="65000:300")
        assert route_target.custom_fields["community_name"] == ("TENANT_BLUE, VPN_BLUE")
        assert standard.custom_fields["community_name"] == (
            "BLUE_EXPORT, CUSTOMER_EXPORT"
        )
        assert site_origin.custom_fields["community_name"] == (
            "ORIGIN_SITE, SITE_ORIGIN"
        )

        response = self._sync(nfclient)
        for result in self._successful_results(response):
            assert result["result"]["route_targets"]["in_sync"] == ["65000:200"]
            assert result["result"]["communities"]["in_sync"] == [
                "65000:100",
                "65000:300",
            ]

    def test_custom_field_name_and_no_deletions(self, nfclient: Any) -> None:
        self.nb.ipam.route_targets.create(
            name="65000:200",
            custom_fields={"community_aliases": "stale"},
        )
        for value in ("65000:100", "65000:300"):
            self.nb.plugins.bgp.community.create(
                value=value,
                custom_fields={"community_aliases": "stale"},
            )
        self.nb.ipam.route_targets.create(name="65000:999")
        self.nb.plugins.bgp.community.create(value="65000:999")

        response = self._sync(
            nfclient,
            community_name_field="community_aliases",
        )
        for result in self._successful_results(response):
            assert result["result"]["route_targets"]["updated"] == ["65000:200"]
            assert result["result"]["communities"]["updated"] == [
                "65000:100",
                "65000:300",
            ]
            assert result["diff"]["route_targets"]["delete"] == []
            assert result["diff"]["communities"]["delete"] == []

        route_target = self.nb.ipam.route_targets.get(name="65000:200")
        assert route_target.custom_fields["community_aliases"] == (
            "TENANT_BLUE, VPN_BLUE"
        )
        assert self.nb.ipam.route_targets.get(name="65000:999") is not None
        assert self.nb.plugins.bgp.community.get(value="65000:999") is not None

    def test_custom_field_sync_can_be_disabled(self, nfclient: Any) -> None:
        response = self._sync(nfclient, community_name_field=False)
        for result in self._successful_results(response):
            assert result["result"]["route_targets"]["created"] == ["65000:200"]
            assert result["result"]["communities"]["created"] == [
                "65000:100",
                "65000:300",
            ]

        route_target = self.nb.ipam.route_targets.get(name="65000:200")
        standard = self.nb.plugins.bgp.community.get(value="65000:100")
        site_origin = self.nb.plugins.bgp.community.get(value="65000:300")
        assert route_target.custom_fields.get("community_name") is None
        assert standard.custom_fields.get("community_name") is None
        assert site_origin.custom_fields.get("community_name") is None

        response = self._sync(nfclient, community_name_field=False)
        for result in self._successful_results(response):
            assert result["result"]["route_targets"]["in_sync"] == ["65000:200"]
            assert result["result"]["communities"]["in_sync"] == [
                "65000:100",
                "65000:300",
            ]

    def test_nornir_filter_resolution(self, nfclient: Any) -> None:
        response = self._sync(nfclient, devices=[], FR="fn-ceos-lf-[12]")
        for result in self._successful_results(response):
            assert result["result"]["route_targets"]["created"] == ["65000:200"]
            assert result["result"]["communities"]["created"] == [
                "65000:100",
                "65000:300",
            ]
