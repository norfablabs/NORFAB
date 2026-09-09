from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest

from norfab.models import Result
from norfab.workers.netbox_worker.interfaces_tasks import _build_interface_payload
from norfab.workers.netbox_worker.netbox_models import SyncVlansInput
from norfab.workers.netbox_worker.netbox_worker_utilities import (
    resolve_live_vlans,
    validate_vlan_group_scope,
)
from tests.services.netbox.common import get_pynetbox

pytestmark = [
    pytest.mark.netbox,
    pytest.mark.netbox_sync_vlans,
]


class TestVlanResolution:
    @staticmethod
    def _record(**kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(**kwargs)

    @classmethod
    def _device_scope(cls, **overrides: Any) -> dict[str, Any]:
        scope = {
            "device_name": "leaf-1",
            "site_id": 1,
            "site_name": "site-a",
            "region_id": 10,
            "region_name": "region-a",
            "site_group_id": 20,
            "site_group_name": "sites-a",
            "location_id": 30,
            "location_name": "location-a",
            "rack_id": 40,
            "rack_name": "rack-a",
            "rack_group_id": 50,
            "rack_group_name": "racks-a",
        }
        scope.update(overrides)
        return scope

    @classmethod
    def _group(
        cls,
        group_id: int,
        scope_type: str | None = None,
        scope_id: int | None = None,
        vid_ranges: list | None = None,
    ) -> SimpleNamespace:
        return cls._record(
            id=group_id,
            name=f"group-{group_id}",
            vid_ranges=vid_ranges if vid_ranges is not None else [[1, 4094]],
            scope_type=f"dcim.{scope_type}" if scope_type else None,
            scope_id=scope_id,
            scope=(
                cls._record(id=scope_id, name=f"scope-{scope_id}")
                if scope_type
                else None
            ),
        )

    @classmethod
    def _vlan(
        cls,
        vlan_id: int,
        vid: int,
        *,
        site_id: int | None = None,
        group_id: int | None = None,
    ) -> SimpleNamespace:
        return cls._record(
            id=vlan_id,
            vid=vid,
            site=cls._record(id=site_id) if site_id else None,
            group=cls._record(id=group_id) if group_id else None,
        )

    @classmethod
    def _resolve(cls, vlans: list, groups: dict, **live: Any) -> dict:
        return resolve_live_vlans(
            live_vlans=[{"device_name": "leaf-1", "vid": 100, **live}],
            netbox_vlans=vlans,
            vlan_groups=groups,
            device_scopes={"leaf-1": cls._device_scope()},
        )[0]

    def test_group_vlan_precedes_site_and_global_vlan(self) -> None:
        result = self._resolve(
            [
                self._vlan(1, 100),
                self._vlan(2, 100, site_id=1),
                self._vlan(3, 100, group_id=30),
            ],
            {30: self._group(30)},
        )

        assert result["vlan"].id == 3
        assert result["error"] is None

    def test_resolver_skips_incompatible_group_then_uses_compatible_group(
        self,
    ) -> None:
        result = self._resolve(
            [self._vlan(1, 100, group_id=30), self._vlan(2, 100, group_id=31)],
            {30: self._group(30, "site", 2), 31: self._group(31, "region", 10)},
        )

        assert result["vlan"].id == 2

    def test_site_vlan_precedes_global_fallback(self) -> None:
        result = self._resolve([self._vlan(1, 100), self._vlan(2, 100, site_id=1)], {})

        assert result["vlan"].id == 2

    def test_global_vlan_is_used_as_fallback(self) -> None:
        result = self._resolve([self._vlan(1, 100)], {})

        assert result["vlan"].id == 1

    def test_explicit_group_scope_mismatch_is_error_without_fallback(self) -> None:
        result = self._resolve(
            [self._vlan(1, 100, site_id=1)],
            {30: self._group(30, "site", 2)},
            selected_group_id=30,
        )

        assert result["vlan"] is None
        assert "scoped to site 'scope-2'" in result["error"]
        assert "site 'site-a'" in result["error"]

    @pytest.mark.parametrize(
        ("scope_type", "scope_id"),
        [
            ("site", 1),
            ("region", 10),
            ("sitegroup", 20),
            ("location", 30),
            ("rack", 40),
            ("rackgroup", 50),
        ],
    )
    def test_group_scope_requires_exact_direct_match(
        self, scope_type: str, scope_id: int
    ) -> None:
        assert (
            validate_vlan_group_scope(
                self._group(30, scope_type, scope_id), self._device_scope(), 100
            )
            is None
        )
        assert (
            validate_vlan_group_scope(
                self._group(31, scope_type, 999), self._device_scope(), 100
            )
            is not None
        )

    @pytest.mark.parametrize(
        ("scope_type", "id_field", "name_field"),
        [
            ("location", "location_id", "location_name"),
            ("rack", "rack_id", "rack_name"),
            ("rackgroup", "rack_group_id", "rack_group_name"),
        ],
    )
    def test_missing_device_scope_rejects_group(
        self, scope_type: str, id_field: str, name_field: str
    ) -> None:
        device_scope = self._device_scope(**{id_field: None, name_field: None})

        error = validate_vlan_group_scope(
            self._group(30, scope_type, 999), device_scope, 100
        )

        assert "no assignment" in error

    def test_multiple_equally_preferred_vlans_is_error(self) -> None:
        result = self._resolve(
            [self._vlan(1, 100, group_id=30), self._vlan(2, 100, group_id=31)],
            {30: self._group(30), 31: self._group(31)},
        )

        assert result["vlan"] is None
        assert "multiple equally preferred" in result["error"]
        assert "VLAN IDs: 1, 2" in result["error"]

    def test_cluster_scoped_group_is_ignored(self) -> None:
        result = self._resolve(
            [self._vlan(1, 100, group_id=30), self._vlan(2, 100, site_id=1)],
            {30: self._group(30, "cluster", 60)},
        )

        assert result["vlan"].id == 2

    def test_group_vid_ranges_use_native_integer_pairs(self) -> None:
        result = self._resolve(
            [self._vlan(1, 100, group_id=30)],
            {30: self._group(30, vid_ranges=[[1, 20], [50, 100]])},
        )

        assert result["vlan"].id == 1

    def test_out_of_range_group_candidate_falls_back_to_site(self) -> None:
        result = self._resolve(
            [self._vlan(1, 100, group_id=30), self._vlan(2, 100, site_id=1)],
            {30: self._group(30, vid_ranges=[[1, 20]])},
        )

        assert result["vlan"].id == 2

    def test_explicit_out_of_range_group_is_error_without_fallback(self) -> None:
        result = self._resolve(
            [self._vlan(1, 100, site_id=1)],
            {30: self._group(30, vid_ranges=[[1, 20]])},
            selected_group_id=30,
        )

        assert result["vlan"] is None
        assert "outside VLAN group 'group-30' VID ranges" in result["error"]

    def test_unresolved_bulk_created_vlans_are_omitted_from_interface_payload(
        self,
    ) -> None:
        desired = {
            "description": "live description",
            "untagged_vlan": 100,
            "tagged_vlans": [100, 200],
            "qinq_svlan": 200,
        }
        unresolved = {
            ("leaf-1", "Ethernet1", 100): ("new", "site", 1, 100),
            ("leaf-1", "Ethernet1", 200): ("new", "site", 1, 200),
        }

        payload = _build_interface_payload(
            job=object(),
            desired=desired,
            ret=Result(task="test"),
            worker_name="test",
            changed_fields=set(desired),
            name_to_id={},
            device={"id": 1, "name": "leaf-1"},
            intf_name="Ethernet1",
            resolved_vlans=unresolved,
        )

        assert payload == {
            "device": 1,
            "name": "Ethernet1",
            "description": "live description",
        }


class TestSyncVlans:
    DEVICE_1 = "fn-ceos-lf-1"
    DEVICE_2 = "fn-ceos-lf-2"
    SITE_NAME = "NORFAB-LAB"
    GROUP_1_NAME = "SYNC_VLANS_GROUP_1"
    GROUP_2_NAME = "SYNC_VLANS_GROUP_2"
    TEST_VIDS = {110, 111, 120, 121, 190, 191, 199, 210}

    @pytest.fixture(autouse=True)
    def cleanup_test_vlans(self, nfclient: Any) -> Iterator[None]:
        self.nb = get_pynetbox(nfclient)
        self.site = self.nb.dcim.sites.get(name=self.SITE_NAME)
        self.group_1 = self.nb.ipam.vlan_groups.get(name=self.GROUP_1_NAME)
        self.group_2 = self.nb.ipam.vlan_groups.get(name=self.GROUP_2_NAME)
        assert self.site is not None
        assert self.group_1 is not None
        assert self.group_2 is not None
        self._delete_test_vlans()
        yield
        self._delete_test_vlans()

    def _delete_test_vlans(self) -> None:
        for vid in self.TEST_VIDS:
            for vlan in list(self.nb.ipam.vlans.filter(vid=vid, site_id=self.site.id)):
                vlan.delete()
            for group in (self.group_1, self.group_2):
                for vlan in list(self.nb.ipam.vlans.filter(vid=vid, group_id=group.id)):
                    vlan.delete()

    @staticmethod
    def _sync(nfclient: Any, devices: list[str], **kwargs: object) -> dict:
        return nfclient.run_job(
            "netbox",
            "sync_vlans",
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

    def _site_scope(self) -> str:
        return f"site:{self.site.name}"

    @staticmethod
    def _group_scope(group: Any) -> str:
        return f"group:{group.name}"

    def _site_vlan(self, vid: int) -> Any:
        return self.nb.ipam.vlans.get(vid=vid, site_id=self.site.id)

    def _global_vlan(self, vid: int) -> Any:
        return next(
            (
                vlan
                for vlan in self.nb.ipam.vlans.filter(vid=vid)
                if not vlan.site and not vlan.group
            ),
            None,
        )

    def _group_vlan(self, group: Any, vid: int) -> Any:
        return self.nb.ipam.vlans.get(vid=vid, group_id=group.id)

    def test_require_vlan_group_defaults_and_alias(self) -> None:
        assert SyncVlansInput().require_vlan_group is False
        model = SyncVlansInput.model_validate({"require-vlan-group": True})
        assert model.require_vlan_group is True

    def test_dry_run_create_and_second_sync_are_end_to_end(self, nfclient: Any) -> None:
        vlan_filter = ["190-191"]

        dry_run = self._sync(
            nfclient,
            [self.DEVICE_1],
            dry_run=True,
            filter_by_vlan_ids=vlan_filter,
        )
        for result in self._successful_results(dry_run):
            actions = result["result"][self._site_scope()]
            assert actions["create"] == [190, 191]
            assert actions["update"] == {}
            assert actions["delete"] == []
        assert self._site_vlan(190) is None
        assert self._site_vlan(191) is None

        first_sync = self._sync(
            nfclient,
            [self.DEVICE_1],
            filter_by_vlan_ids=vlan_filter,
        )
        for result in self._successful_results(first_sync):
            assert result["result"][self._site_scope()]["created"] == [190, 191]

        assert self._site_vlan(190).name == "TEST_SYNC_CONFLICT_L1"
        assert self._site_vlan(191).name == "TEST_SYNC_SHARED"

        second_sync = self._sync(
            nfclient,
            [self.DEVICE_1],
            filter_by_vlan_ids=vlan_filter,
        )
        for result in self._successful_results(second_sync):
            actions = result["result"][self._site_scope()]
            assert actions["created"] == []
            assert actions["updated"] == []
            assert actions["in_sync"] == [190, 191]

    def test_live_sync_description_preservation_modes(self, nfclient: Any) -> None:
        self.nb.ipam.vlans.create(
            vid=120,
            name="VLAN_120",
            description="stale description",
            site=self.site.id,
        )

        response = self._sync(
            nfclient,
            [self.DEVICE_2],
            filter_by_vlan_ids=["120"],
        )

        for result in self._successful_results(response):
            assert result["result"][self._site_scope()]["updated"] == [120]
        vlan = self._site_vlan(120)
        assert vlan.name == "TEST_L2_TRUNK_A"
        assert vlan.description == "stale description"

        response = self._sync(
            nfclient,
            [self.DEVICE_2],
            filter_by_vlan_ids=["120"],
            preserve_description=False,
        )

        for result in self._successful_results(response):
            assert result["result"][self._site_scope()]["updated"] == [120]
        vlan = self._site_vlan(120)
        assert vlan.description == ""

    def test_vlan_map_group_range_mismatch_is_reported(self, nfclient: Any) -> None:
        response = self._sync(
            nfclient,
            [self.DEVICE_1],
            filter_by_vlan_ids=["110", "210"],
            vlan_map=[
                {
                    "set_vlan_group": self.GROUP_1_NAME,
                    "vlan_names": ["TEST_L1*"],
                    "match_device_names": ["fn-ceos-lf-*"],
                    "match_interface_names": ["ignored-by-vlan-sync"],
                }
            ],
        )

        for worker, result in response.items():
            assert result["failed"] is False, f"{worker} failed: {result}"
            assert any(
                "VLAN 210 is outside VLAN group" in error and self.GROUP_1_NAME in error
                for error in result["errors"]
            )
            group_actions = result["result"][self._group_scope(self.group_1)]
            assert group_actions["created"] == [110]
        assert self._group_vlan(self.group_1, 110).name == "TEST_L1_TRUNK_A"
        assert self._site_vlan(210) is None
        assert self._global_vlan(210).name == "TEST_L1_ACCESS"

    def test_vlan_map_from_nf_url(self, nfclient: Any) -> None:
        response = self._sync(
            nfclient,
            [self.DEVICE_1],
            dry_run=True,
            filter_by_vlan_ids=["110"],
            vlan_map="nf://netbox/vlan_map.yaml",
        )

        for result in self._successful_results(response):
            assert self._group_scope(self.group_1) in result["result"]

    def test_explicit_vlan_ids_narrow_vlan_map_match(self, nfclient: Any) -> None:
        response = self._sync(
            nfclient,
            [self.DEVICE_1],
            filter_by_vlan_ids=["110-111"],
            vlan_map=[
                {
                    "set_vlan_group": self.GROUP_1_NAME,
                    "match_vlan_ids": ["111"],
                }
            ],
        )

        for result in self._successful_results(response):
            group_actions = result["result"][self._group_scope(self.group_1)]
            assert group_actions["created"] == [111]
            assert result["result"]["global"]["in_sync"] == [110]
        assert self._group_vlan(self.group_1, 111).name == "TEST_L1_TRUNK_B"
        assert self._site_vlan(110) is None
        assert self._global_vlan(110).name == "TEST_L1_TRUNK_A"

    def test_vlan_map_matches_vlan_and_device_name_globs(self, nfclient: Any) -> None:
        response = self._sync(
            nfclient,
            [self.DEVICE_1],
            filter_by_vlan_ids=["110-111"],
            vlan_map=[
                {
                    "set_vlan_group": self.GROUP_1_NAME,
                    "vlan_names": ["*_TRUNK_A"],
                    "match_device_names": ["fn-ceos-lf-1"],
                },
                {
                    "set_vlan_group": self.GROUP_2_NAME,
                    "vlan_names": ["*_TRUNK_B"],
                    "match_device_names": ["fn-ceos-lf-*"],
                },
            ],
        )

        for result in self._successful_results(response):
            group_1_actions = result["result"][self._group_scope(self.group_1)]
            group_2_actions = result["result"][self._group_scope(self.group_2)]
            assert group_1_actions["created"] == [110]
            assert group_2_actions["created"] == [111]
        assert self._group_vlan(self.group_1, 110).name == "TEST_L1_TRUNK_A"
        assert self._group_vlan(self.group_2, 111).name == "TEST_L1_TRUNK_B"

    def test_vlan_map_first_matching_rule_wins(self, nfclient: Any) -> None:
        response = self._sync(
            nfclient,
            [self.DEVICE_1],
            filter_by_vlan_ids=["110"],
            vlan_map=[
                {
                    "set_vlan_group": self.GROUP_1_NAME,
                    "vlan_names": ["TEST_L1_TRUNK_A"],
                },
                {
                    "set_vlan_group": self.GROUP_2_NAME,
                    "vlan_names": ["TEST_L1_TRUNK_A"],
                },
            ],
        )

        for result in self._successful_results(response):
            group_1_actions = result["result"][self._group_scope(self.group_1)]
            group_2_actions = result["result"][self._group_scope(self.group_2)]
            assert group_1_actions["created"] == [110]
            assert group_2_actions["created"] == []
        assert self._group_vlan(self.group_1, 110).name == "TEST_L1_TRUNK_A"
        assert self._group_vlan(self.group_2, 110) is None

    def test_vlan_map_device_mismatch_falls_back_to_site(self, nfclient: Any) -> None:
        response = self._sync(
            nfclient,
            [self.DEVICE_2],
            filter_by_vlan_ids=["121"],
            vlan_map=[
                {
                    "set_vlan_group": self.GROUP_1_NAME,
                    "match_device_names": [self.DEVICE_1],
                }
            ],
        )

        for result in self._successful_results(response):
            assert result["result"]["global"]["in_sync"] == [121]
        assert self._site_vlan(121) is None
        assert self._global_vlan(121).name == "TEST_L2_TRUNK_B"
        assert self._group_vlan(self.group_1, 121) is None

    def test_require_vlan_group_skips_unmapped_vlan(self, nfclient: Any) -> None:
        response = self._sync(
            nfclient,
            [self.DEVICE_2],
            filter_by_vlan_ids=["121"],
            require_vlan_group=True,
            vlan_map=[
                {
                    "set_vlan_group": self.GROUP_1_NAME,
                    "match_device_names": [self.DEVICE_1],
                }
            ],
        )

        assert response
        for worker, result in response.items():
            assert result["failed"] is False, f"{worker} failed: {result}"
            assert any(
                "VLAN 121" in error and "no VLAN group mapping found" in error
                for error in result["errors"]
            )
            assert result["result"][self._site_scope()]["created"] == []
        assert self._site_vlan(121) is None
        assert self._group_vlan(self.group_1, 121) is None

    def test_site_scope_uses_first_device_for_conflicting_vid(
        self, nfclient: Any
    ) -> None:
        response = self._sync(
            nfclient,
            [self.DEVICE_1, self.DEVICE_2],
            filter_by_vlan_ids=["190-191"],
        )

        assert response
        for worker, result in response.items():
            assert result["failed"] is False, f"{worker} failed: {result}"
            assert result["result"][self._site_scope()]["created"] == [190, 191]
            conflict = next(
                error
                for error in result["errors"]
                if "VLAN 190 source conflict" in error
            )
            assert self.DEVICE_1 in conflict
            assert self.DEVICE_2 in conflict
        site_vlans = [
            vlan
            for vid in (190, 191)
            for vlan in self.nb.ipam.vlans.filter(vid=vid, site_id=self.site.id)
        ]
        assert sorted((vlan.vid, vlan.name) for vlan in site_vlans) == [
            (190, "TEST_SYNC_CONFLICT_L1"),
            (191, "TEST_SYNC_SHARED"),
        ]

    def test_group_identity_reports_conflicting_names(self, nfclient: Any) -> None:
        response = self._sync(
            nfclient,
            [self.DEVICE_1, self.DEVICE_2],
            dry_run=True,
            filter_by_vlan_ids=["190"],
            vlan_map=[
                {
                    "set_vlan_group": self.GROUP_1_NAME,
                    "match_vlan_ids": ["190"],
                }
            ],
        )

        assert response
        for worker, result in response.items():
            assert result["failed"] is False, f"{worker} failed: {result}"
            assert result["result"][self._group_scope(self.group_1)]["create"] == [190]
            conflict = next(
                error
                for error in result["errors"]
                if "VLAN 190 source conflict" in error
            )
            assert self.DEVICE_1 in conflict
            assert self.DEVICE_2 in conflict

    def test_vlan_map_precedes_vlan_group(self, nfclient: Any) -> None:
        response = self._sync(
            nfclient,
            [self.DEVICE_1],
            filter_by_vlan_ids=["110", "210"],
            vlan_group=self.GROUP_2_NAME,
            require_vlan_group=True,
            vlan_map=[
                {
                    "set_vlan_group": self.GROUP_1_NAME,
                    "match_vlan_ids": ["110"],
                }
            ],
        )

        for result in self._successful_results(response):
            assert result["result"][self._group_scope(self.group_1)]["created"] == [110]
            assert result["result"][self._group_scope(self.group_2)]["created"] == [210]
            assert result["result"][self._site_scope()]["created"] == []
        assert self._group_vlan(self.group_1, 110).name == "TEST_L1_TRUNK_A"
        assert self._group_vlan(self.group_2, 210).name == "TEST_L1_ACCESS"
        assert self._site_vlan(110) is None
        assert self._site_vlan(210) is None

    def test_unknown_vlan_map_group_skips_matching_vlans(self, nfclient: Any) -> None:
        response = self._sync(
            nfclient,
            [self.DEVICE_1],
            filter_by_vlan_ids=["110", "210"],
            vlan_map=[
                {
                    "set_vlan_group": "DOES_NOT_EXIST",
                    "match_vlan_ids": ["110"],
                }
            ],
        )

        assert response
        for worker, result in response.items():
            assert result["failed"] is False, f"{worker} failed: {result}"
            assert any(
                "VLAN 110" in error
                and "skipped" in error
                and "does not exist in NetBox" in error
                for error in result["errors"]
            )
        assert self._site_vlan(110) is None
        assert self._site_vlan(210) is None
        assert self._global_vlan(210).name == "TEST_L1_ACCESS"
        assert self._group_vlan(self.group_1, 110) is None
        assert self._group_vlan(self.group_2, 110) is None

    def test_unmatched_netbox_vlan_is_not_deleted(self, nfclient: Any) -> None:
        self.nb.ipam.vlans.create(
            vid=199,
            name="KEEP_ME",
            site=self.site.id,
        )

        response = self._sync(
            nfclient,
            [self.DEVICE_1],
            filter_by_vlan_ids=["199"],
        )

        for result in self._successful_results(response):
            actions = result["result"][self._site_scope()]
            assert actions["deleted"] == []
            assert result["diff"][self._site_scope()]["delete"] == []
        assert self._site_vlan(199).name == "KEEP_ME"

    def test_device_compatible_group_scope_precedes_direct_site_vlan(
        self, nfclient: Any
    ) -> None:
        group_name = "SYNC_VLANS_SCOPED_SITE"
        old_group = self.nb.ipam.vlan_groups.get(name=group_name)
        if old_group:
            for vlan in list(self.nb.ipam.vlans.filter(group_id=old_group.id)):
                vlan.delete()
            old_group.delete()
        group = self.nb.ipam.vlan_groups.create(
            name=group_name,
            slug="sync-vlans-scoped-site",
            scope_type="dcim.site",
            scope_id=self.site.id,
            vid_ranges=[[100, 199]],
        )
        self.nb.ipam.vlans.create(
            vid=110,
            name="STALE_SITE_VLAN",
            site=self.site.id,
        )
        self.nb.ipam.vlans.create(
            vid=110,
            name="STALE_GROUP_VLAN",
            group=group.id,
        )

        try:
            response = self._sync(
                nfclient,
                [self.DEVICE_1],
                dry_run=True,
                filter_by_vlan_ids=["110"],
            )

            for result in self._successful_results(response):
                assert result["result"][self._group_scope(group)]["update"] == {
                    "110": {
                        "name": {
                            "old_value": "STALE_GROUP_VLAN",
                            "new_value": "TEST_L1_TRUNK_A",
                        }
                    }
                }
                assert result["result"][self._site_scope()]["update"] == {}
        finally:
            for vlan in list(self.nb.ipam.vlans.filter(group_id=group.id)):
                vlan.delete()
            group.delete()

    def test_vlan_map_group_scope_mismatch_is_reported(self, nfclient: Any) -> None:
        group_name = "SYNC_VLANS_WRONG_SITE"
        other_site = self.nb.dcim.sites.get(name="SALTNORNIR-LAB2")
        assert other_site is not None
        old_group = self.nb.ipam.vlan_groups.get(name=group_name)
        if old_group:
            for vlan in list(self.nb.ipam.vlans.filter(group_id=old_group.id)):
                vlan.delete()
            old_group.delete()
        group = self.nb.ipam.vlan_groups.create(
            name=group_name,
            slug="sync-vlans-wrong-site",
            scope_type="dcim.site",
            scope_id=other_site.id,
            vid_ranges=[[100, 199]],
        )

        try:
            response = self._sync(
                nfclient,
                [self.DEVICE_1],
                dry_run=True,
                filter_by_vlan_ids=["110"],
                vlan_map=[
                    {
                        "set_vlan_group": group_name,
                        "match_vlan_ids": ["110"],
                    }
                ],
            )

            for worker, result in response.items():
                assert result["failed"] is False, f"{worker} failed: {result}"
                assert any(
                    "scoped to site 'SALTNORNIR-LAB2'" in error
                    and "device 'fn-ceos-lf-1'" in error
                    and "fix the VLAN map mapping" in error
                    for error in result["errors"]
                )
                assert result["result"][self._group_scope(group)]["create"] == []
                assert result["result"][self._site_scope()]["create"] == []
        finally:
            for vlan in list(self.nb.ipam.vlans.filter(group_id=group.id)):
                vlan.delete()
            group.delete()
