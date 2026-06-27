import pprint

import pytest

try:
    from tests.services.netbox.common import (
        cache_options,
        clear_nb_cache,
        delete_branch,
        delete_interfaces,
        delete_interfaces_with_description,
        get_nb_version,
        get_pynetbox,
    )
except ModuleNotFoundError as exc:
    if exc.name not in {
        "tests",
        "tests.services",
        "tests.services.netbox",
        "tests.services.netbox.common",
    }:
        raise
    from services.netbox.common import (
        cache_options,
        clear_nb_cache,
        delete_branch,
        delete_interfaces,
        delete_interfaces_with_description,
        get_nb_version,
        get_pynetbox,
    )

pytestmark = [pytest.mark.netbox, pytest.mark.interfaces]


@pytest.mark.task_get_interfaces
class TestGetInterfaces:
    nb_version = None

    def test_get_interfaces(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)
        clear_nb_cache("get_interfaces*", nfclient)
        ret = nfclient.run_job(
            "netbox",
            "get_interfaces",
            workers="any",
            kwargs={"devices": ["ceos1", "fceos4"]},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert "ceos1" in res["result"], f"{worker} returned no results for ceos1"
            assert "fceos4" in res["result"], f"{worker} returned no results for fceos4"
            for device, interfaces in res["result"].items():
                assert isinstance(
                    interfaces, dict
                ), f"{worker}:{device} did not return interfaces dictionary"
                for intf_name, intf_data in interfaces.items():
                    assert all(
                        k in intf_data
                        for k in [
                            "enabled",
                            "description",
                            "mtu",
                            "parent",
                            "mode",
                            "untagged_vlan",
                            "vrf",
                            "tagged_vlans",
                            "tags",
                            "custom_fields",
                            "last_updated",
                            "bridge",
                            "child_interfaces",
                            "bridge_interfaces",
                            "member_interfaces",
                            "wwn",
                            "duplex",
                            "speed",
                        ]
                    ), f"{worker}:{device}:{intf_name} not all data returned"
                    if self.nb_version >= (4, 2, 0):
                        assert "mac_addresses" in intf_data
                    else:
                        assert "mac_address" in intf_data

    def test_get_interfaces_with_instance(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)
        clear_nb_cache("get_interfaces*", nfclient)
        ret = nfclient.run_job(
            "netbox",
            "get_interfaces",
            workers="any",
            kwargs={"devices": ["ceos1", "fceos4"], "instance": "prod"},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert "ceos1" in res["result"], f"{worker} returned no results for ceos1"
            assert "fceos4" in res["result"], f"{worker} returned no results for fceos4"
            for device, interfaces in res["result"].items():
                assert isinstance(
                    interfaces, dict
                ), f"{worker}:{device} did not return interfaces dictionary"
                for intf_name, intf_data in interfaces.items():
                    assert all(
                        k in intf_data
                        for k in [
                            "enabled",
                            "description",
                            "mtu",
                            "parent",
                            "mode",
                            "untagged_vlan",
                            "vrf",
                            "tagged_vlans",
                            "tags",
                            "custom_fields",
                            "last_updated",
                            "bridge",
                            "child_interfaces",
                            "bridge_interfaces",
                            "member_interfaces",
                            "wwn",
                            "duplex",
                            "speed",
                        ]
                    ), f"{worker}:{device}:{intf_name} not all data returned"
                    if self.nb_version >= (4, 2, 0):
                        assert "mac_addresses" in intf_data
                    else:
                        assert "mac_address" in intf_data

    def test_get_interfaces_dry_run(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        ret = nfclient.run_job(
            "netbox",
            "get_interfaces",
            workers="any",
            kwargs={"devices": ["ceos1", "fceos4"], "dry_run": True},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert res["result"] == {
                "filter_params": {"device": ["ceos1", "fceos4"]}
            }, f"{worker} did not return correct query string"

    def test_get_interfaces_add_ip(self, nfclient):
        clear_nb_cache("get_interfaces*", nfclient)
        ret = nfclient.run_job(
            "netbox",
            "get_interfaces",
            workers="any",
            kwargs={"devices": ["ceos1", "fceos4"], "ip_addresses": True},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert "ceos1" in res["result"], f"{worker} returned no results for ceos1"
            assert "fceos4" in res["result"], f"{worker} returned no results for fceos4"
            for device, interfaces in res["result"].items():
                assert isinstance(
                    interfaces, dict
                ), f"{worker}:{device} did not return interfaces dictionary"
                for intf_name, intf_data in interfaces.items():
                    assert (
                        "ip_addresses" in intf_data
                    ), f"{worker}:{device}:{intf_name} no IP addresses data returned"
                    for ip in intf_data["ip_addresses"]:
                        assert all(
                            k in ip
                            for k in [
                                "address",
                                "family",
                            ]
                        ), f"{worker}:{device}:{intf_name} not all IP data returned"

    def test_get_interfaces_add_inventory_items(self, nfclient):
        clear_nb_cache("get_interfaces*", nfclient)
        ret = nfclient.run_job(
            "netbox",
            "get_interfaces",
            workers="any",
            kwargs={
                "devices": ["ceos1", "fceos4"],
                "inventory_items": True,
            },
        )
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert "ceos1" in res["result"], f"{worker} returned no results for ceos1"
            assert "fceos4" in res["result"], f"{worker} returned no results for fceos4"
            for device, interfaces in res["result"].items():
                assert isinstance(
                    interfaces, dict
                ), f"{worker}:{device} did not return interfaces dictionary"
                for intf_name, intf_data in interfaces.items():
                    assert (
                        "inventory_items" in intf_data
                    ), f"{worker}:{device}:{intf_name} no inventory items data returned"
                    for item in intf_data["inventory_items"]:
                        assert all(
                            k in item
                            for k in [
                                "name",
                                "role",
                                "manufacturer",
                                "custom_fields",
                                "serial",
                            ]
                        ), f"{worker}:{device}:{intf_name} not all inventory item data returned"

    def test_get_interfaces_with_interface_regex(self, nfclient):
        clear_nb_cache("get_interfaces*", nfclient)
        ret = nfclient.run_job(
            "netbox",
            "get_interfaces",
            workers="any",
            kwargs={
                "devices": ["ceos1", "fceos4"],
                "interface_regex": "loop.+",
            },
        )
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert "ceos1" in res["result"], f"{worker} returned no results for ceos1"
            assert "fceos4" in res["result"], f"{worker} returned no results for fceos4"
            for device, interfaces in res["result"].items():
                assert isinstance(
                    interfaces, dict
                ), f"{worker}:{device} did not return interfaces dictionary"
                for intf_name, intf_data in interfaces.items():
                    assert (
                        "loopback" in intf_name.lower()
                    ), f"{worker}:{device}:{intf_name} interface name does not match regex pattern"

    def test_get_interfaces_with_interface_list(self, nfclient):
        clear_nb_cache("get_interfaces*", nfclient)
        ret = nfclient.run_job(
            "netbox",
            "get_interfaces",
            workers="any",
            kwargs={
                "devices": ["fceos4"],
                "interface_list": ["eth9", "eth8"],
            },
        )
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert "fceos4" in res["result"], f"{worker} returned no results for fceos4"
            for device, interfaces in res["result"].items():
                assert isinstance(
                    interfaces, dict
                ), f"{worker}:{device} did not return interfaces dictionary"
                assert "eth8" in interfaces, f"{worker}:{device}:eth8 no interface data"
                assert "eth9" in interfaces, f"{worker}:{device}:eth9 no interface data"
                assert (
                    len(interfaces) == 2
                ), f"{worker}:{device} was expecting only 2 interfaces"

    @pytest.mark.parametrize("cache", cache_options)
    def test_get_interfaces_cache(self, nfclient, cache):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)
        ret = nfclient.run_job(
            "netbox",
            "get_interfaces",
            workers="any",
            kwargs={"devices": ["ceos1", "fceos4"], "cache": cache},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert "ceos1" in res["result"], f"{worker} returned no results for ceos1"
            assert "fceos4" in res["result"], f"{worker} returned no results for fceos4"
            for device, interfaces in res["result"].items():
                assert isinstance(
                    interfaces, dict
                ), f"{worker}:{device} did not return interfaces dictionary"
                for intf_name, intf_data in interfaces.items():
                    assert all(
                        k in intf_data
                        for k in [
                            "enabled",
                            "description",
                            "mtu",
                            "parent",
                            "mode",
                            "untagged_vlan",
                            "vrf",
                            "tagged_vlans",
                            "tags",
                            "custom_fields",
                            "last_updated",
                            "bridge",
                            "child_interfaces",
                            "bridge_interfaces",
                            "member_interfaces",
                            "wwn",
                            "duplex",
                            "speed",
                        ]
                    ), f"{worker}:{device}:{intf_name} not all data returned"
                    if self.nb_version >= (4, 2, 0):
                        assert "mac_addresses" in intf_data
                    else:
                        assert "mac_address" in intf_data


@pytest.mark.task_update_interfaces_description
class TestUpdateInterfacesDescription:
    DEVICE = "fceos4"
    INTERFACE = "loopback0"
    DESCRIPTION = "TEST_UPDATE_DESCRIPTION loopback0 none virtual"
    CONNECTED_VIRTUAL_INTERFACE = "Port-Channel1.101"
    CONNECTED_VIRTUAL_DESCRIPTION = "TEST_UPDATE_DESCRIPTION fceos5 ae5.101 virtual"
    CONNECTED_INTERFACE = "eth11"
    CONNECTED_INTERFACE_DESCRIPTION = "TEST_UPDATE_DESCRIPTION fceos5 eth11 interface"
    STATIC_DESCRIPTION = "TEST_UPDATE_DESCRIPTION static loopback0"

    @staticmethod
    def _set_interface_description(nfclient, device, interface, description):
        pynb = get_pynetbox(nfclient)
        nb_interface = pynb.dcim.interfaces.get(device=device, name=interface)
        assert nb_interface is not None, f"{device}:{interface} not found in NetBox"
        nb_interface.description = description
        nb_interface.save()

    @staticmethod
    def _get_interface(nfclient, device, interface):
        pynb = get_pynetbox(nfclient)
        return pynb.dcim.interfaces.get(device=device, name=interface)

    @staticmethod
    def _assert_description_result(ret, device, interface, before, after):
        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            assert device in res["result"], f"{worker} missing {device}"
            assert (
                interface in res["result"][device]
            ), f"{worker} missing {device}:{interface}"
            assert res["result"][device][interface] == {
                "-": before,
                "+": after,
            }

    def test_update_virtual_interface_description_without_connection_data(
        self, nfclient
    ):
        self._set_interface_description(nfclient, self.DEVICE, self.INTERFACE, "")

        try:
            ret = nfclient.run_job(
                "netbox",
                "update_interfaces_description",
                workers="any",
                kwargs={
                    "devices": [self.DEVICE],
                    "interfaces": [self.INTERFACE],
                    "description_template": (
                        "TEST_UPDATE_DESCRIPTION {{ interface.name }} "
                        "{{ remote_device or 'none' }} {{ termination_type }}"
                    ),
                },
            )
            pprint.pprint(ret)

            self._assert_description_result(
                ret, self.DEVICE, self.INTERFACE, "", self.DESCRIPTION
            )

            nb_interface = self._get_interface(nfclient, self.DEVICE, self.INTERFACE)
            assert (
                nb_interface.description == self.DESCRIPTION
            ), f"{self.DEVICE}:{self.INTERFACE} description was not updated"
        finally:
            self._set_interface_description(nfclient, self.DEVICE, self.INTERFACE, "")

    def test_update_virtual_interface_description_dry_run(self, nfclient):
        self._set_interface_description(nfclient, self.DEVICE, self.INTERFACE, "")

        ret = nfclient.run_job(
            "netbox",
            "update_interfaces_description",
            workers="any",
            kwargs={
                "devices": [self.DEVICE],
                "interfaces": [self.INTERFACE],
                "description_template": (
                    "TEST_UPDATE_DESCRIPTION {{ interface.name }} "
                    "{{ remote_device or 'none' }} {{ termination_type }}"
                ),
                "dry_run": True,
            },
        )
        pprint.pprint(ret)

        self._assert_description_result(
            ret, self.DEVICE, self.INTERFACE, "", self.DESCRIPTION
        )
        nb_interface = self._get_interface(nfclient, self.DEVICE, self.INTERFACE)
        assert (
            nb_interface.description == ""
        ), f"{self.DEVICE}:{self.INTERFACE} description changed during dry run"

    def test_update_virtual_interface_description_static_mapping(self, nfclient):
        self._set_interface_description(nfclient, self.DEVICE, self.INTERFACE, "")

        try:
            ret = nfclient.run_job(
                "netbox",
                "update_interfaces_description",
                workers="any",
                kwargs={
                    "devices": [self.DEVICE],
                    "descriptions": {self.INTERFACE: self.STATIC_DESCRIPTION},
                },
            )
            pprint.pprint(ret)

            self._assert_description_result(
                ret, self.DEVICE, self.INTERFACE, "", self.STATIC_DESCRIPTION
            )
            nb_interface = self._get_interface(nfclient, self.DEVICE, self.INTERFACE)
            assert (
                nb_interface.description == self.STATIC_DESCRIPTION
            ), f"{self.DEVICE}:{self.INTERFACE} static description was not updated"
        finally:
            self._set_interface_description(nfclient, self.DEVICE, self.INTERFACE, "")

    def test_update_connected_virtual_interface_description_from_connection_data(
        self, nfclient
    ):
        self._set_interface_description(
            nfclient, self.DEVICE, self.CONNECTED_VIRTUAL_INTERFACE, ""
        )

        try:
            ret = nfclient.run_job(
                "netbox",
                "update_interfaces_description",
                workers="any",
                kwargs={
                    "devices": [self.DEVICE],
                    "interfaces": [self.CONNECTED_VIRTUAL_INTERFACE],
                    "description_template": (
                        "TEST_UPDATE_DESCRIPTION {{ remote_device }} "
                        "{{ remote_interface }} {{ termination_type }}"
                    ),
                },
            )
            pprint.pprint(ret)

            self._assert_description_result(
                ret,
                self.DEVICE,
                self.CONNECTED_VIRTUAL_INTERFACE,
                "",
                self.CONNECTED_VIRTUAL_DESCRIPTION,
            )
            nb_interface = self._get_interface(
                nfclient, self.DEVICE, self.CONNECTED_VIRTUAL_INTERFACE
            )
            assert (
                nb_interface.description == self.CONNECTED_VIRTUAL_DESCRIPTION
            ), f"{self.DEVICE}:{self.CONNECTED_VIRTUAL_INTERFACE} was not updated"
        finally:
            self._set_interface_description(
                nfclient, self.DEVICE, self.CONNECTED_VIRTUAL_INTERFACE, ""
            )

    def test_update_connected_interface_description_from_connection_data(
        self, nfclient
    ):
        self._set_interface_description(
            nfclient, self.DEVICE, self.CONNECTED_INTERFACE, ""
        )

        try:
            ret = nfclient.run_job(
                "netbox",
                "update_interfaces_description",
                workers="any",
                kwargs={
                    "devices": [self.DEVICE],
                    "interfaces": [self.CONNECTED_INTERFACE],
                    "description_template": (
                        "TEST_UPDATE_DESCRIPTION {{ remote_device }} "
                        "{{ remote_interface }} {{ termination_type }}"
                    ),
                },
            )
            pprint.pprint(ret)

            self._assert_description_result(
                ret,
                self.DEVICE,
                self.CONNECTED_INTERFACE,
                "",
                self.CONNECTED_INTERFACE_DESCRIPTION,
            )
            nb_interface = self._get_interface(
                nfclient, self.DEVICE, self.CONNECTED_INTERFACE
            )
            assert (
                nb_interface.description == self.CONNECTED_INTERFACE_DESCRIPTION
            ), f"{self.DEVICE}:{self.CONNECTED_INTERFACE} was not updated"
        finally:
            self._set_interface_description(
                nfclient, self.DEVICE, self.CONNECTED_INTERFACE, ""
            )


@pytest.mark.task_sync_device_interfaces
class TestSyncDeviceInterfaces:
    # Parse data provides these TEST_SYNC_ interfaces on all ceos devices.
    # Live state comes from interfaces_parse_data.json served by the Nornir parse_ttp mock.
    ALL_DEVICES = [
        "ceos-spine-1",
        "ceos-spine-2",
        "ceos-leaf-1",
        "ceos-leaf-2",
        "ceos-leaf-3",
    ]
    SPINE_DEVICES = ["ceos-spine-1", "ceos-spine-2"]
    # Keys present in a live-run per-device result dict
    LIVE_RUN_KEYS = {"created", "updated", "deleted", "in_sync"}
    # Keys present in a dry-run per-device result dict
    DRY_RUN_KEYS = {"create", "delete", "update", "in_sync"}
    # TEST_SYNC interfaces expected in live data for spine-1 / spine-2
    TEST_SYNC_INTERFACES = {
        "Port-Channel41",
        "Ethernet6",
        "Ethernet7",
        "Ethernet8",
        "Ethernet9",
        "Ethernet9.610",
        "Loopback10",
        "Loopback11",
    }

    # ------------------------------------------------------------------ #
    # Class-level helpers                                                  #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _cleanup(nfclient, devices):
        """Delete TEST_SYNC interfaces and VLAN 410 from NetBox."""
        delete_interfaces_with_description(
            nfclient, TestSyncDeviceInterfaces.ALL_DEVICES, "TEST_SYNC"
        )
        TestSyncDeviceInterfaces._delete_vlan(nfclient, 410)

    @staticmethod
    def _delete_vlan(nfclient, vid):
        """Delete all NetBox VLANs matching VID."""
        pynb = get_pynetbox(nfclient)
        for vlan in list(pynb.ipam.vlans.filter(vid=vid)):
            vlan.delete()
        print(f"Deleted VLAN '{vid}' from NetBox")

    @staticmethod
    def _get_vlan(nfclient, vid):
        """Fetch a single VLAN by VID from NetBox via pynetbox."""
        pynb = get_pynetbox(nfclient)
        vlans = list(pynb.ipam.vlans.filter(vid=vid))
        return vlans[0] if vlans else None

    @staticmethod
    def _get_vlan_group(nfclient, name):
        """Fetch a single VLAN group by name from NetBox."""
        pynb = get_pynetbox(nfclient)
        return pynb.ipam.vlan_groups.get(name=name)

    @staticmethod
    def _sync(nfclient, devices, **extra_kwargs):
        """Run sync_device_interfaces and return the result dict."""
        return nfclient.run_job(
            "netbox",
            "sync_device_interfaces",
            workers="any",
            kwargs={"devices": devices, **extra_kwargs},
        )

    @staticmethod
    def _get_intf_id(nfclient, device, name):
        resp = nfclient.run_job(
            "netbox",
            "rest",
            workers="any",
            kwargs={
                "method": "get",
                "api": "dcim/interfaces",
                "params": {"device": device, "name": name},
            },
        )
        worker, result = tuple(resp.items())[0]
        return result["result"]["results"][0]["id"]

    @staticmethod
    def _patch_intf(nfclient, intf_id, patch):
        nfclient.run_job(
            "netbox",
            "rest",
            workers="any",
            kwargs={
                "method": "patch",
                "api": f"dcim/interfaces/{intf_id}",
                "json": patch,
            },
        )

    @staticmethod
    def _get_nb_intf(nfclient, device, name):
        """Fetch a single interface record from NetBox via pynetbox. Returns None if not found."""
        pynb = get_pynetbox(nfclient)
        return pynb.dcim.interfaces.get(device=device, name=name)

    # ------------------------------------------------------------------ #
    # Basic smoke tests                                                    #
    # ------------------------------------------------------------------ #

    def test_sync_device_interfaces(self, nfclient):
        """Clean TEST_SYNC interfaces from spines then sync. All TEST_SYNC interfaces
        must be created from live data; result must carry live-run keys."""
        self._cleanup(nfclient, self.SPINE_DEVICES)

        ret = self._sync(nfclient, self.SPINE_DEVICES)
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            for device in self.SPINE_DEVICES:
                assert (
                    device in res["result"]
                ), f"{worker} returned no results for {device}"
            for device, device_data in res["result"].items():
                assert (
                    self.LIVE_RUN_KEYS <= device_data.keys()
                ), f"{worker}:{device} missing keys in result, got: {set(device_data)}"
                assert device_data[
                    "created"
                ], f"{worker}:{device} no interfaces created after cleanup"

    def test_sync_device_interfaces_all_devices(self, nfclient):
        """Clean TEST_SYNC from all 5 devices then sync. Each device must have
        at least one interface created."""
        self._cleanup(nfclient, self.ALL_DEVICES)

        ret = self._sync(nfclient, self.ALL_DEVICES)
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            for device in self.ALL_DEVICES:
                assert (
                    device in res["result"]
                ), f"{worker} returned no results for {device}"
            for device, device_data in res["result"].items():
                assert (
                    self.LIVE_RUN_KEYS <= device_data.keys()
                ), f"{worker}:{device} missing keys in result"
                assert device_data[
                    "created"
                ], f"{worker}:{device} no interfaces created after cleanup"

    def test_sync_device_interfaces_dry_run(self, nfclient):
        """Clean TEST_SYNC from spines then dry_run sync. The plan must list
        cleaned interfaces under 'create' and expose correct key/type structure."""
        self._cleanup(nfclient, self.SPINE_DEVICES)

        ret = self._sync(nfclient, self.SPINE_DEVICES, dry_run=True)
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            for device in self.SPINE_DEVICES:
                assert (
                    device in res["result"]
                ), f"{worker} returned no results for {device}"
            for device, device_data in res["result"].items():
                assert (
                    self.DRY_RUN_KEYS <= device_data.keys()
                ), f"{worker}:{device} dry-run result missing keys, got: {set(device_data)}"
                assert isinstance(
                    device_data["create"], list
                ), f"{worker}:{device} create not a list"
                assert isinstance(
                    device_data["delete"], list
                ), f"{worker}:{device} delete not a list"
                assert isinstance(
                    device_data["update"], dict
                ), f"{worker}:{device} update not a dict"
                assert isinstance(
                    device_data["in_sync"], list
                ), f"{worker}:{device} in_sync not a list"
                assert device_data[
                    "create"
                ], f"{worker}:{device} create list is empty after cleanup"

    # ------------------------------------------------------------------ #
    # Create scenarios                                                     #
    # ------------------------------------------------------------------ #

    def test_sync_device_interfaces_create(self, nfclient):
        """Clean TEST_SYNC from spine-2 then verify sync creates Loopback10
        (TEST_SYNC_LOOPBACK_IPV4) and Loopback11 (TEST_SYNC_LOOPBACK_IPV6) from live data.
        """
        self._cleanup(nfclient, ["ceos-spine-2"])

        ret = self._sync(nfclient, ["ceos-spine-2"])
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            device_data = res["result"]["ceos-spine-2"]
            assert (
                "Loopback10" in device_data["created"]
            ), f"{worker} Loopback10 not in created list"
            assert (
                "Loopback11" in device_data["created"]
            ), f"{worker} Loopback11 not in created list"

        # Validate Loopback10 record in NetBox
        nb_lb10 = self._get_nb_intf(nfclient, "ceos-spine-2", "Loopback10")
        assert nb_lb10 is not None, "Loopback10 not found in NetBox after sync"
        assert (
            nb_lb10.description == "TEST_SYNC_LOOPBACK_IPV4"
        ), f"Loopback10 description mismatch: got {nb_lb10.description!r}"
        assert (
            nb_lb10.type.value == "virtual"
        ), f"Loopback10 type mismatch: got {nb_lb10.type.value!r}"
        # Validate Loopback11 record in NetBox
        nb_lb11 = self._get_nb_intf(nfclient, "ceos-spine-2", "Loopback11")
        assert nb_lb11 is not None, "Loopback11 not found in NetBox after sync"
        assert (
            nb_lb11.description == "TEST_SYNC_LOOPBACK_IPV6"
        ), f"Loopback11 description mismatch: got {nb_lb11.description!r}"
        assert (
            nb_lb11.type.value == "virtual"
        ), f"Loopback11 type mismatch: got {nb_lb11.type.value!r}"

    def test_sync_device_interfaces_create_child(self, nfclient):
        """Clean TEST_SYNC from spine-1 then verify sync creates Ethernet9.610
        (sub-interface, description TEST_SYNC_SUBINTERFACE) as a child of Ethernet9."""
        self._cleanup(nfclient, ["ceos-spine-1"])

        ret = self._sync(nfclient, ["ceos-spine-1"])
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            device_data = res["result"]["ceos-spine-1"]
            assert (
                "Ethernet9.610" in device_data["created"]
            ), f"{worker} Ethernet9.610 (child interface) not in created list"

        # Validate Ethernet9.610 record in NetBox
        nb_subif = self._get_nb_intf(nfclient, "ceos-spine-1", "Ethernet9.610")
        assert nb_subif is not None, "Ethernet9.610 not found in NetBox after sync"
        assert (
            nb_subif.description == "TEST_SYNC_SUBINTERFACE"
        ), f"Ethernet9.610 description mismatch: got {nb_subif.description!r}"
        assert (
            nb_subif.type.value == "virtual"
        ), f"Ethernet9.610 type mismatch: got {nb_subif.type.value!r}"
        assert (
            nb_subif.parent is not None and nb_subif.parent.name == "Ethernet9"
        ), f"Ethernet9.610 parent mismatch: got {nb_subif.parent!r}"

    def test_sync_device_interfaces_create_lag_with_members(self, nfclient):
        """Clean TEST_SYNC from spine-1 then verify sync creates Port-Channel41 (LAG)
        and its member interfaces Ethernet6 (TEST_SYNC_LAG_MEMBER_A) and
        Ethernet7 (TEST_SYNC_LAG_MEMBER_B)."""
        self._cleanup(nfclient, ["ceos-spine-1"])

        ret = self._sync(nfclient, ["ceos-spine-1"])
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            device_data = res["result"]["ceos-spine-1"]
            assert (
                "Port-Channel41" in device_data["created"]
            ), f"{worker} Port-Channel41 LAG not in created list"
            assert (
                "Ethernet6" in device_data["created"]
            ), f"{worker} Ethernet6 LAG member not in created list"
            assert (
                "Ethernet7" in device_data["created"]
            ), f"{worker} Ethernet7 LAG member not in created list"

        # Validate Port-Channel41 record in NetBox
        nb_lag = self._get_nb_intf(nfclient, "ceos-spine-1", "Port-Channel41")
        assert nb_lag is not None, "Port-Channel41 not found in NetBox after sync"
        assert (
            nb_lag.description == "TEST_SYNC_LAG_TRUNK"
        ), f"Port-Channel41 description mismatch: got {nb_lag.description!r}"
        assert (
            nb_lag.type.value == "lag"
        ), f"Port-Channel41 type mismatch: got {nb_lag.type.value!r}"
        assert (
            nb_lag.mode is not None and nb_lag.mode.value == "tagged"
        ), f"Port-Channel41 mode mismatch: got {nb_lag.mode!r}"
        lag_vids = {v.vid for v in nb_lag.tagged_vlans}
        assert {
            410,
            411,
            510,
        } <= lag_vids, f"Port-Channel41 tagged_vlans mismatch: expected {{410, 411, 510}} subset, got VIDs {lag_vids}"
        nb_vlan_410 = self._get_vlan(nfclient, 410)
        assert nb_vlan_410 is not None, "VLAN 410 not recreated in NetBox after sync"
        assert (
            nb_vlan_410.name == "VLAN_410"
        ), f"VLAN 410 name mismatch: got {nb_vlan_410.name!r}"
        assert (
            nb_vlan_410.description == "VLAN_410"
        ), f"VLAN 410 description mismatch: got {nb_vlan_410.description!r}"
        assert (
            nb_vlan_410.site is not None and nb_vlan_410.site.name == "NORFAB-LAB"
        ), f"VLAN 410 site mismatch: got {nb_vlan_410.site!r}"
        # Validate LAG member Ethernet6
        nb_eth6 = self._get_nb_intf(nfclient, "ceos-spine-1", "Ethernet6")
        assert nb_eth6 is not None, "Ethernet6 not found in NetBox after sync"
        assert (
            nb_eth6.description == "TEST_SYNC_LAG_MEMBER_A"
        ), f"Ethernet6 description mismatch: got {nb_eth6.description!r}"
        assert (
            nb_eth6.lag is not None and nb_eth6.lag.name == "Port-Channel41"
        ), f"Ethernet6 lag association mismatch: got {nb_eth6.lag!r}"
        # Validate LAG member Ethernet7
        nb_eth7 = self._get_nb_intf(nfclient, "ceos-spine-1", "Ethernet7")
        assert nb_eth7 is not None, "Ethernet7 not found in NetBox after sync"
        assert (
            nb_eth7.description == "TEST_SYNC_LAG_MEMBER_B"
        ), f"Ethernet7 description mismatch: got {nb_eth7.description!r}"
        assert (
            nb_eth7.lag is not None and nb_eth7.lag.name == "Port-Channel41"
        ), f"Ethernet7 lag association mismatch: got {nb_eth7.lag!r}"

    def test_sync_device_interfaces_create_vlan_with_group(self, nfclient):
        """Delete VLAN 510 then sync with vlan_group and verify it is recreated in that group."""
        vlan_group_name = "VLAN_GROUP_1"
        self._cleanup(nfclient, ["ceos-spine-1"])
        nb_vlan_group = self._get_vlan_group(nfclient, vlan_group_name)
        assert nb_vlan_group is not None, f"{vlan_group_name} VLAN group not found"
        self._delete_vlan(nfclient, 510)

        try:
            ret = self._sync(
                nfclient,
                ["ceos-spine-1"],
                vlan_group=vlan_group_name,
            )
            pprint.pprint(ret)
            for worker, res in ret.items():
                assert res["failed"] == False, f"{worker} failed - {res}"
                device_data = res["result"]["ceos-spine-1"]
                assert (
                    "Ethernet8" in device_data["created"]
                ), f"{worker} Ethernet8 not created during VLAN group sync"

            nb_vlan_510 = self._get_vlan(nfclient, 510)
            assert (
                nb_vlan_510 is not None
            ), "VLAN 510 not recreated in NetBox after sync"
            assert (
                nb_vlan_510.name == "VLAN_510"
            ), f"VLAN 510 name mismatch: got {nb_vlan_510.name!r}"
            assert (
                nb_vlan_510.description == "VLAN_510"
            ), f"VLAN 510 description mismatch: got {nb_vlan_510.description!r}"
            assert (
                nb_vlan_510.group is not None
                and nb_vlan_510.group.name == vlan_group_name
            ), f"VLAN 510 group mismatch: got {nb_vlan_510.group!r}"
        finally:
            delete_interfaces_with_description(
                nfclient, TestSyncDeviceInterfaces.ALL_DEVICES, "TEST_SYNC"
            )
            self._delete_vlan(nfclient, 510)

    # ------------------------------------------------------------------ #
    # Update scenarios                                                     #
    # ------------------------------------------------------------------ #

    def test_sync_device_interfaces_update_description(self, nfclient):
        """Clean TEST_SYNC for spine-2, run sync to create Loopback10 with the
        correct description, then corrupt it and verify sync restores it.
        Field-level diff must be present in res['diff']."""
        self._cleanup(nfclient, ["ceos-spine-2"])

        # Create correct NB state from live data
        setup = self._sync(nfclient, ["ceos-spine-2"])
        for worker, res in setup.items():
            assert not res["failed"], f"Setup sync failed for {worker}: {res['errors']}"
            assert (
                "Loopback10" in res["result"]["ceos-spine-2"]["created"]
            ), f"{worker} Loopback10 not created during setup"

        # Corrupt description
        intf_id = self._get_intf_id(nfclient, "ceos-spine-2", "Loopback10")
        self._patch_intf(nfclient, intf_id, {"description": "corrupted-by-test"})

        ret = self._sync(nfclient, ["ceos-spine-2"])
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            device_data = res["result"]["ceos-spine-2"]
            assert (
                "Loopback10" in device_data["updated"]
            ), f"{worker} Loopback10 not in updated list after description corruption"
            assert "ceos-spine-2" in res["diff"], f"{worker} diff not populated"
            assert (
                "Loopback10" in res["diff"]["ceos-spine-2"]["update"]
            ), f"{worker} Loopback10 field diff missing"
            assert (
                "description" in res["diff"]["ceos-spine-2"]["update"]["Loopback10"]
            ), f"{worker} description field missing from diff"

        # Validate description restored in NetBox
        nb_lb10 = self._get_nb_intf(nfclient, "ceos-spine-2", "Loopback10")
        assert nb_lb10 is not None, "Loopback10 not found in NetBox after sync"
        assert (
            nb_lb10.description == "TEST_SYNC_LOOPBACK_IPV4"
        ), f"Loopback10 description not restored in NetBox: got {nb_lb10.description!r}"

    def test_sync_device_interfaces_update_mode(self, nfclient):
        """Clean TEST_SYNC for spine-1, run sync to create Ethernet8 (TEST_SYNC_ACCESS_PORT,
        mode=access), then corrupt mode to tagged and verify sync restores access mode.
        """
        self._cleanup(nfclient, ["ceos-spine-1"])

        # Create correct NB state
        setup = self._sync(nfclient, ["ceos-spine-1"])
        for worker, res in setup.items():
            assert not res["failed"], f"Setup sync failed for {worker}: {res['errors']}"
            assert (
                "Ethernet8" in res["result"]["ceos-spine-1"]["created"]
            ), f"{worker} Ethernet8 not created during setup"

        # Corrupt mode
        intf_id = self._get_intf_id(nfclient, "ceos-spine-1", "Ethernet8")
        self._patch_intf(nfclient, intf_id, {"mode": "tagged", "untagged_vlan": None})

        ret = self._sync(nfclient, ["ceos-spine-1"])
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            device_data = res["result"]["ceos-spine-1"]
            assert (
                "Ethernet8" in device_data["updated"]
            ), f"{worker} Ethernet8 not in updated list after mode corruption"

        # Validate mode and untagged_vlan restored in NetBox
        nb_eth8 = self._get_nb_intf(nfclient, "ceos-spine-1", "Ethernet8")
        assert nb_eth8 is not None, "Ethernet8 not found in NetBox after sync"
        assert (
            nb_eth8.mode is not None and nb_eth8.mode.value == "access"
        ), f"Ethernet8 mode not restored in NetBox: got {nb_eth8.mode!r}"
        assert (
            nb_eth8.untagged_vlan is not None and nb_eth8.untagged_vlan.vid == 510
        ), f"Ethernet8 untagged_vlan not restored in NetBox: got {nb_eth8.untagged_vlan!r}"

    def test_sync_device_interfaces_update_tagged_vlans(self, nfclient):
        """Clean TEST_SYNC for spine-1, run sync to create Port-Channel41
        (TEST_SYNC_LAG_TRUNK, tagged_vlans=[410, 411, 510]), then clear VLANs and verify
        sync restores the VLAN list."""
        self._cleanup(nfclient, ["ceos-spine-1"])

        # Create correct NB state
        setup = self._sync(nfclient, ["ceos-spine-1"])
        for worker, res in setup.items():
            assert not res["failed"], f"Setup sync failed for {worker}: {res['errors']}"
            assert (
                "Port-Channel41" in res["result"]["ceos-spine-1"]["created"]
            ), f"{worker} Port-Channel41 not created during setup"

        # Clear tagged VLANs
        intf_id = self._get_intf_id(nfclient, "ceos-spine-1", "Port-Channel41")
        self._patch_intf(nfclient, intf_id, {"tagged_vlans": []})

        ret = self._sync(nfclient, ["ceos-spine-1"])
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            device_data = res["result"]["ceos-spine-1"]
            assert (
                "Port-Channel41" in device_data["updated"]
            ), f"{worker} Port-Channel41 not in updated list after tagged_vlans cleared"

        # Validate tagged VLANs restored in NetBox
        nb_lag = self._get_nb_intf(nfclient, "ceos-spine-1", "Port-Channel41")
        assert nb_lag is not None, "Port-Channel41 not found in NetBox after sync"
        lag_vids = {v.vid for v in nb_lag.tagged_vlans}
        assert {
            410,
            411,
            510,
        } <= lag_vids, f"Port-Channel41 tagged_vlans not restored in NetBox: expected {{410, 411, 510}} subset, got VIDs {lag_vids}"

    # ------------------------------------------------------------------ #
    # Delete scenarios                                                     #
    # ------------------------------------------------------------------ #

    def test_sync_device_interfaces_delete(self, nfclient):
        """Create a stray non-TEST_SYNC interface on spine-1 then verify
        process_deletions=True removes it."""
        stray = "TestSyncStrayInterface"
        delete_interfaces(nfclient, "ceos-spine-1", stray)

        nfclient.run_job(
            "netbox",
            "create_device_interfaces",
            workers="any",
            kwargs={
                "devices": ["ceos-spine-1"],
                "interface_name": stray,
                "interface_type": "virtual",
            },
        )

        ret = self._sync(nfclient, ["ceos-spine-1"], process_deletions=True)
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            device_data = res["result"]["ceos-spine-1"]
            assert (
                stray in device_data["deleted"]
            ), f"{worker} stray interface {stray!r} not in deleted list"

        # Validate the stray interface is gone from NetBox
        nb_stray = self._get_nb_intf(nfclient, "ceos-spine-1", stray)
        assert (
            nb_stray is None
        ), f"Stray interface {stray!r} still exists in NetBox after process_deletions sync"

    def test_sync_device_interfaces_no_deletions_by_default(self, nfclient):
        """A stray interface in NetBox must NOT be deleted when process_deletions is
        omitted (defaults to False)."""
        stray = "TestSyncStrayNoDelete"
        delete_interfaces(nfclient, "ceos-spine-1", stray)

        nfclient.run_job(
            "netbox",
            "create_device_interfaces",
            workers="any",
            kwargs={
                "devices": ["ceos-spine-1"],
                "interface_name": stray,
                "interface_type": "virtual",
            },
        )

        ret = self._sync(
            nfclient, ["ceos-spine-1"]
        )  # process_deletions defaults to False
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            assert (
                stray not in res["result"]["ceos-spine-1"]["deleted"]
            ), f"{worker} stray interface {stray!r} was deleted but process_deletions=False"

        # Cleanup
        delete_interfaces(nfclient, "ceos-spine-1", stray)

    def test_sync_device_interfaces_filter_excludes_from_deletion(self, nfclient):
        """Interface whose description does NOT match filter_by_description must
        not be deleted even when process_deletions=True.

        Setup: create a stray interface with description 'NOT_TEST_SYNC_DESCRIPTION'.
        Sync with process_deletions=True and filter_by_description='TEST_SYNC_*'.
        The stray must remain untouched because it is outside the filter scope."""
        device = "ceos-spine-1"
        stray = "TestSyncStrayNoMatchFilter"
        delete_interfaces(nfclient, device, stray)

        nfclient.run_job(
            "netbox",
            "create_device_interfaces",
            workers="any",
            kwargs={
                "devices": [device],
                "interface_name": stray,
                "interface_type": "virtual",
                "description": "NOT_TEST_SYNC_DESCRIPTION",
            },
        )

        ret = self._sync(
            nfclient,
            [device],
            process_deletions=True,
            filter_by_description="TEST_SYNC_*",
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            device_data = res["result"][device]
            assert (
                stray not in device_data["deleted"]
            ), f"{worker} interface {stray!r} with non-matching description was deleted"

        # Validate stray still exists in NetBox
        nb_stray = self._get_nb_intf(nfclient, device, stray)
        assert nb_stray is not None, (
            f"Interface {stray!r} was removed from NetBox even though its description "
            f"did not match filter_by_description='TEST_SYNC_*'"
        )

        # Cleanup
        delete_interfaces(nfclient, device, stray)

    def test_sync_device_interfaces_filter_deletes_only_matching(self, nfclient):
        """Only the interface matching filter_by_description AND absent from live
        data is deleted.  Interfaces outside the filter scope are not touched.

        Setup:
        - clean all TEST_SYNC interfaces from spine-1
        - run a setup sync to populate NB with the live TEST_SYNC set
        - create an extra stray with description 'TEST_SYNC_STRAY_DELETE'
          (matches filter, no live counterpart -> must be deleted)
        - create a second stray with description 'PERMANENT_STRAY'
          (does not match filter -> must survive)

        Assert: stray deleted, permanent_stray kept, Loopback0 untouched."""
        device = "ceos-spine-1"
        stray_match = "TestSyncStrayMatchFilter"
        stray_no_match = "TestSyncStrayPermanent"
        delete_interfaces(nfclient, device, stray_match)
        delete_interfaces(nfclient, device, stray_no_match)
        self._cleanup(nfclient, [device])

        # Populate NB with live TEST_SYNC interfaces
        setup = self._sync(nfclient, [device])
        for worker, res in setup.items():
            assert not res["failed"], f"Setup sync failed for {worker}: {res['errors']}"

        # Stray that matches filter but has no live counterpart
        nfclient.run_job(
            "netbox",
            "create_device_interfaces",
            workers="any",
            kwargs={
                "devices": [device],
                "interface_name": stray_match,
                "interface_type": "virtual",
                "description": "TEST_SYNC_STRAY_DELETE",
            },
        )
        # Stray whose description does not match the filter
        nfclient.run_job(
            "netbox",
            "create_device_interfaces",
            workers="any",
            kwargs={
                "devices": [device],
                "interface_name": stray_no_match,
                "interface_type": "virtual",
                "description": "PERMANENT_STRAY",
            },
        )

        ret = self._sync(
            nfclient,
            [device],
            process_deletions=True,
            filter_by_description="TEST_SYNC_*",
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            device_data = res["result"][device]
            # Matching stray must be deleted
            assert (
                stray_match in device_data["deleted"]
            ), f"{worker} matching stray {stray_match!r} not deleted"
            # Non-matching stray must not be deleted
            assert (
                stray_no_match not in device_data["deleted"]
            ), f"{worker} non-matching stray {stray_no_match!r} was deleted"
            # Permanent non-TEST_SYNC fixture must not be deleted
            assert (
                "Loopback0" not in device_data["deleted"]
            ), f"{worker} Loopback0 was incorrectly deleted"

        # Validate in NetBox
        nb_match = self._get_nb_intf(nfclient, device, stray_match)
        assert (
            nb_match is None
        ), f"Matching stray {stray_match!r} still exists in NetBox after deletion"
        nb_no_match = self._get_nb_intf(nfclient, device, stray_no_match)
        assert (
            nb_no_match is not None
        ), f"Non-matching stray {stray_no_match!r} was removed from NetBox unexpectedly"
        nb_lb0 = self._get_nb_intf(nfclient, device, "Loopback0")
        assert nb_lb0 is not None, "Loopback0 was incorrectly deleted from NetBox"

        # Cleanup
        delete_interfaces(nfclient, device, stray_no_match)

    # ------------------------------------------------------------------ #
    # Edge-case / filtering scenarios                                      #
    # ------------------------------------------------------------------ #

    def test_sync_device_interfaces_non_existing_device(self, nfclient):
        """Sync of a device not in NetBox should report an error."""
        ret = self._sync(nfclient, ["nonexistent-device-12345"])
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert (
                len(res["errors"]) > 0
            ), f"{worker} should have errors for nonexistent device"

    def test_sync_device_interfaces_disabled_interface(self, nfclient):
        """ceos-leaf-2 Ethernet5 is shutdown (enabled=False) in live data.
        Clean TEST_SYNC interfaces first, then dry_run sync must include Ethernet5
        in the plan (in create, update, or in_sync)."""
        self._cleanup(nfclient, ["ceos-leaf-2"])

        ret = self._sync(nfclient, ["ceos-leaf-2"], dry_run=True)
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            device_data = res["result"]["ceos-leaf-2"]
            all_tracked = (
                device_data["create"]
                + list(device_data["update"].keys())
                + device_data["in_sync"]
                + device_data["delete"]
            )
            assert (
                "Ethernet5" in all_tracked
            ), f"{worker} Ethernet5 not tracked in dry-run plan for ceos-leaf-2"

    def test_sync_device_interfaces_filter_by_name(self, nfclient):
        """Clean TEST_SYNC from spine-1 then run dry_run with filter_by_name='Loopback*'.
        Non-loopback interfaces must not appear in the plan. Loopback10 and Loopback11
        (cleaned) must appear in create."""
        self._cleanup(nfclient, ["ceos-spine-1"])

        ret = self._sync(
            nfclient, ["ceos-spine-1"], dry_run=True, filter_by_name="Loopback*"
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            device_data = res["result"]["ceos-spine-1"]
            all_names = (
                device_data["create"]
                + list(device_data["update"].keys())
                + device_data["in_sync"]
                + device_data["delete"]
            )
            non_loopback = [n for n in all_names if not n.startswith("Loopback")]
            assert (
                not non_loopback
            ), f"{worker} non-loopback interfaces leaked through filter_by_name: {non_loopback}"
            # Cleaned TEST_SYNC loopbacks must appear in create
            assert (
                "Loopback10" in device_data["create"]
            ), f"{worker} Loopback10 not in create after cleanup + filter_by_name='Loopback*'"
            assert (
                "Loopback11" in device_data["create"]
            ), f"{worker} Loopback11 not in create after cleanup + filter_by_name='Loopback*'"

    def test_sync_device_interfaces_filter_by_description(self, nfclient):
        """Clean TEST_SYNC from spine-1 then run dry_run with filter_by_description='TEST_SYNC_*'.
        All known TEST_SYNC interfaces must appear in create (they were cleaned).
        Non-TEST_SYNC interfaces must not appear in the plan at all."""
        self._cleanup(nfclient, ["ceos-spine-1"])

        ret = self._sync(
            nfclient,
            ["ceos-spine-1"],
            dry_run=True,
            filter_by_description="TEST_SYNC_*",
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            device_data = res["result"]["ceos-spine-1"]
            all_names = (
                device_data["create"]
                + list(device_data["update"].keys())
                + device_data["in_sync"]
                + device_data["delete"]
            )
            # All TEST_SYNC interfaces must be in create (cleaned from NB above)
            missing = self.TEST_SYNC_INTERFACES - set(device_data["create"])
            assert (
                not missing
            ), f"{worker} TEST_SYNC interfaces missing from create: {missing}"
            # Non-TEST_SYNC permanent fixtures must not appear
            non_test_sync = {"Loopback0", "Loopback123", "Ethernet1", "Ethernet2"}
            leaked = non_test_sync & set(all_names)
            assert (
                not leaked
            ), f"{worker} non-TEST_SYNC interfaces leaked through filter_by_description: {leaked}"

    def test_sync_device_interfaces_diff_populated(self, nfclient):
        """Corrupt Ethernet2 description (permanent non-TEST_SYNC fixture) on spine-1
        and verify res['diff'] carries field-level change details after sync."""
        # Ethernet2 is a permanent fixture - no cleanup needed
        intf_id = self._get_intf_id(nfclient, "ceos-spine-1", "Ethernet2")
        self._patch_intf(nfclient, intf_id, {"description": "diff-test-corruption"})

        ret = self._sync(nfclient, ["ceos-spine-1"])
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            assert "ceos-spine-1" in res["diff"], f"{worker} diff not populated"
            assert (
                "Ethernet2" in res["diff"]["ceos-spine-1"]["update"]
            ), f"{worker} Ethernet2 missing from diff"
            intf_diff = res["diff"]["ceos-spine-1"]["update"]["Ethernet2"]
            assert (
                "description" in intf_diff
            ), f"{worker} description field missing from diff"
            assert (
                intf_diff["description"]["old_value"] == "diff-test-corruption"
            ), f"{worker} unexpected old_value in diff: {intf_diff['description']}"

    def test_sync_device_interfaces_with_branch(self, nfclient):
        """Clean TEST_SYNC from spines, delete the branch, then sync into a new branch.
        Result must carry live-run keys and at least one interface must be created."""
        delete_branch("update_interfaces_branch_1", nfclient)
        self._cleanup(nfclient, self.SPINE_DEVICES)

        ret = self._sync(
            nfclient,
            self.SPINE_DEVICES,
            branch="update_interfaces_branch_1",
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            for device in self.SPINE_DEVICES:
                assert (
                    device in res["result"]
                ), f"{worker} returned no results for {device}"
            for device, device_data in res["result"].items():
                assert (
                    self.LIVE_RUN_KEYS <= device_data.keys()
                ), f"{worker}:{device} missing keys in branch-run result"


@pytest.mark.task_create_device_interfaces
class TestCreateDeviceInterfaces:
    def test_create_device_interfaces_single(self, nfclient):
        """Test creating a single interface on a device"""
        delete_interfaces(nfclient, "ceos-spine-1", "TestInterface1")

        ret = nfclient.run_job(
            "netbox",
            "create_device_interfaces",
            workers="any",
            kwargs={
                "devices": ["ceos-spine-1"],
                "interface_name": "TestInterface1",
                "interface_type": "virtual",
            },
        )

        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            assert (
                "ceos-spine-1" in res["result"]
            ), f"{worker} returned no results for ceos-spine-1"
            assert (
                "TestInterface1" in res["result"]["ceos-spine-1"]["created"]
            ), f"{worker} did not create TestInterface1"

    def test_create_device_interfaces_multiple_devices(self, nfclient):
        """Test creating interfaces on multiple devices"""
        delete_interfaces(nfclient, "ceos-spine-1", "TestInterface2")
        delete_interfaces(nfclient, "ceos-spine-2", "TestInterface2")

        ret = nfclient.run_job(
            "netbox",
            "create_device_interfaces",
            workers="any",
            kwargs={
                "devices": ["ceos-spine-1", "ceos-spine-2"],
                "interface_name": "TestInterface2",
                "interface_type": "virtual",
            },
        )

        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            assert (
                "ceos-spine-1" in res["result"]
            ), f"{worker} returned no results for ceos-spine-1"
            assert (
                "ceos-spine-2" in res["result"]
            ), f"{worker} returned no results for ceos-spine-2"
            assert (
                "TestInterface2" in res["result"]["ceos-spine-1"]["created"]
            ), f"{worker} did not create TestInterface2 on ceos-spine-1"
            assert (
                "TestInterface2" in res["result"]["ceos-spine-2"]["created"]
            ), f"{worker} did not create TestInterface2 on ceos-spine-2"

    def test_create_device_interfaces_with_range_numeric(self, nfclient):
        """Test creating interfaces with numeric range expansion"""
        for i in range(1, 4):
            delete_interfaces(nfclient, "ceos-spine-1", f"Loopback{i}")

        ret = nfclient.run_job(
            "netbox",
            "create_device_interfaces",
            workers="any",
            kwargs={
                "devices": ["ceos-spine-1"],
                "interface_name": "Loopback[1-3]",
                "interface_type": "virtual",
            },
        )

        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            assert (
                "ceos-spine-1" in res["result"]
            ), f"{worker} returned no results for ceos-spine-1"
            assert (
                len(res["result"]["ceos-spine-1"]["created"]) == 3
            ), f"{worker} did not create 3 interfaces"
            assert (
                "Loopback1" in res["result"]["ceos-spine-1"]["created"]
            ), f"{worker} did not create Loopback1"
            assert (
                "Loopback2" in res["result"]["ceos-spine-1"]["created"]
            ), f"{worker} did not create Loopback2"
            assert (
                "Loopback3" in res["result"]["ceos-spine-1"]["created"]
            ), f"{worker} did not create Loopback3"

    def test_create_device_interfaces_with_range_list(self, nfclient):
        """Test creating interfaces with comma-separated list expansion"""
        delete_interfaces(nfclient, "ceos-spine-1", "ge-0/0/0")
        delete_interfaces(nfclient, "ceos-spine-1", "xe-0/0/0")

        ret = nfclient.run_job(
            "netbox",
            "create_device_interfaces",
            workers="any",
            kwargs={
                "devices": ["ceos-spine-1"],
                "interface_name": "[ge,xe]-0/0/0",
                "interface_type": "1000base-t",
            },
        )

        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            assert (
                "ceos-spine-1" in res["result"]
            ), f"{worker} returned no results for ceos-spine-1"
            assert (
                len(res["result"]["ceos-spine-1"]["created"]) == 2
            ), f"{worker} did not create 2 interfaces"
            assert (
                "ge-0/0/0" in res["result"]["ceos-spine-1"]["created"]
            ), f"{worker} did not create ge-0/0/0"
            assert (
                "xe-0/0/0" in res["result"]["ceos-spine-1"]["created"]
            ), f"{worker} did not create xe-0/0/0"

    def test_create_device_interfaces_with_multiple_ranges(self, nfclient):
        """Test creating interfaces with multiple range patterns"""
        for prefix in ["ge", "xe"]:
            for i in range(0, 2):
                delete_interfaces(nfclient, "ceos-spine-1", f"{prefix}-0/0/{i}")

        ret = nfclient.run_job(
            "netbox",
            "create_device_interfaces",
            workers="any",
            kwargs={
                "devices": ["ceos-spine-1"],
                "interface_name": "[ge,xe]-0/0/[0-1]",
                "interface_type": "1000base-t",
            },
        )

        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            assert (
                "ceos-spine-1" in res["result"]
            ), f"{worker} returned no results for ceos-spine-1"
            assert (
                len(res["result"]["ceos-spine-1"]["created"]) == 4
            ), f"{worker} did not create 4 interfaces"
            assert "ge-0/0/0" in res["result"]["ceos-spine-1"]["created"]
            assert "ge-0/0/1" in res["result"]["ceos-spine-1"]["created"]
            assert "xe-0/0/0" in res["result"]["ceos-spine-1"]["created"]
            assert "xe-0/0/1" in res["result"]["ceos-spine-1"]["created"]

    def test_create_device_interfaces_multiple_names_list(self, nfclient):
        """Test creating multiple interfaces passed as a list"""
        delete_interfaces(nfclient, "ceos-spine-1", "TestIntf1")
        delete_interfaces(nfclient, "ceos-spine-1", "TestIntf2")

        ret = nfclient.run_job(
            "netbox",
            "create_device_interfaces",
            workers="any",
            kwargs={
                "devices": ["ceos-spine-1"],
                "interface_name": ["TestIntf1", "TestIntf2"],
                "interface_type": "virtual",
            },
        )

        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            assert (
                "ceos-spine-1" in res["result"]
            ), f"{worker} returned no results for ceos-spine-1"
            assert (
                len(res["result"]["ceos-spine-1"]["created"]) == 2
            ), f"{worker} did not create 2 interfaces"
            assert "TestIntf1" in res["result"]["ceos-spine-1"]["created"]
            assert "TestIntf2" in res["result"]["ceos-spine-1"]["created"]

    def test_create_device_interfaces_skip_existing(self, nfclient):
        """Test that existing interfaces are skipped"""
        # First create the interface
        ret1 = nfclient.run_job(
            "netbox",
            "create_device_interfaces",
            workers="any",
            kwargs={
                "devices": ["ceos-spine-1"],
                "interface_name": "TestExisting",
                "interface_type": "virtual",
            },
        )

        # Try to create it again
        ret2 = nfclient.run_job(
            "netbox",
            "create_device_interfaces",
            workers="any",
            kwargs={
                "devices": ["ceos-spine-1"],
                "interface_name": "TestExisting",
                "interface_type": "virtual",
            },
        )

        pprint.pprint(ret2)
        for worker, res in ret2.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            assert (
                "ceos-spine-1" in res["result"]
            ), f"{worker} returned no results for ceos-spine-1"
            assert (
                "TestExisting" in res["result"]["ceos-spine-1"]["skipped"]
            ), f"{worker} did not skip existing TestExisting interface"
            assert (
                len(res["result"]["ceos-spine-1"]["created"]) == 0
            ), f"{worker} should not have created any interfaces"

        # Cleanup
        delete_interfaces(nfclient, "ceos-spine-1", "TestExisting")

    def test_create_device_interfaces_dry_run(self, nfclient):
        """Test dry run mode"""
        delete_interfaces(nfclient, "ceos-spine-1", "TestDryRun")

        ret = nfclient.run_job(
            "netbox",
            "create_device_interfaces",
            workers="any",
            kwargs={
                "devices": ["ceos-spine-1"],
                "interface_name": "TestDryRun",
                "interface_type": "virtual",
                "dry_run": True,
            },
        )

        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            assert (
                "ceos-spine-1" in res["result"]
            ), f"{worker} returned no results for ceos-spine-1"
            assert (
                "TestDryRun" in res["result"]["ceos-spine-1"]["created"]
            ), f"{worker} did not mark TestDryRun for creation in dry run"

        # Verify interface was not actually created
        resp_get = nfclient.run_job(
            "netbox",
            "rest",
            workers="any",
            kwargs={
                "method": "get",
                "api": "/dcim/interfaces/",
                "params": {"device": "ceos-spine-1", "name": "TestDryRun"},
            },
        )
        worker, interfaces = tuple(resp_get.items())[0]
        assert (
            len(interfaces["result"]["results"]) == 0
        ), "Interface should not exist after dry run"

    def test_create_device_interfaces_with_branch(self, nfclient):
        """Test creating interfaces with a branch"""
        delete_branch("create_interfaces_branch_1", nfclient)
        delete_interfaces(nfclient, "ceos-spine-1", "TestBranch")

        ret = nfclient.run_job(
            "netbox",
            "create_device_interfaces",
            workers="any",
            kwargs={
                "devices": ["ceos-spine-1"],
                "interface_name": "TestBranch",
                "interface_type": "virtual",
                "branch": "create_interfaces_branch_1",
            },
        )

        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            assert (
                "ceos-spine-1" in res["result"]
            ), f"{worker} returned no results for ceos-spine-1"
            assert (
                "TestBranch" in res["result"]["ceos-spine-1"]["created"]
            ), f"{worker} did not create TestBranch"

        # Cleanup
        delete_interfaces(nfclient, "ceos-spine-1", "TestBranch")
        delete_branch("create_interfaces_branch_1", nfclient)

    def test_create_device_interfaces_non_existing_device(self, nfclient):
        """Test handling of non-existing device"""
        ret = nfclient.run_job(
            "netbox",
            "create_device_interfaces",
            workers="any",
            kwargs={
                "devices": ["nonexistent-device-12345"],
                "interface_name": "TestInterface",
                "interface_type": "virtual",
            },
        )

        pprint.pprint(ret)
        for worker, res in ret.items():
            assert len(res["errors"]) > 0, f"{worker} should have errors"
