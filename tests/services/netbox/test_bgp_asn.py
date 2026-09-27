from collections.abc import Iterator
from typing import Any

import pytest

from tests.services.netbox.common import get_pynetbox

pytestmark = [pytest.mark.netbox, pytest.mark.netbox_sync_bgp_asn]


@pytest.mark.netbox_create_asn
class TestCreateBgpAsn:
    def test_allocates_and_assigns_sites(self, nfclient: Any) -> None:
        """Allocate through the public task and replace the assigned site list."""
        nb = get_pynetbox(nfclient)
        site_names = ["NORFAB ASN TASK SITE A", "NORFAB ASN TASK SITE B"]
        if (
            nb.ipam.asns.get(asn=4200999700)
            or nb.ipam.asns.get(asn=4200999701)
            or nb.ipam.asn_ranges.get(name="NORFAB ASN TASK RANGE")
            or nb.ipam.rirs.get(name="NORFAB ASN TASK RIR")
            or any(nb.dcim.sites.get(name=name) for name in site_names)
        ):
            pytest.skip("ASN task test objects already exist")

        try:
            rir = nb.ipam.rirs.create(
                {"name": "NORFAB ASN TASK RIR", "slug": "norfab-asn-task-rir"}
            )
            nb.dcim.sites.create(
                [
                    {"name": site_names[0], "slug": "norfab-asn-task-site-a"},
                    {"name": site_names[1], "slug": "norfab-asn-task-site-b"},
                ]
            )
            nb.ipam.asn_ranges.create(
                {
                    "name": "NORFAB ASN TASK RANGE",
                    "slug": "norfab-asn-task-range",
                    "start": 4200999700,
                    "end": 4200999701,
                    "rir": rir.id,
                }
            )

            for dry_run in (True, False):
                response = nfclient.run_job(
                    "netbox",
                    "create_asn",
                    workers="any",
                    kwargs={
                        "asn_range": "NORFAB ASN TASK RANGE",
                        "description": "NORFAB ASN TASK ALLOCATION",
                        "sites": site_names,
                        "dry_run": dry_run,
                    },
                )
                for result in response.values():
                    assert not result["failed"], result
                    assert result["result"]["asn"] == 4200999700
                    assert result["result"]["status"] == (
                        "create" if dry_run else "created"
                    )
                if dry_run:
                    assert nb.ipam.asns.get(asn=4200999700) is None

            asn = nb.ipam.asns.get(asn=4200999700)
            assert {site.name for site in asn.sites} == set(site_names)

            response = nfclient.run_job(
                "netbox",
                "create_asn",
                workers="any",
                kwargs={
                    "asn_range": "NORFAB ASN TASK RANGE",
                    "description": "NORFAB ASN TASK ALLOCATION",
                    "sites": [site_names[1]],
                },
            )
            for result in response.values():
                assert not result["failed"], result
                assert result["result"]["status"] == "updated"
            asn = nb.ipam.asns.get(asn=4200999700)
            assert [site.name for site in asn.sites] == [site_names[1]]

            response = nfclient.run_job(
                "netbox",
                "create_asn",
                workers="any",
                kwargs={
                    "asn_range": "NORFAB ASN TASK RANGE",
                    "description": "NORFAB ASN TASK ALLOCATION",
                    "site": site_names[0],
                },
            )
            for result in response.values():
                assert result["failed"], result
                assert any("site" in error for error in result["errors"])
        finally:
            asn = nb.ipam.asns.get(asn=4200999700)
            if asn:
                asn.delete()
            asn_range = nb.ipam.asn_ranges.get(name="NORFAB ASN TASK RANGE")
            if asn_range:
                asn_range.delete()
            for name in site_names:
                site = nb.dcim.sites.get(name=name)
                if site:
                    site.delete()
            rir = nb.ipam.rirs.get(name="NORFAB ASN TASK RIR")
            if rir:
                rir.delete()


