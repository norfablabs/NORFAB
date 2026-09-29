from collections.abc import Iterator
from typing import Any

import pytest

from tests.services.netbox.common import get_pynetbox

pytestmark = [pytest.mark.netbox, pytest.mark.netbox_sync_bgp_asn]


@pytest.mark.netbox_create_asn
class TestCreateBgpAsn:
    def test_allocates_and_assigns_sites(self, nfclient: Any) -> None:
        """Allocate an ASN and add sites on repeated create_asn calls."""
        nb = get_pynetbox(nfclient)
        site_names = [
            "NORFAB ASN TASK SITE A",
            "NORFAB ASN TASK SITE B",
        ]
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
            assert {site.name for site in asn.sites} == set(site_names)

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
            for number in (4200999700, 4200999701):
                asn = nb.ipam.asns.get(asn=number)
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

    def test_adds_tags_and_array_custom_fields(self, nfclient: Any) -> None:
        """Keep ASN tags and site references when adding values on repeat calls."""
        nb = get_pynetbox(nfclient)
        asn_number = 4200999702
        rir_name = "NORFAB ASN ARRAY RIR"
        field_name = "norfab_asn_array_sites"
        site_names = [
            "NORFAB ASN ARRAY SITE A",
            "NORFAB ASN ARRAY SITE B",
        ]
        tag_names = [
            "norfab-asn-array-a",
            "norfab-asn-array-b",
        ]
        if (
            nb.ipam.asns.get(asn=asn_number)
            or nb.ipam.rirs.get(name=rir_name)
            or nb.extras.custom_fields.get(name=field_name)
            or any(nb.dcim.sites.get(name=name) for name in site_names)
            or any(nb.extras.tags.get(name=name) for name in tag_names)
        ):
            pytest.skip("ASN array test objects already exist")

        try:
            nb.ipam.rirs.create({"name": rir_name, "slug": "norfab-asn-array-rir"})
            created_sites = nb.dcim.sites.create(
                [
                    {"name": site_names[0], "slug": "norfab-asn-array-site-a"},
                    {"name": site_names[1], "slug": "norfab-asn-array-site-b"},
                ]
            )
            nb.extras.tags.create(
                [
                    {"name": tag_names[0], "slug": tag_names[0]},
                    {"name": tag_names[1], "slug": tag_names[1]},
                ]
            )
            nb.extras.custom_fields.create(
                {
                    "name": field_name,
                    "type": "multiobject",
                    "object_types": ["ipam.asn"],
                    "related_object_type": "dcim.site",
                }
            )
            for index, (tags, references) in enumerate(
                (
                    ([tag_names[0]], [created_sites[0].id]),
                    (tag_names[:2], [created_sites[1].id]),
                    ([], []),
                )
            ):
                response = nfclient.run_job(
                    "netbox",
                    "create_asn",
                    workers="any",
                    kwargs={
                        "asn": asn_number,
                        "rir": rir_name,
                        "tags": tags,
                        "custom_fields": {field_name: references},
                    },
                )
                for result in response.values():
                    assert not result["failed"], result
                asn = nb.ipam.asns.get(asn=asn_number)
                expected_tags = tag_names[:1] if index == 0 else tag_names[:2]
                expected_sites = (
                    [created_sites[0].id]
                    if index == 0
                    else [site.id for site in created_sites[:2]]
                )
                assert {tag.name for tag in asn.tags} == set(expected_tags)
                assert {site["id"] for site in asn.custom_fields[field_name]} == set(
                    expected_sites
                )
            response = nfclient.run_job(
                "netbox",
                "create_asn",
                workers="any",
                kwargs={
                    "asn": asn_number,
                    "rir": rir_name,
                    "custom_fields": {field_name: None},
                },
            )
            for result in response.values():
                assert not result["failed"], result
            assert nb.ipam.asns.get(asn=asn_number).custom_fields[field_name] is None

            response = nfclient.run_job(
                "netbox",
                "create_asn",
                workers="any",
                kwargs={
                    "asn": asn_number,
                    "rir": rir_name,
                    "custom_fields": {field_name: [site.id for site in created_sites]},
                },
            )
            for result in response.values():
                assert not result["failed"], result

        finally:
            asn = nb.ipam.asns.get(asn=asn_number)
            if asn:
                asn.delete()
            field = nb.extras.custom_fields.get(name=field_name)
            if field:
                field.delete()
            for name in tag_names:
                tag = nb.extras.tags.get(name=name)
                if tag:
                    tag.delete()
            for name in site_names:
                site = nb.dcim.sites.get(name=name)
                if site:
                    site.delete()
            rir = nb.ipam.rirs.get(name=rir_name)
            if rir:
                rir.delete()

    def test_resolves_custom_field_object_names(self, nfclient: Any) -> None:
        """Resolve ASN object custom fields by their related NetBox type."""
        nb = get_pynetbox(nfclient)
        asn_number = 4200999703
        rir_name = "NORFAB ASN NAMED RIR"
        site_names = ["NORFAB ASN NAMED SITE A", "NORFAB ASN NAMED SITE B"]
        field_names = (
            "norfab_asn_named_devices",
            "norfab_asn_named_site",
            "norfab_asn_named_labels",
            "norfab_asn_named_interfaces",
            "norfab_asn_named_policy",
            "norfab_asn_named_note",
        )
        device_names = ["fn-ceos-lf-1", "fn-ceos-lf-2"]
        devices = [nb.dcim.devices.get(name=name) for name in device_names]
        policy_names = ["ALLOW-ALL", "ALLOW-10_8"]
        policies = [
            nb.plugins.bgp.routing_policy.get(name=name) for name in policy_names
        ]
        if not all(devices) or not all(policies):
            pytest.skip("NetBox device and routing policy fixtures are required")
        if (
            nb.ipam.asns.get(asn=asn_number)
            or nb.ipam.rirs.get(name=rir_name)
            or any(nb.dcim.sites.get(name=name) for name in site_names)
            or any(nb.extras.custom_fields.get(name=name) for name in field_names)
        ):
            pytest.skip("ASN named custom-field test objects already exist")

        try:
            nb.ipam.rirs.create({"name": rir_name, "slug": "norfab-asn-named-rir"})
            sites = nb.dcim.sites.create(
                [
                    {"name": site_names[0], "slug": "norfab-asn-named-site-a"},
                    {"name": site_names[1], "slug": "norfab-asn-named-site-b"},
                ]
            )
            nb.extras.custom_fields.create(
                [
                    {
                        "name": field_names[0],
                        "type": "multiobject",
                        "object_types": ["ipam.asn"],
                        "related_object_type": "dcim.device",
                    },
                    {
                        "name": field_names[1],
                        "type": "object",
                        "object_types": ["ipam.asn"],
                        "related_object_type": "dcim.site",
                    },
                    {
                        "name": field_names[2],
                        "type": "json",
                        "object_types": ["ipam.asn"],
                    },
                    {
                        "name": field_names[3],
                        "type": "multiobject",
                        "object_types": ["ipam.asn"],
                        "related_object_type": "dcim.interface",
                    },
                    {
                        "name": field_names[4],
                        "type": "multiobject",
                        "object_types": ["ipam.asn"],
                        "related_object_type": "netbox_bgp.routingpolicy",
                    },
                    {
                        "name": field_names[5],
                        "type": "text",
                        "object_types": ["ipam.asn"],
                    },
                ]
            )
            for (
                requested_devices,
                requested_site,
                requested_labels,
                requested_policies,
                note,
            ) in (
                (
                    [device_names[0]],
                    site_names[0],
                    ["first"],
                    [policy_names[0]],
                    "first note",
                ),
                (
                    [device_names[0], device_names[1]],
                    site_names[1],
                    ["second"],
                    [policy_names[1]],
                    "revised note",
                ),
                ([device_names[1]], site_names[1], [], [], "final note"),
            ):
                response = nfclient.run_job(
                    "netbox",
                    "create_asn",
                    workers="any",
                    kwargs={
                        "asn": asn_number,
                        "rir": rir_name,
                        "custom_fields": {
                            field_names[0]: requested_devices,
                            field_names[1]: requested_site,
                            field_names[2]: requested_labels,
                            field_names[4]: requested_policies,
                            field_names[5]: note,
                        },
                    },
                )
                for result in response.values():
                    assert not result["failed"], result
                asn = nb.ipam.asns.get(asn=asn_number)
                expected_devices = (
                    devices[:1] if requested_site == site_names[0] else devices
                )
                assert {item["id"] for item in asn.custom_fields[field_names[0]]} == {
                    device.id for device in expected_devices
                }
                expected_site = (
                    sites[0] if requested_site == site_names[0] else sites[1]
                )
                assert asn.custom_fields[field_names[1]]["id"] == expected_site.id
                expected_labels = (
                    ["first"]
                    if requested_site == site_names[0]
                    else ["first", "second"]
                )
                assert asn.custom_fields[field_names[2]] == expected_labels
                expected_policies = (
                    policies[:1] if requested_site == site_names[0] else policies
                )
                assert {item["id"] for item in asn.custom_fields[field_names[4]]} == {
                    policy.id for policy in expected_policies
                }
                assert asn.custom_fields[field_names[5]] == note
            response = nfclient.run_job(
                "netbox",
                "create_asn",
                workers="any",
                kwargs={
                    "asn": asn_number,
                    "rir": rir_name,
                    "custom_fields": {field_names[5]: "scalar update only"},
                },
            )
            for result in response.values():
                assert not result["failed"], result
            asn = nb.ipam.asns.get(asn=asn_number)
            assert asn.custom_fields[field_names[5]] == "scalar update only"
            assert asn.custom_fields[field_names[2]] == ["first", "second"]
            assert {item["id"] for item in asn.custom_fields[field_names[0]]} == {
                device.id for device in devices
            }
            assert {item["id"] for item in asn.custom_fields[field_names[4]]} == {
                policy.id for policy in policies
            }
            if len(list(nb.dcim.interfaces.filter(name="Ethernet1"))) > 1:
                response = nfclient.run_job(
                    "netbox",
                    "create_asn",
                    workers="any",
                    kwargs={
                        "asn": asn_number,
                        "rir": rir_name,
                        "custom_fields": {field_names[3]: ["Ethernet1"]},
                    },
                )
                for result in response.values():
                    assert result["failed"], result
                    assert "matched" in str(result["errors"])
        finally:
            asn = nb.ipam.asns.get(asn=asn_number)
            if asn:
                asn.delete()
            for name in field_names:
                field = nb.extras.custom_fields.get(name=name)
                if field:
                    field.delete()
            for name in site_names:
                site = nb.dcim.sites.get(name=name)
                if site:
                    site.delete()
            rir = nb.ipam.rirs.get(name=rir_name)
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
