from collections.abc import Iterator
from typing import Any

import pytest

from tests.services.netbox.common import get_pynetbox

pytestmark = [pytest.mark.netbox, pytest.mark.netbox_design_deploy]


class TestDesignDeploy:
    DEVICES = ["design-router-1", "design-router-2"]

    @pytest.fixture(autouse=True)
    def cleanup_design_objects(self, nfclient: Any) -> Iterator[None]:
        nb = get_pynetbox(nfclient)
        existed = {
            "region": nb.dcim.regions.get(name="undefined"),
            "site": nb.dcim.sites.get(name="undefined"),
            "manufacturer": nb.dcim.manufacturers.get(name="undefined"),
            "role": nb.dcim.device_roles.get(name="undefined"),
            "device_type": nb.dcim.device_types.get(model="undefined"),
        }
        for device_name in self.DEVICES:
            device = nb.dcim.devices.get(name=device_name)
            if device:
                device.delete()
        yield
        for device_name in self.DEVICES:
            device = nb.dcim.devices.get(name=device_name)
            if device:
                device.delete()
        for key, endpoint, filters in (
            ("device_type", nb.dcim.device_types, {"model": "undefined"}),
            ("role", nb.dcim.device_roles, {"name": "undefined"}),
            ("site", nb.dcim.sites, {"name": "undefined"}),
            ("manufacturer", nb.dcim.manufacturers, {"name": "undefined"}),
            ("region", nb.dcim.regions, {"name": "undefined"}),
        ):
            if existed[key] is None:
                obj = endpoint.get(**filters)
                if obj:
                    obj.delete()

    def run_design(self, nfclient: Any, dry_run: bool) -> dict:
        return nfclient.run_job(
            "netbox",
            "design_deploy",
            workers="any",
            kwargs={
                "design": "nf://netbox/designs/includes/base_devices.yaml",
                "context": {"devices": self.DEVICES},
                "dry_run": dry_run,
            },
        )

    def test_inline_input_schema_rejects_invalid_data(self, nfclient: Any) -> None:
        response = nfclient.run_job(
            "netbox",
            "design_deploy",
            workers="any",
            kwargs={
                "design": "nf://netbox/designs/includes/base_devices.yaml",
                "context": {"devices": self.DEVICES, "unknown": True},
            },
        )

        for result in response.values():
            assert result["failed"] is True

    def test_pydantic_input_schema_and_include(self, nfclient: Any) -> None:
        response = nfclient.run_job(
            "netbox",
            "design_deploy",
            workers="any",
            kwargs={
                "design": "nf://netbox/designs/pydantic_input_design.yaml",
                "context": {"devices": self.DEVICES},
                "dry_run": True,
            },
        )

        for worker, result in response.items():
            assert result["failed"] is False, f"{worker} failed: {result}"
            assert result["result"]["created"]["devices"] == self.DEVICES

    def test_minimal_device_design_dry_run(self, nfclient: Any) -> None:
        response = self.run_design(nfclient, dry_run=True)

        for worker, result in response.items():
            assert result["failed"] is False, f"{worker} failed: {result}"
            assert result["dry_run"] is True
            assert result["result"]["created"]["devices"] == self.DEVICES
            handled_collections = set(result["result"]["created"]) | set(
                result["result"]["unchanged"]
            )
            assert handled_collections >= {
                "regions",
                "sites",
                "manufacturers",
                "device_roles",
                "device_types",
                "devices",
            }
            assert result["diff"]["devices"]["design-router-1"]["fields"] == {
                "name": "design-router-1",
                "site": {"name": "undefined"},
                "role": {"name": "undefined"},
                "device_type": {"model": "undefined"},
                "status": "active",
            }

    def test_minimal_device_design_apply_is_idempotent(self, nfclient: Any) -> None:
        first = self.run_design(nfclient, dry_run=False)
        for worker, result in first.items():
            assert result["failed"] is False, f"{worker} failed: {result}"
            assert result["result"]["created"]["devices"] == self.DEVICES

        second = self.run_design(nfclient, dry_run=False)
        for worker, result in second.items():
            assert result["failed"] is False, f"{worker} failed: {result}"
            assert result["result"]["unchanged"]["devices"] == self.DEVICES


