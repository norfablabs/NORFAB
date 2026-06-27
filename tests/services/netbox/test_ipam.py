import pprint
import random

import pytest

try:
    from tests.services.netbox.common import (
        delete_branch,
        delete_interfaces_with_description,
        delete_ips,
        delete_prefixes_within,
        delete_test_sync_ips,
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
        delete_branch,
        delete_interfaces_with_description,
        delete_ips,
        delete_prefixes_within,
        delete_test_sync_ips,
        get_nb_version,
        get_pynetbox,
    )

pytestmark = [pytest.mark.netbox, pytest.mark.ipam]


@pytest.mark.task_sync_device_ip
class TestSyncDeviceIP:
    SPINE_DEVICES = ["ceos-spine-1", "ceos-spine-2"]
    ALL_DEVICES = [
        "ceos-spine-1",
        "ceos-spine-2",
        "ceos-leaf-1",
        "ceos-leaf-2",
        "ceos-leaf-3",
    ]
    RESULT_KEYS = {"created", "updated", "in_sync"}

    # Known TEST_SYNC IPs from interfaces_parse_data.json (10.3.x.x / 2001:beef:: only)
    SPINE1_IP = "10.3.15.33/30"  # ceos-spine-1 Ethernet9 (TEST_SYNC_ROUTED_WITH_MAC)
    SPINE1_INTF = "Ethernet9"
    SPINE1_LOOPBACK_IP = (
        "10.3.4.1/32"  # ceos-spine-1 Loopback10 (TEST_SYNC_LOOPBACK_IPV4)
    )
    SPINE2_IP = "10.3.16.41/30"  # ceos-spine-2 Ethernet9 (TEST_SYNC_ROUTED_WITH_MAC)
    ANYCAST_IP = (
        "10.3.250.250/32"  # Loopback250 on all devices (TEST_SYNC_ANYCAST_IPV4)
    )
    ANYCAST_RANGE = "10.3.250.0/24"

    # ------------------------------------------------------------------ #
    # Class-level helpers                                                  #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _cleanup(nfclient, devices):
        """Delete IPs in 10.3.0.0/16 and 2001:beef::/32"""
        delete_test_sync_ips(nfclient, devices)

    @staticmethod
    def _sync(nfclient, devices, **extra_kwargs):
        """Run sync_device_ip and return the result dict."""
        return nfclient.run_job(
            "netbox",
            "sync_device_ip",
            workers="any",
            kwargs={"devices": devices, **extra_kwargs},
        )

    @staticmethod
    def _get_nb_ip(nfclient, device, interface):
        """Return a list of NetBox IP address records for the given device interface."""
        pynb = get_pynetbox(nfclient)
        return list(pynb.ipam.ip_addresses.filter(device=device, interface=interface))

    @pytest.fixture(autouse=True, scope="class")
    def ensure_test_sync_interfaces(self, nfclient):
        """Create TEST_SYNC interfaces in NetBox for all devices before any IP sync
        test runs. TestSyncDeviceInterfaces cleans these up at the end of its own
        tests, so they must be re-created here."""
        nfclient.run_job(
            "netbox",
            "sync_device_interfaces",
            workers="any",
            kwargs={"devices": self.ALL_DEVICES},
        )
        yield
        delete_interfaces_with_description(nfclient, self.ALL_DEVICES, "TEST_SYNC")

    # ------------------------------------------------------------------ #
    # Basic smoke tests                                                    #
    # ------------------------------------------------------------------ #

    def test_sync_device_ip(self, nfclient):
        """Clean IPs from both spines then sync. Both spine IPs must be created;
        result must carry the correct RESULT_KEYS per device."""
        self._cleanup(nfclient, self.SPINE_DEVICES)

        ret = self._sync(nfclient, self.SPINE_DEVICES)
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            for device in self.SPINE_DEVICES:
                assert (
                    device in res["result"]
                ), f"{worker} returned no result for {device}"
            for device, device_data in res["result"].items():
                assert (
                    self.RESULT_KEYS <= device_data.keys()
                ), f"{worker}:{device} missing keys in result, got: {set(device_data)}"
                assert device_data[
                    "created"
                ], f"{worker}:{device} no IPs created after cleanup"

        # Validate both spine IPs exist in NetBox assigned to the correct interface
        pynb = get_pynetbox(nfclient)
        nb_spine1 = list(
            pynb.ipam.ip_addresses.filter(address=self.SPINE1_IP, device="ceos-spine-1")
        )
        assert nb_spine1, f"{self.SPINE1_IP} not found in NetBox for ceos-spine-1"
        assert (
            nb_spine1[0].assigned_object is not None
        ), f"{self.SPINE1_IP} not assigned to any interface on ceos-spine-1"
        assert (
            nb_spine1[0].assigned_object.name == self.SPINE1_INTF
        ), f"{self.SPINE1_IP} assigned to {nb_spine1[0].assigned_object.name!r}, expected {self.SPINE1_INTF!r}"
        nb_spine2 = list(
            pynb.ipam.ip_addresses.filter(address=self.SPINE2_IP, device="ceos-spine-2")
        )
        assert nb_spine2, f"{self.SPINE2_IP} not found in NetBox for ceos-spine-2"
        assert (
            nb_spine2[0].assigned_object is not None
        ), f"{self.SPINE2_IP} not assigned to any interface on ceos-spine-2"

    def test_sync_device_ip_dry_run(self, nfclient):
        """Clean IPs from both spines then dry_run. Result keys must be RESULT_KEYS
        and 'created' must be non-empty (no actual NB writes)."""
        self._cleanup(nfclient, self.SPINE_DEVICES)

        ret = self._sync(nfclient, self.SPINE_DEVICES, dry_run=True)
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            for device in self.SPINE_DEVICES:
                assert (
                    device in res["result"]
                ), f"{worker} returned no result for {device}"
            for device, device_data in res["result"].items():
                assert (
                    self.RESULT_KEYS <= device_data.keys()
                ), f"{worker}:{device} dry-run result missing keys, got: {set(device_data)}"
                assert device_data[
                    "created"
                ], f"{worker}:{device} dry-run created list is empty after cleanup"

        # Verify dry-run made no writes - IPs must still be absent from NetBox
        pynb = get_pynetbox(nfclient)
        ips_in_nb = list(
            pynb.ipam.ip_addresses.filter(address=self.SPINE1_IP, device="ceos-spine-1")
        )
        assert (
            not ips_in_nb
        ), f"dry-run wrote IP {self.SPINE1_IP} to NetBox: {[str(i) for i in ips_in_nb]}"

    def test_sync_device_ip_already_in_sync(self, nfclient):
        """Sync spines, then sync again. The second run must report all IPs as
        in_sync with nothing created."""
        self._cleanup(nfclient, self.SPINE_DEVICES)

        # First sync: create IPs
        setup = self._sync(nfclient, self.SPINE_DEVICES)
        for worker, res in setup.items():
            assert not res["failed"], f"Setup sync failed for {worker}: {res['errors']}"
            assert res["result"]["ceos-spine-1"][
                "created"
            ], f"{worker} no IPs created during setup sync"

        # Second sync: everything must be in_sync
        ret = self._sync(nfclient, self.SPINE_DEVICES)
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            for device, device_data in res["result"].items():
                assert not device_data[
                    "created"
                ], f"{worker}:{device} unexpected creates on second sync: {device_data['created']}"
                assert device_data[
                    "in_sync"
                ], f"{worker}:{device} in_sync list empty on second sync"

        # Validate IPs are still correctly assigned in NetBox after second sync
        pynb = get_pynetbox(nfclient)
        nb_ips = list(
            pynb.ipam.ip_addresses.filter(address=self.SPINE1_IP, device="ceos-spine-1")
        )
        assert nb_ips, f"{self.SPINE1_IP} missing from NetBox after second sync"
        assert (
            nb_ips[0].assigned_object is not None
        ), f"{self.SPINE1_IP} lost its interface assignment after second sync"
        assert (
            nb_ips[0].assigned_object.name == self.SPINE1_INTF
        ), f"{self.SPINE1_IP} assigned to wrong interface {nb_ips[0].assigned_object.name!r} after second sync"

    # ------------------------------------------------------------------ #
    # Create scenarios                                                     #
    # ------------------------------------------------------------------ #

    def test_sync_device_ip_create(self, nfclient):
        """Clean IPs from spine-1 then sync. Verify Ethernet9 IP is created
        and the NetBox record matches the expected IP value and interface assignment."""
        self._cleanup(nfclient, ["ceos-spine-1"])

        ret = self._sync(nfclient, ["ceos-spine-1"])
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            device_data = res["result"]["ceos-spine-1"]
            assert (
                self.SPINE1_IP in device_data["created"]
            ), f"{worker} {self.SPINE1_IP} not in created list"

        # Validate the IP record in NetBox
        nb_ips = self._get_nb_ip(nfclient, "ceos-spine-1", self.SPINE1_INTF)
        assert (
            nb_ips
        ), f"{self.SPINE1_IP} not found in NetBox for ceos-spine-1:{self.SPINE1_INTF}"
        ip_values = [str(i) for i in nb_ips]
        assert (
            self.SPINE1_IP in ip_values
        ), f"Expected IP {self.SPINE1_IP} not found in NetBox; got {ip_values}"

        self._cleanup(nfclient, ["ceos-spine-1"])

    def test_sync_device_ip_loopback_role(self, nfclient):
        """Sync spine-1 and verify Loopback10 IP gets the 'loopback' role in NetBox."""
        self._cleanup(nfclient, ["ceos-spine-1"])

        ret = self._sync(nfclient, ["ceos-spine-1"])
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            assert (
                self.SPINE1_LOOPBACK_IP in res["result"]["ceos-spine-1"]["created"]
            ), f"{worker} {self.SPINE1_LOOPBACK_IP} not in created list"

        pynb = get_pynetbox(nfclient)
        nb_ip = pynb.ipam.ip_addresses.get(
            address=self.SPINE1_LOOPBACK_IP, device="ceos-spine-1"
        )
        assert nb_ip is not None, f"{self.SPINE1_LOOPBACK_IP} not found in NetBox"
        assert (
            str(nb_ip.role).lower() == "loopback"
        ), f"Expected loopback role for {self.SPINE1_LOOPBACK_IP}, got {nb_ip.role!r}"

        self._cleanup(nfclient, ["ceos-spine-1"])

    # ------------------------------------------------------------------ #
    # Anycast scenarios                                                    #
    # ------------------------------------------------------------------ #

    def test_sync_device_ip_anycast_ranges(self, nfclient):
        """Sync all devices with anycast_ranges set. The anycast IP on Loopback250
        must be created with role='anycast' on each device, creating multiple entries
        for the same IP address (one per device)."""
        self._cleanup(nfclient, self.ALL_DEVICES)

        ret = self._sync(
            nfclient,
            self.ALL_DEVICES,
            anycast_ranges=self.ANYCAST_RANGE,
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            for device in self.ALL_DEVICES:
                assert (
                    device in res["result"]
                ), f"{worker} returned no result for {device}"
                assert (
                    self.ANYCAST_IP in res["result"][device]["created"]
                ), f"{worker}:{device} anycast IP {self.ANYCAST_IP} not in created list"

        # Verify multiple entries exist in NetBox (one per device - anycast allows duplicates)
        pynb = get_pynetbox(nfclient)
        nb_anycast_ips = list(pynb.ipam.ip_addresses.filter(address=self.ANYCAST_IP))
        assert len(nb_anycast_ips) >= len(self.ALL_DEVICES), (
            f"Expected at least {len(self.ALL_DEVICES)} anycast entries for {self.ANYCAST_IP}, "
            f"got {len(nb_anycast_ips)}"
        )
        for ip_entry in nb_anycast_ips:
            assert (
                str(ip_entry.role).lower() == "anycast"
            ), f"Expected anycast role, got {ip_entry.role!r} for {ip_entry}"

        self._cleanup(nfclient, self.ALL_DEVICES)

    def test_sync_device_ip_anycast_already_in_sync(self, nfclient):
        """Sync all devices with anycast_ranges twice. The second run must report
        anycast IPs as in_sync without creating duplicates."""
        self._cleanup(nfclient, self.ALL_DEVICES)

        # First sync: create anycast IPs
        setup = self._sync(
            nfclient, self.ALL_DEVICES, anycast_ranges=self.ANYCAST_RANGE
        )
        for worker, res in setup.items():
            assert not res["failed"], f"Setup sync failed for {worker}: {res['errors']}"

        # Second sync: anycast IPs must be in_sync
        ret = self._sync(nfclient, self.ALL_DEVICES, anycast_ranges=self.ANYCAST_RANGE)
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            for device in self.ALL_DEVICES:
                device_data = res["result"][device]
                assert (
                    self.ANYCAST_IP in device_data["in_sync"]
                ), f"{worker}:{device} anycast IP {self.ANYCAST_IP} not in in_sync on second run"
                assert (
                    self.ANYCAST_IP not in device_data["created"]
                ), f"{worker}:{device} anycast IP {self.ANYCAST_IP} incorrectly re-created"

        # Validate no extra anycast entries were added by the second sync
        pynb = get_pynetbox(nfclient)
        nb_anycast_ips = list(pynb.ipam.ip_addresses.filter(address=self.ANYCAST_IP))
        assert len(nb_anycast_ips) == len(self.ALL_DEVICES), (
            f"Expected exactly {len(self.ALL_DEVICES)} anycast entries after second sync, "
            f"got {len(nb_anycast_ips)}"
        )

        self._cleanup(nfclient, self.ALL_DEVICES)

    # ------------------------------------------------------------------ #
    # Update scenarios                                                     #
    # ------------------------------------------------------------------ #

    def test_sync_device_ip_update_unassigned(self, nfclient):
        """Pre-create spine-1's Ethernet9 IP in NetBox without assigning it to any
        interface, then sync. The IP must be updated (assigned to Ethernet9) rather
        than created."""
        self._cleanup(nfclient, ["ceos-spine-1"])

        # Pre-create IP unassigned
        pynb = get_pynetbox(nfclient)
        pynb.ipam.ip_addresses.create(address=self.SPINE1_IP)

        ret = self._sync(nfclient, ["ceos-spine-1"])
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            device_data = res["result"]["ceos-spine-1"]
            assert (
                self.SPINE1_IP in device_data["updated"]
            ), f"{worker} {self.SPINE1_IP} not in updated list - expected update of unassigned IP"
            assert (
                self.SPINE1_IP not in device_data["created"]
            ), f"{worker} {self.SPINE1_IP} incorrectly listed as created"

        # Validate the IP is now assigned to the correct interface
        nb_ips = self._get_nb_ip(nfclient, "ceos-spine-1", self.SPINE1_INTF)
        assert (
            nb_ips
        ), f"{self.SPINE1_IP} not found on ceos-spine-1:{self.SPINE1_INTF} after update"
        assert any(
            str(i) == self.SPINE1_IP for i in nb_ips
        ), f"{self.SPINE1_IP} value not found on ceos-spine-1:{self.SPINE1_INTF}"

        self._cleanup(nfclient, ["ceos-spine-1"])

    def test_sync_device_ip_update_unassigned_dry_run(self, nfclient):
        """Pre-create spine-1's Ethernet9 IP unassigned in NB. Dry-run sync must
        list it under 'updated', and the IP must remain unassigned after the dry-run."""
        self._cleanup(nfclient, ["ceos-spine-1"])

        pynb = get_pynetbox(nfclient)
        pynb.ipam.ip_addresses.create(address=self.SPINE1_IP)

        ret = self._sync(nfclient, ["ceos-spine-1"], dry_run=True)
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            device_data = res["result"]["ceos-spine-1"]
            assert (
                self.SPINE1_IP in device_data["updated"]
            ), f"{worker} {self.SPINE1_IP} not in updated list for dry-run"

        # Dry-run must not have made any changes - IP must remain unassigned
        pynb = get_pynetbox(nfclient)
        nb_entry = pynb.ipam.ip_addresses.get(address=self.SPINE1_IP)
        assert nb_entry is not None, f"{self.SPINE1_IP} gone from NetBox after dry-run"
        assert (
            nb_entry.assigned_object is None
        ), f"Dry-run unexpectedly assigned {self.SPINE1_IP} to {nb_entry.assigned_object!r}"

        self._cleanup(nfclient, ["ceos-spine-1"])

    # ------------------------------------------------------------------ #
    # Duplicate IP scenarios                                               #
    # ------------------------------------------------------------------ #

    def test_sync_device_ip_duplicate_assigned_to_other_device(self, nfclient):
        """Pre-assign spine-1's Ethernet9 IP to spine-2's Ethernet9 in NetBox, then
        sync spine-1. The sync must report an error (duplicate non-anycast IP) and
        must NOT create or update the IP for spine-1."""
        self._cleanup(nfclient, self.SPINE_DEVICES)

        # Pre-assign spine-1's IP to spine-2's Ethernet9 (TEST_SYNC interface, cleaned up at end)
        pynb = get_pynetbox(nfclient)
        nb_intf = pynb.dcim.interfaces.get(device="ceos-spine-2", name="Ethernet9")
        pynb.ipam.ip_addresses.create(
            address=self.SPINE1_IP,
            assigned_object_type="dcim.interface",
            assigned_object_id=nb_intf.id,
        )

        ret = self._sync(nfclient, ["ceos-spine-1"])
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert (
                len(res["errors"]) > 0
            ), f"{worker} expected errors for duplicate IP assigned to different device, got none"
            device_data = res["result"]["ceos-spine-1"]
            assert (
                self.SPINE1_IP not in device_data["created"]
            ), f"{worker} {self.SPINE1_IP} incorrectly created despite conflict"
            assert (
                self.SPINE1_IP not in device_data["updated"]
            ), f"{worker} {self.SPINE1_IP} incorrectly updated despite conflict"

        # Validate the IP is still only on spine-2's Ethernet9, not created for spine-1
        pynb = get_pynetbox(nfclient)
        all_entries = list(pynb.ipam.ip_addresses.filter(address=self.SPINE1_IP))
        assert len(all_entries) == 1, (
            f"Expected exactly 1 entry for {self.SPINE1_IP}, got {len(all_entries)}: "
            f"{[str(i) for i in all_entries]}"
        )
        assert (
            all_entries[0].assigned_object is not None
        ), f"{self.SPINE1_IP} unexpectedly lost its assignment"
        assert all_entries[0].assigned_object.device.name == "ceos-spine-2", (
            f"{self.SPINE1_IP} ended up on wrong device "
            f"{all_entries[0].assigned_object.device.name!r}, expected ceos-spine-2"
        )

        self._cleanup(nfclient, self.SPINE_DEVICES)

    # ------------------------------------------------------------------ #
    # Edge-case / error scenarios                                          #
    # ------------------------------------------------------------------ #

    def test_sync_device_ip_non_existing_device(self, nfclient):
        """Sync against a device name that does not exist in NetBox.
        The task must fail and report an error."""
        ret = self._sync(nfclient, ["nonexistent-device-12345"])
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert (
                len(res["errors"]) > 0
            ), f"{worker} should have errors for nonexistent device"

    # ------------------------------------------------------------------ #
    # Process prefixes scenarios                                           #
    # ------------------------------------------------------------------ #

    def test_sync_device_ip_create_prefixes(self, nfclient):
        """Sync spine-1 with create_prefixes=True. Verify Ethernet9 IP prefix
        is created in NetBox."""
        self._cleanup(nfclient, ["ceos-spine-1"])
        delete_prefixes_within("10.3.15.32/30", nfclient)

        ret = self._sync(nfclient, ["ceos-spine-1"], create_prefixes=True)
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"

        # Verify the prefix for spine-1 Ethernet9 IP (10.3.15.33/30) was created
        pynb = get_pynetbox(nfclient)
        # 10.3.15.33/30 network is 10.3.15.32/30
        nb_pfx = pynb.ipam.prefixes.get(prefix="10.3.15.32/30")
        assert (
            nb_pfx is not None
        ), "Prefix 10.3.15.32/30 was not created in NetBox after sync with create_prefixes=True"
        # Also validate the IP itself was created and assigned to the correct interface
        nb_ips = list(
            pynb.ipam.ip_addresses.filter(address=self.SPINE1_IP, device="ceos-spine-1")
        )
        assert (
            nb_ips
        ), f"{self.SPINE1_IP} not found in NetBox after sync with create_prefixes=True"
        assert (
            nb_ips[0].assigned_object is not None
        ), f"{self.SPINE1_IP} not assigned to any interface"
        assert (
            nb_ips[0].assigned_object.name == self.SPINE1_INTF
        ), f"{self.SPINE1_IP} assigned to {nb_ips[0].assigned_object.name!r}, expected {self.SPINE1_INTF!r}"

        self._cleanup(nfclient, ["ceos-spine-1"])
        delete_prefixes_within("10.3.15.32/30", nfclient)

    def test_sync_device_ip_create_prefixes_idempotent(self, nfclient):
        """Run sync_device_ip with create_prefixes=True twice on spine-1.
        The second run must not fail even though the prefix already exists."""
        self._cleanup(nfclient, ["ceos-spine-1"])
        delete_prefixes_within("10.3.15.32/30", nfclient)

        self._sync(nfclient, ["ceos-spine-1"], create_prefixes=True)
        ret = self._sync(nfclient, ["ceos-spine-1"], create_prefixes=True)
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed on second run - {res}"

        # Validate prefix was not duplicated and IP is still correctly assigned
        pynb = get_pynetbox(nfclient)
        nb_pfxs = list(pynb.ipam.prefixes.filter(prefix="10.3.15.32/30"))
        assert (
            len(nb_pfxs) == 1
        ), f"Expected exactly 1 prefix 10.3.15.32/30 after two syncs, got {len(nb_pfxs)}"
        nb_ips = list(
            pynb.ipam.ip_addresses.filter(address=self.SPINE1_IP, device="ceos-spine-1")
        )
        assert (
            nb_ips
        ), f"{self.SPINE1_IP} not found in NetBox after idempotent create_prefixes sync"
        assert (
            nb_ips[0].assigned_object is not None
        ), f"{self.SPINE1_IP} not assigned to any interface after idempotent sync"

        self._cleanup(nfclient, ["ceos-spine-1"])
        delete_prefixes_within("10.3.15.32/30", nfclient)

    # ------------------------------------------------------------------ #
    # Branch scenario                                                      #
    # ------------------------------------------------------------------ #

    def test_sync_device_ip_with_branch(self, nfclient):
        """Clean spine IPs, delete the test branch, then sync into a new branch.
        Result must carry RESULT_KEYS and at least one IP must be created."""
        branch = "sync_device_ip_branch_1"
        delete_branch(branch, nfclient)
        self._cleanup(nfclient, self.SPINE_DEVICES)

        ret = self._sync(nfclient, self.SPINE_DEVICES, branch=branch)
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            for device in self.SPINE_DEVICES:
                assert (
                    device in res["result"]
                ), f"{worker} returned no result for {device}"
            for device, device_data in res["result"].items():
                assert (
                    self.RESULT_KEYS <= device_data.keys()
                ), f"{worker}:{device} missing keys in branch-run result"

        # Validate IPs were NOT written to the main NetBox context (branch-only writes)
        pynb = get_pynetbox(nfclient)
        nb_ips = list(
            pynb.ipam.ip_addresses.filter(address=self.SPINE1_IP, device="ceos-spine-1")
        )
        assert not nb_ips, (
            f"Branch sync wrote {self.SPINE1_IP} to main NetBox context (should be branch-only): "
            f"{[str(i) for i in nb_ips]}"
        )

        delete_branch(branch, nfclient)

    # ------------------------------------------------------------------ #
    # Filter scenarios                                                     #
    # ------------------------------------------------------------------ #

    def test_sync_device_ip_filter_by_name_loopback(self, nfclient):
        """filter_by_name='Loopback*' must include only loopback interfaces.
        SPINE1_LOOPBACK_IP must be created; SPINE1_IP (Ethernet9) must NOT appear."""
        self._cleanup(nfclient, ["ceos-spine-1"])

        ret = self._sync(nfclient, ["ceos-spine-1"], filter_by_name="Loopback*")
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            device_data = res["result"]["ceos-spine-1"]
            assert (
                self.SPINE1_LOOPBACK_IP in device_data["created"]
            ), f"{worker} {self.SPINE1_LOOPBACK_IP} not in created with filter_by_name='Loopback*'"
            all_touched = (
                device_data["created"] + device_data["updated"] + device_data["in_sync"]
            )
            assert (
                self.SPINE1_IP not in all_touched
            ), f"{worker} {self.SPINE1_IP} (Ethernet9) appeared despite filter_by_name='Loopback*'"

        # Validate SPINE1_LOOPBACK_IP written to NetBox; SPINE1_IP absent
        pynb = get_pynetbox(nfclient)
        nb_loopback = list(
            pynb.ipam.ip_addresses.filter(
                address=self.SPINE1_LOOPBACK_IP, device="ceos-spine-1"
            )
        )
        assert (
            nb_loopback
        ), f"{self.SPINE1_LOOPBACK_IP} not found in NetBox after filter_by_name='Loopback*'"
        assert (
            nb_loopback[0].assigned_object is not None
        ), f"{self.SPINE1_LOOPBACK_IP} not assigned to any interface"
        nb_eth = list(
            pynb.ipam.ip_addresses.filter(address=self.SPINE1_IP, device="ceos-spine-1")
        )
        assert (
            not nb_eth
        ), f"{self.SPINE1_IP} found in NetBox despite filter_by_name='Loopback*': {[str(i) for i in nb_eth]}"

        self._cleanup(nfclient, ["ceos-spine-1"])

    def test_sync_device_ip_filter_by_name_ethernet(self, nfclient):
        """filter_by_name='Ethernet*' must include only ethernet interfaces.
        SPINE1_IP must be created; SPINE1_LOOPBACK_IP must NOT appear."""
        self._cleanup(nfclient, ["ceos-spine-1"])

        ret = self._sync(nfclient, ["ceos-spine-1"], filter_by_name="Ethernet*")
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            device_data = res["result"]["ceos-spine-1"]
            assert (
                self.SPINE1_IP in device_data["created"]
            ), f"{worker} {self.SPINE1_IP} not in created with filter_by_name='Ethernet*'"
            all_touched = (
                device_data["created"] + device_data["updated"] + device_data["in_sync"]
            )
            assert (
                self.SPINE1_LOOPBACK_IP not in all_touched
            ), f"{worker} {self.SPINE1_LOOPBACK_IP} (Loopback10) appeared despite filter_by_name='Ethernet*'"

        # Validate SPINE1_IP written to NetBox assigned to Ethernet9; loopback IP absent
        pynb = get_pynetbox(nfclient)
        nb_eth = list(
            pynb.ipam.ip_addresses.filter(address=self.SPINE1_IP, device="ceos-spine-1")
        )
        assert (
            nb_eth
        ), f"{self.SPINE1_IP} not found in NetBox after filter_by_name='Ethernet*'"
        assert (
            nb_eth[0].assigned_object is not None
        ), f"{self.SPINE1_IP} not assigned to any interface"
        assert (
            nb_eth[0].assigned_object.name == self.SPINE1_INTF
        ), f"{self.SPINE1_IP} assigned to {nb_eth[0].assigned_object.name!r}, expected {self.SPINE1_INTF!r}"
        nb_loopback = list(
            pynb.ipam.ip_addresses.filter(
                address=self.SPINE1_LOOPBACK_IP, device="ceos-spine-1"
            )
        )
        assert not nb_loopback, (
            f"{self.SPINE1_LOOPBACK_IP} found in NetBox despite filter_by_name='Ethernet*': "
            f"{[str(i) for i in nb_loopback]}"
        )

        self._cleanup(nfclient, ["ceos-spine-1"])

    def test_sync_device_ip_filter_by_name_no_match(self, nfclient):
        """filter_by_name that matches nothing must result in empty created/updated/in_sync lists."""
        self._cleanup(nfclient, ["ceos-spine-1"])

        ret = self._sync(nfclient, ["ceos-spine-1"], filter_by_name="NonExistent*")
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            device_data = res["result"]["ceos-spine-1"]
            assert not device_data[
                "created"
            ], f"{worker} unexpected created IPs with non-matching filter_by_name: {device_data['created']}"
            assert not device_data[
                "updated"
            ], f"{worker} unexpected updated IPs with non-matching filter_by_name: {device_data['updated']}"

        # Validate no IPs were written to NetBox for spine-1 at all
        pynb = get_pynetbox(nfclient)
        for addr in [self.SPINE1_IP, self.SPINE1_LOOPBACK_IP]:
            nb_ips = list(
                pynb.ipam.ip_addresses.filter(address=addr, device="ceos-spine-1")
            )
            assert (
                not nb_ips
            ), f"{addr} found in NetBox despite non-matching filter_by_name: {[str(i) for i in nb_ips]}"

    def test_sync_device_ip_filter_by_description(self, nfclient):
        """filter_by_description='*LOOPBACK*' must restrict to interfaces whose
        description matches. SPINE1_LOOPBACK_IP must be created; SPINE1_IP must NOT appear.
        """
        self._cleanup(nfclient, ["ceos-spine-1"])

        ret = self._sync(nfclient, ["ceos-spine-1"], filter_by_description="*LOOPBACK*")
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            device_data = res["result"]["ceos-spine-1"]
            assert (
                self.SPINE1_LOOPBACK_IP in device_data["created"]
            ), f"{worker} {self.SPINE1_LOOPBACK_IP} not in created with filter_by_description='*LOOPBACK*'"
            all_touched = (
                device_data["created"] + device_data["updated"] + device_data["in_sync"]
            )
            assert (
                self.SPINE1_IP not in all_touched
            ), f"{worker} {self.SPINE1_IP} appeared despite filter_by_description='*LOOPBACK*'"

        # Validate SPINE1_LOOPBACK_IP written to NetBox; SPINE1_IP absent
        pynb = get_pynetbox(nfclient)
        nb_loopback = list(
            pynb.ipam.ip_addresses.filter(
                address=self.SPINE1_LOOPBACK_IP, device="ceos-spine-1"
            )
        )
        assert (
            nb_loopback
        ), f"{self.SPINE1_LOOPBACK_IP} not found in NetBox after filter_by_description='*LOOPBACK*'"
        assert (
            nb_loopback[0].assigned_object is not None
        ), f"{self.SPINE1_LOOPBACK_IP} not assigned to any interface"
        nb_eth = list(
            pynb.ipam.ip_addresses.filter(address=self.SPINE1_IP, device="ceos-spine-1")
        )
        assert not nb_eth, (
            f"{self.SPINE1_IP} found in NetBox despite filter_by_description='*LOOPBACK*': "
            f"{[str(i) for i in nb_eth]}"
        )

        self._cleanup(nfclient, ["ceos-spine-1"])

    def test_sync_device_ip_filter_by_prefix(self, nfclient):
        """filter_by_prefix='10.3.15.0/24' must include only IPs within that prefix.
        SPINE1_IP (10.3.15.33) must be created; SPINE1_LOOPBACK_IP (10.3.4.1) must NOT appear.
        """
        self._cleanup(nfclient, ["ceos-spine-1"])

        ret = self._sync(nfclient, ["ceos-spine-1"], filter_by_prefix="10.3.15.0/24")
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            device_data = res["result"]["ceos-spine-1"]
            assert (
                self.SPINE1_IP in device_data["created"]
            ), f"{worker} {self.SPINE1_IP} not in created with filter_by_prefix='10.3.15.0/24'"
            all_touched = (
                device_data["created"] + device_data["updated"] + device_data["in_sync"]
            )
            assert (
                self.SPINE1_LOOPBACK_IP not in all_touched
            ), f"{worker} {self.SPINE1_LOOPBACK_IP} appeared despite filter_by_prefix='10.3.15.0/24'"

        # Validate SPINE1_IP written to NetBox; SPINE1_LOOPBACK_IP absent
        pynb = get_pynetbox(nfclient)
        nb_eth = list(
            pynb.ipam.ip_addresses.filter(address=self.SPINE1_IP, device="ceos-spine-1")
        )
        assert (
            nb_eth
        ), f"{self.SPINE1_IP} not found in NetBox after filter_by_prefix='10.3.15.0/24'"
        assert (
            nb_eth[0].assigned_object is not None
        ), f"{self.SPINE1_IP} not assigned to any interface"
        assert (
            nb_eth[0].assigned_object.name == self.SPINE1_INTF
        ), f"{self.SPINE1_IP} assigned to {nb_eth[0].assigned_object.name!r}, expected {self.SPINE1_INTF!r}"
        nb_loopback = list(
            pynb.ipam.ip_addresses.filter(
                address=self.SPINE1_LOOPBACK_IP, device="ceos-spine-1"
            )
        )
        assert not nb_loopback, (
            f"{self.SPINE1_LOOPBACK_IP} found in NetBox despite filter_by_prefix='10.3.15.0/24': "
            f"{[str(i) for i in nb_loopback]}"
        )

        self._cleanup(nfclient, ["ceos-spine-1"])

    def test_sync_device_ip_filter_by_prefix_loopback_range(self, nfclient):
        """filter_by_prefix='10.3.4.0/24' must include only IPs within that prefix.
        SPINE1_LOOPBACK_IP (10.3.4.1) must be created; SPINE1_IP (10.3.15.33) must NOT appear.
        """
        self._cleanup(nfclient, ["ceos-spine-1"])

        ret = self._sync(nfclient, ["ceos-spine-1"], filter_by_prefix="10.3.4.0/24")
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            device_data = res["result"]["ceos-spine-1"]
            assert (
                self.SPINE1_LOOPBACK_IP in device_data["created"]
            ), f"{worker} {self.SPINE1_LOOPBACK_IP} not in created with filter_by_prefix='10.3.4.0/24'"
            all_touched = (
                device_data["created"] + device_data["updated"] + device_data["in_sync"]
            )
            assert (
                self.SPINE1_IP not in all_touched
            ), f"{worker} {self.SPINE1_IP} appeared despite filter_by_prefix='10.3.4.0/24'"

        # Validate SPINE1_LOOPBACK_IP written to NetBox; SPINE1_IP absent
        pynb = get_pynetbox(nfclient)
        nb_loopback = list(
            pynb.ipam.ip_addresses.filter(
                address=self.SPINE1_LOOPBACK_IP, device="ceos-spine-1"
            )
        )
        assert (
            nb_loopback
        ), f"{self.SPINE1_LOOPBACK_IP} not found in NetBox after filter_by_prefix='10.3.4.0/24'"
        assert (
            nb_loopback[0].assigned_object is not None
        ), f"{self.SPINE1_LOOPBACK_IP} not assigned to any interface"
        nb_eth = list(
            pynb.ipam.ip_addresses.filter(address=self.SPINE1_IP, device="ceos-spine-1")
        )
        assert not nb_eth, (
            f"{self.SPINE1_IP} found in NetBox despite filter_by_prefix='10.3.4.0/24': "
            f"{[str(i) for i in nb_eth]}"
        )

        self._cleanup(nfclient, ["ceos-spine-1"])

    def test_sync_device_ip_filter_by_ip(self, nfclient):
        """filter_by_ip='10.3.4.*' glob must include only matching IP host addresses.
        SPINE1_LOOPBACK_IP (10.3.4.1) must be created; SPINE1_IP (10.3.15.33) must NOT appear.
        """
        self._cleanup(nfclient, ["ceos-spine-1"])

        ret = self._sync(nfclient, ["ceos-spine-1"], filter_by_ip="10.3.4.*")
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            device_data = res["result"]["ceos-spine-1"]
            assert (
                self.SPINE1_LOOPBACK_IP in device_data["created"]
            ), f"{worker} {self.SPINE1_LOOPBACK_IP} not in created with filter_by_ip='10.3.4.*'"
            all_touched = (
                device_data["created"] + device_data["updated"] + device_data["in_sync"]
            )
            assert (
                self.SPINE1_IP not in all_touched
            ), f"{worker} {self.SPINE1_IP} appeared despite filter_by_ip='10.3.4.*'"

        # Validate SPINE1_LOOPBACK_IP written to NetBox; SPINE1_IP absent
        pynb = get_pynetbox(nfclient)
        nb_loopback = list(
            pynb.ipam.ip_addresses.filter(
                address=self.SPINE1_LOOPBACK_IP, device="ceos-spine-1"
            )
        )
        assert (
            nb_loopback
        ), f"{self.SPINE1_LOOPBACK_IP} not found in NetBox after filter_by_ip='10.3.4.*'"
        assert (
            nb_loopback[0].assigned_object is not None
        ), f"{self.SPINE1_LOOPBACK_IP} not assigned to any interface"
        nb_eth = list(
            pynb.ipam.ip_addresses.filter(address=self.SPINE1_IP, device="ceos-spine-1")
        )
        assert not nb_eth, (
            f"{self.SPINE1_IP} found in NetBox despite filter_by_ip='10.3.4.*': "
            f"{[str(i) for i in nb_eth]}"
        )

        self._cleanup(nfclient, ["ceos-spine-1"])

    def test_sync_device_ip_filter_by_name_and_prefix_combined(self, nfclient):
        """Combining filter_by_name='Loopback*' with filter_by_prefix='10.3.4.0/24' must
        intersect both filters - only SPINE1_LOOPBACK_IP must be created."""
        self._cleanup(nfclient, ["ceos-spine-1"])

        ret = self._sync(
            nfclient,
            ["ceos-spine-1"],
            filter_by_name="Loopback*",
            filter_by_prefix="10.3.4.0/24",
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            device_data = res["result"]["ceos-spine-1"]
            assert (
                self.SPINE1_LOOPBACK_IP in device_data["created"]
            ), f"{worker} {self.SPINE1_LOOPBACK_IP} not in created with combined filters"
            all_touched = (
                device_data["created"] + device_data["updated"] + device_data["in_sync"]
            )
            assert (
                self.SPINE1_IP not in all_touched
            ), f"{worker} {self.SPINE1_IP} appeared despite combined name+prefix filters"
            # ANYCAST_IP is on Loopback250 but outside 10.3.4.0/24 - must not appear
            assert (
                self.ANYCAST_IP not in all_touched
            ), f"{worker} {self.ANYCAST_IP} (Loopback250) appeared despite filter_by_prefix='10.3.4.0/24'"

        # Validate only SPINE1_LOOPBACK_IP written to NetBox; SPINE1_IP and ANYCAST_IP absent
        pynb = get_pynetbox(nfclient)
        nb_loopback = list(
            pynb.ipam.ip_addresses.filter(
                address=self.SPINE1_LOOPBACK_IP, device="ceos-spine-1"
            )
        )
        assert (
            nb_loopback
        ), f"{self.SPINE1_LOOPBACK_IP} not found in NetBox after combined filter_by_name+filter_by_prefix"
        assert (
            nb_loopback[0].assigned_object is not None
        ), f"{self.SPINE1_LOOPBACK_IP} not assigned to any interface"
        nb_eth = list(
            pynb.ipam.ip_addresses.filter(address=self.SPINE1_IP, device="ceos-spine-1")
        )
        assert (
            not nb_eth
        ), f"{self.SPINE1_IP} found in NetBox despite combined filters: {[str(i) for i in nb_eth]}"
        nb_anycast = list(
            pynb.ipam.ip_addresses.filter(
                address=self.ANYCAST_IP, device="ceos-spine-1"
            )
        )
        assert not nb_anycast, (
            f"{self.ANYCAST_IP} found in NetBox despite filter_by_prefix='10.3.4.0/24': "
            f"{[str(i) for i in nb_anycast]}"
        )

        self._cleanup(nfclient, ["ceos-spine-1"])


@pytest.mark.task_create_ip
class TestCreateIP:
    nb_version = None

    def setup_method(self):
        pass

    def teardown_method(self):
        pass

    def test_create_ip_by_prefix(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        delete_ips("10.0.0.0/24", nfclient)

        rand = random.randint(1, 1000)
        if self.nb_version[0] == 4:
            create_1 = nfclient.run_job(
                "netbox",
                "create_ip",
                workers="any",
                kwargs={
                    "prefix": "10.0.0.0/24",
                    "description": f"test create ip {rand}",
                },
            )
            create_2 = nfclient.run_job(
                "netbox",
                "create_ip",
                workers="any",
                kwargs={
                    "prefix": "10.0.0.0/24",
                    "description": f"test create ip {rand}",
                },
            )
            print("create_1")
            pprint.pprint(create_1, width=200)
            print("create_2")
            pprint.pprint(create_2, width=200)

            for worker, res1 in create_1.items():
                assert res1["failed"] == False, "Allocation failed"
                assert res1["result"]["address"], f"Result has no ip {res1['result']}"

            worker, res2 = tuple(create_2.items())[0]
            assert (
                res1["result"]["address"] == res2["result"]["address"]
            ), "Should have been same IP address"
            assert (
                res1["result"]["description"] == res2["result"]["description"]
            ), "Should have been same IP description"

    def test_create_ip_by_prefix_description(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        delete_ips("10.0.0.0/24", nfclient)

        rand = random.randint(1, 1000)
        if self.nb_version[0] == 4:
            create_1 = nfclient.run_job(
                "netbox",
                "create_ip",
                workers="any",
                kwargs={
                    "prefix": "TEST NEXT IP PREFIX",
                    "description": f"test create ip {rand}",
                },
            )
            create_2 = nfclient.run_job(
                "netbox",
                "create_ip",
                workers="any",
                kwargs={
                    "prefix": "TEST NEXT IP PREFIX",
                    "description": f"test create ip {rand}",
                },
            )
            print("create_1")
            pprint.pprint(create_1, width=200)
            print("create_2")
            pprint.pprint(create_2, width=200)

            for worker, res1 in create_1.items():
                assert res1["failed"] == False, "Allocation failed"
                assert res1["result"]["address"], f"Result has no ip {res1['result']}"

            worker, res2 = tuple(create_2.items())[0]
            assert (
                res1["result"]["address"] == res2["result"]["address"]
            ), "Should have been same IP address"
            assert (
                res1["result"]["description"] == res2["result"]["description"]
            ), "Should have been same IP description"

    def test_create_ip_by_prefix_role_and_site(self, nfclient):
        delete_ips("192.168.100.0/24", nfclient)

        create_1 = nfclient.run_job(
            "netbox",
            "create_ip",
            workers="any",
            kwargs={
                "prefix": {
                    "role__name": "PREFIX_ROLE_1".lower(),
                    "site": "NORFAB-LAB".lower(),
                },
                "description": f"test create ip by prefix role and site 1st",
            },
        )

        create_2 = nfclient.run_job(
            "netbox",
            "create_ip",
            workers="any",
            kwargs={
                "prefix": {
                    "role": "PREFIX_ROLE_1".lower(),
                    "site": "NORFAB-LAB".lower(),
                },
                "description": f"test create ip by prefix role and site 2nd",
            },
        )
        print("create_1")
        pprint.pprint(create_1, width=200)
        print("create_2")
        pprint.pprint(create_2, width=200)

        for worker, res1 in create_1.items():
            assert res1["failed"] == False, "Allocation failed"
            assert res1["result"]["address"], f"Result has no ip {res1['result']}"

        for worker, res2 in create_2.items():
            assert res2["failed"] == False, "Allocation failed"
            assert res2["result"]["address"], f"Result has no ip {res2['result']}"

    def test_create_ip_by_prefix_multiple(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        delete_ips("10.0.0.0/24", nfclient)

        if self.nb_version[0] == 4:
            create_1 = nfclient.run_job(
                "netbox",
                "create_ip",
                workers="any",
                kwargs={
                    "prefix": "10.0.0.0/24",
                    "description": f"test create ip {random.randint(1, 1000)}",
                },
            )
            create_2 = nfclient.run_job(
                "netbox",
                "create_ip",
                workers="any",
                kwargs={
                    "prefix": "10.0.0.0/24",
                    "description": f"test create ip {random.randint(1, 1000)}",
                },
            )
            print("create_1")
            pprint.pprint(create_1, width=200)
            print("create_2")
            pprint.pprint(create_2, width=200)

            worker, res1 = tuple(create_1.items())[0]
            worker, res2 = tuple(create_2.items())[0]

            assert res1["failed"] == False, "Allocation failed"
            assert res2["failed"] == False, "Allocation failed"

            assert res1["result"]["address"] != res2["result"]["address"]
            assert res1["result"]["description"] != res2["result"]["description"]

    def test_create_ip_nonexist_prefix(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        if self.nb_version[0] == 4:
            create_1 = nfclient.run_job(
                "netbox",
                "create_ip",
                workers="any",
                kwargs={
                    "prefix": "1.2.3.0/24",
                    "description": f"test create ip {random.randint(1, 1000)}",
                },
            )
            pprint.pprint(create_1, width=200)
            worker, res1 = tuple(create_1.items())[0]
            assert res1["failed"] == True, "Allocation not failed"
            assert "Unable to source parent prefix from Netbox" in res1["messages"][0]

    def test_create_ip_by_prefix_device_interface(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        delete_ips("10.0.0.0/24", nfclient)

        if self.nb_version[0] == 4:
            create_1 = nfclient.run_job(
                "netbox",
                "create_ip",
                workers="any",
                kwargs={
                    "prefix": "10.0.0.0/24",
                    "device": "fceos4",
                    "interface": "eth1",
                },
            )
            create_2 = nfclient.run_job(
                "netbox",
                "create_ip",
                workers="any",
                kwargs={
                    "prefix": "10.0.0.0/24",
                    "device": "fceos4",
                    "interface": "eth1",
                },
            )
            print("create_1")
            pprint.pprint(create_1, width=200)
            print("create_2")
            pprint.pprint(create_2, width=200)

            worker, res1 = tuple(create_1.items())[0]
            worker, res2 = tuple(create_2.items())[0]

            assert res1["failed"] == False, "Allocation failed"
            assert res2["failed"] == False, "Allocation failed"

            assert (
                res1["result"]["address"] == res2["result"]["address"]
            ), "Should be same IP"

    def test_create_ip_by_prefix_description_device_interface(self, nfclient):
        "This test should allocate two different IPs since device, interface, description given"
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        delete_ips("10.0.0.0/24", nfclient)

        if self.nb_version[0] == 4:
            create_1 = nfclient.run_job(
                "netbox",
                "create_ip",
                workers="any",
                kwargs={
                    "prefix": "10.0.0.0/24",
                    "device": "fceos4",
                    "interface": "eth1",
                    "description": "foo1",
                },
            )
            create_2 = nfclient.run_job(
                "netbox",
                "create_ip",
                workers="any",
                kwargs={
                    "prefix": "10.0.0.0/24",
                    "device": "fceos4",
                    "interface": "eth1",
                    "description": "foo2",
                },
            )
            print("create_1")
            pprint.pprint(create_1, width=200)
            print("create_2")
            pprint.pprint(create_2, width=200)

            worker, res1 = tuple(create_1.items())[0]
            worker, res2 = tuple(create_2.items())[0]

            assert res1["failed"] == False, "Allocation failed"
            assert res2["failed"] == False, "Allocation failed"

            assert (
                res1["result"]["address"] != res2["result"]["address"]
            ), "Should be different IP cause description is different"

    def test_create_ip_with_vrf_tags_tenant_role_dnsname_comments(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        delete_ips("10.0.0.0/24", nfclient)

        if self.nb_version[0] == 4:
            create_1 = nfclient.run_job(
                "netbox",
                "create_ip",
                workers="any",
                kwargs={
                    "prefix": "10.0.0.0/24",
                    "device": "fceos4",
                    "interface": "eth1",
                    "description": "foo1",
                    "vrf": "VRF1",
                    "tags": ["NORFAB", "ACCESS"],
                    "tenant": "NORFAB",
                    "dns_name": "foo1.lab.local",
                    "role": "anycast",
                    "comments": "Some comments",
                },
            )
            print("create_1")
            pprint.pprint(create_1, width=200)

            worker, res1 = tuple(create_1.items())[0]

            assert res1["failed"] == False, "Allocation failed"
            assert res1["result"]["address"], "No ip allocated"

    def test_create_ip_non_existing_device(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        if self.nb_version[0] == 4:
            create_1 = nfclient.run_job(
                "netbox",
                "create_ip",
                workers="any",
                kwargs={
                    "prefix": "10.0.0.0/24",
                    "device": "does_not_exist",
                    "interface": "eth1",
                    "description": "foo1",
                },
            )
            print("create_1")
            pprint.pprint(create_1, width=200)

            worker, res1 = tuple(create_1.items())[0]

            assert res1["failed"] == True, "Allocation should have failed"

    def test_create_ip_non_existing_interface(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        if self.nb_version[0] == 4:
            create_1 = nfclient.run_job(
                "netbox",
                "create_ip",
                workers="any",
                kwargs={
                    "prefix": "10.0.0.0/24",
                    "device": "fce0s4",
                    "interface": "does_not_exist",
                    "description": "foo1",
                },
            )
            print("create_1")
            pprint.pprint(create_1, width=200)

            worker, res1 = tuple(create_1.items())[0]

            assert res1["failed"] == True, "Allocation should have failed"

    def test_create_ip_is_primary(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        delete_ips("10.0.0.0/24", nfclient)

        if self.nb_version[0] == 4:
            create_1 = nfclient.run_job(
                "netbox",
                "create_ip",
                workers="any",
                kwargs={
                    "prefix": "10.0.0.0/24",
                    "device": "ceos-spine-1",
                    "interface": "Ethernet1",
                    "description": "foo1",
                    "is_primary": True,
                },
            )
            print("create_1")
            pprint.pprint(create_1, width=200)

            worker, res1 = tuple(create_1.items())[0]

            assert res1["failed"] == False, "Allocation failed"
            assert res1["result"]["address"], "No ip allocated"

    def test_create_ip_dry_run_new_ip(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        delete_ips("10.0.0.0/24", nfclient)

        if self.nb_version[0] == 4:
            # test dry run for new ip
            create_1 = nfclient.run_job(
                "netbox",
                "create_ip",
                workers="any",
                kwargs={
                    "prefix": "10.0.0.0/24",
                    "device": "ceos-spine-1",
                    "interface": "Ethernet1",
                    "dry_run": True,
                },
            )
            create_2 = nfclient.run_job(
                "netbox",
                "create_ip",
                workers="any",
                kwargs={"prefix": "10.0.0.0/24", "description": "foo", "dry_run": True},
            )
            print("create_1")
            pprint.pprint(create_1, width=200)
            print("create_2")
            pprint.pprint(create_2, width=200)

            worker, res1 = tuple(create_1.items())[0]
            worker, res2 = tuple(create_2.items())[0]

            assert res1["failed"] == False, "Allocation failed"
            assert res1["result"]["address"], "No ip allocated"
            assert res1["dry_run"] is True, "No dry run flag set to true"
            assert res1["status"] == "unchanged", "Unexpected status"

            assert res2["failed"] == False, "Allocation failed"
            assert res2["result"]["address"], "No ip allocated"
            assert res2["dry_run"] is True, "No dry run flag set to true"
            assert res2["status"] == "unchanged", "Unexpected status"

    def test_create_ip_dry_run_existing_ip(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        delete_ips("10.0.0.0/24", nfclient)

        if self.nb_version[0] == 4:
            create_1 = nfclient.run_job(
                "netbox",
                "create_ip",
                workers="any",
                kwargs={
                    "prefix": "10.0.0.0/24",
                    "description": "foobar",
                },
            )
            create_2 = nfclient.run_job(
                "netbox",
                "create_ip",
                workers="any",
                kwargs={
                    "prefix": "10.0.0.0/24",
                    "description": "foobar",
                    "role": "anycast",
                    "dry_run": True,
                },
            )
            print("create_1")
            pprint.pprint(create_1, width=200)
            print("create_2")
            pprint.pprint(create_2, width=200)

            worker, res1 = tuple(create_1.items())[0]
            worker, res2 = tuple(create_2.items())[0]

            assert res1["failed"] == False, "Allocation failed"
            assert res1["result"]["address"], "No ip allocated"
            assert res1["dry_run"] is False, "No dry run flag set to true"
            assert res1["status"] == "created", "Unexpected status"

            assert res2["failed"] == False, "Allocation failed"
            assert res2["result"]["address"], "No ip allocated"
            assert res2["dry_run"] is True, "No dry run flag set to true"
            assert res2["status"] == "unchanged", "Unexpected status"

    def test_create_ip_with_nb_instance(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        delete_ips("10.0.0.0/24", nfclient)

        if self.nb_version[0] == 4:
            create_1 = nfclient.run_job(
                "netbox",
                "create_ip",
                workers="any",
                kwargs={
                    "prefix": "10.0.0.0/24",
                    "description": "foobar",
                    "instance": "dev",
                },
            )
            print("create_1")
            pprint.pprint(create_1, width=200)

            worker, res1 = tuple(create_1.items())[0]

            assert res1["failed"] == False, "Allocation failed"
            assert res1["result"]["address"], "No ip allocated"
            assert res1["dry_run"] is False, "No dry run flag set to true"
            assert res1["status"] == "created", "Unexpected status"
            assert "dev" in res1["resources"]

    def test_create_ip_with_branch(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)
        delete_branch("create_ip_1", nfclient)
        delete_ips("10.0.0.0/24", nfclient)

        if self.nb_version[0] == 4:
            create_1 = nfclient.run_job(
                "netbox",
                "create_ip",
                workers="any",
                kwargs={
                    "prefix": "10.0.0.0/24",
                    "device": "fceos4",
                    "interface": "eth1",
                    "description": "foo1",
                    "vrf": "VRF1",
                    "tags": ["NORFAB", "ACCESS"],
                    "tenant": "NORFAB",
                    "dns_name": "foo1.lab.local",
                    "role": "anycast",
                    "comments": "Some comments",
                    "branch": "create_ip_1",
                },
            )
            print("create_1")
            pprint.pprint(create_1, width=200)

            worker, res1 = tuple(create_1.items())[0]

            assert res1["failed"] == False, "Allocation failed"
            assert res1["result"]["address"], "No ip allocated"
            assert (
                res1["result"]["branch"] == "create_ip_1"
            ), "No branch info in results"

    def test_create_ip_with_mask_len(self, nfclient):
        delete_prefixes_within("10.0.0.0/24", nfclient)
        delete_ips("10.0.0.0/24", nfclient)
        create_1 = nfclient.run_job(
            "netbox",
            "create_ip",
            workers="any",
            kwargs={
                "prefix": "10.0.0.0/24",
                "device": "fceos4",
                "interface": "Port-Channel1",
                "mask_len": 31,
            },
        )
        print("create_1")
        pprint.pprint(create_1, width=200)
        worker, res1 = tuple(create_1.items())[0]
        assert res1["result"]["address"] == "10.0.0.0/31", "Wrong ip allocated"

    def test_create_ip_with_mask_len_dry_run(self, nfclient):
        delete_prefixes_within("10.0.0.0/24", nfclient)
        delete_ips("10.0.0.0/24", nfclient)
        create_1 = nfclient.run_job(
            "netbox",
            "create_ip",
            workers="any",
            kwargs={
                "prefix": "10.0.0.0/24",
                "device": "fceos4",
                "interface": "Port-Channel1",
                "mask_len": 31,
                "dry_run": True,
            },
        )
        print("create_1")
        pprint.pprint(create_1, width=200)
        worker, res1 = tuple(create_1.items())[0]
        # dry run will allocate first ip within /24 as opposed to /31
        assert res1["result"]["address"] == "10.0.0.1/24", "Wrong ip allocated"

    def test_create_ip_check_create_peer_ip(self, nfclient):
        delete_prefixes_within("10.0.0.0/24", nfclient)
        delete_ips("10.0.0.0/24", nfclient)
        create_1 = nfclient.run_job(
            "netbox",
            "create_ip",
            workers="any",
            kwargs={
                "prefix": "10.0.0.0/24",
                "device": "fceos4",
                "interface": "Port-Channel1.101",
                "mask_len": 31,
            },
        )
        print("create_1")
        pprint.pprint(create_1, width=200)

        worker, res1 = tuple(create_1.items())[0]

        assert res1["result"]["address"] == "10.0.0.0/31", "Wrong ip allocated"
        assert (
            res1["result"]["peer"]["address"] == "10.0.0.1/31"
        ), "Wrong ip allocated for peer"
        assert (
            res1["result"]["peer"]["device"] == "fceos5"
        ), "Wrong ip allocated for peer"
        assert (
            res1["result"]["peer"]["interface"] == "ae5.101"
        ), "Wrong ip allocated for peer"

    def test_create_ip_check_create_peer_ip_with_branch(self, nfclient):
        delete_prefixes_within("10.0.0.0/24", nfclient)
        delete_ips("10.0.0.0/24", nfclient)
        delete_branch("create_ip_with_peer", nfclient)
        create_1 = nfclient.run_job(
            "netbox",
            "create_ip",
            workers="any",
            kwargs={
                "prefix": "10.0.0.0/24",
                "device": "fceos4",
                "interface": "Port-Channel1.101",
                "mask_len": 31,
                "branch": "create_ip_with_peer",
            },
        )
        print("create_1")
        pprint.pprint(create_1, width=200)

        worker, res1 = tuple(create_1.items())[0]

        assert res1["result"]["address"] == "10.0.0.0/31", "Wrong ip allocated"
        assert res1["result"]["branch"] == "create_ip_with_peer", "Wrong branch"
        assert (
            res1["result"]["peer"]["address"] == "10.0.0.1/31"
        ), "Wrong ip allocated for peer"
        assert (
            res1["result"]["peer"]["device"] == "fceos5"
        ), "Wrong ip allocated for peer"
        assert (
            res1["result"]["peer"]["interface"] == "ae5.101"
        ), "Wrong ip allocated for peer"

    def test_create_ip_check_skip_create_peer_ip(self, nfclient):
        delete_prefixes_within("10.0.0.0/24", nfclient)
        delete_ips("10.0.0.0/24", nfclient)
        create_1 = nfclient.run_job(
            "netbox",
            "create_ip",
            workers="any",
            kwargs={
                "prefix": "10.0.0.0/24",
                "device": "fceos4",
                "interface": "Port-Channel1.101",
                "mask_len": 31,
                "create_peer_ip": False,
            },
        )
        print("create_1")
        pprint.pprint(create_1, width=200)

        worker, res1 = tuple(create_1.items())[0]

        assert res1["result"]["address"] == "10.0.0.0/31", "Wrong ip allocated"
        assert (
            "peer" not in res1["result"]
        ), "SHould have been skipping peer ip creation"

    def test_create_ip_use_peer_ip(self, nfclient):
        delete_prefixes_within("10.0.0.0/24", nfclient)
        delete_ips("10.0.0.0/24", nfclient)
        create_1 = nfclient.run_job(
            "netbox",
            "create_ip",
            workers="any",
            kwargs={
                "prefix": "10.0.0.0/24",
                "device": "fceos4",
                "interface": "Port-Channel1.101",
                "mask_len": 31,
                "create_peer_ip": False,
            },
        )
        create_2 = nfclient.run_job(
            "netbox",
            "create_ip",
            workers="any",
            kwargs={
                "prefix": "10.0.0.0/24",
                "device": "fceos5",
                "interface": "ae5.101",
            },
        )
        print("create_1")
        pprint.pprint(create_1, width=200)
        print("create_2")
        pprint.pprint(create_2, width=200)

        worker, res1 = tuple(create_1.items())[0]
        worker, res2 = tuple(create_2.items())[0]

        assert res1["result"]["address"] == "10.0.0.0/31", "Wrong ip allocated"
        assert res2["result"]["address"] == "10.0.0.1/31", "Wrong ip allocated"

    def test_create_ip_with_link_peer_dry_run(self, nfclient):
        delete_prefixes_within("10.0.0.0/24", nfclient)
        delete_ips("10.0.0.0/24", nfclient)
        create_1 = nfclient.run_job(
            "netbox",
            "create_ip",
            workers="any",
            kwargs={
                "prefix": "10.0.0.0/24",
                "device": "fceos4",
                "interface": "Port-Channel1.101",
                "mask_len": 31,
            },
        )
        create_2 = nfclient.run_job(
            "netbox",
            "create_ip",
            workers="any",
            kwargs={
                "prefix": "10.0.0.0/24",
                "device": "fceos5",
                "interface": "ae5.101",
                "dry_run": True,
            },
        )
        print("create_1")
        pprint.pprint(create_1, width=200)
        print("create_2")
        pprint.pprint(create_2, width=200)

        worker, res1 = tuple(create_1.items())[0]
        worker, res2 = tuple(create_2.items())[0]

        assert res1["result"]["address"] == "10.0.0.0/31", "Wrong ip allocated"
        assert res2["result"]["address"] == "10.0.0.1/31", "Wrong ip allocated"

    def test_create_ip_with_link_peer_within_parent(self, nfclient):
        delete_prefixes_within("10.0.0.0/24", nfclient)
        delete_ips("10.0.0.0/24", nfclient)
        create_1 = nfclient.run_job(
            "netbox",
            "create_ip",
            workers="any",
            kwargs={
                "prefix": "10.0.0.0/24",
                "device": "fceos4",
                "interface": "Port-Channel1.101",
            },
        )
        create_2 = nfclient.run_job(
            "netbox",
            "create_ip",
            workers="any",
            kwargs={
                "prefix": "10.0.0.0/24",
                "device": "fceos5",
                "interface": "ae5.101",
            },
        )
        print("create_1")
        pprint.pprint(create_1, width=200)
        print("create_2")
        pprint.pprint(create_2, width=200)

        worker, res1 = tuple(create_1.items())[0]
        worker, res2 = tuple(create_2.items())[0]

        assert res1["result"]["address"] == "10.0.0.1/24", "Wrong ip allocated"
        assert res2["result"]["address"] == "10.0.0.2/24", "Wrong ip allocated"


@pytest.mark.task_create_prefix
class TestCreatePrefix:
    nb_version = None

    def test_create_prefix(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        delete_prefixes_within("10.1.0.0/24", nfclient)

        rand = random.randint(1, 1000)
        if self.nb_version[0] == 4:
            create_1 = nfclient.run_job(
                "netbox",
                "create_prefix",
                workers="any",
                kwargs={
                    "parent": "10.1.0.0/24",
                    "prefixlen": 30,
                    "description": f"test create prefix {rand}",
                },
            )
            create_2 = nfclient.run_job(
                "netbox",
                "create_prefix",
                workers="any",
                kwargs={
                    "parent": "10.1.0.0/24",
                    "prefixlen": 30,
                    "description": f"test create prefix {rand}",
                },
            )
            print("create_1")
            pprint.pprint(create_1, width=200)
            print("create_2")
            pprint.pprint(create_2, width=200)

            for worker, res1 in create_1.items():
                assert res1["failed"] == False, "Allocation failed"
                assert res1["result"][
                    "prefix"
                ], f"Result has no prefix {res1['result']}"

            worker, res2 = tuple(create_2.items())[0]
            assert (
                res1["result"]["prefix"] == res2["result"]["prefix"]
            ), "Should have been same prefix"
            assert (
                res1["result"]["description"] == res2["result"]["description"]
            ), "Should have been same prefix description"

    def test_create_prefix_multiple(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        delete_prefixes_within("10.1.0.0/24", nfclient)

        if self.nb_version[0] == 4:
            create_1 = nfclient.run_job(
                "netbox",
                "create_prefix",
                workers="any",
                kwargs={
                    "parent": "10.1.0.0/24",
                    "prefixlen": 30,
                    "description": f"test create prefix {random.randint(1, 100)}",
                },
            )
            create_2 = nfclient.run_job(
                "netbox",
                "create_prefix",
                workers="any",
                kwargs={
                    "parent": "10.1.0.0/24",
                    "prefixlen": 30,
                    "description": f"test create prefix {random.randint(200, 300)}",
                },
            )
            print("create_1")
            pprint.pprint(create_1, width=200)
            print("create_2")
            pprint.pprint(create_2, width=200)

            for worker, res1 in create_1.items():
                assert res1["failed"] == False, "Allocation failed"
                assert res1["result"][
                    "prefix"
                ], f"Result has no prefix {res1['result']}"

            worker, res2 = tuple(create_2.items())[0]
            assert (
                res1["result"]["prefix"] != res2["result"]["prefix"]
            ), "Should have been different prefix"

    def test_create_prefix_non_exist_parent(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        if self.nb_version[0] == 4:
            create_1 = nfclient.run_job(
                "netbox",
                "create_prefix",
                workers="any",
                kwargs={
                    "parent": "10.1.123.0/24",
                    "prefixlen": 30,
                    "description": f"test create prefix {random.randint(1, 100)}",
                },
            )
            print("create_1")
            pprint.pprint(create_1, width=200)

            for worker, res1 in create_1.items():
                assert res1["failed"] == True, "Allocation not failed"
                assert (
                    "Unable to source parent prefix from Netbox" in res1["messages"][0]
                ), "Result has no errors"

    def test_create_prefix_with_vrf(self, nfclient):
        """Should create single prefix and handle deduplication within vrf"""
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        delete_prefixes_within("10.2.0.0/24", nfclient)

        rand = random.randint(1, 1000)
        if self.nb_version[0] == 4:
            create_1 = nfclient.run_job(
                "netbox",
                "create_prefix",
                workers="any",
                kwargs={
                    "parent": "10.2.0.0/24",
                    "prefixlen": 30,
                    "description": f"test create prefix {rand}",
                    "vrf": "VRF1",
                },
            )
            create_2 = nfclient.run_job(
                "netbox",
                "create_prefix",
                workers="any",
                kwargs={
                    "parent": "10.2.0.0/24",
                    "prefixlen": 30,
                    "description": f"test create prefix {rand}",
                    "vrf": "VRF1",
                },
            )
            create_3 = nfclient.run_job(
                "netbox",
                "create_prefix",
                workers="any",
                kwargs={
                    "parent": "10.2.0.0/24",
                    "prefixlen": 30,
                    "description": f"test create prefix {rand+1}",
                    "vrf": "VRF1",
                },
            )
            print("create_1")
            pprint.pprint(create_1, width=200)
            print("create_2")
            pprint.pprint(create_2, width=200)
            print("create_3")
            pprint.pprint(create_3, width=200)

            for worker, res1 in create_1.items():
                assert res1["failed"] == False, "Allocation failed"
                assert res1["result"][
                    "prefix"
                ], f"Result has no prefix {res1['result']}"

            worker, res1 = tuple(create_1.items())[0]
            worker, res2 = tuple(create_2.items())[0]
            worker, res3 = tuple(create_3.items())[0]
            assert (
                res1["result"]["prefix"] == res2["result"]["prefix"]
            ), "Should have been same prefix"
            assert (
                res1["result"]["prefix"] != res3["result"]["prefix"]
            ), "Should have been different prefix"

    def test_create_prefix_with_parent_vrf_mismatch(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        delete_prefixes_within("10.1.0.0/24", nfclient)

        rand = random.randint(1, 1000)
        if self.nb_version[0] == 4:
            create_1 = nfclient.run_job(
                "netbox",
                "create_prefix",
                workers="any",
                kwargs={
                    "parent": "10.1.0.0/24",
                    "prefixlen": 30,
                    "description": f"test create prefix {rand}",
                    "vrf": "VRF1",
                },
            )
            print("create_1")
            pprint.pprint(create_1, width=200)

            for worker, res1 in create_1.items():
                assert res1["failed"] == True, "Allocation not failed"
                assert "NetboxAllocationError" in res1["errors"][0]

    def test_create_prefix_by_parent_prefix_name(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        delete_prefixes_within("10.1.0.0/24", nfclient)

        rand = random.randint(1, 1000)
        if self.nb_version[0] == 4:
            create_1 = nfclient.run_job(
                "netbox",
                "create_prefix",
                workers="any",
                kwargs={
                    "parent": "TEST CREATE PREFIXES",
                    "prefixlen": 30,
                    "description": f"test create prefix {rand}",
                },
            )
            create_2 = nfclient.run_job(
                "netbox",
                "create_prefix",
                workers="any",
                kwargs={
                    "parent": "TEST CREATE PREFIXES",
                    "prefixlen": 30,
                    "description": f"test create prefix {rand}",
                },
            )
            print("create_1")
            pprint.pprint(create_1, width=200)
            print("create_2")
            pprint.pprint(create_2, width=200)

            for worker, res1 in create_1.items():
                assert res1["failed"] == False, "Allocation failed"
                assert res1["result"][
                    "prefix"
                ], f"Result has no prefix {res1['result']}"

            worker, res2 = tuple(create_2.items())[0]
            assert (
                res1["result"]["prefix"] == res2["result"]["prefix"]
            ), "Should have been same prefix"
            assert (
                res1["result"]["description"] == res2["result"]["description"]
            ), "Should have been same prefix description"

    def test_create_prefix_by_parent_prefix_dictionary(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        delete_prefixes_within("10.1.0.0/24", nfclient)

        rand = random.randint(1, 1000)
        if self.nb_version[0] == 4:
            create_1 = nfclient.run_job(
                "netbox",
                "create_prefix",
                workers="any",
                kwargs={
                    "parent": {"description": "TEST CREATE PREFIXES"},
                    "prefixlen": 30,
                    "description": f"test create prefix {rand}",
                },
            )
            create_2 = nfclient.run_job(
                "netbox",
                "create_prefix",
                workers="any",
                kwargs={
                    "parent": {"description": "TEST CREATE PREFIXES"},
                    "prefixlen": 30,
                    "description": f"test create prefix {rand}",
                },
            )
            print("create_1")
            pprint.pprint(create_1, width=200)
            print("create_2")
            pprint.pprint(create_2, width=200)

            for worker, res1 in create_1.items():
                assert res1["failed"] == False, "Allocation failed"
                assert res1["result"][
                    "prefix"
                ], f"Result has no prefix {res1['result']}"

            worker, res2 = tuple(create_2.items())[0]
            assert (
                res1["result"]["prefix"] == res2["result"]["prefix"]
            ), "Should have been same prefix"
            assert (
                res1["result"]["description"] == res2["result"]["description"]
            ), "Should have been same prefix description"

    def test_create_prefix_within_vrf_by_parent_prefix_name(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        delete_prefixes_within("10.2.0.0/24", nfclient)

        rand = random.randint(1, 1000)
        if self.nb_version[0] == 4:
            create_1 = nfclient.run_job(
                "netbox",
                "create_prefix",
                workers="any",
                kwargs={
                    "parent": "TEST CREATE PREFIXES WITH VRF",
                    "prefixlen": 30,
                    "description": f"test create prefix {rand}",
                    "vrf": "VRF1",
                },
            )
            create_2 = nfclient.run_job(
                "netbox",
                "create_prefix",
                workers="any",
                kwargs={
                    "parent": "TEST CREATE PREFIXES WITH VRF",
                    "prefixlen": 30,
                    "description": f"test create prefix {rand}",
                    "vrf": "VRF1",
                },
            )
            create_3 = nfclient.run_job(
                "netbox",
                "create_prefix",
                workers="any",
                kwargs={
                    "parent": "TEST CREATE PREFIXES WITH VRF",
                    "prefixlen": 30,
                    "description": f"test create prefix {rand+1}",
                    "vrf": "VRF1",
                },
            )
            print("create_1")
            pprint.pprint(create_1, width=200)
            print("create_2")
            pprint.pprint(create_2, width=200)
            print("create_3")
            pprint.pprint(create_3, width=200)

            for worker, res1 in create_1.items():
                assert res1["failed"] == False, "Allocation failed"
                assert res1["result"][
                    "prefix"
                ], f"Result has no prefix {res1['result']}"

            worker, res1 = tuple(create_1.items())[0]
            worker, res2 = tuple(create_2.items())[0]
            worker, res3 = tuple(create_3.items())[0]

            assert (
                res1["result"]["prefix"] == res2["result"]["prefix"]
            ), "Should have been same prefix"
            assert (
                res1["result"]["description"] == res2["result"]["description"]
            ), "Should have been same prefix description"
            assert (
                res1["result"]["prefix"] != res3["result"]["prefix"]
            ), "Should have been different prefix"

    def test_create_prefix_dry_run_empty_parent(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        delete_prefixes_within("10.1.0.0/24", nfclient)

        rand = random.randint(1, 1000)
        if self.nb_version[0] == 4:
            create_1 = nfclient.run_job(
                "netbox",
                "create_prefix",
                workers="any",
                kwargs={
                    "parent": "10.1.0.0/24",
                    "prefixlen": 30,
                    "description": f"test create prefix {rand}",
                    "dry_run": True,
                },
            )
            print("create_1")
            pprint.pprint(create_1, width=200)

            for worker, res1 in create_1.items():
                assert res1["failed"] == False, "Allocation failed"
                assert res1["dry_run"] == True
                assert res1["status"] == "unchanged"
                assert res1["result"]["prefix"] == "10.1.0.0/30"

    def test_create_prefix_dry_run_parent_has_children(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        delete_prefixes_within("10.1.0.0/24", nfclient)

        rand = random.randint(1, 1000)
        if self.nb_version[0] == 4:
            create_1 = nfclient.run_job(
                "netbox",
                "create_prefix",
                workers="any",
                kwargs={
                    "parent": "10.1.0.0/24",
                    "prefixlen": 31,
                    "description": f"test create prefix {rand}",
                },
            )
            create_dry_run = nfclient.run_job(
                "netbox",
                "create_prefix",
                workers="any",
                kwargs={
                    "parent": "10.1.0.0/24",
                    "prefixlen": 30,
                    "description": f"test create prefix {rand+1}",
                    "dry_run": True,
                },
            )
            print("create_dry_run")
            pprint.pprint(create_dry_run, width=200)

            for worker, res1 in create_dry_run.items():
                assert res1["failed"] == False, "Allocation failed"
                assert res1["dry_run"] == True
                assert res1["status"] == "unchanged"
                assert res1["result"]["prefix"] == "10.1.0.4/30"

    def test_create_prefix_dry_run_prefix_exists(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        delete_prefixes_within("10.1.0.0/24", nfclient)

        rand = random.randint(1, 1000)
        if self.nb_version[0] == 4:
            create_1 = nfclient.run_job(
                "netbox",
                "create_prefix",
                workers="any",
                kwargs={
                    "parent": "10.1.0.0/24",
                    "prefixlen": 30,
                    "description": f"test create prefix {rand}",
                },
            )
            create_dry_run = nfclient.run_job(
                "netbox",
                "create_prefix",
                workers="any",
                kwargs={
                    "parent": "10.1.0.0/24",
                    "prefixlen": 30,
                    "description": f"test create prefix {rand}",
                    "dry_run": True,
                },
            )
            print("create_dry_run")
            pprint.pprint(create_dry_run, width=200)

            for worker, res1 in create_dry_run.items():
                assert res1["failed"] == False, "Allocation failed"
                assert res1["dry_run"] == True
                assert res1["status"] == "unchanged"
                assert res1["result"]["prefix"] == "10.1.0.0/30"

    def test_create_prefix_test_length_mismatch(self, nfclient):
        """We creating first prefix, next creating prefix with same
        description but different prefix length"""
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        delete_prefixes_within("10.1.0.0/24", nfclient)

        rand = random.randint(1, 1000)
        if self.nb_version[0] == 4:
            create_1 = nfclient.run_job(
                "netbox",
                "create_prefix",
                workers="any",
                kwargs={
                    "parent": "10.1.0.0/24",
                    "prefixlen": 31,
                    "description": f"test create prefix {rand}",
                },
            )
            create_2 = nfclient.run_job(
                "netbox",
                "create_prefix",
                workers="any",
                kwargs={
                    "parent": "10.1.0.0/24",
                    "prefixlen": 30,
                    "description": f"test create prefix {rand}",
                },
            )
            print("create_1")
            pprint.pprint(create_1, width=200)
            print("create_2")
            pprint.pprint(create_2, width=200)

            for worker, res in create_2.items():
                assert res["failed"] == True, "Allocation not failed"
                assert "NetboxAllocationError" in res["errors"][0]

    def test_create_prefix_with_attributes(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        delete_prefixes_within("10.2.0.0/24", nfclient)

        rand = random.randint(1, 1000)
        if self.nb_version[0] == 4:
            create_1 = nfclient.run_job(
                "netbox",
                "create_prefix",
                workers="any",
                kwargs={
                    "parent": "10.2.0.0/24",
                    "prefixlen": 30,
                    "description": f"test create prefix {rand}",
                    "site": "NORFAB-LAB",
                    "tenant": "NORFAB",
                    "role": "PREFIX_ROLE_1",
                    "comments": "Some important comment",
                    "vrf": "VRF1",
                    "tags": ["NORFAB"],
                    "status": "reserved",
                },
            )
            print("create_1")
            pprint.pprint(create_1, width=200)

            for worker, res1 in create_1.items():
                assert res1["failed"] == False, "Allocation failed"
                assert all(
                    k in res1["diff"]
                    for k in [
                        "comments",
                        "description",
                        "role",
                        "site",
                        "status",
                        "tags",
                        "tenant",
                    ]
                )

            # retrieve created prefix details from Netbox
            nb_prefix = nfclient.run_job(
                "netbox",
                "rest",
                workers="any",
                kwargs={
                    "method": "get",
                    "api": "/ipam/prefixes/",
                    "params": {"prefix": res1["result"]["prefix"]},
                },
            )
            print("nb_prefix:")
            pprint.pprint(nb_prefix, width=200)
            worker, created_prefix = tuple(nb_prefix.items())[0]
            created_prefix = created_prefix["result"]["results"][0]

            assert created_prefix["role"]["name"] == "PREFIX_ROLE_1"
            assert created_prefix["scope"]["name"] == "NORFAB-LAB"
            assert created_prefix["tags"][0]["name"] == "NORFAB"
            assert created_prefix["tenant"]["name"] == "NORFAB"
            assert created_prefix["vrf"]["name"] == "VRF1"
            assert created_prefix["description"]
            assert created_prefix["comments"]

    def test_create_prefix_with_attributes_updates(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        delete_prefixes_within("10.2.0.0/24", nfclient)

        rand = random.randint(1, 1000)
        if self.nb_version[0] == 4:
            create_1 = nfclient.run_job(
                "netbox",
                "create_prefix",
                workers="any",
                kwargs={
                    "parent": "10.2.0.0/24",
                    "prefixlen": 30,
                    "description": f"test create prefix {rand}",
                    "site": "NORFAB-LAB",
                    "tenant": "NORFAB",
                    "role": "PREFIX_ROLE_1",
                    "comments": "Some important comment",
                    "tags": ["NORFAB"],
                    "status": "reserved",
                },
            )
            create_2 = nfclient.run_job(
                "netbox",
                "create_prefix",
                workers="any",
                kwargs={
                    "parent": "10.2.0.0/24",
                    "description": f"test create prefix {rand}",
                    "site": "SALTNORNIR-LAB",
                    "tenant": "SALTNORNIR",
                    "role": "PREFIX_ROLE_2",
                    "comments": "Some important comments updates",
                    "tags": ["ACCESS"],
                    "status": "active",
                },
            )
            print("create_1")
            pprint.pprint(create_1, width=200)
            print("create_2")
            pprint.pprint(create_2, width=200)

            # verify has changes
            for worker, res1 in create_2.items():
                assert res1["failed"] == False, "Allocation failed"
                assert all(
                    k in res1["diff"]
                    for k in [
                        "comments",
                        "role",
                        "site",
                        "status",
                        "tags",
                        "tenant",
                    ]
                )

            # retrieve created prefix details from Netbox
            nb_prefix = nfclient.run_job(
                "netbox",
                "rest",
                workers="any",
                kwargs={
                    "method": "get",
                    "api": "/ipam/prefixes/",
                    "params": {"prefix": res1["result"]["prefix"]},
                },
            )
            print("nb_prefix:")
            pprint.pprint(nb_prefix, width=200)
            worker, created_prefix = tuple(nb_prefix.items())[0]
            created_prefix = created_prefix["result"]["results"][0]

            assert created_prefix["role"]["name"] == "PREFIX_ROLE_2"
            assert created_prefix["scope"]["name"] == "SALTNORNIR-LAB"
            for tag in created_prefix["tags"]:
                assert tag["name"] == "NORFAB" or tag["name"] == "ACCESS"
            assert created_prefix["tenant"]["name"] == "SALTNORNIR"
            assert created_prefix["vrf"]["name"] == "VRF1"
            assert created_prefix["description"] == f"test create prefix {rand}"
            assert created_prefix["comments"] == "Some important comments updates"

    def test_create_prefix_with_branch(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        delete_branch("create_prefix_1", nfclient)
        delete_prefixes_within("10.2.0.0/24", nfclient)

        rand = random.randint(1, 1000)
        if self.nb_version[0] == 4:
            create_1 = nfclient.run_job(
                "netbox",
                "create_prefix",
                workers="any",
                kwargs={
                    "parent": "10.2.0.0/24",
                    "prefixlen": 30,
                    "description": f"test create prefix {rand}",
                    "site": "NORFAB-LAB",
                    "tenant": "NORFAB",
                    "role": "PREFIX_ROLE_1",
                    "comments": "Some important comment",
                    "vrf": "VRF1",
                    "tags": ["NORFAB"],
                    "status": "reserved",
                    "branch": "create_prefix_1",
                },
            )
            print("create_1")
            pprint.pprint(create_1, width=200)

            for worker, res1 in create_1.items():
                assert res1["failed"] == False, "Allocation with branch failed"
                assert (
                    res1["result"]["branch"] == "create_prefix_1"
                ), "No branch details in result"


@pytest.mark.task_create_ip_bulk
class TestCreateIPBulk:
    nb_version = None

    def test_create_ip_bulk(self, nfclient):
        delete_prefixes_within("10.0.0.0/24", nfclient)
        delete_ips("10.0.0.0/24", nfclient)
        create_1 = nfclient.run_job(
            "netbox",
            "create_ip_bulk",
            workers="any",
            kwargs={
                "prefix": "10.0.0.0/24",
                "devices": ["fceos4", "fceos5"],
                "interface_regex": "eth103.0|eth11.123|Port-Channel1.101|ae5.101",
                "mask_len": 31,
            },
        )
        print("create_1")
        pprint.pprint(create_1, width=200)

        for worker, res1 in create_1.items():
            assert res1["failed"] == False, "Allocation failed"
            assert res1["result"] == {
                "fceos4": {
                    "Port-Channel1.101": {
                        "address": "10.0.0.0/31",
                        "description": "",
                        "device": "fceos4",
                        "interface": "Port-Channel1.101",
                        "peer": {
                            "address": "10.0.0.1/31",
                            "description": "",
                            "device": "fceos5",
                            "interface": "ae5.101",
                            "vrf": "None",
                        },
                        "vrf": "None",
                    },
                    "eth103.0": {
                        "address": "10.0.0.2/31",
                        "description": "",
                        "device": "fceos4",
                        "interface": "eth103.0",
                        "peer": {
                            "address": "10.0.0.3/31",
                            "description": "",
                            "device": "fceos5",
                            "interface": "eth103",
                            "vrf": "None",
                        },
                        "vrf": "None",
                    },
                    "eth11.123": {
                        "address": "10.0.0.4/31",
                        "description": "",
                        "device": "fceos4",
                        "interface": "eth11.123",
                        "peer": {
                            "address": "10.0.0.5/31",
                            "description": "",
                            "device": "fceos5",
                            "interface": "eth11.123",
                            "vrf": "None",
                        },
                        "vrf": "None",
                    },
                },
                "fceos5": {
                    "ae5.101": {
                        "address": "10.0.0.1/31",
                        "description": "",
                        "device": "fceos5",
                        "interface": "ae5.101",
                        "vrf": "None",
                    },
                    "eth11.123": {
                        "address": "10.0.0.5/31",
                        "description": "",
                        "device": "fceos5",
                        "interface": "eth11.123",
                        "vrf": "None",
                    },
                },
            }