class TestSyncBgpAsn:
    DEVICE_1 = "fn-ceos-lf-1"
    DEVICE_2 = "fn-ceos-lf-2"
    DEVICE_1_ASNS = {4200000101, 4200000200, 4200000301}
    DEVICE_2_ASNS = {4200000102, 4200000200, 4200000302}
    TEST_ASNS = DEVICE_1_ASNS | DEVICE_2_ASNS | {4200000999}
    RIR = "lab"

    @pytest.fixture(autouse=True)
    def cleanup_test_asns(self, nfclient: Any) -> Iterator[None]:
        self.nb = get_pynetbox(nfclient)
        created_custom_fields = []
        restored_custom_fields = []
        for field_name in ("devices", "asn_devices"):
            custom_field = self.nb.extras.custom_fields.get(name=field_name)
            if custom_field is not None:
                object_types = list(
                    getattr(custom_field, "object_types", None)
                    or getattr(custom_field, "content_types", None)
                    or []
                )
                if "ipam.asn" not in object_types:
                    field_name_key = (
                        "content_types"
                        if float(".".join(self.nb.version.split(".")[:2])) < 4.0
                        else "object_types"
                    )
                    custom_field.update({field_name_key: object_types + ["ipam.asn"]})
                    restored_custom_fields.append(
                        (custom_field, field_name_key, object_types)
                    )
                continue
            payload = {
                "name": field_name,
                "label": field_name.replace("_", " ").title(),
                "type": "multiobject",
                "object_types": ["ipam.asn"],
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
        for custom_field, field_name_key, object_types in restored_custom_fields:
            custom_field.update({field_name_key: object_types})

    def _delete_test_data(self) -> None:
        for asn in self.TEST_ASNS:
            for record in list(self.nb.ipam.asns.filter(asn=asn)):
                record.delete()

    @staticmethod
    def _sync(
        nfclient: Any,
        devices: list[str] | None = None,
        **kwargs: object,
    ) -> dict:
        if devices is None and not any(key.startswith("F") for key in kwargs):
            devices = [TestSyncBgpAsn.DEVICE_1]
        sync_kwargs = {"devices": devices, **kwargs} if devices else kwargs
        return nfclient.run_job(
            "netbox", "sync_bgp_asn", workers="any", kwargs=sync_kwargs
        )

    @staticmethod
    def _successful_results(response: dict, allow_errors: bool = False) -> list[dict]:
        assert response
        results = []
        for worker, result in response.items():
            assert result["failed"] is False, f"{worker} failed: {result}"
            if not allow_errors:
                assert result["errors"] == [], f"{worker} returned errors: {result}"
            results.append(result)
        return results

    @staticmethod
    def _custom_field_device_ids(asn: Any, field_name: str) -> set[int]:
        values = (asn.custom_fields or {}).get(field_name) or []
        return {
            int(
                value.get("id")
                if isinstance(value, dict)
                else getattr(value, "id", value)
            )
            for value in values
        }

    def test_dry_run_apply_and_idempotency(self, nfclient: Any) -> None:
        dry_run = self._sync(nfclient, dry_run=True)
        for result in self._successful_results(dry_run):
            assert set(result["result"]["global"]["create"]) == self.DEVICE_1_ASNS
            assert result["result"]["global"]["update"] == {}
            assert result["result"]["global"]["delete"] == []
        assert self.nb.ipam.asns.get(asn=4200000200) is None

        first_sync = self._sync(nfclient, rir=self.RIR, batch_size=1)
        for result in self._successful_results(first_sync):
            assert set(result["result"]["global"]["created"]) == self.DEVICE_1_ASNS

        transit = self.nb.ipam.asns.get(asn=4200000200)
        device = self.nb.dcim.devices.get(name=self.DEVICE_1)
        assert transit.description == "TRANSIT"
        assert self._custom_field_device_ids(transit, "devices") == set()
        local_asn = self.nb.ipam.asns.get(asn=4200000101)
        assert self._custom_field_device_ids(local_asn, "devices") == {device.id}

        second_sync = self._sync(nfclient, rir=self.RIR)
        for result in self._successful_results(second_sync):
            assert result["result"]["global"]["created"] == []
            assert result["result"]["global"]["updated"] == []
            assert set(result["result"]["global"]["in_sync"]) == self.DEVICE_1_ASNS

    def test_without_rir_updates_existing_and_skips_creation(
        self, nfclient: Any
    ) -> None:
        rir = self.nb.ipam.rirs.get(name=self.RIR)
        existing_device = self.nb.dcim.devices.get(name=self.DEVICE_2)
        self.nb.ipam.asns.create(
            asn=4200000200,
            rir=rir.id,
            description="Old description",
            custom_fields={"devices": [existing_device.id]},
        )
        self.nb.ipam.asns.create(
            asn=4200000101,
            rir=rir.id,
            description="Old local description",
        )

        response = self._sync(nfclient)

        for result in self._successful_results(response, allow_errors=True):
            assert result["result"]["global"]["created"] == []
            assert result["result"]["global"]["updated"] == [4200000101]
            assert any("no RIR provided" in error for error in result["errors"])
        transit = self.nb.ipam.asns.get(asn=4200000200)
        local_asn = self.nb.ipam.asns.get(asn=4200000101)
        selected_device = self.nb.dcim.devices.get(name=self.DEVICE_1)
        assert transit.description == "Old description"
        assert self._custom_field_device_ids(transit, "devices") == {
            existing_device.id,
        }
        assert local_asn.description == "Old local description"
        assert self._custom_field_device_ids(local_asn, "devices") == {
            selected_device.id,
        }
        assert self.nb.ipam.asns.get(asn=4200000301) is None

    def test_can_override_existing_description(self, nfclient: Any) -> None:
        rir = self.nb.ipam.rirs.get(name=self.RIR)
        self.nb.ipam.asns.create(
            asn=4200000200,
            rir=rir.id,
            description="Old description",
        )

        response = self._sync(nfclient, preserve_description=False)

        for result in self._successful_results(response, allow_errors=True):
            assert result["result"]["global"]["updated"] == [4200000200]
            assert any("no RIR provided" in error for error in result["errors"])
        transit = self.nb.ipam.asns.get(asn=4200000200)
        assert transit.description == "TRANSIT"

    def test_multiple_devices_are_aggregated(self, nfclient: Any) -> None:
        response = self._sync(
            nfclient, devices=[self.DEVICE_1, self.DEVICE_2], rir=self.RIR
        )

        expected_asns = self.DEVICE_1_ASNS | self.DEVICE_2_ASNS
        for result in self._successful_results(response):
            assert set(result["result"]["global"]["created"]) == expected_asns
        transit = self.nb.ipam.asns.get(asn=4200000200)
        assert transit.description == "TRANSIT"
        assert self._custom_field_device_ids(transit, "devices") == set()
        assert self._custom_field_device_ids(
            self.nb.ipam.asns.get(asn=4200000101), "devices"
        ) == {self.nb.dcim.devices.get(name=self.DEVICE_1).id}
        assert self._custom_field_device_ids(
            self.nb.ipam.asns.get(asn=4200000102), "devices"
        ) == {self.nb.dcim.devices.get(name=self.DEVICE_2).id}
        assert self.nb.ipam.asns.get(asn=4200000301).description == "CUSTOMER_A"
        assert self.nb.ipam.asns.get(asn=4200000302).description == "CUSTOMER_B"

    def test_custom_device_field_and_range_filter(self, nfclient: Any) -> None:
        response = self._sync(
            nfclient,
            rir=self.RIR,
            device_custom_field="asn_devices",
            ignore_asn_by_range=["4200000101", "4200000200-4200000300"],
        )

        for result in self._successful_results(response):
            assert result["result"]["global"]["created"] == [4200000301]
        customer = self.nb.ipam.asns.get(asn=4200000301)
        assert self._custom_field_device_ids(customer, "asn_devices") == set()
        assert self.nb.ipam.asns.get(asn=4200000101) is None
        assert self.nb.ipam.asns.get(asn=4200000200) is None

    def test_missing_device_custom_field_is_ignored(self, nfclient: Any) -> None:
        response = self._sync(
            nfclient, rir=self.RIR, device_custom_field="does_not_exist"
        )

        for result in self._successful_results(response):
            assert set(result["result"]["global"]["created"]) == self.DEVICE_1_ASNS
        transit = self.nb.ipam.asns.get(asn=4200000200)
        assert "does_not_exist" not in transit.custom_fields

    def test_nornir_filter_resolution(self, nfclient: Any) -> None:
        response = self._sync(nfclient, devices=[], FR="fn-ceos-lf-[12]", rir=self.RIR)

        for result in self._successful_results(response):
            assert set(result["result"]["global"]["created"]) == (
                self.DEVICE_1_ASNS | self.DEVICE_2_ASNS
            )

    def test_unmatched_netbox_asn_is_not_deleted(self, nfclient: Any) -> None:
        rir = self.nb.ipam.rirs.get(name=self.RIR)
        self.nb.ipam.asns.create(asn=4200000999, rir=rir.id)

        response = self._sync(nfclient, rir=self.RIR)

        for result in self._successful_results(response):
            assert result["result"]["global"]["deleted"] == []
            assert result["diff"]["global"]["delete"] == []
        assert self.nb.ipam.asns.get(asn=4200000999) is not None