class TestDeviceInterfacesDesign:
    DEVICES = ["design-edge-1", "design-edge-2"]

    def remove_design_objects(self, nfclient: Any) -> None:
        nb = get_pynetbox(nfclient)
        for device_name in self.DEVICES:
            device = nb.dcim.devices.get(name=device_name)
            if device:
                device.delete()
        for endpoint, filters in (
            (nb.dcim.device_types, {"model": "DESIGN ROUTER"}),
            (nb.dcim.device_roles, {"name": "ROUTER"}),
            (nb.dcim.sites, {"name": "DESIGN SITE"}),
            (nb.dcim.platforms, {"name": "DESIGN OS"}),
            (nb.dcim.manufacturers, {"name": "DESIGN LABS"}),
            (nb.dcim.regions, {"name": "DESIGN REGION"}),
        ):
            obj = endpoint.get(**filters)
            if obj:
                obj.delete()

    @pytest.fixture(autouse=True)
    def cleanup_design_objects(self, nfclient: Any) -> Iterator[None]:
        self.remove_design_objects(nfclient)
        yield
        self.remove_design_objects(nfclient)

    def run_design(self, nfclient: Any, dry_run: bool = False) -> dict:
        return nfclient.run_job(
            "netbox",
            "design_deploy",
            workers="any",
            kwargs={
                "design": "nf://netbox/designs/device_interfaces_design.yaml",
                "dry_run": dry_run,
            },
        )

    def test_device_interfaces_design_end_to_end(self, nfclient: Any) -> None:
        first = self.run_design(nfclient)
        for worker, result in first.items():
            assert result["failed"] is False, f"{worker} failed: {result}"
            assert result["result"]["created"]["devices"] == self.DEVICES
            assert len(result["result"]["created"]["interfaces"]) == 12

        nb = get_pynetbox(nfclient)
        first_device = nb.dcim.devices.get(name="design-edge-1")
        assert first_device.device_type.model == "DESIGN ROUTER"
        assert first_device.role.name == "ROUTER"
        assert first_device.site.name == "DESIGN SITE"
        assert first_device.platform.name == "DESIGN OS"

        interfaces = list(nb.dcim.interfaces.filter(device_id=first_device.id))
        assert {interface.name for interface in interfaces} == {
            "Ethernet1",
            "Ethernet2",
            "Ethernet3",
            "Ethernet4",
            "Loopback0",
            "Loopback1",
        }

        first_device.update({"status": "planned"})
        nb.dcim.interfaces.get(device_id=first_device.id, name="Ethernet1").update(
            {"enabled": False}
        )

        repaired = self.run_design(nfclient)
        for worker, result in repaired.items():
            assert result["failed"] is False, f"{worker} failed: {result}"
            assert result["result"]["updated"]["devices"] == ["design-edge-1"]
            assert result["result"]["updated"]["interfaces"] == ["Ethernet1"]

        unchanged = self.run_design(nfclient)
        for worker, result in unchanged.items():
            assert result["failed"] is False, f"{worker} failed: {result}"
            assert result["result"]["updated"] == {}
            assert result["result"]["unchanged"]["devices"] == self.DEVICES
            assert len(result["result"]["unchanged"]["interfaces"]) == 12


class TestAllocationsDesign:
    PARENT_PREFIX = "10.254.0.0/16"
    VLAN_GROUP = "DESIGN VLAN POOL"
    ASN_RANGE = "DESIGN ASN POOL"
    RIR = "DESIGN RIR"

    def remove_design_objects(self, nfclient: Any) -> None:
        nb = get_pynetbox(nfclient)
        session = nb.plugins.bgp.session.get(name="DESIGN ALLOCATED BGP SESSION")
        if session:
            session.delete()
        mac_address = nb.dcim.mac_addresses.get(mac_address="02:00:00:00:00:01")
        if mac_address:
            mac_address.delete()
        device = nb.dcim.devices.get(name="design-allocation-1")
        if device:
            device.delete()
        for ip_address in list(nb.ipam.ip_addresses.filter(parent=self.PARENT_PREFIX)):
            ip_address.delete()
        for prefix in list(nb.ipam.prefixes.filter(within=self.PARENT_PREFIX)):
            prefix.delete()
        parent = nb.ipam.prefixes.get(prefix=self.PARENT_PREFIX)
        if parent:
            parent.delete()

        vlan_group = nb.ipam.vlan_groups.get(name=self.VLAN_GROUP)
        if vlan_group:
            for vlan in list(nb.ipam.vlans.filter(group_id=vlan_group.id)):
                vlan.delete()
            vlan_group.delete()

        for asn in list(nb.ipam.asns.filter(asn__gte=64512, asn__lte=64599)):
            asn.delete()
        asn_range = nb.ipam.asn_ranges.get(name=self.ASN_RANGE)
        if asn_range:
            asn_range.delete()
        rir = nb.ipam.rirs.get(name=self.RIR)
        if rir:
            rir.delete()
        vrf = nb.ipam.vrfs.get(name="DESIGN ALLOCATED VRF")
        if vrf:
            vrf.delete()
        route_target = nb.ipam.route_targets.get(name="64512:100")
        if route_target:
            route_target.delete()

    @pytest.fixture(autouse=True)
    def allocation_pools(self, nfclient: Any) -> Iterator[None]:
        self.remove_design_objects(nfclient)
        nb = get_pynetbox(nfclient)
        nb.ipam.prefixes.create(prefix=self.PARENT_PREFIX, status="active")
        nb.ipam.vlan_groups.create(
            name=self.VLAN_GROUP,
            slug="design-vlan-pool",
            vid_ranges=[[1000, 1099]],
        )
        rir = nb.ipam.rirs.create(name=self.RIR, slug="design-rir", is_private=True)
        nb.ipam.asn_ranges.create(
            name=self.ASN_RANGE,
            slug="design-asn-pool",
            rir=rir.id,
            start=64512,
            end=64599,
        )
        yield
        self.remove_design_objects(nfclient)

    def run_design(self, nfclient: Any) -> dict:
        return nfclient.run_job(
            "netbox",
            "design_deploy",
            workers="any",
            kwargs={
                "design": "nf://netbox/designs/allocations_design.yaml",
            },
        )

    def test_allocations_design_end_to_end(self, nfclient: Any) -> None:
        first = self.run_design(nfclient)
        for worker, result in first.items():
            assert result["failed"] is False, f"{worker} failed: {result}"

        nb = get_pynetbox(nfclient)
        prefix = nb.ipam.prefixes.get(description="DESIGN ALLOCATED PREFIX")
        assert prefix is not None
        assert prefix.prefix == "10.254.0.0/28"

        ip_address = nb.ipam.ip_addresses.get(description="DESIGN ALLOCATED IP")
        assert ip_address is not None
        assert ip_address.address == "10.254.0.1/28"
        assert ip_address.assigned_object.device.name == "design-allocation-1"
        assert ip_address.assigned_object.name == "Ethernet1"

        vlan_group = nb.ipam.vlan_groups.get(name=self.VLAN_GROUP)
        vlan = nb.ipam.vlans.get(group_id=vlan_group.id, name="DESIGN VLAN")
        assert vlan is not None
        assert vlan.vid == 1000

        interface = nb.dcim.interfaces.get(
            device="design-allocation-1", name="Ethernet1"
        )
        assert interface.mode.value == "access"
        assert interface.untagged_vlan.id == vlan.id

        asn = nb.ipam.asns.get(description="DESIGN LOCAL ASN")
        assert asn is not None
        assert asn.asn == 64512
        assert asn.rir.name == self.RIR

        mac_address = nb.dcim.mac_addresses.get(mac_address="02:00:00:00:00:01")
        assert mac_address.assigned_object.id == interface.id
        session = nb.plugins.bgp.session.get(name="DESIGN ALLOCATED BGP SESSION")
        assert session.device.name == "design-allocation-1"
        assert session.local_as.asn == 64512
        assert session.remote_as.asn == 64513
        vrf = nb.ipam.vrfs.get(name="DESIGN ALLOCATED VRF")
        assert [target.name for target in vrf.import_targets] == ["64512:100"]

        second = self.run_design(nfclient)
        for worker, result in second.items():
            assert result["failed"] is False, f"{worker} failed: {result}"
            assert result["result"]["created"] == {}
            assert result["result"]["updated"] == {}
            assert {"devices", "interfaces"}.issubset(result["result"]["unchanged"])
            assert {"prefixes", "ip_addresses"}.issubset(result["result"]["unchanged"])
            assert not {"vlans", "asns"}.intersection(result["result"]["unchanged"])


