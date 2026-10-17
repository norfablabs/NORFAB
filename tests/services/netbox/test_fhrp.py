from collections.abc import Iterator
from typing import Any

import pytest

from tests.services.netbox.common import get_pynetbox

pytestmark = [
    pytest.mark.netbox,
    pytest.mark.netbox_sync_vrrp,
]


class TestSyncVrrp:
    DEVICE = "xr1"
    NETWORK = "netbox-vrrp-sync"
    FAKENOS_INVENTORY = "nf://fakenos/net2.yaml"
    NORNIR_WORKER = "nornir-worker-4"
    INTERFACES = {
        10: "GigabitEthernet0/0/0/3",
        30: "GigabitEthernet0/0/0/4",
    }
    VIRTUAL_ADDRESSES = {
        10: "198.18.250.1/24",
        30: "198.18.251.1/24",
    }
    PRIORITIES = {10: 110, 30: 120}
    DUAL_STACK_INTERFACE = "BVI123"
    DUAL_STACK_ADDRESSES = {
        "vrrp2": "10.123.123.123/24",
        "vrrp3": "2123:1111:1111:1111::1/64",
    }
    KEYS = {
        10: "GigabitEthernet0/0/0/3:vrrp2:10",
        30: "GigabitEthernet0/0/0/4:vrrp2:30",
    }
    DUAL_STACK_KEYS = ["BVI123:vrrp2:1", "BVI123:vrrp3:1"]
    ALL_KEYS = sorted([KEYS[10], KEYS[30], *DUAL_STACK_KEYS])
    ALL_INTERFACES = [*INTERFACES.values(), DUAL_STACK_INTERFACE]
    ALL_ADDRESSES = [*VIRTUAL_ADDRESSES.values(), *DUAL_STACK_ADDRESSES.values()]

    VRF_DEVICES = ["fn-vrrp-vrf-1", "fn-vrrp-vrf-2"]
    VRF_INTERFACE_VRFS = {
        "Vlan10": "TEST_VRRP_BLUE",
        "Vlan20": "TEST_VRRP_RED",
        "Vlan30": None,
    }
    VRF_ADDRESS = "198.19.238.1"
    VRF_PREFIX = "198.19.238.0/24"
    VRF_KEYS = ["Vlan10:vrrp3:20", "Vlan20:vrrp3:20", "Vlan30:vrrp3:20"]

    @staticmethod
    def _successful_results(response: dict) -> list[dict]:
        assert response
        results = []
        for worker, result in response.items():
            assert result["failed"] is False, f"{worker} failed: {result}"
            assert result["errors"] == [], f"{worker} returned errors: {result}"
            results.append(result)
        return results

    @classmethod
    def _cleanup_vrrp_records(cls, nfclient: Any) -> None:
        nb = get_pynetbox(nfclient)
        device = nb.dcim.devices.get(name=cls.DEVICE)
        assert device is not None, (
            f"seeded NetBox device '{cls.DEVICE}' is missing; "
            "populate the baseline with tests/netbox_data.py"
        )
        group_ids = set()
        for interface_name in cls.ALL_INTERFACES:
            interface = nb.dcim.interfaces.get(device_id=device.id, name=interface_name)
            assert interface is not None, (
                f"seeded NetBox interface '{cls.DEVICE}:{interface_name}' is missing; "
                "populate the baseline with tests/netbox_data.py"
            )
            for assignment in nb.ipam.fhrp_group_assignments.filter(
                interface_id=interface.id
            ):
                group_ids.add(assignment.group.id)

        for group_id in group_ids:
            for ip_address in nb.ipam.ip_addresses.filter(
                assigned_object_type="ipam.fhrpgroup",
                assigned_object_id=group_id,
            ):
                ip_address.delete()
            group = nb.ipam.fhrp_groups.get(id=group_id)
            if group:
                group.delete()

        for address in cls.ALL_ADDRESSES:
            host_address = address.split("/")[0]
            for ip_address in nb.ipam.ip_addresses.filter(address=host_address):
                if str(ip_address.address).startswith(f"{host_address}/"):
                    ip_address.delete()

    @classmethod
    def _start_fakenos(cls, nfclient: Any) -> None:
        nfclient.run_job("fakenos", "stop", kwargs={"network": cls.NETWORK})
        started = nfclient.run_job(
            "fakenos",
            "start",
            kwargs={"network": cls.NETWORK, "inventory": cls.FAKENOS_INVENTORY},
        )
        cls._successful_results(started)

        exported = nfclient.run_job(
            "fakenos",
            "get_nornir_inventory",
            kwargs={"network": cls.NETWORK},
        )
        hosts = {}
        for result in cls._successful_results(exported):
            hosts.update(result["result"]["hosts"])
        assert cls.DEVICE in hosts
        hosts[cls.DEVICE]["platform"] = "cisco_xr"

        loaded = nfclient.run_job(
            "nornir",
            "runtime_inventory",
            workers=[cls.NORNIR_WORKER],
            kwargs={
                "action": "create_host",
                "name": cls.DEVICE,
                **hosts[cls.DEVICE],
            },
        )
        cls._successful_results(loaded)

    @classmethod
    def _stop_fakenos(cls, nfclient: Any) -> None:
        nfclient.run_job(
            "nornir",
            "runtime_inventory",
            workers=[cls.NORNIR_WORKER],
            kwargs={"action": "delete_host", "name": cls.DEVICE},
        )
        nfclient.run_job("fakenos", "stop", kwargs={"network": cls.NETWORK})

    @classmethod
    def _sync_vrrp(cls, nfclient: Any, **kwargs: Any) -> dict:
        return nfclient.run_job(
            "netbox",
            "sync_vrrp",
            workers="any",
            kwargs={"devices": [cls.DEVICE], "timeout": 120, **kwargs},
            timeout=180,
        )

    @pytest.fixture
    def sync_vrrp_fixture(self, nfclient: Any) -> Iterator[None]:
        self._cleanup_vrrp_records(nfclient)
        self._start_fakenos(nfclient)
        yield
        self._stop_fakenos(nfclient)
        self._cleanup_vrrp_records(nfclient)

    @pytest.mark.usefixtures("sync_vrrp_fixture")
    def test_vrrp_getter_reads_fakenos_data(self, nfclient: Any) -> None:
        response = nfclient.run_job(
            "nornir",
            "parse_ttp",
            workers=[self.NORNIR_WORKER],
            kwargs={"get": "vrrp", "FL": [self.DEVICE]},
            timeout=120,
        )

        result = self._successful_results(response)[0]
        assert sorted(
            result["result"][self.DEVICE],
            key=lambda item: (item["interface"], item["protocol"], item["group"]),
        ) == [
            {
                "interface": self.DUAL_STACK_INTERFACE,
                "vrf": None,
                "group": 1,
                "protocol": "vrrpv2",
                "virtual_address": "10.123.123.123",
                "priority": 123,
                "authentication_type": "text",
            },
            {
                "interface": self.DUAL_STACK_INTERFACE,
                "vrf": None,
                "group": 1,
                "protocol": "vrrpv3",
                "virtual_address": "2123:1111:1111:1111::1",
                "priority": 123,
                "authentication_type": None,
            },
            {
                "interface": self.INTERFACES[10],
                "vrf": None,
                "group": 10,
                "protocol": "vrrpv2",
                "virtual_address": "198.18.250.1",
                "priority": 110,
                "authentication_type": None,
            },
            {
                "interface": self.INTERFACES[30],
                "vrf": None,
                "group": 30,
                "protocol": "vrrpv2",
                "virtual_address": "198.18.251.1",
                "priority": 120,
                "authentication_type": None,
            },
        ]

    @pytest.mark.usefixtures("sync_vrrp_fixture")
    def test_sync_vrrp_dry_run_does_not_write_to_netbox(self, nfclient: Any) -> None:
        response = self._sync_vrrp(nfclient, dry_run=True)

        for result in self._successful_results(response):
            actions = result["result"][self.DEVICE]
            assert actions["create"] == self.ALL_KEYS
            assert actions["update"] == {}
            assert actions["delete"] == []
            assert actions["in_sync"] == []

        nb = get_pynetbox(nfclient)
        for interface_name in self.ALL_INTERFACES:
            interface = nb.dcim.interfaces.get(device=self.DEVICE, name=interface_name)
            assert (
                list(nb.ipam.fhrp_group_assignments.filter(interface_id=interface.id))
                == []
            )

    @pytest.mark.usefixtures("sync_vrrp_fixture")
    def test_sync_vrrp_same_interface_group_for_ipv4_and_ipv6(
        self, nfclient: Any
    ) -> None:
        response = self._sync_vrrp(nfclient)
        for result in self._successful_results(response):
            assert set(self.DUAL_STACK_KEYS).issubset(
                result["result"][self.DEVICE]["created"]
            )

        nb = get_pynetbox(nfclient)
        interface = nb.dcim.interfaces.get(
            device=self.DEVICE, name=self.DUAL_STACK_INTERFACE
        )
        assignments = list(
            nb.ipam.fhrp_group_assignments.filter(interface_id=interface.id)
        )
        assert len(assignments) == 2

        groups = {}
        for assignment in assignments:
            group = nb.ipam.fhrp_groups.get(id=assignment.group.id)
            virtual_ip = nb.ipam.ip_addresses.get(
                assigned_object_type="ipam.fhrpgroup",
                assigned_object_id=group.id,
            )
            groups[group.protocol] = {
                "group_id": group.group_id,
                "priority": assignment.priority,
                "authentication_type": getattr(
                    group.auth_type, "value", group.auth_type
                ),
                "virtual_address": str(virtual_ip.address),
            }

        assert groups == {
            "vrrp2": {
                "group_id": 1,
                "priority": 123,
                "authentication_type": "plaintext",
                "virtual_address": self.DUAL_STACK_ADDRESSES["vrrp2"],
            },
            "vrrp3": {
                "group_id": 1,
                "priority": 123,
                "authentication_type": None,
                "virtual_address": self.DUAL_STACK_ADDRESSES["vrrp3"],
            },
        }

    @pytest.mark.usefixtures("sync_vrrp_fixture")
    def test_sync_vrrp_creates_missing_group_virtual_ip(self, nfclient: Any) -> None:
        self._successful_results(self._sync_vrrp(nfclient))
        nb = get_pynetbox(nfclient)
        interface = nb.dcim.interfaces.get(device=self.DEVICE, name=self.INTERFACES[10])
        assignment = list(
            nb.ipam.fhrp_group_assignments.filter(interface_id=interface.id)
        )[0]
        group_id = assignment.group.id
        original_ip = list(
            nb.ipam.ip_addresses.filter(
                assigned_object_type="ipam.fhrpgroup",
                assigned_object_id=group_id,
            )
        )[0]
        original_ip_id = original_ip.id
        original_ip.delete()

        dry_run = self._sync_vrrp(nfclient, dry_run=True)
        key = self.KEYS[10]
        for result in self._successful_results(dry_run):
            assert result["result"][self.DEVICE]["update"][key]["virtual_address"] == {
                "old_value": None,
                "new_value": self.VIRTUAL_ADDRESSES[10].split("/")[0],
            }

        response = self._sync_vrrp(nfclient)

        for result in self._successful_results(response):
            assert result["result"][self.DEVICE]["updated"] == [key]
        virtual_ips = list(
            nb.ipam.ip_addresses.filter(
                assigned_object_type="ipam.fhrpgroup",
                assigned_object_id=group_id,
            )
        )
        assert len(virtual_ips) == 1
        assert virtual_ips[0].id != original_ip_id
        assert str(virtual_ips[0].address) == self.VIRTUAL_ADDRESSES[10]
        role = getattr(virtual_ips[0].role, "value", virtual_ips[0].role)
        assert role == "vrrp"

    @pytest.mark.usefixtures("sync_vrrp_fixture")
    @pytest.mark.parametrize("role", [None, "vip"])
    def test_sync_vrrp_normalizes_group_virtual_ip_role(
        self, nfclient: Any, role: str | None
    ) -> None:
        self._successful_results(self._sync_vrrp(nfclient))
        nb = get_pynetbox(nfclient)
        vip = nb.ipam.ip_addresses.get(address=self.VIRTUAL_ADDRESSES[10])
        original_group_id = vip.assigned_object_id
        original_vrf_id = vip.vrf.id if vip.vrf else None
        vip.update({"role": role})

        dry_run = self._successful_results(self._sync_vrrp(nfclient, dry_run=True))[0]
        assert dry_run["diff"][self.DEVICE]["update"][self.KEYS[10]]["role"] == {
            "old_value": role,
            "new_value": "vrrp",
        }
        assert getattr(nb.ipam.ip_addresses.get(id=vip.id).role, "value", None) == role

        result = self._successful_results(self._sync_vrrp(nfclient))[0]
        assert result["result"][self.DEVICE]["updated"] == [self.KEYS[10]]
        updated = nb.ipam.ip_addresses.get(id=vip.id)
        assert updated.role.value == "vrrp"
        assert updated.assigned_object_id == original_group_id
        assert (updated.vrf.id if updated.vrf else None) == original_vrf_id
        assert (
            len(list(nb.ipam.ip_addresses.filter(address=self.VIRTUAL_ADDRESSES[10])))
            == 1
        )
        repeated = self._successful_results(self._sync_vrrp(nfclient))[0]
        assert repeated["result"][self.DEVICE]["in_sync"] == self.ALL_KEYS

    @pytest.mark.usefixtures("sync_vrrp_fixture")
    def test_sync_vrrp_reuses_preferred_existing_virtual_ip(
        self, nfclient: Any
    ) -> None:
        nb = get_pynetbox(nfclient)
        host_address = self.VIRTUAL_ADDRESSES[10].split("/")[0]
        vrf = nb.ipam.vrfs.get(name="VRF1")
        assert vrf is not None
        first_ip = nb.ipam.ip_addresses.create(
            address=f"{host_address}/32",
            status="active",
            vrf=vrf.id,
        )
        preferred_ip = nb.ipam.ip_addresses.create(
            address=self.VIRTUAL_ADDRESSES[10],
            status="active",
            role="vip",
        )
        ordinary_ip = nb.ipam.ip_addresses.create(
            address=self.VIRTUAL_ADDRESSES[30],
            status="active",
        )

        self._successful_results(self._sync_vrrp(nfclient))

        interface = nb.dcim.interfaces.get(device=self.DEVICE, name=self.INTERFACES[10])
        assignment = list(
            nb.ipam.fhrp_group_assignments.filter(interface_id=interface.id)
        )[0]
        reused_ip = nb.ipam.ip_addresses.get(id=preferred_ip.id)
        untouched_ip = nb.ipam.ip_addresses.get(id=first_ip.id)
        matching_ips = [
            ip_address
            for ip_address in nb.ipam.ip_addresses.filter(address=host_address)
            if str(ip_address.address).startswith(f"{host_address}/")
        ]

        assert len(matching_ips) == 2
        assert reused_ip.assigned_object.id == assignment.group.id
        assert reused_ip.assigned_object_type == "ipam.fhrpgroup"
        role = getattr(reused_ip.role, "value", reused_ip.role)
        assert role == "vrrp"
        assert untouched_ip.assigned_object is None

        interface = nb.dcim.interfaces.get(device=self.DEVICE, name=self.INTERFACES[30])
        assignment = list(
            nb.ipam.fhrp_group_assignments.filter(interface_id=interface.id)
        )[0]
        reused_ordinary_ip = nb.ipam.ip_addresses.get(id=ordinary_ip.id)
        assert reused_ordinary_ip.assigned_object.id == assignment.group.id
        role = getattr(reused_ordinary_ip.role, "value", reused_ordinary_ip.role)
        assert role == "vrrp"

    @pytest.mark.usefixtures("sync_vrrp_fixture")
    @pytest.mark.parametrize("dry_run", [False, True])
    def test_sync_vrrp_does_not_reassign_an_assigned_ip(
        self, nfclient: Any, dry_run: bool
    ) -> None:
        nb = get_pynetbox(nfclient)
        address = self.VIRTUAL_ADDRESSES[10]
        interface = nb.dcim.interfaces.get(device=self.DEVICE, name=self.INTERFACES[30])
        existing_ip = nb.ipam.ip_addresses.create(
            address=address,
            status="active",
            role="vip",
            assigned_object_type="dcim.interface",
            assigned_object_id=interface.id,
        )

        response = self._sync_vrrp(nfclient, dry_run=dry_run)

        for result in response.values():
            assert result["failed"] is False
            assert any(
                "already assigned" in error
                and address in error
                and f"{self.DEVICE}:{self.KEYS[10]}" in error
                for error in result["errors"]
            )
        existing_ip = nb.ipam.ip_addresses.get(id=existing_ip.id)
        assert existing_ip.assigned_object_type == "dcim.interface"
        assert existing_ip.assigned_object.id == interface.id
        role = getattr(existing_ip.role, "value", existing_ip.role)
        assert role == "vip"
        target_interface = nb.dcim.interfaces.get(
            device=self.DEVICE, name=self.INTERFACES[10]
        )
        assert (
            list(
                nb.ipam.fhrp_group_assignments.filter(interface_id=target_interface.id)
            )
            == []
        )
        expected_group_name = f"{self.DEVICE}_{self.INTERFACES[10]}_VRRP10"
        assert nb.ipam.fhrp_groups.get(name=expected_group_name) is None

    @pytest.mark.usefixtures("sync_vrrp_fixture")
    def test_sync_vrrp_creates_netbox_records_and_is_idempotent(
        self, nfclient: Any
    ) -> None:
        first_response = self._sync_vrrp(nfclient)
        for result in self._successful_results(first_response):
            assert result["result"][self.DEVICE]["created"] == self.ALL_KEYS

        nb = get_pynetbox(nfclient)
        for group_id, interface_name in self.INTERFACES.items():
            interface = nb.dcim.interfaces.get(device=self.DEVICE, name=interface_name)
            assignments = list(
                nb.ipam.fhrp_group_assignments.filter(interface_id=interface.id)
            )
            assert len(assignments) == 1
            assert assignments[0].priority == self.PRIORITIES[group_id]

            group = nb.ipam.fhrp_groups.get(id=assignments[0].group.id)
            assert group.protocol == "vrrp2"
            assert group.group_id == group_id
            assert group.auth_type is None
            assert group.name == f"{self.DEVICE}_{interface_name}_VRRP{group_id}"

            virtual_addresses = list(
                nb.ipam.ip_addresses.filter(
                    assigned_object_type="ipam.fhrpgroup",
                    assigned_object_id=group.id,
                )
            )
            assert [str(address.address) for address in virtual_addresses] == [
                self.VIRTUAL_ADDRESSES[group_id]
            ]
            role = getattr(
                virtual_addresses[0].role, "value", virtual_addresses[0].role
            )
            assert role == "vrrp"

        second_response = self._sync_vrrp(nfclient)
        for result in self._successful_results(second_response):
            actions = result["result"][self.DEVICE]
            assert actions["created"] == []
            assert actions["updated"] == []
            assert actions["in_sync"] == self.ALL_KEYS

        rename_response = self._sync_vrrp(
            nfclient,
            name_template="nf://netbox/vrrp_group_name.j2",
        )
        for result in self._successful_results(rename_response):
            actions = result["result"][self.DEVICE]
            assert actions["created"] == []
            assert actions["updated"] == self.ALL_KEYS

        for group_id, interface_name in self.INTERFACES.items():
            interface = nb.dcim.interfaces.get(device=self.DEVICE, name=interface_name)
            assignment = list(
                nb.ipam.fhrp_group_assignments.filter(interface_id=interface.id)
            )[0]
            group = nb.ipam.fhrp_groups.get(id=assignment.group.id)
            assert group.name == f"{self.DEVICE}-{interface_name}-vrrp{group_id}"

        final_response = self._sync_vrrp(
            nfclient,
            name_template="nf://netbox/vrrp_group_name.j2",
        )
        for result in self._successful_results(final_response):
            actions = result["result"][self.DEVICE]
            assert actions["created"] == []
            assert actions["updated"] == []
            assert actions["in_sync"] == self.ALL_KEYS

    @pytest.mark.usefixtures("sync_vrrp_fixture")
    def test_priority_update_only_changes_assignment(self, nfclient: Any) -> None:
        self._successful_results(self._sync_vrrp(nfclient))
        nb = get_pynetbox(nfclient)
        interface = nb.dcim.interfaces.get(device=self.DEVICE, name=self.INTERFACES[10])
        assignment = list(
            nb.ipam.fhrp_group_assignments.filter(interface_id=interface.id)
        )[0]
        group = nb.ipam.fhrp_groups.get(id=assignment.group.id)
        vip = nb.ipam.ip_addresses.get(
            assigned_object_type="ipam.fhrpgroup", assigned_object_id=group.id
        )
        group_updated = group.last_updated
        vip_updated = vip.last_updated
        assignment.update({"priority": 1})

        result = self._successful_results(self._sync_vrrp(nfclient))[0]

        assert result["diff"][self.DEVICE]["update"] == {
            self.KEYS[10]: {
                "priority": {"old_value": 1, "new_value": self.PRIORITIES[10]}
            }
        }
        assert result["result"][self.DEVICE]["updated"] == [self.KEYS[10]]
        assert (
            nb.ipam.fhrp_group_assignments.get(id=assignment.id).priority
            == self.PRIORITIES[10]
        )
        assert nb.ipam.fhrp_groups.get(id=group.id).last_updated == group_updated
        assert nb.ipam.ip_addresses.get(id=vip.id).last_updated == vip_updated

    def _cleanup_vrrp_vrf_records(self) -> None:
        ips = list(self.nb.ipam.ip_addresses.filter(address=self.VRF_ADDRESS))
        group_ids = {group.id for group in self.owned_groups}
        group_ids.update(
            ip.assigned_object_id
            for ip in ips
            if ip.assigned_object_type == "ipam.fhrpgroup"
        )
        group_ids.update(
            assignment.group.id
            for assignment in self.nb.ipam.fhrp_group_assignments.filter(
                device=self.VRF_DEVICES
            )
        )
        if ips:
            self.nb.ipam.ip_addresses.delete(ips)
        if group_ids:
            self.nb.ipam.fhrp_groups.delete(list(group_ids))
        self.owned_groups.clear()

    @pytest.fixture
    def vrrp_vrfs_fixture(self, nfclient: Any) -> Iterator[None]:
        self.nb = get_pynetbox(nfclient)
        vrfs = list(
            self.nb.ipam.vrfs.filter(
                name=[name for name in self.VRF_INTERFACE_VRFS.values() if name]
            )
        )
        self.vrf_ids = {vrf.name: vrf.id for vrf in vrfs}
        self.interfaces = list(
            self.nb.dcim.interfaces.filter(
                device=self.VRF_DEVICES, name=list(self.VRF_INTERFACE_VRFS)
            )
        )
        seed_hint = (
            "missing VRRP seed data; populate the baseline with tests/netbox_data.py"
        )
        assert len(vrfs) == 2, seed_hint
        assert {
            (interface.device.name, interface.name) for interface in self.interfaces
        } == {
            (device, name)
            for device in self.VRF_DEVICES
            for name in self.VRF_INTERFACE_VRFS
        }, seed_hint
        assert all(
            (interface.vrf.name if interface.vrf else None)
            == self.VRF_INTERFACE_VRFS[interface.name]
            for interface in self.interfaces
        ), seed_hint
        assert list(self.nb.ipam.prefixes.filter(prefix=self.VRF_PREFIX)), seed_hint
        self.owned_groups = []
        self._cleanup_vrrp_vrf_records()
        try:
            yield
        finally:
            self._cleanup_vrrp_vrf_records()

    def _sync_vrrp_vrfs(self, nfclient: Any, **kwargs: Any) -> dict:
        kwargs.setdefault("devices", self.VRF_DEVICES)
        return self._successful_results(self._sync_vrrp(nfclient, **kwargs))[0]

    @pytest.mark.usefixtures("vrrp_vrfs_fixture")
    @pytest.mark.parametrize("vip_use_vrf", [False, True])
    def test_same_vip_in_multiple_vrfs_and_later_peer(
        self, nfclient: Any, vip_use_vrf: bool
    ) -> None:
        parsed = nfclient.run_job(
            "nornir",
            "parse_ttp",
            workers=[self.NORNIR_WORKER],
            kwargs={"get": "vrrp", "FL": [self.VRF_DEVICES[0]]},
            timeout=120,
        )
        records = self._successful_results(parsed)[0]["result"][self.VRF_DEVICES[0]]
        assert {
            record["interface"]: record["vrf"] for record in records
        } == self.VRF_INTERFACE_VRFS
        dry_run = self._sync_vrrp_vrfs(nfclient, dry_run=True, vip_use_vrf=vip_use_vrf)
        assert dry_run["result"][self.VRF_DEVICES[0]]["create"] == self.VRF_KEYS
        assert not list(self.nb.ipam.ip_addresses.filter(address=self.VRF_ADDRESS))
        first = self._sync_vrrp_vrfs(
            nfclient, devices=[self.VRF_DEVICES[0]], vip_use_vrf=vip_use_vrf
        )
        assert first["result"][self.VRF_DEVICES[0]]["created"] == self.VRF_KEYS
        ips = list(self.nb.ipam.ip_addresses.filter(address=self.VRF_ADDRESS))
        assert len(ips) == 3
        assert all(str(ip.address) == f"{self.VRF_ADDRESS}/24" for ip in ips)
        assert {ip.vrf.name if ip.vrf else None for ip in ips} == (
            set(self.VRF_INTERFACE_VRFS.values()) if vip_use_vrf else {None}
        )
        initial_groups = {ip.assigned_object_id for ip in ips}
        assert len(initial_groups) == 3
        names = {
            group.id: group.name
            for group in self.nb.ipam.fhrp_groups.filter(id=list(initial_groups))
        }
        # Toggling the flag must not move existing VIPs into or out of VRFs.
        second = self._sync_vrrp_vrfs(
            nfclient, devices=[self.VRF_DEVICES[1]], vip_use_vrf=not vip_use_vrf
        )
        assert second["result"][self.VRF_DEVICES[1]]["created"] == self.VRF_KEYS
        assignments = list(
            self.nb.ipam.fhrp_group_assignments.filter(device=self.VRF_DEVICES)
        )
        assert len(assignments) == 6
        group_vrfs = {}
        for assignment in assignments:
            interface = next(
                item for item in self.interfaces if item.id == assignment.interface_id
            )
            group_vrfs.setdefault(assignment.group.id, set()).add(
                self.VRF_INTERFACE_VRFS[interface.name]
            )
        assert set(group_vrfs) == initial_groups
        assert {frozenset(vrfs) for vrfs in group_vrfs.values()} == {
            frozenset([vrf]) for vrf in self.VRF_INTERFACE_VRFS.values()
        }
        assert {
            group.id: group.name
            for group in self.nb.ipam.fhrp_groups.filter(id=list(initial_groups))
        } == names
        repeated = self._sync_vrrp_vrfs(nfclient, vip_use_vrf=not vip_use_vrf)
        for device in self.VRF_DEVICES:
            assert repeated["result"][device]["in_sync"] == self.VRF_KEYS
            assert repeated["result"][device]["created"] == []
            assert repeated["result"][device]["updated"] == []
        after_ips = list(self.nb.ipam.ip_addresses.filter(address=self.VRF_ADDRESS))
        assert {ip.id: ip.vrf.id if ip.vrf else None for ip in after_ips} == {
            ip.id: ip.vrf.id if ip.vrf else None for ip in ips
        }

    @pytest.mark.usefixtures("vrrp_vrfs_fixture")
    @pytest.mark.parametrize("vip_vrf", [None, "TEST_VRRP_BLUE"])
    def test_reused_vip_preserves_vrf(self, nfclient: Any, vip_vrf: str | None) -> None:
        vip = self.nb.ipam.ip_addresses.create(
            address=f"{self.VRF_ADDRESS}/32",
            status="active",
            role="vip",
            vrf=self.vrf_ids.get(vip_vrf),
        )
        self._sync_vrrp_vrfs(nfclient, vip_use_vrf=True)
        reused = self.nb.ipam.ip_addresses.get(id=vip.id)
        assert str(reused.address) == f"{self.VRF_ADDRESS}/32"
        assert (reused.vrf.name if reused.vrf else None) == vip_vrf
        blue_interfaces = {
            interface.id for interface in self.interfaces if interface.name == "Vlan10"
        }
        assert {
            assignment.interface_id
            for assignment in self.nb.ipam.fhrp_group_assignments.filter(
                group_id=reused.assigned_object_id
            )
        } == blue_interfaces
        repeated = self._sync_vrrp_vrfs(nfclient, vip_use_vrf=True)
        assert all(
            repeated["result"][device]["in_sync"] == self.VRF_KEYS
            for device in self.VRF_DEVICES
        )

    @pytest.mark.usefixtures("vrrp_vrfs_fixture")
    def test_named_vip_vrf_shortcut_without_assignments(self, nfclient: Any) -> None:
        group = self.nb.ipam.fhrp_groups.create(
            protocol="vrrp3", group_id=20, name="TEST_VRRP_SHORTCUT"
        )
        self.owned_groups.append(group)
        vip = self.nb.ipam.ip_addresses.create(
            address=f"{self.VRF_ADDRESS}/32",
            status="active",
            role="vip",
            vrf=self.vrf_ids["TEST_VRRP_BLUE"],
            assigned_object_type="ipam.fhrpgroup",
            assigned_object_id=group.id,
        )
        self._sync_vrrp_vrfs(nfclient)
        blue_interface_ids = {
            interface.id for interface in self.interfaces if interface.name == "Vlan10"
        }
        assignments = list(
            self.nb.ipam.fhrp_group_assignments.filter(group_id=group.id)
        )
        assert {
            assignment.interface_id for assignment in assignments
        } == blue_interface_ids
        assert (
            self.nb.ipam.ip_addresses.get(id=vip.id).vrf.id
            == self.vrf_ids["TEST_VRRP_BLUE"]
        )
        assert (
            len(list(self.nb.ipam.ip_addresses.filter(address=self.VRF_ADDRESS))) == 3
        )
        assert self.nb.ipam.ip_addresses.get(id=vip.id).role.value == "vrrp"

    @pytest.mark.usefixtures("vrrp_vrfs_fixture")
    def test_missing_vrf_is_not_created(self, nfclient: Any) -> None:
        blue = self.nb.ipam.vrfs.get(id=self.vrf_ids["TEST_VRRP_BLUE"])
        for interface in self.interfaces:
            if interface.name == "Vlan10":
                interface.update({"vrf": None})
        blue.delete()
        try:
            response = nfclient.run_job(
                "netbox",
                "sync_vrrp",
                workers=["netbox-worker-1.1"],
                kwargs={
                    "devices": [self.VRF_DEVICES[0]],
                    "vip_use_vrf": True,
                    "timeout": 120,
                },
                timeout=180,
            )
            assert response
            for result in response.values():
                assert any(
                    "vrf 'TEST_VRRP_BLUE' not found" in error
                    for error in result["errors"]
                )
                assert (
                    result["result"][self.VRF_DEVICES[0]]["created"]
                    == self.VRF_KEYS[1:]
                )
            assert not list(self.nb.ipam.vrfs.filter(name="TEST_VRRP_BLUE"))
        finally:
            # Restore the baseline record and only the owned interfaces changed above.
            blue = self.nb.ipam.vrfs.get(name="TEST_VRRP_BLUE")
            if blue is None:
                blue = self.nb.ipam.vrfs.create(
                    name="TEST_VRRP_BLUE", description="TEST_VRRP_SYNC"
                )
            self.nb.dcim.interfaces.update(
                [
                    {"id": interface.id, "vrf": blue.id}
                    for interface in self.interfaces
                    if interface.name == "Vlan10"
                ]
            )

    @pytest.mark.usefixtures("vrrp_vrfs_fixture")
    @pytest.mark.parametrize("mixed_vrfs", [False, True])
    def test_ambiguous_groups_are_reported_without_writes(
        self, nfclient: Any, mixed_vrfs: bool
    ) -> None:
        blue_interfaces = [
            interface for interface in self.interfaces if interface.name == "Vlan10"
        ]
        if mixed_vrfs:
            blue_interfaces[1] = next(
                interface for interface in self.interfaces if interface.name == "Vlan20"
            )
        group = None
        for index, interface in enumerate(blue_interfaces):
            if not mixed_vrfs or group is None:
                group = self.nb.ipam.fhrp_groups.create(
                    protocol="vrrp3", group_id=20, name=f"TEST_VRRP_AMBIGUOUS_{index}"
                )
                self.owned_groups.append(group)
                self.nb.ipam.ip_addresses.create(
                    address=f"{self.VRF_ADDRESS}/24",
                    status="active",
                    role="vrrp",
                    assigned_object_type="ipam.fhrpgroup",
                    assigned_object_id=group.id,
                )
            self.nb.ipam.fhrp_group_assignments.create(
                group=group.id,
                interface_type="dcim.interface",
                interface_id=interface.id,
                priority=100,
            )
        before_ips = {
            ip.id for ip in self.nb.ipam.ip_addresses.filter(address=self.VRF_ADDRESS)
        }
        before_assignments = {
            assignment.id
            for assignment in self.nb.ipam.fhrp_group_assignments.filter(
                device=self.VRF_DEVICES
            )
        }
        response = nfclient.run_job(
            "netbox",
            "sync_vrrp",
            workers=["netbox-worker-1.1"],
            kwargs={"devices": self.VRF_DEVICES, "timeout": 120},
            timeout=180,
        )
        assert response
        for result in response.values():
            assert result["failed"] is True
            assert any(
                "ambiguous NetBox VRRP groups" in error for error in result["errors"]
            )
        assert {
            ip.id for ip in self.nb.ipam.ip_addresses.filter(address=self.VRF_ADDRESS)
        } == before_ips
        assert {
            assignment.id
            for assignment in self.nb.ipam.fhrp_group_assignments.filter(
                device=self.VRF_DEVICES
            )
        } == before_assignments


