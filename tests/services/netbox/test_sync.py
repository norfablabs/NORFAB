import pprint

import pytest

try:
    from tests.services.netbox.common import (
        delete_all_mac_addresses,
        delete_branch,
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
        delete_all_mac_addresses,
        delete_branch,
        get_pynetbox,
    )

pytestmark = [pytest.mark.netbox, pytest.mark.sync]


@pytest.mark.task_sync_mac_addresses
class TestSyncMacAddresses:
    # MAC addresses present in interfaces_parse_data.json per device:
    #   ceos-spine-1  : 02:00:00:11:00:09 on Ethernet9  (description TEST_SYNC_ROUTED_WITH_MAC)
    #   ceos-spine-2  : 02:00:00:12:00:09 on Ethernet9  (description TEST_SYNC_ROUTED_WITH_MAC)
    #   ceos-leaf-1   : 12:34:12:34:12:34 on Ethernet1  (description P2P to ceos-spine-1 Ethernet2)
    #                   02:00:00:01:00:06 on Ethernet6  (description TEST_SYNC_ROUTED_WITH_MAC)
    #   ceos-leaf-2   : 02:00:00:02:00:06 on Ethernet6  (description TEST_SYNC_ROUTED_WITH_MAC)
    #   ceos-leaf-3   : 02:00:00:03:00:06 on Ethernet6  (description TEST_SYNC_ROUTED_WITH_MAC)

    ALL_DEVICES = [
        "ceos-spine-1",
        "ceos-spine-2",
        "ceos-leaf-1",
        "ceos-leaf-2",
        "ceos-leaf-3",
    ]
    SPINE_DEVICES = ["ceos-spine-1", "ceos-spine-2"]
    RESULT_KEYS = {"created", "updated", "in_sync"}

    # MAC addresses per device from parse data
    SPINE1_MAC = "02:00:00:11:00:09"
    SPINE1_INTF = "Ethernet9"
    SPINE2_MAC = "02:00:00:12:00:09"
    SPINE2_INTF = "Ethernet9"
    LEAF1_MAC_ETH1 = "12:34:12:34:12:34"
    LEAF1_INTF_ETH1 = "Ethernet1"
    LEAF1_MAC_ETH6 = "02:00:00:01:00:06"
    LEAF1_INTF_ETH6 = "Ethernet6"
    LEAF2_MAC = "02:00:00:02:00:06"
    LEAF2_INTF = "Ethernet6"
    LEAF3_MAC = "02:00:00:03:00:06"
    LEAF3_INTF = "Ethernet6"

    # All TEST_SYNC_ROUTED_WITH_MAC MACs (description matches TEST_SYNC_*)
    TEST_SYNC_MACS = {
        "02:00:00:11:00:09",
        "02:00:00:12:00:09",
        "02:00:00:01:00:06",
        "02:00:00:02:00:06",
        "02:00:00:03:00:06",
    }

    # ------------------------------------------------------------------ #
    # Class-level helpers                                                  #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _cleanup(nfclient, devices):
        """Delete all MAC addresses assigned to any interface on the given devices."""
        delete_all_mac_addresses(nfclient, devices)

    @staticmethod
    def _sync(nfclient, devices, **extra_kwargs):
        """Run sync_mac_addresses and return the result dict."""
        return nfclient.run_job(
            "netbox",
            "sync_mac_addresses",
            workers="any",
            kwargs={"devices": devices, **extra_kwargs},
        )

    @staticmethod
    def _get_intf_id(nfclient, device, name):
        """Return the NetBox ID of the given device interface."""
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
    def _create_nb_mac(nfclient, mac, intf_id=None):
        """Create a MAC address entry in NetBox, optionally assigned to an interface."""
        payload = {"mac_address": mac}
        if intf_id is not None:
            payload["assigned_object_type"] = "dcim.interface"
            payload["assigned_object_id"] = intf_id
        nfclient.run_job(
            "netbox",
            "rest",
            workers="any",
            kwargs={
                "method": "post",
                "api": "/dcim/mac-addresses/",
                "json": payload,
            },
        )

    @staticmethod
    def _get_nb_macs(nfclient, device, interface):
        """Return a list of pynetbox MAC address records for the given device interface."""
        pynb = get_pynetbox(nfclient)
        return list(pynb.dcim.mac_addresses.filter(device=device, interface=interface))

    # ------------------------------------------------------------------ #
    # Basic smoke tests                                                    #
    # ------------------------------------------------------------------ #

    def test_sync_mac_addresses(self, nfclient):
        """Clean MACs from both spines then sync. Both spine MACs must be created;
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
                ], f"{worker}:{device} no MACs created after cleanup"

    def test_sync_mac_addresses_all_devices(self, nfclient):
        """Clean MACs from all 5 devices then sync. Each device must have at least
        one MAC created."""
        self._cleanup(nfclient, self.ALL_DEVICES)

        ret = self._sync(nfclient, self.ALL_DEVICES)
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            for device in self.ALL_DEVICES:
                assert (
                    device in res["result"]
                ), f"{worker} returned no result for {device}"
            for device, device_data in res["result"].items():
                assert (
                    self.RESULT_KEYS <= device_data.keys()
                ), f"{worker}:{device} missing keys in result"
                assert device_data[
                    "created"
                ], f"{worker}:{device} no MACs created after cleanup"

    def test_sync_mac_addresses_dry_run(self, nfclient):
        """Clean MACs from both spines then dry_run. Result keys must be the same
        RESULT_KEYS and 'created' must be non-empty (no actual NB writes)."""
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

        # Verify dry-run made no writes - MACs must still be absent from NetBox
        pynb = get_pynetbox(nfclient)
        macs_in_nb = list(
            pynb.dcim.mac_addresses.filter(
                mac_address=[self.SPINE1_MAC, self.SPINE2_MAC]
            )
        )
        assert (
            not macs_in_nb
        ), f"dry-run wrote MACs to NetBox: {[m.mac_address for m in macs_in_nb]}"

    def test_sync_mac_addresses_already_in_sync(self, nfclient):
        """Sync spines, then sync again. The second run must report all MACs as
        in_sync with nothing created or updated."""
        self._cleanup(nfclient, self.SPINE_DEVICES)

        # First sync: create MACs
        setup = self._sync(nfclient, self.SPINE_DEVICES)
        for worker, res in setup.items():
            assert not res["failed"], f"Setup sync failed for {worker}: {res['errors']}"
            assert res["result"]["ceos-spine-1"][
                "created"
            ], f"{worker} no MACs created during setup sync"

        # Second sync: everything must be in_sync
        ret = self._sync(nfclient, self.SPINE_DEVICES)
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            for device, device_data in res["result"].items():
                assert not device_data[
                    "created"
                ], f"{worker}:{device} unexpected creates on second sync: {device_data['created']}"
                assert not device_data[
                    "updated"
                ], f"{worker}:{device} unexpected updates on second sync: {device_data['updated']}"
                assert device_data[
                    "in_sync"
                ], f"{worker}:{device} in_sync list empty on second sync"

    # ------------------------------------------------------------------ #
    # Create scenarios                                                     #
    # ------------------------------------------------------------------ #

    def test_sync_mac_addresses_create(self, nfclient):
        """Clean MACs from spine-1 then sync. Verify the MAC on Ethernet9 is created
        and the NetBox record matches the expected MAC value and interface assignment.
        """
        self._cleanup(nfclient, ["ceos-spine-1"])

        ret = self._sync(nfclient, ["ceos-spine-1"])
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            device_data = res["result"]["ceos-spine-1"]
            assert (
                self.SPINE1_MAC in device_data["created"]
            ), f"{worker} {self.SPINE1_MAC} not in created list"

        # Validate the MAC record in NetBox
        nb_macs = self._get_nb_macs(nfclient, "ceos-spine-1", self.SPINE1_INTF)
        assert (
            nb_macs
        ), f"{self.SPINE1_MAC} not found in NetBox for ceos-spine-1:{self.SPINE1_INTF}"
        mac_values = [m.mac_address.lower() for m in nb_macs]
        assert (
            self.SPINE1_MAC in mac_values
        ), f"Expected MAC {self.SPINE1_MAC} not found in NetBox; got {mac_values}"
        nb_mac = next(m for m in nb_macs if m.mac_address.lower() == self.SPINE1_MAC)
        assert (
            nb_mac.assigned_object is not None
        ), f"{self.SPINE1_MAC} has no assigned_object in NetBox"
        assert (
            nb_mac.assigned_object.name == self.SPINE1_INTF
        ), f"{self.SPINE1_MAC} assigned to wrong interface: got {nb_mac.assigned_object.name!r}"

    def test_sync_mac_addresses_create_leaf1_two_macs(self, nfclient):
        """ceos-leaf-1 has two interfaces with MACs in live data (Ethernet1 and Ethernet6).
        Clean all leaf-1 MACs then sync. Both MACs must be created and correctly assigned.
        """
        self._cleanup(nfclient, ["ceos-leaf-1"])

        ret = self._sync(nfclient, ["ceos-leaf-1"])
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            device_data = res["result"]["ceos-leaf-1"]
            assert (
                self.LEAF1_MAC_ETH1 in device_data["created"]
            ), f"{worker} {self.LEAF1_MAC_ETH1} not in created list"
            assert (
                self.LEAF1_MAC_ETH6 in device_data["created"]
            ), f"{worker} {self.LEAF1_MAC_ETH6} not in created list"

        # Validate Ethernet1 MAC record
        nb_macs_eth1 = self._get_nb_macs(nfclient, "ceos-leaf-1", self.LEAF1_INTF_ETH1)
        assert (
            nb_macs_eth1
        ), f"{self.LEAF1_MAC_ETH1} not found in NetBox for ceos-leaf-1:{self.LEAF1_INTF_ETH1}"
        assert any(
            m.mac_address.lower() == self.LEAF1_MAC_ETH1 for m in nb_macs_eth1
        ), f"Expected MAC {self.LEAF1_MAC_ETH1} not found on ceos-leaf-1:{self.LEAF1_INTF_ETH1}"

        # Validate Ethernet6 MAC record
        nb_macs_eth6 = self._get_nb_macs(nfclient, "ceos-leaf-1", self.LEAF1_INTF_ETH6)
        assert (
            nb_macs_eth6
        ), f"{self.LEAF1_MAC_ETH6} not found in NetBox for ceos-leaf-1:{self.LEAF1_INTF_ETH6}"
        assert any(
            m.mac_address.lower() == self.LEAF1_MAC_ETH6 for m in nb_macs_eth6
        ), f"Expected MAC {self.LEAF1_MAC_ETH6} not found on ceos-leaf-1:{self.LEAF1_INTF_ETH6}"

    # ------------------------------------------------------------------ #
    # Update scenarios                                                     #
    # ------------------------------------------------------------------ #

    def test_sync_mac_addresses_update_unassigned(self, nfclient):
        """Pre-create the spine-1 MAC in NetBox without assigning it to any interface,
        then sync. The MAC must be updated (assigned to Ethernet9) rather than created.
        """
        self._cleanup(nfclient, ["ceos-spine-1"])

        # Pre-create MAC unassigned (no assigned_object_id)
        self._create_nb_mac(nfclient, self.SPINE1_MAC, intf_id=None)

        ret = self._sync(nfclient, ["ceos-spine-1"])
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            device_data = res["result"]["ceos-spine-1"]
            assert (
                self.SPINE1_MAC in device_data["updated"]
            ), f"{worker} {self.SPINE1_MAC} not in updated list - expected update of unassigned MAC"
            assert (
                self.SPINE1_MAC not in device_data["created"]
            ), f"{worker} {self.SPINE1_MAC} incorrectly listed as created"

        # Validate the MAC is now assigned to the correct interface
        nb_macs = self._get_nb_macs(nfclient, "ceos-spine-1", self.SPINE1_INTF)
        assert (
            nb_macs
        ), f"{self.SPINE1_MAC} not found on ceos-spine-1:{self.SPINE1_INTF} after update"
        nb_mac = next(
            (m for m in nb_macs if m.mac_address.lower() == self.SPINE1_MAC), None
        )
        assert (
            nb_mac is not None
        ), f"{self.SPINE1_MAC} value not found on ceos-spine-1:{self.SPINE1_INTF}"
        assert (
            nb_mac.assigned_object is not None
        ), f"{self.SPINE1_MAC} still has no assigned_object after update"
        assert (
            nb_mac.assigned_object.name == self.SPINE1_INTF
        ), f"{self.SPINE1_MAC} assigned to wrong interface after update: got {nb_mac.assigned_object.name!r}"

    def test_sync_mac_addresses_update_unassigned_dry_run(self, nfclient):
        """Pre-create spine-1 MAC unassigned in NB. Dry-run sync must list it under
        'updated', and the MAC must remain unassigned after the dry-run."""
        self._cleanup(nfclient, ["ceos-spine-1"])
        self._create_nb_mac(nfclient, self.SPINE1_MAC, intf_id=None)

        ret = self._sync(nfclient, ["ceos-spine-1"], dry_run=True)
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            device_data = res["result"]["ceos-spine-1"]
            assert (
                self.SPINE1_MAC in device_data["updated"]
            ), f"{worker} {self.SPINE1_MAC} not in updated list for dry-run"

        # Dry-run must not have made any changes - MAC must remain unassigned
        pynb = get_pynetbox(nfclient)
        nb_entry = pynb.dcim.mac_addresses.get(mac_address=self.SPINE1_MAC)
        assert nb_entry is not None, f"{self.SPINE1_MAC} gone from NetBox after dry-run"
        assert (
            nb_entry.assigned_object is None
        ), f"Dry-run unexpectedly assigned {self.SPINE1_MAC} to {nb_entry.assigned_object!r}"

    # ------------------------------------------------------------------ #
    # Duplicate MAC scenarios                                              #
    # ------------------------------------------------------------------ #

    def test_sync_mac_addresses_duplicate_mac_different_interface(self, nfclient):
        """Pre-assign the spine-1 MAC to a different interface (Ethernet1) in NetBox,
        then run sync. The sync must report an error because the MAC is already
        assigned to a different interface, and must NOT create or update the MAC."""
        self._cleanup(nfclient, ["ceos-spine-1"])

        # Assign the MAC to a *different* interface (Ethernet1, not Ethernet9)
        intf_id = self._get_intf_id(nfclient, "ceos-spine-1", "Ethernet1")
        self._create_nb_mac(nfclient, self.SPINE1_MAC, intf_id=intf_id)

        ret = self._sync(nfclient, ["ceos-spine-1"])
        pprint.pprint(ret)
        for worker, res in ret.items():
            # Errors must be reported for the conflicting MAC
            assert (
                len(res["errors"]) > 0
            ), f"{worker} expected errors for MAC assigned to different interface, got none"
            device_data = res["result"]["ceos-spine-1"]
            # The MAC must NOT appear in created or updated
            assert (
                self.SPINE1_MAC not in device_data["created"]
            ), f"{worker} {self.SPINE1_MAC} incorrectly created despite interface conflict"
            assert (
                self.SPINE1_MAC not in device_data["updated"]
            ), f"{worker} {self.SPINE1_MAC} incorrectly updated despite interface conflict"

        # Validate the MAC is still assigned to Ethernet1 (not moved to Ethernet9)
        nb_macs_eth1 = self._get_nb_macs(nfclient, "ceos-spine-1", "Ethernet1")
        assert any(
            m.mac_address.lower() == self.SPINE1_MAC for m in nb_macs_eth1
        ), f"{self.SPINE1_MAC} no longer on ceos-spine-1:Ethernet1 after conflict sync"
        nb_macs_eth9 = self._get_nb_macs(nfclient, "ceos-spine-1", self.SPINE1_INTF)
        assert not any(
            m.mac_address.lower() == self.SPINE1_MAC for m in nb_macs_eth9
        ), f"{self.SPINE1_MAC} was incorrectly duplicated onto ceos-spine-1:{self.SPINE1_INTF}"

        # Cleanup
        self._cleanup(nfclient, ["ceos-spine-1"])

    def test_sync_mac_addresses_duplicate_mac_same_interface(self, nfclient):
        """Pre-assign the spine-2 MAC to the correct interface (Ethernet9) in NetBox
        to simulate a MAC that already exists as a duplicate entry from a prior run.
        The sync must report it as in_sync without creating duplicates."""
        self._cleanup(nfclient, ["ceos-spine-2"])

        # Pre-assign MAC to the correct interface - simulates an existing correct entry
        intf_id = self._get_intf_id(nfclient, "ceos-spine-2", self.SPINE2_INTF)
        self._create_nb_mac(nfclient, self.SPINE2_MAC, intf_id=intf_id)

        ret = self._sync(nfclient, ["ceos-spine-2"])
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            device_data = res["result"]["ceos-spine-2"]
            assert (
                self.SPINE2_MAC in device_data["in_sync"]
            ), f"{worker} {self.SPINE2_MAC} not in in_sync list - expected in_sync for pre-assigned MAC"
            assert (
                self.SPINE2_MAC not in device_data["created"]
            ), f"{worker} {self.SPINE2_MAC} incorrectly listed as created"
            assert (
                self.SPINE2_MAC not in device_data["updated"]
            ), f"{worker} {self.SPINE2_MAC} incorrectly listed as updated"

        # Validate only one MAC entry exists for this interface (no duplicates added)
        nb_macs = self._get_nb_macs(nfclient, "ceos-spine-2", self.SPINE2_INTF)
        matching = [m for m in nb_macs if m.mac_address.lower() == self.SPINE2_MAC]
        assert len(matching) == 1, (
            f"Expected exactly 1 entry for {self.SPINE2_MAC} on ceos-spine-2:{self.SPINE2_INTF}, "
            f"got {len(matching)}"
        )

    # ------------------------------------------------------------------ #
    # Filter scenarios                                                     #
    # ------------------------------------------------------------------ #

    def test_sync_mac_addresses_filter_by_name(self, nfclient):
        """Clean all spine MACs then sync with filter_by_name='Ethernet9'.
        Only Ethernet9 MACs must be created; no MACs from other interfaces."""
        self._cleanup(nfclient, self.SPINE_DEVICES)

        ret = self._sync(
            nfclient, self.SPINE_DEVICES, dry_run=True, filter_by_name="Ethernet9"
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            all_macs = []
            for device_data in res["result"].values():
                all_macs.extend(device_data["created"])
                all_macs.extend(device_data["updated"])
                all_macs.extend(device_data["in_sync"])
            # Both Ethernet9 MACs must be planned for creation
            assert (
                self.SPINE1_MAC in all_macs
            ), f"{worker} spine-1 Ethernet9 MAC {self.SPINE1_MAC} not in plan after filter_by_name='Ethernet9'"
            assert (
                self.SPINE2_MAC in all_macs
            ), f"{worker} spine-2 Ethernet9 MAC {self.SPINE2_MAC} not in plan after filter_by_name='Ethernet9'"
            # Non-Ethernet9 MACs from leaf-1 must NOT appear
            assert (
                self.LEAF1_MAC_ETH1 not in all_macs
            ), f"{worker} leaf-1 Ethernet1 MAC {self.LEAF1_MAC_ETH1} leaked through filter_by_name='Ethernet9'"

    def test_sync_mac_addresses_filter_by_description(self, nfclient):
        """Clean all MACs from all devices then dry_run with filter_by_description='TEST_SYNC_*'.
        Only MACs on TEST_SYNC interfaces must appear in the plan.
        The non-TEST_SYNC MAC on leaf-1:Ethernet1 must not appear."""
        self._cleanup(nfclient, self.ALL_DEVICES)

        ret = self._sync(
            nfclient,
            self.ALL_DEVICES,
            dry_run=True,
            filter_by_description="TEST_SYNC_*",
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            all_macs = []
            for device_data in res["result"].values():
                all_macs.extend(device_data["created"])
                all_macs.extend(device_data["updated"])
                all_macs.extend(device_data["in_sync"])
            # All TEST_SYNC MACs must be in the plan
            missing = self.TEST_SYNC_MACS - set(all_macs)
            assert not missing, f"{worker} TEST_SYNC MACs missing from plan: {missing}"
            # Non-TEST_SYNC MAC (leaf-1 Ethernet1, description is a P2P label) must not appear
            assert (
                self.LEAF1_MAC_ETH1 not in all_macs
            ), f"{worker} non-TEST_SYNC MAC {self.LEAF1_MAC_ETH1} leaked through filter_by_description"

    def test_sync_mac_addresses_filter_by_mac(self, nfclient):
        """Clean spine-1 MACs then dry_run with filter_by_mac matching only spine-1's MAC.
        Only the matching MAC must appear; spine-2's MAC must be absent."""
        self._cleanup(nfclient, self.SPINE_DEVICES)

        ret = self._sync(
            nfclient,
            self.SPINE_DEVICES,
            dry_run=True,
            filter_by_mac="02:00:00:11:*",
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed - {res}"
            all_macs = []
            for device_data in res["result"].values():
                all_macs.extend(device_data["created"])
                all_macs.extend(device_data["updated"])
                all_macs.extend(device_data["in_sync"])
            assert (
                self.SPINE1_MAC in all_macs
            ), f"{worker} spine-1 MAC {self.SPINE1_MAC} missing from plan with filter_by_mac='02:00:00:11:*'"
            assert (
                self.SPINE2_MAC not in all_macs
            ), f"{worker} spine-2 MAC {self.SPINE2_MAC} leaked through filter_by_mac='02:00:00:11:*'"

    # ------------------------------------------------------------------ #
    # Edge-case scenarios                                                  #
    # ------------------------------------------------------------------ #

    def test_sync_mac_addresses_duplicate_mac_unassigned_and_conflicting(
        self, nfclient
    ):
        """Regression test for the nb_macs dict-overwrite bug.

        Scenario: NetBox contains two entries for the same MAC on spine-1:
          - entry A: assigned to Ethernet1 (wrong interface - conflicts with live Ethernet9)
          - entry B: unassigned (no assigned_object)

        Depending on NetBox's iteration order, the old dict-comprehension could pick up
        entry B last and silently discard the conflicting entry A, causing the sync to
        update the unassigned entry instead of raising an error.

        With the fix, the assigned (conflicting) entry always wins.  The sync must
        report an error and NOT silently move or update the MAC."""
        self._cleanup(nfclient, ["ceos-spine-1"])

        # Create entry A: MAC assigned to Ethernet1 (conflicts with live data pointing to Ethernet9)
        wrong_intf_id = self._get_intf_id(nfclient, "ceos-spine-1", "Ethernet1")
        self._create_nb_mac(nfclient, self.SPINE1_MAC, intf_id=wrong_intf_id)

        # Create entry B: same MAC but unassigned (no interface)
        self._create_nb_mac(nfclient, self.SPINE1_MAC, intf_id=None)

        ret = self._sync(nfclient, ["ceos-spine-1"])
        pprint.pprint(ret)
        for worker, res in ret.items():
            # Must report an error - the assigned conflicting entry must win over the unassigned one
            assert len(res["errors"]) > 0, (
                f"{worker} expected conflict error but got none - "
                f"the unassigned entry may have silently overwritten the conflicting one"
            )
            device_data = res["result"]["ceos-spine-1"]
            # The MAC must NOT be silently updated/created
            assert (
                self.SPINE1_MAC not in device_data["created"]
            ), f"{worker} {self.SPINE1_MAC} incorrectly created despite conflict"
            assert self.SPINE1_MAC not in device_data["updated"], (
                f"{worker} {self.SPINE1_MAC} incorrectly updated despite conflict - "
                f"unassigned entry swallowed the conflicting assigned entry"
            )

        # Cleanup both NB entries
        self._cleanup(nfclient, ["ceos-spine-1"])

    def test_sync_mac_addresses_non_existing_device(self, nfclient):
        """Sync against a device name that does not exist in NetBox.
        The task must fail and report an error."""
        ret = self._sync(nfclient, ["nonexistent-device-12345"])
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert (
                len(res["errors"]) > 0
            ), f"{worker} should have errors for nonexistent device"

    def test_sync_mac_addresses_with_branch(self, nfclient):
        """Clean spine MACs, delete the test branch, then sync into a new branch.
        Result must carry RESULT_KEYS and at least one MAC must be created."""
        branch = "sync_mac_addresses_branch_1"
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


@pytest.mark.task_check_device_sync
class TestCheckDeviceSync:
    """Test suite for check_device_sync task."""

    DEVICES = ["ceos-spine-1", "ceos-spine-2"]
    # Expected per-device sub-categories when all checks are enabled
    ALL_CATEGORIES = {"interfaces", "mac_addresses", "ip_addresses", "bgp_peerings"}

    def test_check_device_sync_result_structure(self, nfclient):
        """Result has a dict per device with all four sync categories."""
        ret = nfclient.run_job(
            "netbox",
            "check_device_sync",
            workers="any",
            kwargs={"devices": self.DEVICES},
        )
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert not res["failed"], f"{worker} failed - {res.get('errors')}"
            for device in self.DEVICES:
                assert device in res["result"], f"{worker} missing {device} in result"
                device_data = res["result"][device]
                assert (
                    self.ALL_CATEGORIES <= device_data.keys()
                ), f"{worker}:{device} missing categories: {self.ALL_CATEGORIES - device_data.keys()}"
                assert (
                    "in_sync" in device_data
                ), f"{worker}:{device} missing top-level 'in_sync' key"
                assert isinstance(
                    device_data["in_sync"], bool
                ), f"{worker}:{device} top-level 'in_sync' is not a bool"
                assert device_data["in_sync"] == all(
                    device_data[category] for category in self.ALL_CATEGORIES
                ), f"{worker}:{device} top-level 'in_sync' does not match categories"
                for category in self.ALL_CATEGORIES:
                    assert isinstance(
                        device_data[category], bool
                    ), f"{worker}:{device}:{category} is not a bool"

    def test_check_device_sync_diff_structure(self, nfclient):
        """Result.diff contains sub-task data keyed by category name."""
        ret = nfclient.run_job(
            "netbox",
            "check_device_sync",
            workers="any",
            kwargs={"devices": self.DEVICES},
        )
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert not res["failed"], f"{worker} failed - {res.get('errors')}"
            assert isinstance(res["diff"], dict), f"{worker} diff should be a dict"
            for category in self.ALL_CATEGORIES:
                assert (
                    category in res["diff"]
                ), f"{worker} diff missing '{category}' key"
                assert isinstance(
                    res["diff"][category], dict
                ), f"{worker} diff['{category}'] should be a dict"

    def test_check_device_sync_no_writes_to_netbox(self, nfclient):
        """check_device_sync must never write to NetBox."""
        pynb = get_pynetbox(nfclient)
        nb_device = pynb.dcim.devices.get(name="ceos-spine-1")
        serial_before = nb_device.serial

        nfclient.run_job(
            "netbox",
            "check_device_sync",
            workers="any",
            kwargs={"devices": ["ceos-spine-1"]},
        )

        nb_device = pynb.dcim.devices.get(name="ceos-spine-1")
        assert (
            nb_device.serial == serial_before
        ), "check_device_sync modified NetBox serial - writes must not occur"

    def test_check_device_sync_selective_interfaces_only(self, nfclient):
        """Only interfaces category returned when other checks disabled."""
        ret = nfclient.run_job(
            "netbox",
            "check_device_sync",
            workers="any",
            kwargs={
                "devices": self.DEVICES,
                "check_interfaces": True,
                "check_mac_addresses": False,
                "check_ip_addresses": False,
                "check_bgp_peerings": False,
            },
        )
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert not res["failed"], f"{worker} failed - {res.get('errors')}"
            for device in self.DEVICES:
                assert device in res["result"], f"{worker} missing {device} in result"
                device_data = res["result"][device]
                assert (
                    "interfaces" in device_data
                ), f"{worker}:{device} missing interfaces"
                assert (
                    "mac_addresses" not in device_data
                ), f"{worker}:{device} mac_addresses should not be present"
                assert (
                    "ip_addresses" not in device_data
                ), f"{worker}:{device} ip_addresses should not be present"
                assert (
                    "bgp_peerings" not in device_data
                ), f"{worker}:{device} bgp_peerings should not be present"
            assert "interfaces" in res["diff"], f"{worker} diff missing interfaces"
            assert (
                "mac_addresses" not in res["diff"]
            ), f"{worker} diff should not have mac_addresses"

    def test_check_device_sync_selective_mac_and_ip_only(self, nfclient):
        """Only mac_addresses and ip_addresses categories returned."""
        ret = nfclient.run_job(
            "netbox",
            "check_device_sync",
            workers="any",
            kwargs={
                "devices": self.DEVICES,
                "check_interfaces": False,
                "check_mac_addresses": True,
                "check_ip_addresses": True,
                "check_bgp_peerings": False,
            },
        )
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert not res["failed"], f"{worker} failed - {res.get('errors')}"
            for device in self.DEVICES:
                device_data = res["result"][device]
                assert (
                    "interfaces" not in device_data
                ), f"{worker}:{device} interfaces should not be present"
                assert (
                    "mac_addresses" in device_data
                ), f"{worker}:{device} missing mac_addresses"
                assert (
                    "ip_addresses" in device_data
                ), f"{worker}:{device} missing ip_addresses"
                assert (
                    "bgp_peerings" not in device_data
                ), f"{worker}:{device} bgp_peerings should not be present"

    def test_check_device_sync_with_nornir_filter(self, nfclient):
        """Devices resolved via Nornir FC filter."""
        ret = nfclient.run_job(
            "netbox",
            "check_device_sync",
            workers="any",
            kwargs={"FC": "spine"},
        )
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert not res["failed"], f"{worker} failed - {res.get('errors')}"
            for device in self.DEVICES:
                assert (
                    device in res["result"]
                ), f"{worker} device {device} missing from filter-resolved result"

    def test_check_device_sync_empty_devices(self, nfclient):
        """Empty devices list with no filters must fail with an error."""
        ret = nfclient.run_job(
            "netbox",
            "check_device_sync",
            workers="any",
            kwargs={"devices": []},
        )
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert res["failed"], f"{worker} should fail when no devices specified"
            assert res["errors"], f"{worker} should report errors"


@pytest.mark.task_sync_all
class TestSyncAll:
    """Verify sync_all calls all five sync tasks in sequence.

    Each test performs a full cleanup before and after via setup_method/teardown_method
    and uses out-of-band pynetbox queries to verify NetBox state directly.
    """

    SPINE_DEVICES = ["ceos-spine-1", "ceos-spine-2"]
    ALL_CATEGORIES = {
        "inventory",
        "interfaces",
        "mac_addresses",
        "ip_addresses",
        "bgp_peerings",
    }
    NETBOX_SERIALS = {
        "ceos-spine-1": "FNS12345678",
        "ceos-spine-2": "FNS123456789",
    }
    LIVE_SERIALS = {
        "ceos-spine-1": "C4889628D19280228439023C4F0C3EE4",
        "ceos-spine-2": "F8B8101D77067B49C0437B3711AA1719",
    }

    # Known TEST_SYNC items from interfaces_parse_data.json for spine devices
    SPINE1_TEST_INTF = (
        "Loopback10"  # TEST_SYNC_LOOPBACK_IPV4 - created by sync_device_interfaces
    )
    SPINE1_TEST_MAC = "02:00:00:11:00:09"  # created by sync_mac_addresses on Ethernet9
    SPINE1_TEST_IP = "10.3.15.33/30"  # created by sync_device_ip on Ethernet9

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    def setup_method(self):
        """Clean all sync-managed data from NetBox before each test."""
        self._do_cleanup()

    def teardown_method(self):
        """Clean all sync-managed data from NetBox after each test."""
        self._do_cleanup()

    @staticmethod
    def _do_cleanup():
        """Remove TEST_SYNC interfaces, all MACs, TEST_SYNC IPs and BGP sessions
        for spine devices using pynetbox directly."""
        nb = get_pynetbox(None)
        devices = ["ceos-spine-1", "ceos-spine-2"]
        # BGP sessions
        for device in devices:
            for session in list(nb.plugins.bgp.session.filter(device=device)):
                session.delete()
            nb.dcim.devices.get(name=device).update(
                {"serial": TestSyncAll.NETBOX_SERIALS[device]}
            )
        # TEST_SYNC IP addresses
        for parent_prefix in ["10.3.0.0/16", "2001:beef::/32"]:
            for ip in nb.ipam.ip_addresses.filter(parent=parent_prefix):
                ip.delete()
        # MAC addresses - delete by device filter (assigned MACs) and by known
        # MAC address values to catch unassigned/orphaned MACs left by other tests
        for device in devices:
            for mac in nb.dcim.mac_addresses.filter(device=device):
                mac.delete()
        for mac_addr in ["02:00:00:11:00:09", "02:00:00:12:00:09"]:
            for mac in nb.dcim.mac_addresses.filter(mac_address=mac_addr):
                mac.delete()
        # TEST_SYNC interfaces - delete children before parents to avoid 409 conflicts.
        # Exclude 'Ethernet9': pre-existing interface updated by sync; needed by TestSyncMacAddresses.
        for device in devices:
            intfs = list(
                nb.dcim.interfaces.filter(device=device, description__ic="TEST_SYNC")
            )
            children = [i for i in intfs if i.parent]
            parents = [i for i in intfs if not i.parent]
            for intf in children + parents:
                intf.delete()
        print("sync_all cleanup complete")

    # ------------------------------------------------------------------ #
    # Class-level helpers                                                  #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _sync(nfclient, devices, **extra_kwargs):
        """Run sync_all and return the result dict."""
        return nfclient.run_job(
            "netbox",
            "sync_all",
            workers="any",
            kwargs={"devices": devices, **extra_kwargs},
        )

    @staticmethod
    def _get_nb_intf(device, name):
        """Fetch a single interface record from NetBox. Returns None if not found."""
        return get_pynetbox(None).dcim.interfaces.get(device=device, name=name)

    @staticmethod
    def _get_nb_macs(device, interface):
        """Return list of MAC address records for the given device interface."""
        return list(
            get_pynetbox(None).dcim.mac_addresses.filter(
                device=device, interface=interface
            )
        )

    @staticmethod
    def _get_nb_ips(device, interface):
        """Return list of IP address records for the given device interface."""
        return list(
            get_pynetbox(None).ipam.ip_addresses.filter(
                device=device, interface=interface
            )
        )

    # ------------------------------------------------------------------ #
    # Basic smoke tests                                                    #
    # ------------------------------------------------------------------ #

    def test_sync_all_result_structure(self, nfclient):
        """All five categories are present per device in dry-run mode."""
        ret = self._sync(nfclient, self.SPINE_DEVICES, dry_run=True)
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert not res["failed"], f"{worker} failed - {res.get('errors')}"
            for device in self.SPINE_DEVICES:
                assert device in res["result"], f"{worker} missing {device} in result"
                device_data = res["result"][device]
                assert self.ALL_CATEGORIES <= device_data.keys(), (
                    f"{worker}:{device} missing categories: "
                    f"{self.ALL_CATEGORIES - device_data.keys()}"
                )
                for category in self.ALL_CATEGORIES:
                    assert isinstance(device_data[category], dict), (
                        f"{worker}:{device}:{category} result should be a dict, "
                        f"got {type(device_data[category])}"
                    )

    def test_sync_all_dry_run_no_writes(self, nfclient):
        """dry_run=True must not write inventory, interfaces, MACs, or IPs."""
        self._sync(nfclient, self.SPINE_DEVICES, dry_run=True)

        nb = get_pynetbox(None)
        for device, serial in self.NETBOX_SERIALS.items():
            assert nb.dcim.devices.get(name=device).serial == serial
        # Interface must not exist
        intf = nb.dcim.interfaces.get(device="ceos-spine-1", name=self.SPINE1_TEST_INTF)
        assert (
            intf is None
        ), f"dry_run wrote interface {self.SPINE1_TEST_INTF!r} to NetBox"
        # MAC must not exist
        macs = list(
            nb.dcim.mac_addresses.filter(
                device="ceos-spine-1", mac_address=self.SPINE1_TEST_MAC
            )
        )
        assert not macs, f"dry_run wrote MAC {self.SPINE1_TEST_MAC!r} to NetBox"
        # IP must not exist
        ips = list(
            nb.ipam.ip_addresses.filter(
                address=self.SPINE1_TEST_IP, device="ceos-spine-1"
            )
        )
        assert not ips, f"dry_run wrote IP {self.SPINE1_TEST_IP!r} to NetBox"

    # ------------------------------------------------------------------ #
    # Live run - creates in NetBox                                         #
    # ------------------------------------------------------------------ #

    def test_sync_all_updates_device_inventory_in_netbox(self, nfclient):
        """sync_all updates device serials through sync_device_inventory."""
        ret = self._sync(nfclient, self.SPINE_DEVICES)
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert not res["failed"], f"{worker} failed - {res.get('errors')}"
            for device in self.SPINE_DEVICES:
                inventory = res["result"][device]["inventory"]
                assert "chassis" in inventory["updated"]

        nb = get_pynetbox(None)
        for device, serial in self.LIVE_SERIALS.items():
            assert nb.dcim.devices.get(name=device).serial == serial

    def test_sync_all_creates_interfaces_in_netbox(self, nfclient):
        """After cleanup, sync_all must create TEST_SYNC interfaces in NetBox;
        Loopback10 must appear with correct description."""
        ret = self._sync(nfclient, self.SPINE_DEVICES)
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert not res["failed"], f"{worker} failed - {res.get('errors')}"
            for device in self.SPINE_DEVICES:
                assert device in res["result"], f"{worker} missing {device}"
                intf_data = res["result"][device].get("interfaces", {})
                assert intf_data.get(
                    "created"
                ), f"{worker}:{device} no interfaces created after cleanup"

        # Out-of-band: verify Loopback10 exists in NetBox with correct description
        nb_intf = self._get_nb_intf("ceos-spine-1", self.SPINE1_TEST_INTF)
        assert (
            nb_intf is not None
        ), f"{self.SPINE1_TEST_INTF} not found in NetBox after sync_all"
        assert (
            nb_intf.description == "TEST_SYNC_LOOPBACK_IPV4"
        ), f"{self.SPINE1_TEST_INTF} description mismatch: got {nb_intf.description!r}"
        assert (
            nb_intf.type.value == "virtual"
        ), f"{self.SPINE1_TEST_INTF} type mismatch: got {nb_intf.type.value!r}"

    def test_sync_all_creates_mac_addresses_in_netbox(self, nfclient):
        """After cleanup, sync_all must create MAC addresses in NetBox;
        spine-1 MAC must appear on Ethernet9."""
        ret = self._sync(nfclient, self.SPINE_DEVICES)
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert not res["failed"], f"{worker} failed - {res.get('errors')}"
            mac_data = res["result"]["ceos-spine-1"].get("mac_addresses", {})
            assert mac_data.get(
                "created"
            ), f"{worker}:ceos-spine-1 no MACs created after cleanup"

        # Out-of-band: verify spine-1 MAC exists on Ethernet9
        macs = self._get_nb_macs("ceos-spine-1", "Ethernet9")
        mac_addresses = [str(m.mac_address).lower() for m in macs]
        assert self.SPINE1_TEST_MAC in mac_addresses, (
            f"MAC {self.SPINE1_TEST_MAC!r} not found on ceos-spine-1:Ethernet9 "
            f"after sync_all; found: {mac_addresses}"
        )

    def test_sync_all_creates_ip_addresses_in_netbox(self, nfclient):
        """After cleanup, sync_all must create IP addresses in NetBox;
        spine-1 Ethernet9 IP must appear."""
        ret = self._sync(nfclient, self.SPINE_DEVICES)
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert not res["failed"], f"{worker} failed - {res.get('errors')}"
            ip_data = res["result"]["ceos-spine-1"].get("ip_addresses", {})
            assert ip_data.get(
                "created"
            ), f"{worker}:ceos-spine-1 no IPs created after cleanup"

        # Out-of-band: verify spine-1 Ethernet9 IP exists in NetBox
        ips = self._get_nb_ips("ceos-spine-1", "Ethernet9")
        ip_addresses = [str(ip.address) for ip in ips]
        assert self.SPINE1_TEST_IP in ip_addresses, (
            f"IP {self.SPINE1_TEST_IP!r} not found on ceos-spine-1:Ethernet9 "
            f"after sync_all; found: {ip_addresses}"
        )

    # ------------------------------------------------------------------ #
    # Idempotency                                                          #
    # ------------------------------------------------------------------ #

    def test_sync_all_idempotent(self, nfclient):
        """Second sync_all run reports all managed data in sync."""
        # First run - creates everything
        first = self._sync(nfclient, self.SPINE_DEVICES)
        for worker, res in first.items():
            assert not res[
                "failed"
            ], f"First sync_all failed for {worker}: {res.get('errors')}"

        # Second run - must be fully in_sync for interfaces/MACs/IPs
        ret = self._sync(nfclient, self.SPINE_DEVICES)
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert not res["failed"], f"{worker} failed - {res.get('errors')}"
            for device in self.SPINE_DEVICES:
                intf_data = res["result"][device].get("interfaces", {})
                mac_data = res["result"][device].get("mac_addresses", {})
                ip_data = res["result"][device].get("ip_addresses", {})
                inventory_data = res["result"][device].get("inventory", {})
                assert not inventory_data.get("created")
                assert not inventory_data.get("updated")
                assert "chassis" in inventory_data.get("in_sync", [])
                assert not intf_data.get("created"), (
                    f"{worker}:{device} unexpected interface creates on 2nd run: "
                    f"{intf_data.get('created')}"
                )
                assert not mac_data.get("created"), (
                    f"{worker}:{device} unexpected MAC creates on 2nd run: "
                    f"{mac_data.get('created')}"
                )
                assert not ip_data.get("created"), (
                    f"{worker}:{device} unexpected IP creates on 2nd run: "
                    f"{ip_data.get('created')}"
                )
                assert intf_data.get(
                    "in_sync"
                ), f"{worker}:{device} no interfaces in_sync on 2nd run"
                assert mac_data.get(
                    "in_sync"
                ), f"{worker}:{device} no MACs in_sync on 2nd run"
                assert ip_data.get(
                    "in_sync"
                ), f"{worker}:{device} no IPs in_sync on 2nd run"

    # ------------------------------------------------------------------ #
    # Filtering                                                            #
    # ------------------------------------------------------------------ #

    def test_sync_all_with_nornir_filter(self, nfclient):
        """Devices resolved via Nornir FC filter must include both spine devices."""
        ret = nfclient.run_job(
            "netbox",
            "sync_all",
            workers="any",
            kwargs={"FC": "spine", "dry_run": True},
        )
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert not res["failed"], f"{worker} failed - {res.get('errors')}"
            for device in self.SPINE_DEVICES:
                assert (
                    device in res["result"]
                ), f"{worker} device {device!r} missing from filter-resolved result"

    # ------------------------------------------------------------------ #
    # Error cases                                                          #
    # ------------------------------------------------------------------ #

    def test_sync_all_empty_devices(self, nfclient):
        """Empty devices list with no filters must fail with an error."""
        ret = nfclient.run_job(
            "netbox",
            "sync_all",
            workers="any",
            kwargs={"devices": []},
        )
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert res["failed"], f"{worker} should fail when no devices specified"
            assert res["errors"], f"{worker} should report errors"