class TestStaticNestedDesign:
    @pytest.fixture(autouse=True)
    def cleanup_design_objects(self, nfclient: Any) -> Iterator[None]:
        nb = get_pynetbox(nfclient)

        def remove() -> None:
            device = nb.dcim.devices.get(name="design-static-1")
            if device:
                device.delete()
            for address in ("10.253.0.1/24", "10.253.0.254/24"):
                ip_address = nb.ipam.ip_addresses.get(address=address)
                if ip_address:
                    ip_address.delete()
            prefix = nb.ipam.prefixes.get(prefix="10.253.0.0/24")
            if prefix:
                prefix.delete()
            vrf = nb.ipam.vrfs.get(name="DESIGN STATIC VRF")
            if vrf:
                vrf.delete()
            route_target = nb.ipam.route_targets.get(name="65000:1200")
            if route_target:
                route_target.delete()
            vlan_group = nb.ipam.vlan_groups.get(name="DESIGN STATIC VLAN POOL")
            if vlan_group:
                for vlan in list(nb.ipam.vlans.filter(group_id=vlan_group.id)):
                    vlan.delete()
                vlan_group.delete()
            role = nb.ipam.roles.get(name="DESIGN STATIC ACCESS")
            if role:
                role.delete()
            site = nb.dcim.sites.get(name="DESIGN STATIC SITE")
            if site:
                site.delete()

        remove()
        yield
        remove()

    @staticmethod
    def run_design(nfclient: Any) -> dict:
        return nfclient.run_job(
            "netbox",
            "design_deploy",
            workers="any",
            kwargs={"design": "nf://netbox/designs/static_nested_design.yaml"},
        )

    def test_static_global_and_nested_objects(self, nfclient: Any) -> None:
        first = self.run_design(nfclient)
        for worker, result in first.items():
            assert result["failed"] is False, f"{worker} failed: {result}"

        nb = get_pynetbox(nfclient)
        prefix = nb.ipam.prefixes.get(prefix="10.253.0.0/24")
        assert prefix.scope.name == "DESIGN STATIC SITE"
        assert prefix.role.name == "DESIGN STATIC ACCESS"

        interface = nb.dcim.interfaces.get(device="design-static-1", name="Ethernet1")
        assert interface.mode.value == "access"
        assert interface.untagged_vlan.name == "DESIGN STATIC VLAN"
        tagged_interface = nb.dcim.interfaces.get(
            device="design-static-1", name="Ethernet2"
        )
        assert tagged_interface.mode.value == "tagged"
        assert [vlan.name for vlan in tagged_interface.tagged_vlans] == [
            "DESIGN STATIC TAGGED VLAN"
        ]

        assigned_ip = nb.ipam.ip_addresses.get(address="10.253.0.1/24")
        assert assigned_ip.assigned_object.id == interface.id
        unassigned_ip = nb.ipam.ip_addresses.get(address="10.253.0.254/24")
        assert unassigned_ip.assigned_object is None

        vrf = nb.ipam.vrfs.get(name="DESIGN STATIC VRF")
        assert [target.name for target in vrf.import_targets] == ["65000:1200"]
        assert [target.name for target in vrf.export_targets] == ["65000:1200"]

        second = self.run_design(nfclient)
        for worker, result in second.items():
            assert result["failed"] is False, f"{worker} failed: {result}"
            assert result["result"]["created"] == {}
            assert result["result"]["updated"] == {}