class TestSyncVrrpEmptyResult:
    DEVICE = "fn-ceos-lf-3"
    NORNIR_WORKER = "nornir-worker-4"

    def test_sync_vrrp_empty_live_and_netbox_are_in_sync(self, nfclient: Any) -> None:
        parsed = nfclient.run_job(
            "nornir",
            "parse_ttp",
            workers=[self.NORNIR_WORKER],
            kwargs={"get": "vrrp", "FL": [self.DEVICE]},
            timeout=120,
        )
        assert parsed
        for result in parsed.values():
            assert result["failed"] is False
            assert result["result"][self.DEVICE] == []

        nb = get_pynetbox(nfclient)
        device = nb.dcim.devices.get(name=self.DEVICE)
        interface_ids = [
            interface.id for interface in nb.dcim.interfaces.filter(device_id=device.id)
        ]
        assignments_before = {
            assignment.id
            for interface_id in interface_ids
            for assignment in nb.ipam.fhrp_group_assignments.filter(
                interface_id=interface_id
            )
        }
        assert not assignments_before

        response = nfclient.run_job(
            "netbox",
            "sync_vrrp",
            workers="any",
            kwargs={"devices": [self.DEVICE], "timeout": 120},
            timeout=180,
        )

        assert response
        for result in response.values():
            assert result["failed"] is False
            assert result["errors"] == []
            assert result["result"][self.DEVICE] == {
                "created": [],
                "updated": [],
                "deleted": [],
                "in_sync": [],
            }
        assignments_after = {
            assignment.id
            for interface_id in interface_ids
            for assignment in nb.ipam.fhrp_group_assignments.filter(
                interface_id=interface_id
            )
        }
        assert assignments_after == assignments_before

    def test_sync_vrrp_reports_deletion_without_deleting(self, nfclient: Any) -> None:
        nb = get_pynetbox(nfclient)
        device = nb.dcim.devices.get(name=self.DEVICE)
        interface = next(iter(nb.dcim.interfaces.filter(device_id=device.id)))
        group = None
        assignment = None
        try:
            group = nb.ipam.fhrp_groups.create(
                protocol="vrrp2", group_id=2999, name="TEST_VRRP_DELETION_PLAN"
            )
            assignment = nb.ipam.fhrp_group_assignments.create(
                group=group.id,
                interface_type="dcim.interface",
                interface_id=interface.id,
                priority=100,
            )
            response = nfclient.run_job(
                "netbox",
                "sync_vrrp",
                workers="any",
                kwargs={"devices": [self.DEVICE], "timeout": 120},
                timeout=180,
            )
            key = f"{interface.name}:vrrp2:2999"
            assert response
            for result in response.values():
                assert result["failed"] is False
                assert result["errors"] == []
                assert result["diff"][self.DEVICE]["delete"] == [key]
                assert result["result"][self.DEVICE]["deleted"] == []
            assert nb.ipam.fhrp_group_assignments.get(id=assignment.id) is not None
        finally:
            if assignment is not None:
                assignment.delete()
            if group is not None:
                group.delete()


