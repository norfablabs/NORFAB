from collections.abc import Iterator
from typing import Any

import pytest

from tests.services.netbox.common import get_pynetbox

pytestmark = [
    pytest.mark.netbox,
    pytest.mark.netbox_sync_vlans,
]


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

    def _group_vlan(self, group: Any, vid: int) -> Any:
        return self.nb.ipam.vlans.get(vid=vid, group_id=group.id)

    def test_dry_run_create_and_second_sync_are_end_to_end(self, nfclient: Any) -> None:
        vlan_filter = ["110-111"]

        dry_run = self._sync(
            nfclient,
            [self.DEVICE_1],
            dry_run=True,
            filter_by_vlan_ids=vlan_filter,
        )
        for result in self._successful_results(dry_run):
            actions = result["result"][self._site_scope()]
            assert actions["create"] == [110, 111]
            assert actions["update"] == {}
            assert actions["delete"] == []
        assert self._site_vlan(110) is None
        assert self._site_vlan(111) is None

        first_sync = self._sync(
            nfclient,
            [self.DEVICE_1],
            filter_by_vlan_ids=vlan_filter,
        )
        for result in self._successful_results(first_sync):
            assert result["result"][self._site_scope()]["created"] == [110, 111]

        assert self._site_vlan(110).name == "TEST_L1_TRUNK_A"
        assert self._site_vlan(111).name == "TEST_L1_TRUNK_B"

        second_sync = self._sync(
            nfclient,
            [self.DEVICE_1],
            filter_by_vlan_ids=vlan_filter,
        )
        for result in self._successful_results(second_sync):
            actions = result["result"][self._site_scope()]
            assert actions["created"] == []
            assert actions["updated"] == []
            assert actions["in_sync"] == [110, 111]

    def test_live_sync_updates_name_and_description(self, nfclient: Any) -> None:
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
        assert vlan.description == ""

    def test_vlan_map_uses_netbox_group_ranges_and_site_fallback(
        self, nfclient: Any
    ) -> None:
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

        for result in self._successful_results(response):
            group_actions = result["result"][self._group_scope(self.group_1)]
            assert group_actions["created"] == [110]
            assert result["result"][self._site_scope()]["created"] == [210]
        assert self._group_vlan(self.group_1, 110).name == "TEST_L1_TRUNK_A"
        assert self._site_vlan(210).name == "TEST_L1_ACCESS"

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

    def test_explicit_vlan_ids_narrow_group_ranges(self, nfclient: Any) -> None:
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
            assert result["result"][self._site_scope()]["created"] == [110]
        assert self._group_vlan(self.group_1, 111).name == "TEST_L1_TRUNK_B"
        assert self._site_vlan(110).name == "TEST_L1_TRUNK_A"

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
            assert result["result"][self._site_scope()]["created"] == [121]
        assert self._site_vlan(121).name == "TEST_L2_TRUNK_B"
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

    def test_unknown_vlan_group_fails_before_writes(self, nfclient: Any) -> None:
        response = self._sync(
            nfclient,
            [self.DEVICE_1],
            filter_by_vlan_ids=["110"],
            vlan_group="DOES_NOT_EXIST",
        )

        assert response
        for worker, result in response.items():
            assert result["failed"] is True, f"{worker} did not fail: {result}"
            assert any(
                "does not exist in NetBox" in error for error in result["errors"]
            )
        assert self._site_vlan(110) is None
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