class TestBranchOfficeDesign:
    SITE = "BRANCH-001"
    DEVICES = [
        "branch-001-rtr-1",
        "branch-001-rtr-2",
        "branch-001-sw-1",
        "branch-001-sw-2",
    ]
    VRFS = ["MGMT", "VOICE", "CORP", "INTERNET"]
    PREFIX = "10.60.0.0/16"
    VLAN_GROUP = "BRANCH-001 VLANS"
    ASN_RANGE = "BRANCH-ASNS"
    RIR = "BRANCH-001-RIR"
    RD_PREFIX = 65000
    ASN_START = 4200101000
    ASN_END = 4200101099

    @pytest.fixture(autouse=True)
    def cleanup_design_objects(self, nfclient: Any) -> Iterator[None]:
        nb = get_pynetbox(nfclient)

        def remove() -> None:
            for name in ("BRANCH-001-RTR-1-IBGP", "BRANCH-001-RTR-2-IBGP"):
                session = nb.plugins.bgp.session.get(name=name)
                if session:
                    session.delete()
            for label in (
                "BRANCH-001-RTR-1-UPLINK",
                "BRANCH-001-RTR-2-UPLINK",
                "BRANCH-001-SWITCH-PEER",
            ):
                cable = nb.dcim.cables.get(label=label)
                if cable:
                    cable.delete()
            for name in (
                "BRANCH-001-MGMT-VRRP",
                "BRANCH-001-VOICE-VRRP",
                "BRANCH-001-CORP-VRRP",
                "BRANCH-001-INTERNET-VRRP",
            ):
                group = nb.ipam.fhrp_groups.get(name=name)
                if group:
                    for assignment in list(
                        nb.ipam.fhrp_group_assignments.filter(group_id=group.id)
                    ):
                        assignment.delete()
                    group.delete()
            for address in (
                "02:60:00:00:00:01",
                "02:60:00:00:00:02",
                "02:60:00:00:01:01",
                "02:60:00:00:01:02",
            ):
                mac_address = nb.dcim.mac_addresses.get(mac_address=address)
                if mac_address:
                    mac_address.delete()
            for device_name in self.DEVICES:
                device = nb.dcim.devices.get(name=device_name)
                if device:
                    device.delete()
            for prefix in list(nb.ipam.prefixes.filter(within=self.PREFIX)):
                for ip_address in list(
                    nb.ipam.ip_addresses.filter(parent=prefix.prefix)
                ):
                    ip_address.delete()
                prefix.delete()
            top_level_prefix = nb.ipam.prefixes.get(prefix=self.PREFIX)
            if top_level_prefix:
                top_level_prefix.delete()
            for name in self.VRFS:
                vrf = nb.ipam.vrfs.get(name=name)
                if vrf:
                    vrf.delete()
            for name in ("65000:10", "65000:11", "65000:12", "65000:13"):
                route_target = nb.ipam.route_targets.get(name=name)
                if route_target:
                    route_target.delete()
            vlan_group = nb.ipam.vlan_groups.get(name=self.VLAN_GROUP)
            if vlan_group:
                for vlan in list(nb.ipam.vlans.filter(group_id=vlan_group.id)):
                    vlan.delete()
                vlan_group.delete()
            for asn in list(
                nb.ipam.asns.filter(asn__gte=4200101000, asn__lte=4200101099)
            ):
                asn.delete()
            asn_range = nb.ipam.asn_ranges.get(name=self.ASN_RANGE)
            if asn_range:
                asn_range.delete()
            rir = nb.ipam.rirs.get(name=self.RIR)
            if rir:
                rir.delete()
            for rack_name in ("NETWORK-RACK-A", "NETWORK-RACK-B"):
                rack = nb.dcim.racks.get(name=rack_name)
                if rack:
                    rack.delete()
            location = nb.dcim.locations.get(name="MAIN-EQUIPMENT-ROOM")
            if location:
                location.delete()
            site = nb.dcim.sites.get(name=self.SITE)
            if site:
                site.delete()
            for model in ("Branch Router", "Access Switch"):
                device_type = nb.dcim.device_types.get(model=model)
                if device_type:
                    device_type.delete()
            for name in ("ROUTER", "ACCESS-SWITCH"):
                role = nb.dcim.device_roles.get(name=name)
                if role:
                    role.delete()
            manufacturer = nb.dcim.manufacturers.get(name="Example Networks")
            if manufacturer:
                manufacturer.delete()
            rack_role = nb.dcim.rack_roles.get(name="NETWORK")
            if rack_role:
                rack_role.delete()
            for name in (
                "BRANCH-LINKS",
                "BRANCH-LOOPBACKS",
                "BRANCH-MGMT",
                "BRANCH-VOICE",
                "BRANCH-CORP",
                "BRANCH-INTERNET",
            ):
                role = nb.ipam.roles.get(name=name)
                if role:
                    role.delete()
            region = nb.dcim.regions.get(name="LAB-REGION")
            if region:
                region.delete()

        remove()
        yield
        remove()

    @staticmethod
    def run_design(nfclient: Any) -> dict:
        return nfclient.run_job(
            "netbox",
            "design_deploy",
            workers="any",
            kwargs={
                "design": "nf://netbox/designs/branch_office_design.yaml",
                "context": {
                    "site": TestBranchOfficeDesign.SITE,
                    "prefix": TestBranchOfficeDesign.PREFIX,
                    "asn_range": TestBranchOfficeDesign.ASN_RANGE,
                    "rir": TestBranchOfficeDesign.RIR,
                    "rd_prefix": TestBranchOfficeDesign.RD_PREFIX,
                    "asn_start": TestBranchOfficeDesign.ASN_START,
                    "asn_end": TestBranchOfficeDesign.ASN_END,
                },
            },
        )

    def test_branch_office_context_validation(self, nfclient: Any) -> None:
        response = nfclient.run_job(
            "netbox",
            "design_deploy",
            workers="any",
            kwargs={
                "design": "nf://netbox/designs/branch_office_design.yaml",
                "context": {"site": self.SITE},
            },
        )

        for result in response.values():
            assert result["failed"] is True

    def test_branch_office_design_end_to_end(self, nfclient: Any) -> None:
        first = self.run_design(nfclient)
        for worker, result in first.items():
            assert result["failed"] is False, f"{worker} failed: {result}"

        nb = get_pynetbox(nfclient)
        site = nb.dcim.sites.get(name=self.SITE)
        assert {
            device.name for device in nb.dcim.devices.filter(site_id=site.id)
        } >= set(self.DEVICES)
        vlan_group = nb.ipam.vlan_groups.get(name=self.VLAN_GROUP)
        assert vlan_group.scope.name == self.SITE
        asn_range = nb.ipam.asn_ranges.get(name=self.ASN_RANGE)
        assert asn_range.scope.name == self.SITE
        assert (
            nb.dcim.devices.get(name="branch-001-rtr-1").rack.name == "NETWORK-RACK-A"
        )
        assert (
            nb.dcim.devices.get(name="branch-001-rtr-2").rack.name == "NETWORK-RACK-B"
        )
        assert len(list(nb.dcim.cables.filter(label__ic=f"{self.SITE}-"))) == 3

        for vrf_name in self.VRFS:
            vrf = nb.ipam.vrfs.get(name=vrf_name)
            assert len(vrf.import_targets) == 1
            assert len(vrf.export_targets) == 1
            assert (
                nb.ipam.prefixes.get(
                    description=f"{self.SITE} {vrf_name} PREFIX"
                ).vrf.name
                == vrf_name
            )
        for role_name in ("BRANCH-LINKS", "BRANCH-LOOPBACKS"):
            prefix = nb.ipam.prefixes.get(role__name=role_name, site__name=self.SITE)
            assert prefix.scope.name == self.SITE

        corp_vlan = nb.ipam.vlans.get(
            group_id=nb.ipam.vlan_groups.get(name=self.VLAN_GROUP).id, name="CORP"
        )
        corp_interface = nb.dcim.interfaces.get(
            device="branch-001-rtr-1", name=f"Ethernet2.{corp_vlan.vid}"
        )
        assert corp_interface.vrf.name == "CORP"
        corp_ip = nb.ipam.ip_addresses.get(
            description="BRANCH-001 branch-001-rtr-1 CORP"
        )
        assert corp_ip.assigned_object.id == corp_interface.id
        assert (
            nb.ipam.prefixes.get(description=f"{self.SITE} CORP PREFIX").vrf.name
            == "CORP"
        )

        access_interface = nb.dcim.interfaces.get(
            device="branch-001-sw-1", name="Ethernet1"
        )
        assert access_interface.untagged_vlan.name == "CORP"
        tagged_interface = nb.dcim.interfaces.get(
            device="branch-001-sw-1", name="Ethernet2"
        )
        assert {vlan.name for vlan in tagged_interface.tagged_vlans} == {
            "VOICE",
            "CORP",
        }
        assert (
            nb.dcim.mac_addresses.get(
                mac_address="02:60:00:00:00:01"
            ).assigned_object.name
            == "Ethernet1"
        )

        assert nb.plugins.bgp.session.get(name="BRANCH-001-RTR-1-IBGP") is not None
        assert nb.plugins.bgp.session.get(name="BRANCH-001-RTR-2-IBGP") is not None
        assert nb.ipam.asns.get(description=f"{self.SITE} router 1 ASN") is not None
        assert nb.ipam.asns.get(description=f"{self.SITE} router 2 ASN") is not None

        for name in (
            "BRANCH-001-MGMT-VRRP",
            "BRANCH-001-VOICE-VRRP",
            "BRANCH-001-CORP-VRRP",
            "BRANCH-001-INTERNET-VRRP",
        ):
            group = nb.ipam.fhrp_groups.get(name=name)
            assert (
                len(list(nb.ipam.fhrp_group_assignments.filter(group_id=group.id))) == 2
            )

        second = self.run_design(nfclient)
        for worker, result in second.items():
            assert result["failed"] is False, f"{worker} failed: {result}"
            assert result["result"]["created"] == {}
            assert result["result"]["updated"] == {}


