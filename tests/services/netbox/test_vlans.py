from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import orjson
import pytest

from norfab.workers.netbox_worker.netbox_models import SyncVlansInput
from norfab.workers.netbox_worker.netbox_worker import NetboxWorker
from norfab.workers.netbox_worker.vlan_tasks import (
    resolve_live_vlans,
    validate_vlan_group_scope,
)
from tests.services.netbox.common import get_pynetbox

pytestmark = [
    pytest.mark.netbox,
    pytest.mark.netbox_sync_vlans,
]


class TestSyncVlanMemberships:
    """Exercise collection, the real diff, and writes without network services."""

    @staticmethod
    def _live(
        vid: int = 50, tagged: tuple = (), untagged: tuple = (), **values: Any
    ) -> dict:
        return {
            "vid": vid,
            "name": f"VLAN{vid}",
            "description": None,
            "tagged_interfaces": list(tagged),
            "untagged_interfaces": list(untagged),
            **values,
        }

    @staticmethod
    def _vlan(vid: int, group: Any = None, **values: Any) -> SimpleNamespace:
        return SimpleNamespace(
            **{
                "id": vid + 1000,
                "vid": vid,
                "name": f"VLAN{vid}",
                "description": "",
                "group": group,
                "site": None if group else SimpleNamespace(id=1, name="lab"),
                **values,
            }
        )

    @staticmethod
    def _interface(
        name: str = "Ethernet6",
        device: str = "leaf-1",
        tagged: tuple = (),
        untagged: Any = None,
        mode: str = "tagged",
        interface_id: int = 10,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            id=interface_id,
            name=name,
            device=SimpleNamespace(name=device),
            tagged_vlans=list(tagged),
            untagged_vlan=untagged,
            mode=SimpleNamespace(value=mode) if mode else None,
        )

    def _run(
        self,
        records: dict,
        vlans: list | None = None,
        interfaces: list | None = None,
        groups: list | None = None,
        dry_run: bool = True,
        create_error: bool = False,
        **kwargs: Any,
    ) -> tuple:
        vlans, interfaces, groups = (
            list(vlans or []),
            list(interfaces or []),
            list(groups or []),
        )
        site = SimpleNamespace(id=1, name="lab", region=None, group=None)
        devices = [
            SimpleNamespace(
                id=index,
                name=name,
                site=site,
                rack=None,
                location=None,
                device_type=SimpleNamespace(model="test"),
            )
            for index, name in enumerate(records, 1)
        ]
        nb = SimpleNamespace(
            dcim=SimpleNamespace(devices=Mock(), interfaces=Mock()),
            ipam=SimpleNamespace(vlans=Mock(), vlan_groups=Mock()),
        )
        nb.dcim.devices.filter.return_value = devices
        nb.dcim.interfaces.filter.return_value = interfaces
        nb.ipam.vlan_groups.get.side_effect = lambda name: next(
            (g for g in groups if g.name == name), None
        )
        nb.ipam.vlan_groups.filter.side_effect = lambda id, **_: [
            g for g in groups if g.id in id
        ]
        nb.ipam.vlans.filter.side_effect = lambda **filters: [
            v
            for v in vlans
            if ("vid" not in filters or v.vid in filters["vid"])
            and ("id" not in filters or v.id in filters["id"])
        ]

        def create(payloads: list) -> list:
            if create_error:
                raise RuntimeError("creation failed")
            created = []
            for payload in payloads:
                group = next((g for g in groups if g.id == payload.get("group")), None)
                vlan = self._vlan(
                    payload["vid"],
                    group=group,
                    id=2000 + len(vlans),
                    name=payload["name"],
                    description=payload["description"],
                )
                vlans.append(vlan)
                created.append(vlan)
            return created

        def update_interfaces(payloads: list) -> None:
            by_id = {v.id: v for v in vlans}
            for payload in payloads:
                interface = next(i for i in interfaces if i.id == payload["id"])
                interface.tagged_vlans = [by_id[vid] for vid in payload["tagged_vlans"]]
                interface.untagged_vlan = by_id.get(payload["untagged_vlan"])
                if "mode" in payload:
                    interface.mode = SimpleNamespace(value=payload["mode"])

        nb.ipam.vlans.create.side_effect = create
        nb.dcim.interfaces.update.side_effect = update_interfaces
        worker = object.__new__(NetboxWorker)
        worker.name, worker.default_instance = "test", "test"
        worker._get_pynetbox = Mock(return_value=nb)
        worker.client = Mock()
        worker.client.run_job.return_value = {"nornir": {"result": records}}
        worker.bulk_filter = lambda endpoint, **filters: list(
            endpoint.filter(**filters)
        )
        job = SimpleNamespace(event=Mock(), request_input=Mock(return_value=False))
        result = worker.sync_vlans(
            job, devices=list(records), dry_run=dry_run, **kwargs
        )
        orjson.dumps(result.model_dump())
        return result, nb, worker, job

    def test_duplicate_records_create_once_with_both_memberships_and_second_run_is_in_sync(
        self,
    ) -> None:
        record = self._live(tagged=("Ethernet6", "Ethernet6"), untagged=("Ethernet6",))
        result, nb, worker, job = self._run(
            {"leaf-1": [record, record]},
            interfaces=[self._interface(mode="")],
            dry_run=False,
        )
        assert not result.failed and not result.errors
        assert result.result["site:lab"]["created"] == [50]
        nb.ipam.vlans.create.assert_called_once()
        assert nb.dcim.interfaces.update.call_args.args[0] == [
            {"id": 10, "tagged_vlans": [2000], "untagged_vlan": 2000, "mode": "tagged"}
        ]
        nb.dcim.interfaces.update.reset_mock()
        second = worker.sync_vlans(job, devices=["leaf-1"])
        assert second.result["site:lab"]["in_sync"] == [50]
        nb.dcim.interfaces.update.assert_not_called()

    def test_existing_membership_diff_preserves_unmanaged_tagged_vlan(self) -> None:
        vlan, unmanaged = self._vlan(50), self._vlan(900)
        result, nb, _, _ = self._run(
            {"leaf-1": [self._live(tagged=("Ethernet5",))]},
            vlans=[vlan, unmanaged],
            interfaces=[
                self._interface(tagged=(vlan, unmanaged)),
                self._interface("Ethernet5", interface_id=11),
            ],
            dry_run=False,
        )
        assert not result.failed and not result.errors
        assert result.diff["site:lab"]["update"]["50"]["tagged_interfaces"] == {
            "old_value": ["leaf-1:Ethernet6"],
            "new_value": ["leaf-1:Ethernet5"],
        }
        payloads = {p["id"]: p for p in nb.dcim.interfaces.update.call_args.args[0]}
        assert payloads[10]["tagged_vlans"] == [unmanaged.id]
        assert payloads[11]["tagged_vlans"] == [vlan.id]
        nb.ipam.vlans.update.assert_not_called()

    def test_native_replacement_outside_filter_is_in_same_diff(self) -> None:
        previous = self._vlan(900, description="keep this")
        result, nb, _, _ = self._run(
            {"leaf-1": [self._live(untagged=("Ethernet6",))]},
            vlans=[previous],
            interfaces=[self._interface(untagged=previous, tagged=(previous,))],
            filter_by_vlan_ids=["50"],
            dry_run=False,
        )
        assert not result.failed and not result.errors
        actions = result.diff["site:lab"]
        assert actions["create"] == [50]
        assert actions["create_details"]["50"]["untagged_interfaces"] == [
            "leaf-1:Ethernet6"
        ]
        assert actions["update"]["900"] == {
            "untagged_interfaces": {"old_value": ["leaf-1:Ethernet6"], "new_value": []}
        }
        payload = nb.dcim.interfaces.update.call_args.args[0][0]
        assert payload["untagged_vlan"] == 2001
        assert payload["tagged_vlans"] == [previous.id]
        nb.ipam.vlans.update.assert_not_called()

    def test_mapping_splits_same_vid_by_interface(self) -> None:
        groups = [TestVlanResolution._group(30), TestVlanResolution._group(40)]
        result, nb, _, _ = self._run(
            {"leaf-1": [self._live(tagged=("Ethernet5", "Ethernet6"))]},
            groups=groups,
            interfaces=[
                self._interface(),
                self._interface("Ethernet5", interface_id=11),
            ],
            vlan_map=[
                {"set_vlan_group": "group-30", "match_interface_names": ["Ethernet5"]}
            ],
            vlan_group="group-40",
            dry_run=False,
        )
        assert not result.failed and not result.errors
        assert result.result["group:group-30"]["created"] == [50]
        assert result.result["group:group-40"]["created"] == [50]
        payloads = {p["id"]: p for p in nb.dcim.interfaces.update.call_args.args[0]}
        assert payloads[11]["tagged_vlans"] == [2000]
        assert payloads[10]["tagged_vlans"] == [2001]

    def test_interface_map_is_applied_before_membership_lookup(self) -> None:
        result, nb, _, _ = self._run(
            {"leaf-1": [self._live(tagged=("Ethernet6",))]},
            interfaces=[self._interface(name="Et6")],
            interface_map=[
                {
                    "device_name": "leaf-*",
                    "device_type": "test",
                    "match": "Ethernet",
                    "replace": "Et",
                }
            ],
            dry_run=False,
        )

        assert not result.failed and not result.errors
        assert result.diff["site:lab"]["create_details"]["50"]["tagged_interfaces"] == [
            "leaf-1:Et6"
        ]
        assert nb.dcim.interfaces.update.call_args.args[0][0]["tagged_vlans"] == [2000]

    def test_interface_rule_does_not_match_vlan_without_interfaces(self) -> None:
        result, nb, _, _ = self._run(
            {"leaf-1": [self._live()]},
            groups=[TestVlanResolution._group(30)],
            vlan_map=[{"set_vlan_group": "group-30", "match_interface_names": ["*"]}],
        )
        assert not result.failed and not result.errors
        assert result.result["site:lab"]["create"] == [50]
        assert result.result["group:group-30"]["create"] == []
        nb.ipam.vlans.create.assert_not_called()

    def test_shared_vlan_keeps_all_devices_memberships_despite_name_conflict(
        self,
    ) -> None:
        result, _, _, _ = self._run(
            {
                "leaf-2": [self._live(tagged=("Ethernet6",), name="other")],
                "leaf-1": [self._live(untagged=("Ethernet6",))],
            },
            interfaces=[
                self._interface(),
                self._interface(device="leaf-2", interface_id=11),
            ],
        )
        assert not result.failed
        assert len(result.errors) == 1 and "source conflict" in result.errors[0]
        desired = result.result["site:lab"]["create_details"]["50"]
        assert desired["name"] == "VLAN50"
        assert desired["tagged_interfaces"] == ["leaf-2:Ethernet6"]
        assert desired["untagged_interfaces"] == ["leaf-1:Ethernet6"]

    def test_creation_failure_stops_attribute_and_interface_updates(self) -> None:
        result, nb, _, _ = self._run(
            {
                "leaf-1": [
                    self._live(untagged=("Ethernet6",)),
                    self._live(102, name="new-name"),
                ]
            },
            vlans=[self._vlan(102)],
            interfaces=[self._interface()],
            create_error=True,
            dry_run=False,
        )
        assert result.failed and "creation failed" in result.errors[-1]
        nb.ipam.vlans.update.assert_not_called()
        nb.dcim.interfaces.update.assert_not_called()

    @pytest.mark.parametrize("with_approval", [False, True])
    def test_preview_and_declined_approval_never_write(
        self, with_approval: bool
    ) -> None:
        result, nb, _, job = self._run(
            {"leaf-1": [self._live(untagged=("Ethernet6",))]},
            interfaces=[self._interface()],
            dry_run=not with_approval,
            with_approval=with_approval,
        )
        assert result.dry_run and not result.failed
        assert result.result["site:lab"]["create_details"]["50"][
            "untagged_interfaces"
        ] == ["leaf-1:Ethernet6"]
        assert job.request_input.call_count == int(with_approval)
        nb.ipam.vlans.create.assert_not_called()
        nb.ipam.vlans.update.assert_not_called()
        nb.dcim.interfaces.update.assert_not_called()

    def test_missing_interface_fails_before_writes(self) -> None:
        result, nb, _, _ = self._run(
            {"leaf-1": [self._live(tagged=("Ethernet404",))]}, dry_run=False
        )
        assert result.failed and "not found in NetBox" in result.errors[-1]
        nb.ipam.vlans.create.assert_not_called()

    def test_multiple_untagged_vlans_fail_before_writes(self) -> None:
        result, nb, _, _ = self._run(
            {
                "leaf-1": [
                    self._live(50, untagged=("Ethernet6",)),
                    self._live(102, untagged=("Ethernet6",)),
                ]
            },
            interfaces=[self._interface()],
            dry_run=False,
        )
        assert result.failed and "multiple live untagged VLANs" in result.errors[-1]
        nb.ipam.vlans.create.assert_not_called()

    def test_empty_memberships_clear_only_managed_device_vlan(self) -> None:
        vlan = self._vlan(50)
        result, nb, _, _ = self._run(
            {"leaf-1": [self._live()], "leaf-2": []},
            vlans=[vlan],
            interfaces=[
                self._interface(tagged=(vlan,), untagged=vlan),
                self._interface(device="leaf-2", tagged=(vlan,), interface_id=11),
            ],
            dry_run=False,
        )
        assert not result.failed and not result.errors
        assert nb.dcim.interfaces.update.call_args.args[0] == [
            {"id": 10, "tagged_vlans": [], "untagged_vlan": None}
        ]

    def test_later_creation_failure_reports_earlier_created_vlan(self) -> None:
        groups = [TestVlanResolution._group(30), TestVlanResolution._group(40)]
        rules = [
            {"set_vlan_group": "group-30", "match_vlan_ids": ["50"]},
            {"set_vlan_group": "group-40", "match_vlan_ids": ["102"]},
        ]
        _, nb, worker, job = self._run(
            {"leaf-1": [self._live(), self._live(102)]},
            groups=groups,
            vlan_map=rules,
        )
        nb.ipam.vlans.create.side_effect = [
            [self._vlan(50, group=groups[0])],
            RuntimeError("second scope failed"),
        ]
        result = worker.sync_vlans(job, devices=["leaf-1"], vlan_map=rules)
        assert result.failed
        assert result.result["group:group-30"]["created"] == [50]
        assert result.result["group:group-40"]["created"] == []
        nb.ipam.vlans.update.assert_not_called()
        nb.dcim.interfaces.update.assert_not_called()

    def test_different_tagged_and_untagged_vids_share_one_interface_payload(
        self,
    ) -> None:
        result, nb, _, _ = self._run(
            {
                "leaf-1": [
                    self._live(tagged=("Ethernet6",)),
                    self._live(102, untagged=("Ethernet6",)),
                ]
            },
            interfaces=[self._interface()],
            dry_run=False,
        )
        assert not result.failed and not result.errors
        assert nb.dcim.interfaces.update.call_args.args[0] == [
            {"id": 10, "mode": "tagged", "tagged_vlans": [2000], "untagged_vlan": 2001}
        ]

    def test_untagged_only_sets_access_mode(self) -> None:
        result, nb, _, _ = self._run(
            {"leaf-1": [self._live(untagged=("Ethernet6",))]},
            interfaces=[self._interface(mode="tagged-all")],
            dry_run=False,
        )
        assert not result.failed and not result.errors
        assert nb.dcim.interfaces.update.call_args.args[0] == [
            {
                "id": 10,
                "mode": "access",
                "tagged_vlans": [],
                "untagged_vlan": 2000,
            }
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
        # VLAN sync now assigns existing interfaces. Supply the live LAGs and
        # restore memberships after each test so interface tests remain isolated.
        created_interfaces = []
        original_interfaces = []
        for device_name, lag_name in (
            (self.DEVICE_1, "Port-Channel31"),
            (self.DEVICE_2, "Port-Channel32"),
        ):
            device = self.nb.dcim.devices.get(name=device_name)
            interfaces = list(self.nb.dcim.interfaces.filter(device_id=device.id))
            original_interfaces.extend(
                {
                    "id": interface.id,
                    "mode": interface.mode.value if interface.mode else "",
                    "tagged_vlans": [vlan.id for vlan in interface.tagged_vlans],
                    "untagged_vlan": (
                        interface.untagged_vlan.id if interface.untagged_vlan else None
                    ),
                }
                for interface in interfaces
            )
            for name, interface_type in (
                (lag_name, "lag"),
                ("Ethernet5", "1000base-t"),
            ):
                interface = next(
                    (item for item in interfaces if item.name == name), None
                )
                if interface is None:
                    interface = self.nb.dcim.interfaces.create(
                        device=device.id, name=name, type=interface_type
                    )
                    created_interfaces.append(interface)
                else:
                    self.nb.dcim.interfaces.update(
                        [
                            {
                                "id": interface.id,
                                "tagged_vlans": [],
                                "untagged_vlan": None,
                            }
                        ]
                    )
        yield
        self._delete_test_vlans()
        self.nb.dcim.interfaces.update(original_interfaces)
        for interface in created_interfaces:
            interface.delete()

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

    def test_interface_map_alias(self) -> None:
        model = SyncVlansInput.model_validate(
            {
                "interface-map": [
                    {
                        "device-name": "leaf-*",
                        "device-type": "test",
                        "match": "Ethernet",
                        "replace": "Et",
                    }
                ]
            }
        )
        assert model.interface_map[0].replace == "Et"

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
                    "match_interface_names": ["Ethernet*", "Port-Channel*"],
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
            assert result["result"]["global"]["updated"] == [110]
            assert result["diff"]["global"]["update"]["110"]["tagged_interfaces"][
                "new_value"
            ] == [f"{self.DEVICE_1}:Port-Channel31"]
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
            assert result["result"]["global"]["updated"] == [121]
            assert result["diff"]["global"]["update"]["121"]["tagged_interfaces"][
                "new_value"
            ] == [f"{self.DEVICE_2}:Port-Channel32"]
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
                        },
                        "tagged_interfaces": {
                            "old_value": [],
                            "new_value": [f"{self.DEVICE_1}:Port-Channel31"],
                        },
                        "untagged_interfaces": {
                            "old_value": [],
                            "new_value": [f"{self.DEVICE_1}:Port-Channel31"],
                        },
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
