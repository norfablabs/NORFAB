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
            "run tests/netbox_data.py --sync-vrrp"
        )
        group_ids = set()
        for interface_name in cls.INTERFACES.values():
            interface = nb.dcim.interfaces.get(device_id=device.id, name=interface_name)
            assert interface is not None, (
                f"seeded NetBox interface '{cls.DEVICE}:{interface_name}' is missing; "
                "run tests/netbox_data.py --sync-vrrp"
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

        for address in cls.VIRTUAL_ADDRESSES.values():
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

    @pytest.fixture(autouse=True)
    def sync_vrrp_fixture(self, nfclient: Any) -> Iterator[None]:
        self._cleanup_vrrp_records(nfclient)
        self._start_fakenos(nfclient)
        yield
        self._stop_fakenos(nfclient)
        self._cleanup_vrrp_records(nfclient)

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
            result["result"][self.DEVICE], key=lambda item: item["group"]
        ) == [
            {
                "interface": self.INTERFACES[10],
                "group": 10,
                "protocol": "vrrpv2",
                "virtual_address": "198.18.250.1",
                "priority": 110,
                "authentication_type": None,
            },
            {
                "interface": self.INTERFACES[30],
                "group": 30,
                "protocol": "vrrpv2",
                "virtual_address": "198.18.251.1",
                "priority": 120,
                "authentication_type": None,
            },
        ]

    def test_sync_vrrp_dry_run_does_not_write_to_netbox(self, nfclient: Any) -> None:
        response = self._sync_vrrp(nfclient, dry_run=True)

        for result in self._successful_results(response):
            actions = result["result"][self.DEVICE]
            assert actions["create"] == [
                f"{self.INTERFACES[10]}:10",
                f"{self.INTERFACES[30]}:30",
            ]
            assert actions["update"] == {}
            assert actions["delete"] == []
            assert actions["in_sync"] == []

        nb = get_pynetbox(nfclient)
        for interface_name in self.INTERFACES.values():
            interface = nb.dcim.interfaces.get(device=self.DEVICE, name=interface_name)
            assert (
                list(nb.ipam.fhrp_group_assignments.filter(interface_id=interface.id))
                == []
            )

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
        key = f"{self.INTERFACES[10]}:10"
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

    def test_sync_vrrp_does_not_reassign_an_assigned_ip(self, nfclient: Any) -> None:
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

        response = self._sync_vrrp(nfclient)

        for result in response.values():
            assert result["failed"] is False
            assert any(
                "already assigned" in error
                and address in error
                and f"{self.DEVICE}:{self.INTERFACES[10]}:10" in error
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
        assert list(nb.ipam.fhrp_groups.filter(protocol="vrrp2", group_id=10)) == []

    def test_sync_vrrp_creates_netbox_records_and_is_idempotent(
        self, nfclient: Any
    ) -> None:
        first_response = self._sync_vrrp(nfclient)
        for result in self._successful_results(first_response):
            assert result["result"][self.DEVICE]["created"] == [
                f"{self.INTERFACES[10]}:10",
                f"{self.INTERFACES[30]}:30",
            ]

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
            assert actions["in_sync"] == [
                f"{self.INTERFACES[10]}:10",
                f"{self.INTERFACES[30]}:30",
            ]

        rename_response = self._sync_vrrp(
            nfclient,
            name_template="nf://netbox/vrrp_group_name.j2",
        )
        for result in self._successful_results(rename_response):
            actions = result["result"][self.DEVICE]
            assert actions["created"] == []
            assert actions["updated"] == [
                f"{self.INTERFACES[10]}:10",
                f"{self.INTERFACES[30]}:30",
            ]

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
            assert actions["in_sync"] == [
                f"{self.INTERFACES[10]}:10",
                f"{self.INTERFACES[30]}:30",
            ]


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
                "missing; run tests/netbox_data.py --sync-vrrp"
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
                    "group": self.GROUP_ID,
                    "protocol": "vrrpv3",
                    "virtual_address": self.VIRTUAL_ADDRESS,
                    "priority": self.PRIORITIES[device_name],
                    "authentication_type": None,
                }
            ]

    def test_sync_vrrp_updates_group_protocol_and_reuses_it(
        self, nfclient: Any
    ) -> None:
        group = self.nb.ipam.fhrp_groups.create(
            protocol="vrrp2",
            group_id=self.GROUP_ID,
            name="fn-ceos-lf-1_Vlan250_VRRP20",
        )
        self.nb.ipam.ip_addresses.create(
            address=f"{self.VIRTUAL_ADDRESS}/24",
            status="active",
            role="vrrp",
            assigned_object_type="ipam.fhrpgroup",
            assigned_object_id=group.id,
        )
        interface = self.nb.dcim.interfaces.get(
            device=self.DEVICES[0], name=self.INTERFACE
        )
        self.nb.ipam.fhrp_group_assignments.create(
            group=group.id,
            interface_type="dcim.interface",
            interface_id=interface.id,
            priority=self.PRIORITIES[self.DEVICES[0]],
        )

        response = self._sync_vrrp(nfclient)

        for result in self._successful_results(response):
            assert result["result"][self.DEVICES[0]]["updated"] == [
                f"{self.INTERFACE}:{self.GROUP_ID}"
            ]
            assert result["result"][self.DEVICES[1]]["created"] == [
                f"{self.INTERFACE}:{self.GROUP_ID}"
            ]
        assert self.nb.ipam.fhrp_groups.get(id=group.id).protocol == "vrrp3"
        assignments = []
        for device_name in self.DEVICES:
            interface = self.nb.dcim.interfaces.get(
                device=device_name, name=self.INTERFACE
            )
            assignments.extend(
                self.nb.ipam.fhrp_group_assignments.filter(interface_id=interface.id)
            )
        assert {assignment.group.id for assignment in assignments} == {group.id}

    def test_sync_vrrp_reuses_one_group_across_peers(self, nfclient: Any) -> None:
        key = f"{self.INTERFACE}:{self.GROUP_ID}"

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