class TestDataCenterLeafSpineDesign:
    SITE = "DC-001"
    FABRIC_PREFIX = "10.70.0.0/16"
    LOOPBACK_PREFIX = "10.71.0.0/24"
    ASN_RANGE = "DC-FABRIC-ASNS"
    RIR = "DC-FABRIC-RIR"
    DEVICES = [
        "dc-001-spine-1",
        "dc-001-spine-2",
        "dc-001-leaf-1",
        "dc-001-leaf-2",
        "dc-001-leaf-3",
    ]

    def remove_design_objects(self, nfclient: Any) -> None:
        nb = get_pynetbox(nfclient)
        for spine in range(1, 3):
            for leaf in range(1, 4):
                for name in (
                    f"{self.SITE}-SPINE-{spine}-LEAF-{leaf}",
                    f"{self.SITE}-LEAF-{leaf}-SPINE-{spine}",
                ):
                    session = nb.plugins.bgp.session.get(name=name)
                    if session:
                        session.delete()
                cable = nb.dcim.cables.get(
                    label=f"{self.SITE}-SPINE-{spine}-LEAF-{leaf}"
                )
                if cable:
                    cable.delete()
        for parent in (self.FABRIC_PREFIX, self.LOOPBACK_PREFIX):
            for address in list(nb.ipam.ip_addresses.filter(parent=parent)):
                address.delete()
        for device_name in self.DEVICES:
            device = nb.dcim.devices.get(name=device_name)
            if device:
                device.delete()
        for prefix in list(nb.ipam.prefixes.filter(within=self.FABRIC_PREFIX)):
            prefix.delete()
        for prefix_value in (self.FABRIC_PREFIX, self.LOOPBACK_PREFIX):
            prefix = nb.ipam.prefixes.get(prefix=prefix_value)
            if prefix:
                prefix.delete()
        for asn in list(nb.ipam.asns.filter(asn__gte=4200200000, asn__lte=4200200099)):
            asn.delete()
        asn_range = nb.ipam.asn_ranges.get(name=self.ASN_RANGE)
        if asn_range:
            asn_range.delete()
        rir = nb.ipam.rirs.get(name=self.RIR)
        if rir:
            rir.delete()
        for rack_name in ("SPINE-RACK", "LEAF-RACK"):
            rack = nb.dcim.racks.get(name=rack_name)
            if rack:
                rack.delete()
        location = nb.dcim.locations.get(name="FABRIC-ROOM")
        if location:
            location.delete()
        for model in ("Fabric Spine", "Fabric Leaf"):
            device_type = nb.dcim.device_types.get(model=model)
            if device_type:
                device_type.delete()
        for name in ("SPINE", "LEAF"):
            role = nb.dcim.device_roles.get(name=name)
            if role:
                role.delete()
        for name in ("FABRIC-LINK", "FABRIC-LOOPBACK"):
            role = nb.ipam.roles.get(name=name)
            if role:
                role.delete()
        manufacturer = nb.dcim.manufacturers.get(name="Example Networks")
        if manufacturer:
            manufacturer.delete()
        rack_role = nb.dcim.rack_roles.get(name="NETWORK")
        if rack_role:
            rack_role.delete()
        site = nb.dcim.sites.get(name=self.SITE)
        if site:
            site.delete()
        region = nb.dcim.regions.get(name="DC-REGION")
        if region:
            region.delete()

    @pytest.fixture(autouse=True)
    def allocation_pools(self, nfclient: Any) -> Iterator[None]:
        self.remove_design_objects(nfclient)
        nb = get_pynetbox(nfclient)
        region = nb.dcim.regions.create(name="DC-REGION", slug="dc-region")
        site = nb.dcim.sites.create(
            name=self.SITE,
            slug="dc-001",
            region=region.id,
            status="active",
        )
        for prefix, description in (
            (self.FABRIC_PREFIX, "Data center fabric link pool"),
            (self.LOOPBACK_PREFIX, "Data center loopback pool"),
        ):
            nb.ipam.prefixes.create(
                prefix=prefix,
                status="active",
                description=description,
                scope_type="dcim.site",
                scope_id=site.id,
            )
        rir = nb.ipam.rirs.create(name=self.RIR, slug="dc-fabric-rir", is_private=True)
        nb.ipam.asn_ranges.create(
            name=self.ASN_RANGE,
            slug="dc-fabric-asns",
            rir=rir.id,
            start=4200200000,
            end=4200200099,
            scope_type="dcim.site",
            scope_id=site.id,
        )
        yield
        self.remove_design_objects(nfclient)

    def run_design(self, nfclient: Any) -> dict:
        return nfclient.run_job(
            "netbox",
            "design_deploy",
            workers="any",
            kwargs={
                "design": "nf://netbox/designs/data_center_leaf_spine_design.yaml",
                "context": {
                    "site": self.SITE,
                    "fabric_prefix": self.FABRIC_PREFIX,
                    "loopback_prefix": self.LOOPBACK_PREFIX,
                    "asn_range": self.ASN_RANGE,
                },
            },
        )

    def test_data_center_leaf_spine_design_end_to_end(self, nfclient: Any) -> None:
        first = self.run_design(nfclient)
        for worker, result in first.items():
            assert result["failed"] is False, f"{worker} failed: {result}"

        nb = get_pynetbox(nfclient)
        site = nb.dcim.sites.get(name=self.SITE)
        assert {
            device.name for device in nb.dcim.devices.filter(site_id=site.id)
        } >= set(self.DEVICES)
        assert nb.dcim.devices.get(name="dc-001-spine-1").rack.name == "SPINE-RACK"
        assert nb.dcim.devices.get(name="dc-001-leaf-1").rack.name == "LEAF-RACK"
        assert len(list(nb.dcim.cables.filter(label__ic=f"{self.SITE}-"))) == 6

        link_prefixes = list(
            nb.ipam.prefixes.filter(role__name="FABRIC-LINK", site__name=self.SITE)
        )
        assert len(link_prefixes) == 6
        assert all(prefix.prefix.endswith("/31") for prefix in link_prefixes)
        assert (
            len(list(nb.ipam.asns.filter(asn__gte=4200200000, asn__lte=4200200099)))
            == 5
        )
        sessions = [
            nb.plugins.bgp.session.get(name=name)
            for spine in range(1, 3)
            for leaf in range(1, 4)
            for name in (
                f"{self.SITE}-SPINE-{spine}-LEAF-{leaf}",
                f"{self.SITE}-LEAF-{leaf}-SPINE-{spine}",
            )
        ]
        assert all(sessions)

        for device_name in self.DEVICES:
            loopback = nb.dcim.interfaces.get(device=device_name, name="Loopback0")
            addresses = list(
                nb.ipam.ip_addresses.filter(
                    device=device_name,
                    interface="Loopback0",
                    parent=self.LOOPBACK_PREFIX,
                )
            )
            assert loopback is not None
            assert len(addresses) == 1

        spine_ip = nb.ipam.ip_addresses.get(
            description=f"{self.SITE} spine-1 leaf-1 SPINE IP"
        )
        leaf_ip = nb.ipam.ip_addresses.get(
            description=f"{self.SITE} spine-1 leaf-1 LEAF IP"
        )
        assert spine_ip.assigned_object.device.name == "dc-001-spine-1"
        assert spine_ip.assigned_object.name == "Ethernet1"
        assert leaf_ip.assigned_object.device.name == "dc-001-leaf-1"
        assert leaf_ip.assigned_object.name == "Ethernet1"

        second = self.run_design(nfclient)
        for worker, result in second.items():
            assert result["failed"] is False, f"{worker} failed: {result}"
            assert result["result"]["created"] == {}
            assert result["result"]["updated"] == {}


