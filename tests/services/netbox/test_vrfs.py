from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch

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
    # Keep this suite's NetBox records separate from parallel IPAM sync tests.
    VRF_NAMES = {
        "TEST_VRF_SYNC_CONTROL_PLANE",
        "TEST_VRF_SYNC_TENANT_A",
        "TEST_VRF_SYNC_TENANT_B",
    }
    CONTROL_PLANE_INTERFACES = {"Ethernet1.101", "Ethernet2.101", "Loopback101"}
    CONTROL_PLANE_INTERFACE_DATA = (
        {"name": "Ethernet1", "type": "other"},
        {"name": "Ethernet2", "type": "other"},
        {
            "name": "Ethernet1.101",
            "type": "virtual",
            "parent": "Ethernet1",
            "description": "TEST_VRF_SYNC_CONTROL_PLANE",
        },
        {
            "name": "Ethernet2.101",
            "type": "virtual",
            "parent": "Ethernet2",
            "description": "TEST_VRF_SYNC_CONTROL_PLANE",
        },
        {
            "name": "Loopback101",
            "type": "virtual",
            "description": "TEST_VRF_SYNC_CONTROL_PLANE",
        },
    )
    ROUTE_TARGET_NAMES = {
        "65100:101",
        "65100:201",
        "65100:202",
        "65100:301",
        "65100:302",
        "65100:303",
        "65100:999",
    }
    DEVICE_1_ROUTE_TARGETS = {
        "65100:101",
        "65100:201",
        "65100:202",
        "65100:301",
        "65100:302",
    }
    ROUTING_POLICY_NAMES = {
        "TEST_VRF_SYNC_CONTROL_PLANE_IMPORT",
        "TEST_VRF_SYNC_CONTROL_PLANE_EXPORT",
        "TEST_VRF_SYNC_TENANT_A_IMPORT",
        "TEST_VRF_SYNC_TENANT_A_EXPORT",
        "TEST_VRF_SYNC_TENANT_B_IMPORT",
        "TEST_VRF_SYNC_TENANT_B_EXPORT",
        "TEST_VRF_SYNC_TENANT_A_EXTRA",
        "TEST_VRF_SYNC_TENANT_A_IPV6_IMPORT_TEST",
        "TEST_VRF_SYNC_TENANT_A_IPV6_EXPORT_TEST",
    }
    DEVICE_1_ROUTING_POLICIES = ROUTING_POLICY_NAMES - {
        "TEST_VRF_SYNC_TENANT_A_EXTRA",
        "TEST_VRF_SYNC_TENANT_A_IPV6_IMPORT_TEST",
        "TEST_VRF_SYNC_TENANT_A_IPV6_EXPORT_TEST",
    }

    @pytest.fixture(autouse=True)
    def cleanup_test_vrfs(self, request: pytest.FixtureRequest) -> Iterator[None]:
        if (
            "nfclient" not in request.fixturenames
            or request.node.name == "test_sync_vrfs_skips_unsupported_device"
        ):
            yield
            return
        self.nb = get_pynetbox(request.getfixturevalue("nfclient"))
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
        created_interfaces = self._create_control_plane_interfaces()
        yield
        self._delete_created_interfaces(created_interfaces)
        self._delete_test_data()
        for custom_field in created_custom_fields:
            custom_field.delete()

    def _create_control_plane_interfaces(self) -> list[int]:
        created_ids = []
        for device_name in (self.DEVICE_1, self.DEVICE_2):
            device = self.nb.dcim.devices.get(name=device_name)
            for interface_data in self.CONTROL_PLANE_INTERFACE_DATA:
                if self.nb.dcim.interfaces.get(
                    device=device_name, name=interface_data["name"]
                ):
                    continue
                payload = {
                    "device": device.id,
                    "name": interface_data["name"],
                    "type": interface_data["type"],
                    "description": interface_data.get("description", ""),
                }
                if parent_name := interface_data.get("parent"):
                    parent = self.nb.dcim.interfaces.get(
                        device=device_name, name=parent_name
                    )
                    payload["parent"] = parent.id
                created_ids.append(self.nb.dcim.interfaces.create(**payload).id)
        return created_ids

    def _delete_created_interfaces(self, interface_ids: list[int]) -> None:
        for interface_id in reversed(interface_ids):
            interface = self.nb.dcim.interfaces.get(id=interface_id)
            if interface is not None:
                interface.delete()

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
            "name": "TEST_VRF_SYNC_TENANT_A",
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
                    "route_policy_import": "TEST_VRF_SYNC_TENANT_A_IPV6_IMPORT_TEST",
                    "route_policy_export": "TEST_VRF_SYNC_TENANT_A_IPV6_EXPORT_TEST",
                },
            },
        }

    def test_sync_vrfs_skips_unsupported_device(self, nfclient: Any) -> None:
        nb = get_pynetbox(nfclient)
        name = "fn-vrf-unsupported-console"
        assert nb.dcim.devices.get(name=name) is None
        kwargs = {"devices": [name], "dry_run": True}

        missing = nfclient.run_job("netbox", "sync_vrfs", workers="any", kwargs=kwargs)
        assert missing
        for result in missing.values():
            assert result["resources_failed"] == [name]

        device = nb.dcim.devices.create(
            name=name,
            device_type=nb.dcim.device_types.get(model="Arista cEOS").id,
            role=nb.dcim.device_roles.get(name="VirtualRouter").id,
            site=nb.dcim.sites.get(name="SALTNORNIR-LAB").id,
            status="active",
        )
        try:
            response = nfclient.run_job(
                "netbox", "sync_vrfs", workers="any", kwargs=kwargs
            )
            assert response
            for result in response.values():
                assert result["resources_unsupported"] == [name]
                assert not result["failed"]
                assert result["resources_failed"] == result["errors"] == []
                assert result["result"] == result["diff"] == {}
                assert any(name in message for message in result["messages"])
        finally:
            device.delete()

    def test_shared_vrf_reports_only_the_device_with_drift(self) -> None:
        devices = [
            SimpleNamespace(
                id=index, name=name, device_type=SimpleNamespace(model="test")
            )
            for index, name in enumerate(("leaf-a", "leaf-b"), 1)
        ]
        target = SimpleNamespace(id=10, name="65000:10")
        new_target = SimpleNamespace(id=20, name="65000:20")
        vrf = SimpleNamespace(
            id=30,
            name="BLUE",
            description="Users",
            import_targets=[target],
            export_targets=[],
            custom_fields={"devices": [{"id": device.id} for device in devices]},
        )
        vrfs = Mock()
        vrfs.filter.return_value = [vrf]
        vrfs.update.return_value = [vrf]
        targets = Mock()
        targets.filter.return_value = [target]
        targets.create.return_value = [new_target]
        interfaces = Mock()
        interfaces.filter.return_value = [
            SimpleNamespace(id=device.id, name="Ethernet1", device=device, vrf=vrf)
            for device in devices
        ]
        nb = SimpleNamespace(
            dcim=SimpleNamespace(
                devices=SimpleNamespace(filter=lambda **kwargs: devices),
                interfaces=interfaces,
            ),
            ipam=SimpleNamespace(vrfs=vrfs, route_targets=targets),
            extras=SimpleNamespace(custom_fields=Mock()),
        )
        nb.extras.custom_fields.filter.return_value = [SimpleNamespace(name="devices")]
        live = {
            device.name: [
                {
                    "name": "BLUE",
                    "description": "Users",
                    "interfaces": ["Ethernet1"],
                    "address_families": {
                        "ipv4": {
                            "rt_import": (
                                ["65000:10", "65000:20"]
                                if device.name == "leaf-b"
                                else ["65000:10"]
                            ),
                            "rt_export": [],
                        }
                    },
                }
            ]
            for device in devices
        }
        worker = SimpleNamespace(
            name="test",
            default_instance="test",
            is_url=lambda value: False,
            _get_pynetbox=lambda *args, **kwargs: nb,
            has_plugin=lambda *args: False,
            bulk_filter=lambda endpoint, **kwargs: endpoint.filter(**kwargs),
            make_diff=lambda source, current: NetboxWorker.make_diff(
                None, source, current
            ),
            client=SimpleNamespace(
                run_job=lambda *args, **kwargs: {"worker": {"result": live}}
            ),
        )
        job = SimpleNamespace(event=Mock())

        empty = NetboxVrfsTasks.sync_vrfs(worker, job, devices=[])
        assert empty.failed is True
        assert empty.errors == ["no devices specified"]
        job.event.assert_called_once_with("no devices specified", severity="ERROR")

        with patch.object(worker, "make_diff", wraps=worker.make_diff) as make_diff:
            preview = NetboxVrfsTasks.sync_vrfs(
                worker, job, devices=["leaf-b", "leaf-a"], dry_run=True
            )
        assert make_diff.call_count == 2
        assert [
            (query.kwargs["device_id"], query.kwargs["name"])
            for query in interfaces.filter.call_args_list
        ] == [(1, ["Ethernet1"]), (2, ["Ethernet1"])]
        assert preview.diff["leaf-a"]["vrfs"]["in_sync"] == ["BLUE"]
        assert preview.diff["leaf-a"]["route_targets"]["create"] == []
        assert preview.diff["leaf-b"]["vrfs"]["update"]["BLUE"] == {
            "import_targets": {
                "old_value": ["65000:10"],
                "new_value": ["65000:10", "65000:20"],
            }
        }
        assert preview.diff["leaf-b"]["route_targets"]["create"] == ["65000:20"]
        vrfs.update.assert_not_called()

        with patch(
            "norfab.workers.netbox_worker.vrf_tasks.review_sync_task_result",
            return_value=False,
        ) as review:
            declined = NetboxVrfsTasks.sync_vrfs(
                worker, job, devices=["leaf-a", "leaf-b"], with_approval=True
            )
        review.assert_called_once_with(job, "VRF sync", preview.diff)
        assert declined.status == "skipped"
        assert declined.result == preview.diff
        vrfs.update.assert_not_called()

        applied = NetboxVrfsTasks.sync_vrfs(worker, job, devices=["leaf-a", "leaf-b"])
        assert applied.diff == preview.diff
        assert applied.result["leaf-a"]["vrfs"]["updated"] == []
        assert applied.result["leaf-b"]["vrfs"]["updated"] == ["BLUE"]
        targets.create.assert_called_once_with([{"name": "65000:20"}])
        vrfs.update.assert_called_once_with([{"id": 30, "import_targets": [10, 20]}])
        interfaces.update.assert_not_called()

        leaf_a_family = live["leaf-a"][0]["address_families"]["ipv4"]
        leaf_b_family = live["leaf-b"][0]["address_families"]["ipv4"]
        leaf_a_family["rt_import"], leaf_b_family["rt_import"] = (
            leaf_b_family["rt_import"],
            leaf_a_family["rt_import"],
        )
        live["leaf-b"][0]["description"] = "Other users"
        vrfs.update.return_value = []
        conflicting = NetboxVrfsTasks.sync_vrfs(
            worker, job, devices=["leaf-a", "leaf-b"]
        )
        assert conflicting.result["leaf-a"]["vrfs"]["updated"] == ["BLUE"]
        assert conflicting.result["leaf-b"]["vrfs"]["updated"] == []
        assert conflicting.diff["leaf-b"]["vrfs"]["update"]["BLUE"] == {
            "description": {"old_value": "Users", "new_value": "Other users"}
        }

        with (
            patch.object(targets, "filter", return_value=[target, new_target]),
            patch.object(
                vrfs, "update", side_effect=RuntimeError("shared write failed")
            ),
        ):
            failed_write = NetboxVrfsTasks.sync_vrfs(
                worker, job, devices=["leaf-a", "leaf-b"]
            )
        assert failed_write.failed is True
        assert failed_write.resources_failed == []
        assert failed_write.result["leaf-a"]["vrfs"]["updated"] == []

        with (
            patch.object(targets, "filter", side_effect=RuntimeError("read failed")),
            pytest.raises(RuntimeError, match="read failed"),
        ):
            NetboxVrfsTasks.sync_vrfs(worker, job, devices=["leaf-a", "leaf-b"])
        assert vrfs.update.call_count == 2
        assert targets.create.call_count == 2
        interfaces.update.assert_not_called()

        vrf.import_targets.append(new_target)
        live["leaf-b"][0]["description"] = "Other users"
        rerun = NetboxVrfsTasks.sync_vrfs(worker, job, devices=["leaf-b", "leaf-a"])
        assert rerun.diff["leaf-a"]["vrfs"]["in_sync"] == ["BLUE"]
        assert rerun.diff["leaf-b"]["vrfs"]["update"]["BLUE"] == {
            "description": {"old_value": "Users", "new_value": "Other users"}
        }
        assert rerun.result["leaf-b"]["vrfs"]["updated"] == []
        assert vrfs.update.call_count == 2

        live["leaf-b"][0]["description"] = "Users"
        leaf_b_interface = interfaces.filter.return_value[1]
        leaf_b_interface.vrf = None
        interfaces.update.side_effect = RuntimeError("write failed")
        partial = NetboxVrfsTasks.sync_vrfs(worker, job, devices=["leaf-a", "leaf-b"])
        assert partial.failed is True
        job.event.assert_any_call(
            "failed to update interfaces batch 1: write failed", severity="ERROR"
        )
        assert partial.resources_failed == ["leaf-b"]
        assert partial.result["leaf-a"]["interfaces"]["in_sync"] == ["Ethernet1"]
        assert partial.result["leaf-b"]["interfaces"]["updated"] == []
        assert partial.diff["leaf-b"]["interfaces"]["update"] == {
            "Ethernet1": {"vrf": {"old_value": None, "new_value": "BLUE"}}
        }

        interfaces.update.side_effect = None
        interfaces.update.return_value = []
        recovered = NetboxVrfsTasks.sync_vrfs(worker, job, devices=["leaf-a", "leaf-b"])
        assert recovered.result["leaf-b"]["interfaces"]["updated"] == ["Ethernet1"]
        interfaces.update.assert_called_with([{"id": leaf_b_interface.id, "vrf": 30}])
        assert vrfs.update.call_count == 2

        del live["leaf-b"]
        incomplete = NetboxVrfsTasks.sync_vrfs(
            worker, job, devices=["leaf-b", "leaf-a"], dry_run=True
        )
        assert incomplete.failed is False
        assert incomplete.resources_failed == ["leaf-b"]
        assert set(incomplete.diff) == {"leaf-a"}
        assert incomplete.diff["leaf-a"]["vrfs"]["in_sync"] == ["BLUE"]

        with patch.object(
            worker.client,
            "run_job",
            return_value={
                "worker": {
                    "result": live,
                    "resources_failed": ["leaf-b", "leaf-b", "outside-selection"],
                }
            },
        ):
            collected = NetboxVrfsTasks.sync_vrfs(
                worker, job, devices=["leaf-a", "leaf-b"], dry_run=True
            )
        assert collected.resources_failed == ["leaf-b"]

        vrf.custom_fields["devices"] = [{"id": 2}]
        membership = NetboxVrfsTasks.sync_vrfs(
            worker, job, devices=["leaf-a"], dry_run=True
        )
        assert membership.diff["leaf-a"]["vrfs"]["update"]["BLUE"] == {
            "devices": {"old_value": [2], "new_value": [1, 2]}
        }
        assert membership.diff["leaf-a"]["interfaces"]["update"] == {}

        vrfs.filter.return_value = []
        vrfs.create.return_value = [SimpleNamespace(name="BLUE", id=31)]
        targets.filter.return_value = [target, new_target]
        interfaces.filter.return_value[0].vrf = None
        interfaces.update.return_value = [interfaces.filter.return_value[0]]
        created = NetboxVrfsTasks.sync_vrfs(worker, job, devices=["leaf-a"])
        assert created.result["leaf-a"]["vrfs"]["created"] == ["BLUE"]
        assert created.result["leaf-a"]["interfaces"]["updated"] == ["Ethernet1"]
        vrfs.create.assert_called_once_with(
            [
                {
                    "name": "BLUE",
                    "description": "Users",
                    "import_targets": [10, 20],
                    "export_targets": [],
                    "custom_fields": {"devices": [1]},
                }
            ]
        )
        interfaces.update.assert_called_with([{"id": 1, "vrf": 31}])

        live["leaf-a"][0]["interfaces"] = []
        interfaces.filter.reset_mock()
        NetboxVrfsTasks.sync_vrfs(worker, job, devices=["leaf-a"], dry_run=True)
        interfaces.filter.assert_not_called()

    def test_ipv6_routing_policies_from_getter(self, nfclient: Any) -> None:
        worker = self._stub_worker([self._ipv6_record()], plugin_installed=True)
        preview = NetboxVrfsTasks.sync_vrfs(
            worker, self._stub_job(), devices=[self.DEVICE_1], dry_run=True
        )
        assert set(preview.result[self.DEVICE_1]["routing_policies"]["create"]) == {
            "TEST_VRF_SYNC_TENANT_A_IPV6_IMPORT_TEST",
            "TEST_VRF_SYNC_TENANT_A_IPV6_EXPORT_TEST",
        }
        changes = preview.result[self.DEVICE_1]["vrfs"]["create"]
        assert changes == ["TEST_VRF_SYNC_TENANT_A"]
        assert (
            self.nb.plugins.bgp.routing_policy.get(
                name="TEST_VRF_SYNC_TENANT_A_IPV6_IMPORT_TEST"
            )
            is None
        )

        applied = NetboxVrfsTasks.sync_vrfs(
            worker, self._stub_job(), devices=[self.DEVICE_1]
        )
        assert set(applied.result[self.DEVICE_1]["routing_policies"]["created"]) == {
            "TEST_VRF_SYNC_TENANT_A_IPV6_IMPORT_TEST",
            "TEST_VRF_SYNC_TENANT_A_IPV6_EXPORT_TEST",
        }
        tenant_a = self.nb.ipam.vrfs.get(name="TEST_VRF_SYNC_TENANT_A")
        assert self._custom_field_policy_names(tenant_a, "rpl_import_ipv6") == {
            "TEST_VRF_SYNC_TENANT_A_IPV6_IMPORT_TEST"
        }
        assert self._custom_field_policy_names(tenant_a, "rpl_export_ipv6") == {
            "TEST_VRF_SYNC_TENANT_A_IPV6_EXPORT_TEST"
        }

    def test_in_sync_live_run_exits_before_approval(self, nfclient: Any) -> None:
        worker = self._stub_worker([self._ipv6_record()], plugin_installed=True)
        job = self._stub_job()
        NetboxVrfsTasks.sync_vrfs(worker, job, devices=[self.DEVICE_1])

        result = NetboxVrfsTasks.sync_vrfs(
            worker,
            job,
            devices=[self.DEVICE_1],
            with_approval=True,
        )

        assert result.result[self.DEVICE_1]["vrfs"]["updated"] == []
        assert result.result[self.DEVICE_1]["vrfs"]["in_sync"] == [
            "TEST_VRF_SYNC_TENANT_A"
        ]
        assert result.result[self.DEVICE_1]["interfaces"] == {
            "created": [],
            "updated": [],
            "deleted": [],
            "in_sync": [],
        }

    def test_missing_bgp_plugin_ignores_policies(self, nfclient: Any) -> None:
        worker = self._stub_worker([self._ipv6_record()], plugin_installed=False)
        live_data = worker.client.run_job()
        live_data["nornir-test"]["result"][self.DEVICE_2] = []
        worker.client.run_job = lambda *args, **kwargs: live_data
        preview = NetboxVrfsTasks.sync_vrfs(
            worker,
            self._stub_job(),
            devices=[self.DEVICE_1, self.DEVICE_2],
            dry_run=True,
        )
        assert preview.errors == []
        assert preview.result[self.DEVICE_1]["vrfs"]["create"] == [
            "TEST_VRF_SYNC_TENANT_A"
        ]
        assert preview.result[self.DEVICE_1]["routing_policies"] == {
            "create": [],
            "update": {},
            "delete": [],
            "in_sync": [],
        }
        assert preview.result[self.DEVICE_2] == {
            section: {"create": [], "update": {}, "delete": [], "in_sync": []}
            for section in ("vrfs", "route_targets", "routing_policies", "interfaces")
        }

    def test_preserve_description_modes(self, nfclient: Any) -> None:
        self.nb.ipam.vrfs.create(
            name="TEST_VRF_SYNC_TENANT_B", description="NetBox empty-live"
        )

        self._successful_results(self._sync(nfclient, [self.DEVICE_1]))
        assert self.nb.ipam.vrfs.get(name="TEST_VRF_SYNC_TENANT_B").description == (
            "NetBox empty-live"
        )

        self._successful_results(
            self._sync(nfclient, [self.DEVICE_1], preserve_description=False)
        )
        assert self.nb.ipam.vrfs.get(name="TEST_VRF_SYNC_TENANT_B").description == ""

        tenant_a = self.nb.ipam.vrfs.get(name="TEST_VRF_SYNC_TENANT_A")
        tenant_a.description = "NetBox curated"
        tenant_a.save()
        self._successful_results(
            self._sync(nfclient, [self.DEVICE_1], preserve_description=True)
        )
        assert (
            self.nb.ipam.vrfs.get(name="TEST_VRF_SYNC_TENANT_A").description
            == "NetBox curated"
        )

        self._successful_results(
            self._sync(nfclient, [self.DEVICE_1], preserve_description=False)
        )
        assert self.nb.ipam.vrfs.get(name="TEST_VRF_SYNC_TENANT_A").description == (
            "Tenant A services"
        )

    def test_dry_run_create_apply_and_exact_match(self, nfclient: Any) -> None:
        dry_run = self._sync(nfclient, [self.DEVICE_1], dry_run=True)
        for result in self._successful_results(dry_run):
            device_result = result["result"][self.DEVICE_1]
            assert device_result["vrfs"]["create"] == sorted(self.VRF_NAMES)
            assert device_result["vrfs"]["update"] == {}
            assert device_result["vrfs"]["delete"] == []
            assert (
                set(device_result["route_targets"]["create"])
                == self.DEVICE_1_ROUTE_TARGETS
            )
            assert device_result["route_targets"]["update"] == {}
            assert device_result["route_targets"]["delete"] == []
            assert device_result["route_targets"]["in_sync"] == []
            assert (
                set(device_result["routing_policies"]["create"])
                == self.DEVICE_1_ROUTING_POLICIES
            )
            assert device_result["routing_policies"]["update"] == {}
            assert device_result["routing_policies"]["delete"] == []
            assert device_result["routing_policies"]["in_sync"] == []
            assert (
                set(device_result["interfaces"]["update"])
                == self.CONTROL_PLANE_INTERFACES
            )
        assert self.nb.ipam.vrfs.get(name="TEST_VRF_SYNC_TENANT_A") is None
        assert self.nb.ipam.route_targets.get(name="65100:201") is None
        assert (
            self.nb.plugins.bgp.routing_policy.get(name="TEST_VRF_SYNC_TENANT_A_IMPORT")
            is None
        )

        first_sync = self._sync(nfclient, [self.DEVICE_1], batch_size=1)
        for result in self._successful_results(first_sync):
            device_result = result["result"][self.DEVICE_1]
            assert device_result["vrfs"]["created"] == sorted(self.VRF_NAMES)
            assert (
                set(device_result["route_targets"]["created"])
                == self.DEVICE_1_ROUTE_TARGETS
            )
            assert (
                set(result["diff"][self.DEVICE_1]["route_targets"]["create"])
                == self.DEVICE_1_ROUTE_TARGETS
            )
            assert device_result["route_targets"]["updated"] == []
            assert device_result["route_targets"]["deleted"] == []
            assert device_result["route_targets"]["in_sync"] == []
            assert (
                set(device_result["routing_policies"]["created"])
                == self.DEVICE_1_ROUTING_POLICIES
            )
            assert (
                set(result["diff"][self.DEVICE_1]["routing_policies"]["create"])
                == self.DEVICE_1_ROUTING_POLICIES
            )
            assert device_result["routing_policies"]["updated"] == []
            assert device_result["routing_policies"]["deleted"] == []
            assert device_result["routing_policies"]["in_sync"] == []
            assert (
                set(device_result["interfaces"]["updated"])
                == self.CONTROL_PLANE_INTERFACES
            )

        tenant_a = self.nb.ipam.vrfs.get(name="TEST_VRF_SYNC_TENANT_A")
        assert tenant_a.description == "Tenant A services"
        assert sorted(target.name for target in tenant_a.import_targets) == [
            "65100:201",
            "65100:301",
        ]
        assert sorted(target.name for target in tenant_a.export_targets) == [
            "65100:201",
            "65100:302",
        ]
        device = self.nb.dcim.devices.get(name=self.DEVICE_1)
        assert self._custom_field_device_ids(tenant_a, "devices") == {device.id}
        assert self._custom_field_policy_names(tenant_a, "rpl_import_ipv4") == {
            "TEST_VRF_SYNC_TENANT_A_IMPORT"
        }
        assert self._custom_field_policy_names(tenant_a, "rpl_export_ipv4") == {
            "TEST_VRF_SYNC_TENANT_A_EXPORT"
        }
        assert self._custom_field_policy_names(tenant_a, "rpl_import_ipv6") == set()
        assert self._custom_field_policy_names(tenant_a, "rpl_export_ipv6") == set()

        second_sync = self._sync(nfclient, [self.DEVICE_1])
        for result in self._successful_results(second_sync):
            device_result = result["result"][self.DEVICE_1]
            actions = device_result["vrfs"]
            assert actions["created"] == []
            assert actions["updated"] == []
            assert actions["in_sync"] == sorted(self.VRF_NAMES)
            assert device_result["route_targets"] == {
                "created": [],
                "updated": [],
                "deleted": [],
                "in_sync": [],
            }
            assert device_result["routing_policies"] == {
                "created": [],
                "updated": [],
                "deleted": [],
                "in_sync": [],
            }
            assert (
                set(device_result["interfaces"]["in_sync"])
                == self.CONTROL_PLANE_INTERFACES
            )

    def test_empty_interface_map_from_nf_url(self, nfclient: Any) -> None:
        response = self._sync(
            nfclient,
            [self.DEVICE_1],
            dry_run=True,
            interface_map="nf://netbox/interface_map_empty.yaml",
        )

        self._successful_results(response)

    def test_extends_route_targets_and_updates_description(self, nfclient: Any) -> None:
        existing_target = self.nb.ipam.route_targets.create(name="65100:999")
        self.nb.ipam.route_targets.create(name="65100:201")
        existing_device = self.nb.dcim.devices.get(name=self.DEVICE_2)
        self.nb.ipam.vrfs.create(
            name="TEST_VRF_SYNC_TENANT_A",
            description="stale description",
            import_targets=[existing_target.id],
            export_targets=[existing_target.id],
            custom_fields={"devices": [existing_device.id]},
        )

        response = self._sync(nfclient, [self.DEVICE_1])

        for result in self._successful_results(response):
            device_result = result["result"][self.DEVICE_1]
            assert "TEST_VRF_SYNC_TENANT_A" in device_result["vrfs"]["updated"]
            assert set(
                device_result["route_targets"]["created"]
            ) == self.DEVICE_1_ROUTE_TARGETS - {"65100:201"}
            changes = result["diff"][self.DEVICE_1]["vrfs"]["update"][
                "TEST_VRF_SYNC_TENANT_A"
            ]
            assert sorted(changes["import_targets"]["new_value"]) == [
                "65100:201",
                "65100:301",
                "65100:999",
            ]
            assert sorted(changes["export_targets"]["new_value"]) == [
                "65100:201",
                "65100:302",
                "65100:999",
            ]
        tenant_a = self.nb.ipam.vrfs.get(name="TEST_VRF_SYNC_TENANT_A")
        assert tenant_a.description == "Tenant A services"
        assert sorted(target.name for target in tenant_a.import_targets) == [
            "65100:201",
            "65100:301",
            "65100:999",
        ]
        assert sorted(target.name for target in tenant_a.export_targets) == [
            "65100:201",
            "65100:302",
            "65100:999",
        ]
        assert len(list(self.nb.ipam.route_targets.filter(name="65100:201"))) == 1
        selected_device = self.nb.dcim.devices.get(name=self.DEVICE_1)
        assert self._custom_field_device_ids(tenant_a, "devices") == {
            existing_device.id,
            selected_device.id,
        }

    def test_routing_policies_are_additive(self, nfclient: Any) -> None:
        existing = self.nb.plugins.bgp.routing_policy.create(
            name="TEST_VRF_SYNC_TENANT_A_EXTRA"
        )
        self.nb.ipam.vrfs.create(
            name="TEST_VRF_SYNC_TENANT_A",
            custom_fields={"rpl_import_ipv4": [existing.id]},
        )

        for result in self._successful_results(self._sync(nfclient, [self.DEVICE_1])):
            changes = result["diff"][self.DEVICE_1]["vrfs"]["update"][
                "TEST_VRF_SYNC_TENANT_A"
            ]
            assert set(changes["rpl_import_ipv4"]["new_value"]) == {
                "TEST_VRF_SYNC_TENANT_A_EXTRA",
                "TEST_VRF_SYNC_TENANT_A_IMPORT",
            }
        tenant_a = self.nb.ipam.vrfs.get(name="TEST_VRF_SYNC_TENANT_A")
        assert self._custom_field_policy_names(tenant_a, "rpl_import_ipv4") == {
            "TEST_VRF_SYNC_TENANT_A_EXTRA",
            "TEST_VRF_SYNC_TENANT_A_IMPORT",
        }

    def test_netbox_only_additive_values_are_in_sync(self, nfclient: Any) -> None:
        self._successful_results(self._sync(nfclient, [self.DEVICE_1]))
        extra_target = self.nb.ipam.route_targets.create(name="65100:999")
        extra_policy = self.nb.plugins.bgp.routing_policy.create(
            name="TEST_VRF_SYNC_TENANT_A_EXTRA"
        )
        tenant_a = self.nb.ipam.vrfs.get(name="TEST_VRF_SYNC_TENANT_A")
        tenant_a.import_targets = [
            *[target.id for target in tenant_a.import_targets],
            extra_target.id,
        ]
        tenant_a.custom_fields["rpl_import_ipv4"] = [
            *[policy["id"] for policy in tenant_a.custom_fields["rpl_import_ipv4"]],
            extra_policy.id,
        ]
        tenant_a.save()

        for result in self._successful_results(self._sync(nfclient, [self.DEVICE_1])):
            device_result = result["result"][self.DEVICE_1]
            assert device_result["vrfs"]["updated"] == []
            assert device_result["vrfs"]["in_sync"] == sorted(self.VRF_NAMES)

    def test_multiple_devices_are_aggregated_with_description_precedence(
        self, nfclient: Any
    ) -> None:
        response = self._sync(nfclient, [self.DEVICE_1, self.DEVICE_2])

        for result in self._successful_results(response):
            assert set(result["result"]) == {self.DEVICE_1, self.DEVICE_2}
            for device in (self.DEVICE_1, self.DEVICE_2):
                assert result["result"][device]["vrfs"]["created"] == sorted(
                    self.VRF_NAMES
                )
                assert result["diff"][device]["vrfs"]["create"] == sorted(
                    self.VRF_NAMES
                )
                assert (
                    "65100:303" in result["result"][device]["route_targets"]["created"]
                ) == (device == self.DEVICE_2)
                assert (
                    "TEST_VRF_SYNC_TENANT_A" in result["diff"][device]["vrfs"]["create"]
                )
        control_plane = self.nb.ipam.vrfs.get(name="TEST_VRF_SYNC_CONTROL_PLANE")
        expected_device_ids = {
            self.nb.dcim.devices.get(name=self.DEVICE_1).id,
            self.nb.dcim.devices.get(name=self.DEVICE_2).id,
        }
        assert self._custom_field_device_ids(control_plane, "devices") == (
            expected_device_ids
        )
        assert control_plane.description == "Control plane VRF for ceos-leaf-1"
        tenant_a = self.nb.ipam.vrfs.get(name="TEST_VRF_SYNC_TENANT_A")
        assert self._custom_field_policy_names(tenant_a, "rpl_import_ipv6") == set()
        assert sorted(target.name for target in tenant_a.import_targets) == [
            "65100:201",
            "65100:301",
            "65100:303",
        ]
        assert sorted(target.name for target in tenant_a.export_targets) == [
            "65100:201",
            "65100:302",
        ]
        tenant_b = self.nb.ipam.vrfs.get(name="TEST_VRF_SYNC_TENANT_B")
        assert tenant_b.description == "Tenant B services"

    def test_custom_device_field_name(self, nfclient: Any) -> None:
        response = self._sync(
            nfclient,
            [self.DEVICE_1],
            device_custom_field="vrf_devices",
        )

        for result in self._successful_results(response):
            device_result = result["result"][self.DEVICE_1]
            assert device_result["vrfs"]["created"] == sorted(self.VRF_NAMES)
        tenant_b = self.nb.ipam.vrfs.get(name="TEST_VRF_SYNC_TENANT_B")
        device = self.nb.dcim.devices.get(name=self.DEVICE_1)
        assert self._custom_field_device_ids(tenant_b, "vrf_devices") == {device.id}

    def test_custom_routing_policy_field_name(self, nfclient: Any) -> None:
        response = self._sync(
            nfclient,
            [self.DEVICE_1],
            rpl_import_ipv4="alternate_rpl_import_ipv4",
        )
        self._successful_results(response)
        tenant_a = self.nb.ipam.vrfs.get(name="TEST_VRF_SYNC_TENANT_A")
        assert self._custom_field_policy_names(
            tenant_a, "alternate_rpl_import_ipv4"
        ) == {"TEST_VRF_SYNC_TENANT_A_IMPORT"}
        assert self._custom_field_policy_names(tenant_a, "rpl_import_ipv4") == set()

    def test_existing_vrf_with_empty_device_custom_field(self, nfclient: Any) -> None:
        self.nb.ipam.vrfs.create(name="TEST_VRF_SYNC_TENANT_A")

        response = self._sync(nfclient, [self.DEVICE_1])

        for result in self._successful_results(response):
            device_result = result["result"][self.DEVICE_1]
            assert "TEST_VRF_SYNC_TENANT_A" in device_result["vrfs"]["updated"]
        tenant_a = self.nb.ipam.vrfs.get(name="TEST_VRF_SYNC_TENANT_A")
        device = self.nb.dcim.devices.get(name=self.DEVICE_1)
        assert self._custom_field_device_ids(tenant_a, "devices") == {device.id}

    def test_missing_device_custom_field_is_ignored(self, nfclient: Any) -> None:
        response = self._sync(
            nfclient,
            [self.DEVICE_1],
            device_custom_field="does_not_exist",
        )

        for result in self._successful_results(response):
            device_result = result["result"][self.DEVICE_1]
            assert device_result["vrfs"]["created"] == sorted(self.VRF_NAMES)
        tenant_a = self.nb.ipam.vrfs.get(name="TEST_VRF_SYNC_TENANT_A")
        assert "does_not_exist" not in tenant_a.custom_fields

    def test_unmatched_netbox_vrf_is_not_deleted(self, nfclient: Any) -> None:
        device = self.nb.dcim.devices.get(name=self.DEVICE_1)
        self.nb.ipam.vrfs.create(
            name="TEST_VRF_SYNC_KEEP_ME", custom_fields={"devices": [device.id]}
        )
        try:
            response = self._sync(nfclient, [self.DEVICE_1])
            for result in self._successful_results(response):
                device_result = result["result"][self.DEVICE_1]
                assert device_result["vrfs"]["deleted"] == []
                vrf_diff = result["diff"][self.DEVICE_1]["vrfs"]
                assert vrf_diff["delete"] == []
                assert "TEST_VRF_SYNC_KEEP_ME" not in vrf_diff["update"]
                assert "TEST_VRF_SYNC_KEEP_ME" not in device_result["vrfs"]["updated"]
            assert self.nb.ipam.vrfs.get(name="TEST_VRF_SYNC_KEEP_ME") is not None
        finally:
            self.nb.ipam.vrfs.get(name="TEST_VRF_SYNC_KEEP_ME").delete()