class TestSyncVrrpAristaPeers:
    DEVICES = ["fn-ceos-lf-1", "fn-ceos-lf-2"]
    NORNIR_WORKER = "nornir-worker-4"
    INTERFACE = "Vlan250"
    GROUP_ID = 20
    VIRTUAL_ADDRESS = "198.18.252.1"
    PRIORITIES = {"fn-ceos-lf-1": 110, "fn-ceos-lf-2": 100}

    @staticmethod
    def _successful_results(response: dict) -> list[dict]:
        assert response
        results = []
        for worker, result in response.items():
            assert result["failed"] is False, f"{worker} failed: {result}"
            assert result["errors"] == [], f"{worker} returned errors: {result}"
            results.append(result)
        return results

    def _delete_vrrp_records(self) -> None:
        group_ids = set()
        for device_name in self.DEVICES:
            interface = self.nb.dcim.interfaces.get(
                device=device_name, name=self.INTERFACE
            )
            assert interface is not None, (
                f"seeded NetBox interface '{device_name}:{self.INTERFACE}' is "
                "missing; populate the baseline with tests/netbox_data.py"
            )
            for assignment in self.nb.ipam.fhrp_group_assignments.filter(
                interface_id=interface.id
            ):
                group_ids.add(assignment.group.id)

        for group_id in group_ids:
            for ip_address in self.nb.ipam.ip_addresses.filter(
                assigned_object_type="ipam.fhrpgroup",
                assigned_object_id=group_id,
            ):
                ip_address.delete()
            group = self.nb.ipam.fhrp_groups.get(id=group_id)
            if group:
                group.delete()

        for ip_address in self.nb.ipam.ip_addresses.filter(
            address=self.VIRTUAL_ADDRESS
        ):
            if str(ip_address.address).startswith(f"{self.VIRTUAL_ADDRESS}/"):
                ip_address.delete()

    @pytest.fixture(autouse=True)
    def sync_vrrp_fixture(self, nfclient: Any) -> Iterator[None]:
        self.nb = get_pynetbox(nfclient)
        self._delete_vrrp_records()
        yield
        self._delete_vrrp_records()

    def _sync_vrrp(self, nfclient: Any, **kwargs: Any) -> dict:
        return nfclient.run_job(
            "netbox",
            "sync_vrrp",
            workers="any",
            kwargs={"devices": self.DEVICES, "timeout": 120, **kwargs},
            timeout=180,
        )

    def test_arista_vrrp_getter_reads_both_peers(self, nfclient: Any) -> None:
        response = nfclient.run_job(
            "nornir",
            "parse_ttp",
            workers=[self.NORNIR_WORKER],
            kwargs={"get": "vrrp", "FL": self.DEVICES},
            timeout=120,
        )

        result = self._successful_results(response)[0]["result"]
        for device_name in self.DEVICES:
            assert result[device_name] == [
                {
                    "interface": self.INTERFACE,
                    "vrf": None,
                    "group": self.GROUP_ID,
                    "protocol": "vrrpv3",
                    "virtual_address": self.VIRTUAL_ADDRESS,
                    "priority": self.PRIORITIES[device_name],
                    "authentication_type": None,
                }
            ]

    def test_sync_vrrp_keeps_different_protocol_assignment(self, nfclient: Any) -> None:
        existing_group = self.nb.ipam.fhrp_groups.create(
            protocol="vrrp2",
            group_id=self.GROUP_ID,
            name="fn-ceos-lf-1_Vlan250_VRRP20",
        )
        self.nb.ipam.ip_addresses.create(
            address="198.18.253.1/24",
            status="active",
            role="vrrp",
            assigned_object_type="ipam.fhrpgroup",
            assigned_object_id=existing_group.id,
        )
        interface = self.nb.dcim.interfaces.get(
            device=self.DEVICES[0], name=self.INTERFACE
        )
        self.nb.ipam.fhrp_group_assignments.create(
            group=existing_group.id,
            interface_type="dcim.interface",
            interface_id=interface.id,
            priority=self.PRIORITIES[self.DEVICES[0]],
        )

        response = self._sync_vrrp(nfclient)

        key = f"{self.INTERFACE}:vrrp3:{self.GROUP_ID}"
        for result in self._successful_results(response):
            assert result["result"][self.DEVICES[0]]["created"] == [key]
            assert result["result"][self.DEVICES[1]]["created"] == [key]

        vrrp3_group_ids = set()
        for device_name in self.DEVICES:
            interface = self.nb.dcim.interfaces.get(
                device=device_name, name=self.INTERFACE
            )
            assignments = list(
                self.nb.ipam.fhrp_group_assignments.filter(interface_id=interface.id)
            )
            protocols = {
                assignment.group.id: self.nb.ipam.fhrp_groups.get(
                    id=assignment.group.id
                ).protocol
                for assignment in assignments
            }
            assert "vrrp3" in protocols.values()
            if device_name == self.DEVICES[0]:
                assert set(protocols.values()) == {"vrrp2", "vrrp3"}
            else:
                assert set(protocols.values()) == {"vrrp3"}
            vrrp3_group_ids.update(
                group_id
                for group_id, protocol in protocols.items()
                if protocol == "vrrp3"
            )
        assert vrrp3_group_ids != {existing_group.id}
        assert len(vrrp3_group_ids) == 1
        assert self.nb.ipam.fhrp_groups.get(id=existing_group.id).protocol == "vrrp2"

    def test_sync_vrrp_reuses_one_group_across_peers(self, nfclient: Any) -> None:
        key = f"{self.INTERFACE}:vrrp3:{self.GROUP_ID}"

        dry_run = self._sync_vrrp(nfclient, dry_run=True)
        for result in self._successful_results(dry_run):
            for device_name in self.DEVICES:
                assert result["result"][device_name]["create"] == [key]

        first_sync = self._sync_vrrp(nfclient)
        for result in self._successful_results(first_sync):
            for device_name in self.DEVICES:
                assert result["result"][device_name]["created"] == [key]

        group_ids = set()
        for device_name in self.DEVICES:
            interface = self.nb.dcim.interfaces.get(
                device=device_name, name=self.INTERFACE
            )
            assignments = list(
                self.nb.ipam.fhrp_group_assignments.filter(interface_id=interface.id)
            )
            assert len(assignments) == 1
            assert assignments[0].priority == self.PRIORITIES[device_name]
            group_ids.add(assignments[0].group.id)

        assert len(group_ids) == 1
        group = self.nb.ipam.fhrp_groups.get(id=group_ids.pop())
        assert group.protocol == "vrrp3"
        assert group.group_id == self.GROUP_ID
        assert group.name == "fn-ceos-lf-1_Vlan250_VRRP20"
        virtual_addresses = list(
            self.nb.ipam.ip_addresses.filter(
                assigned_object_type="ipam.fhrpgroup",
                assigned_object_id=group.id,
            )
        )
        assert [str(address.address) for address in virtual_addresses] == [
            f"{self.VIRTUAL_ADDRESS}/24"
        ]

        second_sync = self._sync_vrrp(nfclient)
        for result in self._successful_results(second_sync):
            for device_name in self.DEVICES:
                actions = result["result"][device_name]
                assert actions["created"] == []
                assert actions["updated"] == []
                assert actions["in_sync"] == [key]

    @pytest.mark.parametrize("repair_existing", [False, True])
    def test_sync_vrrp_joins_existing_group_in_later_call(
        self, nfclient: Any, repair_existing: bool
    ) -> None:
        key = f"{self.INTERFACE}:vrrp3:{self.GROUP_ID}"
        first_device, second_device = self.DEVICES
        first_sync = self._sync_vrrp(nfclient, devices=[first_device])
        for result in self._successful_results(first_sync):
            assert result["result"][first_device]["created"] == [key]
        vip = self.nb.ipam.ip_addresses.get(address=self.VIRTUAL_ADDRESS)
        group_id = vip.assigned_object_id
        group_name = self.nb.ipam.fhrp_groups.get(id=group_id).name
        devices = [second_device]
        if repair_existing:
            self.nb.ipam.fhrp_groups.get(id=group_id).update({"auth_type": "md5"})
            devices = self.DEVICES

        dry_run = self._sync_vrrp(nfclient, devices=devices, dry_run=True)
        for result in self._successful_results(dry_run):
            assert result["result"][second_device]["create"] == [key]

        second_sync = self._sync_vrrp(nfclient, devices=devices)
        for result in self._successful_results(second_sync):
            assert result["result"][second_device]["created"] == [key]
        interface = self.nb.dcim.interfaces.get(
            device=second_device, name=self.INTERFACE
        )
        assignments = list(
            self.nb.ipam.fhrp_group_assignments.filter(interface_id=interface.id)
        )
        assert len(assignments) == 1
        assert assignments[0].group.id == group_id
        assert assignments[0].priority == self.PRIORITIES[second_device]
        assert self.nb.ipam.fhrp_groups.get(id=group_id).name == group_name
        assert self.nb.ipam.fhrp_groups.get(id=group_id).auth_type is None
        assert self.nb.ipam.ip_addresses.get(address=self.VIRTUAL_ADDRESS).id == vip.id

        repeated_sync = self._sync_vrrp(nfclient, devices=[second_device])
        for result in self._successful_results(repeated_sync):
            assert result["result"][second_device]["in_sync"] == [key]
            assert result["result"][second_device]["created"] == []
            assert result["result"][second_device]["updated"] == []
        assert self.nb.ipam.fhrp_groups.get(id=group_id).name == group_name