class TestJinjaFunctionsDesign:
    VRF = "DESIGN CUSTOM FILTER VRF"

    @pytest.fixture(autouse=True)
    def cleanup_design_objects(self, nfclient: Any) -> Iterator[None]:
        nb = get_pynetbox(nfclient)
        vrf = nb.ipam.vrfs.get(name=self.VRF)
        if vrf:
            vrf.delete()
        yield
        vrf = nb.ipam.vrfs.get(name=self.VRF)
        if vrf:
            vrf.delete()

    def run_design(self, nfclient: Any) -> dict:
        return nfclient.run_job(
            "netbox",
            "design_deploy",
            workers="any",
            kwargs={
                "design": "nf://netbox/designs/jinja_functions_design.yaml",
            },
        )

    def test_jinja_functions_design_end_to_end(self, nfclient: Any) -> None:
        first = self.run_design(nfclient)
        for worker, result in first.items():
            assert result["failed"] is False, f"{worker} failed: {result}"
            assert result["result"]["created"]["vrfs"] == [self.VRF]

        vrf = get_pynetbox(nfclient).ipam.vrfs.get(name=self.VRF)
        assert vrf is not None
        assert vrf.rd == "100:3"
        assert (
            vrf.description
            == "Created with the allocate_vrf_route_target custom function"
        )

        second = self.run_design(nfclient)
        for worker, result in second.items():
            assert result["failed"] is False, f"{worker} failed: {result}"
            assert result["result"]["created"] == {}
            assert result["result"]["updated"] == {}
            assert result["result"]["unchanged"]["vrfs"] == [self.VRF]


class TestInfrastructureAndServicesDesigns:
    CUSTOM_FIELD = "design_owner"

    def remove_design_objects(self, nfclient: Any) -> None:
        nb = get_pynetbox(nfclient)
        session = nb.plugins.bgp.session.get(name="DESIGN BGP SESSION 1")
        if session:
            session.delete()
        for assignment in list(
            nb.ipam.fhrp_group_assignments.filter(device="design-services-1")
        ):
            assignment.delete()
        group = nb.ipam.fhrp_groups.get(name="DESIGN VRRP 10")
        if group:
            group.delete()
        l2vpn = nb.vpn.l2vpns.get(name="DESIGN L2VPN 100")
        if l2vpn:
            for termination in list(
                nb.vpn.l2vpn_terminations.filter(l2vpn_id=l2vpn.id)
            ):
                termination.delete()
            l2vpn.delete()
        cable = nb.dcim.cables.get(label="DESIGN PHYSICAL LINK 1")
        if cable:
            cable.delete()
        for address in ("192.0.2.101/32", "192.0.2.102/32"):
            ip_address = nb.ipam.ip_addresses.get(address=address)
            if ip_address:
                ip_address.delete()
        for device_name in (
            "design-services-1",
            "design-physical-1",
            "design-physical-2",
        ):
            device = nb.dcim.devices.get(name=device_name)
            if device:
                device.delete()
        rack = nb.dcim.racks.get(name="DESIGN RACK 1")
        if rack:
            rack.delete()
        location = nb.dcim.locations.get(name="DESIGN ROOM 1")
        if location:
            location.delete()
        site = nb.dcim.sites.get(name="DESIGN SITE PHYSICAL")
        if site:
            site.delete()
        region = nb.dcim.regions.get(name="DESIGN REGION PHYSICAL")
        if region:
            region.delete()
        rack_role = nb.dcim.rack_roles.get(name="DESIGN NETWORK RACK")
        if rack_role:
            rack_role.delete()
        for asn in (4200099001, 4200099002):
            asn_object = nb.ipam.asns.get(asn=asn)
            if asn_object:
                asn_object.delete()
        rir = nb.ipam.rirs.get(name="DESIGN SERVICE RIR")
        if rir:
            rir.delete()

    @pytest.fixture(autouse=True)
    def design_objects(self, nfclient: Any) -> Iterator[None]:
        self.remove_design_objects(nfclient)
        nb = get_pynetbox(nfclient)
        custom_field = nb.extras.custom_fields.get(name=self.CUSTOM_FIELD)
        if custom_field:
            custom_field.delete()
        nb.extras.custom_fields.create(
            name=self.CUSTOM_FIELD,
            label="Design owner",
            type="text",
            object_types=[
                "dcim.region",
                "dcim.site",
                "dcim.location",
                "dcim.rack",
                "dcim.device",
                "dcim.interface",
                "dcim.cable",
                "vpn.l2vpn",
                "vpn.l2vpntermination",
                "ipam.fhrpgroup",
                "netbox_bgp.bgpsession",
            ],
        )
        yield
        self.remove_design_objects(nfclient)
        custom_field = nb.extras.custom_fields.get(name=self.CUSTOM_FIELD)
        if custom_field:
            custom_field.delete()

    @staticmethod
    def run_design(nfclient: Any, filename: str) -> dict:
        return nfclient.run_job(
            "netbox",
            "design_deploy",
            workers="any",
            kwargs={"design": f"nf://netbox/designs/{filename}"},
        )

    def test_physical_hierarchy_and_connection(self, nfclient: Any) -> None:
        first = self.run_design(nfclient, "infrastructure_connections_design.yaml")
        for worker, result in first.items():
            assert result["failed"] is False, f"{worker} failed: {result}"

        nb = get_pynetbox(nfclient)
        rack = nb.dcim.racks.get(name="DESIGN RACK 1")
        assert rack.site.name == "DESIGN SITE PHYSICAL"
        assert rack.location.name == "DESIGN ROOM 1"
        assert rack.custom_fields[self.CUSTOM_FIELD] == "design-engine"
        cable = nb.dcim.cables.get(label="DESIGN PHYSICAL LINK 1")
        assert cable is not None
        assert cable.custom_fields[self.CUSTOM_FIELD] == "design-engine"
        assert nb.dcim.devices.get(name="design-physical-1").rack.name == rack.name

        second = self.run_design(nfclient, "infrastructure_connections_design.yaml")
        for worker, result in second.items():
            assert result["failed"] is False, f"{worker} failed: {result}"
            assert result["result"]["created"] == {}
            assert result["result"]["updated"] == {}

    def test_bgp_l2vpn_and_vrrp(self, nfclient: Any) -> None:
        first = self.run_design(nfclient, "network_services_design.yaml")
        for worker, result in first.items():
            assert result["failed"] is False, f"{worker} failed: {result}"

        nb = get_pynetbox(nfclient)
        session = nb.plugins.bgp.session.get(name="DESIGN BGP SESSION 1")
        assert session is not None
        assert session.custom_fields[self.CUSTOM_FIELD] == "design-engine"
        l2vpn = nb.vpn.l2vpns.get(name="DESIGN L2VPN 100")
        assert l2vpn is not None
        assert l2vpn.custom_fields[self.CUSTOM_FIELD] == "design-engine"
        assert len(list(nb.vpn.l2vpn_terminations.filter(l2vpn_id=l2vpn.id))) == 1
        group = nb.ipam.fhrp_groups.get(name="DESIGN VRRP 10")
        assert group.protocol == "vrrp2"
        assert group.custom_fields[self.CUSTOM_FIELD] == "design-engine"
        assignments = list(nb.ipam.fhrp_group_assignments.filter(group_id=group.id))
        assert len(assignments) == 1
        assert assignments[0].priority == 110

        second = self.run_design(nfclient, "network_services_design.yaml")
        for worker, result in second.items():
            assert result["failed"] is False, f"{worker} failed: {result}"
            assert result["result"]["created"] == {}
            assert result["result"]["updated"] == {}
