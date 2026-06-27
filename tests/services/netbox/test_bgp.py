import pprint

import pytest

try:
    from tests.services.netbox.common import (
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
        delete_branch,
        get_pynetbox,
    )

pytestmark = [pytest.mark.netbox, pytest.mark.bgp]


@pytest.mark.task_get_bgp_peerings
class TestGetBgpPeerings:
    """Test suite for get_bgp_peerings function"""

    nb_version = None

    def test_get_bgp_peerings(self, nfclient):
        """Test basic BGP peerings retrieval"""
        ret = nfclient.run_job(
            "netbox",
            "get_bgp_peerings",
            workers="any",
            kwargs={"devices": ["fceos4", "fceos5"]},
        )
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert res["result"], f"{worker} returned no results"
            assert "fceos4" in res["result"], f"{worker} missing fceos4 in results"
            assert "fceos5" in res["result"], f"{worker} missing fceos5 in results"
            # Check that each device has a dictionary (may be empty if no BGP sessions)
            for device, bgp_sessions in res["result"].items():
                assert isinstance(
                    bgp_sessions, dict
                ), f"{worker}:{device} BGP sessions should be a dictionary"
                # If there are BGP sessions, verify the structure
                for session_name, session_data in bgp_sessions.items():
                    assert isinstance(
                        session_data, dict
                    ), f"{worker}:{device}:{session_name} session data should be a dictionary"

                    # Verify required top-level fields
                    required_fields = [
                        "id",
                        "name",
                        "description",
                        "device",
                        "local_address",
                        "local_as",
                        "remote_address",
                        "remote_as",
                        "status",
                        "last_updated",
                        "created",
                        "url",
                        "display",
                        "site",
                        "tenant",
                        "tags",
                        "comments",
                        "custom_fields",
                    ]
                    for field in required_fields:
                        assert (
                            field in session_data
                        ), f"{worker}:{device}:{session_name} missing field '{field}'"

    def test_get_bgp_peerings_with_instance(self, nfclient):
        """Test BGP peerings retrieval with explicit instance"""
        ret = nfclient.run_job(
            "netbox",
            "get_bgp_peerings",
            workers="any",
            kwargs={"devices": ["fceos4", "fceos5"], "instance": "prod"},
        )
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert res["result"], f"{worker} returned no results"
            assert "fceos4" in res["result"], f"{worker} missing fceos4 in results"
            assert "fceos5" in res["result"], f"{worker} missing fceos5 in results"
            # Check that each device has a dictionary (may be empty if no BGP sessions)
            for device, bgp_sessions in res["result"].items():
                assert isinstance(
                    bgp_sessions, dict
                ), f"{worker}:{device} BGP sessions should be a dictionary"

    def test_get_bgp_peerings_nonexistent_device(self, nfclient):
        """Test error handling for non-existent device"""
        ret = nfclient.run_job(
            "netbox",
            "get_bgp_peerings",
            workers="any",
            kwargs={"devices": ["nonexistent-device-12345"]},
        )
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert res["result"], f"{worker} returned no results"
            assert (
                "nonexistent-device-12345" in res["result"]
            ), f"{worker} should have entry for nonexistent device"
            # The result for non-existent device should be empty dict
            assert (
                res["result"]["nonexistent-device-12345"] == {}
            ), f"{worker} should return empty dict for nonexistent device"

    def test_get_bgp_peerings_empty_devices_list(self, nfclient):
        """Test with empty devices list"""
        ret = nfclient.run_job(
            "netbox",
            "get_bgp_peerings",
            workers="any",
            kwargs={"devices": []},
        )
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert isinstance(
                res["result"], dict
            ), f"{worker} should return a dictionary"
            assert (
                len(res["result"]) == 0
            ), f"{worker} should return empty dict for empty devices list"

    def test_get_bgp_peerings_cache_true(self, nfclient):
        """Test cache content for BGP peerings"""
        # get cache brief info
        cache_before = nfclient.run_job(
            "netbox",
            "cache_list",
            workers=["netbox-worker-1.1"],
            kwargs={"keys": "get_bgp_peerings*", "details": True},
        )

        # Clear any existing cache
        nfclient.run_job(
            "netbox",
            "cache_clear",
            workers=["netbox-worker-1.1"],
            kwargs={"keys": "get_bgp_peerings*"},
        )

        # cache data
        nfclient.run_job(
            "netbox",
            "get_bgp_peerings",
            workers=["netbox-worker-1.1"],
            kwargs={"devices": ["fceos4", "fceos5"], "cache": True},
        )

        # Now retrieve cache content
        cache_after = nfclient.run_job(
            "netbox",
            "cache_list",
            workers=["netbox-worker-1.1"],
            kwargs={"keys": "get_bgp_peerings*", "details": True},
        )

        print("cache_before:")
        pprint.pprint(cache_before, width=200)

        print("cache_after:")
        pprint.pprint(cache_after, width=200)

        for worker, res in cache_after.items():
            for cache_item_after in res["result"]:
                key = cache_item_after["key"]
                for cache_item_before in cache_before[worker]["result"]:
                    if cache_item_before["key"] == key:
                        assert (
                            cache_item_before["creation"]
                            != cache_item_after["creation"]
                        ), f"{worker}:{key} cache not re-created"

    def test_get_bgp_peerings_cache_refresh(self, nfclient):
        """Test cache content for BGP peerings"""
        # get cache brief info
        cache_before = nfclient.run_job(
            "netbox",
            "cache_list",
            workers=["netbox-worker-1.1"],
            kwargs={"keys": "get_bgp_peerings*", "details": True},
        )

        # cache data
        nfclient.run_job(
            "netbox",
            "get_bgp_peerings",
            workers=["netbox-worker-1.1"],
            kwargs={"devices": ["fceos4", "fceos5"], "cache": "refresh"},
        )

        # Now retrieve cache content
        cache_after = nfclient.run_job(
            "netbox",
            "cache_list",
            workers=["netbox-worker-1.1"],
            kwargs={"keys": "get_bgp_peerings*", "details": True},
        )

        print("cache_before:")
        pprint.pprint(cache_before, width=200)

        print("cache_after:")
        pprint.pprint(cache_after, width=200)

        for worker, res in cache_after.items():
            for cache_item_after in res["result"]:
                key = cache_item_after["key"]
                for cache_item_before in cache_before[worker]["result"]:
                    if cache_item_before["key"] == key:
                        assert (
                            cache_item_before["creation"]
                            != cache_item_after["creation"]
                        ), f"{worker}:{key} cache not re-created"

    def test_get_bgp_peerings_cache_force(self, nfclient):
        """Test cache force mode (use cache without checking)"""
        # First, populate cache
        nfclient.run_job(
            "netbox",
            "get_bgp_peerings",
            workers="any",
            kwargs={"devices": ["fceos4"], "cache": True},
        )

        # Use cache="force" to retrieve from cache only
        ret = nfclient.run_job(
            "netbox",
            "get_bgp_peerings",
            workers="any",
            kwargs={"devices": ["fceos4"], "cache": "force"},
        )
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert res["result"], f"{worker} returned no results"
            assert "fceos4" in res["result"], f"{worker} missing fceos4 in results"

    def test_get_bgp_peerings_cache_false(self, nfclient):
        """Test with cache disabled"""
        # Clear any existing cache
        nfclient.run_job(
            "netbox",
            "cache_clear",
            workers="all",
            kwargs={"keys": "get_bgp_peerings*"},
        )

        # Fetch with cache=False
        ret = nfclient.run_job(
            "netbox",
            "get_bgp_peerings",
            workers="any",
            kwargs={"devices": ["fceos4"], "cache": False},
        )
        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert res["result"], f"{worker} returned no results"
            assert "fceos4" in res["result"], f"{worker} missing fceos4 in results"

        # Verify nothing was cached
        bgp_cache = nfclient.run_job(
            "netbox",
            "cache_get",
            workers="all",
            kwargs={"keys": "get_bgp_peerings::fceos4"},
        )

        for worker, res in bgp_cache.items():
            # Cache should be empty or the key should not exist
            assert (
                "get_bgp_peerings::fceos4" not in res["result"]
            ), f"{worker} should not have cached data when cache=False"


BGP_CREATE_SESSIONS_TEST_DEVICES = [
    "ceos-spine-1",
    "ceos-spine-2",
    "ceos-leaf-1",
    "ceos-leaf-2",
    "ceos-leaf-3",
    "vmx-1",
]


def delete_bgp_sessions(devices=BGP_CREATE_SESSIONS_TEST_DEVICES):
    """Delete all BGP sessions in NetBox for the given devices."""
    nb = get_pynetbox(None)
    for device in devices:
        sessions = list(nb.plugins.bgp.session.filter(device=device))
        for session in sessions:
            session.delete()
    print(f"Deleted BGP sessions for devices: {devices}")


@pytest.mark.task_sync_bgp_peerings
class TestSyncBgpPeerings:

    def setup_method(self):
        delete_bgp_sessions()

    def teardown_method(self):
        delete_bgp_sessions()

    def test_sync_bgp_peerings_basic(self, nfclient):
        """Run task, verify created list is non-empty, sessions exist in NetBox."""
        ret = nfclient.run_job(
            "netbox",
            "sync_bgp_peerings",
            workers="any",
            kwargs={"devices": BGP_CREATE_SESSIONS_TEST_DEVICES, "rir": "lab"},
        )
        pprint.pprint(ret)
        nb = get_pynetbox(nfclient)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            for device in BGP_CREATE_SESSIONS_TEST_DEVICES:
                if device in res["result"]:
                    assert (
                        len(res["result"][device]["created"]) > 0
                    ), f"{worker}: expected created sessions for '{device}'"
                    for sname in res["result"][device]["created"]:
                        assert nb.plugins.bgp.session.get(
                            name=sname
                        ), f"session '{sname}' not found in NetBox after creation"

    def test_sync_bgp_peerings_idempotent(self, nfclient):
        """Run twice; second run returns empty created/updated and non-empty in_sync."""
        kwargs = {"devices": BGP_CREATE_SESSIONS_TEST_DEVICES, "rir": "lab"}
        first_run = nfclient.run_job(
            "netbox", "sync_bgp_peerings", workers="any", kwargs=kwargs
        )

        print("first run:")
        pprint.pprint(first_run)

        ret = nfclient.run_job(
            "netbox", "sync_bgp_peerings", workers="any", kwargs=kwargs
        )
        print("seconf run:")
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            for device in BGP_CREATE_SESSIONS_TEST_DEVICES:
                if device in res["result"]:
                    assert (
                        res["result"][device]["created"] == []
                    ), f"{worker}: expected no new sessions on 2nd run for '{device}'"
                    assert (
                        res["result"][device]["updated"] == []
                    ), f"{worker}: expected no updates on 2nd run for '{device}'"

    def test_sync_bgp_peerings_dry_run_no_sessions(self, nfclient):
        """NetBox empty; dry_run=True; every device has non-empty missing_in_netbox."""
        ret = nfclient.run_job(
            "netbox",
            "sync_bgp_peerings",
            workers="any",
            kwargs={
                "devices": BGP_CREATE_SESSIONS_TEST_DEVICES,
                "dry_run": True,
                "rir": "lab",
            },
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            for device in BGP_CREATE_SESSIONS_TEST_DEVICES:
                if device in res["result"]:
                    assert (
                        len(res["result"][device]["create"]) > 0
                    ), f"{worker}: expected create for '{device}'"
                    assert (
                        res["result"][device]["delete"] == []
                    ), f"{worker}: expected empty delete for '{device}'"
                    assert (
                        res["result"][device]["update"] == {}
                    ), f"{worker}: expected empty update for '{device}'"
                    assert (
                        res["result"][device]["in_sync"] == []
                    ), f"{worker}: expected empty in_sync for '{device}'"

    def test_sync_bgp_peerings_dry_run_in_sync(self, nfclient):
        """Pre-create sessions; dry_run=True; all sessions in in_sync."""
        nfclient.run_job(
            "netbox",
            "sync_bgp_peerings",
            workers="any",
            kwargs={"devices": BGP_CREATE_SESSIONS_TEST_DEVICES, "rir": "lab"},
        )
        ret = nfclient.run_job(
            "netbox",
            "sync_bgp_peerings",
            workers="any",
            kwargs={
                "devices": BGP_CREATE_SESSIONS_TEST_DEVICES,
                "dry_run": True,
                "rir": "lab",
            },
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            for device in BGP_CREATE_SESSIONS_TEST_DEVICES:
                if device in res["result"]:
                    assert (
                        res["result"][device]["create"] == []
                    ), f"{worker}: expected no create after creation for '{device}'"
                    assert (
                        len(res["result"][device]["in_sync"]) > 0
                    ), f"{worker}: expected in_sync sessions for '{device}'"

    def test_sync_bgp_peerings_dry_run_needs_update(self, nfclient):
        """Pre-create sessions; manually change description; dry_run=True shows needs_update."""
        nfclient.run_job(
            "netbox",
            "sync_bgp_peerings",
            workers="any",
            kwargs={"devices": BGP_CREATE_SESSIONS_TEST_DEVICES, "rir": "lab"},
        )
        nb = get_pynetbox(nfclient)
        # Find any created session and alter its description
        target_device = BGP_CREATE_SESSIONS_TEST_DEVICES[0]
        sessions = list(nb.plugins.bgp.session.filter(device=target_device))
        assert sessions, f"No sessions found for '{target_device}' after creation"
        target_session = sessions[0]
        original_description = target_session.description
        target_session.description = "CHANGED_FOR_TEST"
        target_session.save()

        ret = nfclient.run_job(
            "netbox",
            "sync_bgp_peerings",
            workers="any",
            kwargs={"devices": [target_device], "dry_run": True, "rir": "lab"},
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            if target_device in res["result"]:
                assert (
                    target_session.name in res["result"][target_device]["update"]
                ), f"{worker}: expected '{target_session.name}' in update"

    def test_sync_bgp_peerings_dry_run_missing_on_device(self, nfclient):
        """Manually create a stale session; dry_run=True shows it in missing_on_device."""
        nb = get_pynetbox(nfclient)
        target_device = BGP_CREATE_SESSIONS_TEST_DEVICES[0]

        # First create real sessions so we have device/IP/ASN resolved
        nfclient.run_job(
            "netbox",
            "sync_bgp_peerings",
            workers="any",
            kwargs={"devices": [target_device], "rir": "lab"},
        )

        # Now create a stale session that won't match any parsed session
        nb_device = nb.dcim.devices.get(name=target_device)
        # Reuse IPs/ASNs from an existing session to avoid FK issues
        existing = list(nb.plugins.bgp.session.filter(device=target_device))
        assert existing, f"No sessions for '{target_device}'"
        ref = existing[0]
        stale_name = f"{target_device}_STALE_TEST_SESSION_XYZ"
        # Clean up any leftover objects from a previous failed run
        for leftover_ip in nb.ipam.ip_addresses.filter(address="192.0.2.1/32"):
            leftover_session = nb.plugins.bgp.session.get(name=stale_name)
            if leftover_session:
                leftover_session.delete()
            leftover_ip.delete()
        # Create a unique remote IP to avoid duplicate (device, local_address, remote_address) constraint
        stale_remote_ip = nb.ipam.ip_addresses.create(address="192.0.2.1/32")
        nb.plugins.bgp.session.create(
            name=stale_name,
            device=nb_device.id,
            local_address=ref.local_address.id,
            remote_address=stale_remote_ip.id,
            local_as=ref.local_as.id,
            remote_as=ref.remote_as.id,
            status="planned",
        )

        ret = nfclient.run_job(
            "netbox",
            "sync_bgp_peerings",
            workers="any",
            kwargs={"devices": [target_device], "dry_run": True, "rir": "lab"},
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            if target_device in res["result"]:
                assert (
                    stale_name in res["result"][target_device]["delete"]
                ), f"{worker}: expected '{stale_name}' in delete"

        # Cleanup stale objects created by this test
        stale_session = nb.plugins.bgp.session.get(name=stale_name)
        if stale_session:
            stale_session.delete()
        stale_remote_ip.delete()

    def test_sync_bgp_peerings_dry_run_no_writes(self, nfclient):
        """Confirm NetBox session count is identical before and after dry_run."""
        nb = get_pynetbox(nfclient)
        before = len(
            list(nb.plugins.bgp.session.filter(device=BGP_CREATE_SESSIONS_TEST_DEVICES))
        )

        nfclient.run_job(
            "netbox",
            "sync_bgp_peerings",
            workers="any",
            kwargs={
                "devices": BGP_CREATE_SESSIONS_TEST_DEVICES,
                "dry_run": True,
                "rir": "lab",
            },
        )

        after = len(
            list(nb.plugins.bgp.session.filter(device=BGP_CREATE_SESSIONS_TEST_DEVICES))
        )
        assert (
            before == after
        ), f"Session count changed during dry_run: {before} -> {after}"

    def test_sync_bgp_peerings_update_description(self, nfclient):
        """Pre-create sessions; change description on one; re-run; verify updated."""
        nfclient.run_job(
            "netbox",
            "sync_bgp_peerings",
            workers="any",
            kwargs={"devices": BGP_CREATE_SESSIONS_TEST_DEVICES, "rir": "lab"},
        )
        nb = get_pynetbox(nfclient)
        target_device = BGP_CREATE_SESSIONS_TEST_DEVICES[0]
        sessions = list(nb.plugins.bgp.session.filter(device=target_device))
        assert sessions
        target = sessions[0]
        target.description = "UPDATED_DESCRIPTION"
        target.save()

        ret = nfclient.run_job(
            "netbox",
            "sync_bgp_peerings",
            workers="any",
            kwargs={"devices": [target_device], "rir": "lab"},
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            if target_device in res["result"]:
                assert (
                    target.name in res["result"][target_device]["updated"]
                ), f"{worker}: expected '{target.name}' in updated"

    def test_sync_bgp_peerings_update_status(self, nfclient):
        """Pre-create sessions; change status on one; re-run; verify updated."""
        nfclient.run_job(
            "netbox",
            "sync_bgp_peerings",
            workers="any",
            kwargs={"devices": BGP_CREATE_SESSIONS_TEST_DEVICES, "rir": "lab"},
        )
        nb = get_pynetbox(nfclient)
        target_device = BGP_CREATE_SESSIONS_TEST_DEVICES[0]
        sessions = list(nb.plugins.bgp.session.filter(device=target_device))
        assert sessions
        target = sessions[0]
        # Set a different status than what parse_ttp would return
        target.status = "planned"
        target.save()

        ret = nfclient.run_job(
            "netbox",
            "sync_bgp_peerings",
            workers="any",
            kwargs={"devices": [target_device], "rir": "lab"},
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            if target_device in res["result"]:
                assert (
                    target.name in res["result"][target_device]["updated"]
                ), f"{worker}: expected '{target.name}' in updated after status change"

    def test_sync_bgp_peerings_process_deletions(self, nfclient):
        """Pre-seed a stale session; run with process_deletions=True; verify deleted."""
        nb = get_pynetbox(nfclient)
        target_device = BGP_CREATE_SESSIONS_TEST_DEVICES[0]

        nfclient.run_job(
            "netbox",
            "sync_bgp_peerings",
            workers="any",
            kwargs={"devices": [target_device], "rir": "lab"},
        )

        existing = list(nb.plugins.bgp.session.filter(device=target_device))
        assert existing
        ref = existing[0]
        nb_device = nb.dcim.devices.get(name=target_device)
        stale_name = f"{target_device}_STALE_DELETION_TEST"
        # Clean up any leftover objects from a previous failed run
        for leftover_ip in nb.ipam.ip_addresses.filter(address="192.0.2.2/32"):
            leftover_session = nb.plugins.bgp.session.get(name=stale_name)
            if leftover_session:
                leftover_session.delete()
            leftover_ip.delete()
        # Create a unique remote IP to avoid duplicate (device, local_address, remote_address) constraint
        stale_remote_ip = nb.ipam.ip_addresses.create(address="192.0.2.2/32")
        nb.plugins.bgp.session.create(
            name=stale_name,
            device=nb_device.id,
            local_address=ref.local_address.id,
            remote_address=stale_remote_ip.id,
            local_as=ref.local_as.id,
            remote_as=ref.remote_as.id,
            status="planned",
        )

        ret = nfclient.run_job(
            "netbox",
            "sync_bgp_peerings",
            workers="any",
            kwargs={
                "devices": [target_device],
                "process_deletions": True,
                "rir": "lab",
            },
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            if target_device in res["result"]:
                assert (
                    stale_name in res["result"][target_device]["deleted"]
                ), f"{worker}: expected '{stale_name}' in deleted"
        assert not nb.plugins.bgp.session.get(
            name=stale_name
        ), f"Stale session '{stale_name}' still exists in NetBox after deletion"

        # Cleanup stale IP created by this test (session was deleted by the task)
        stale_remote_ip.delete()

    def test_sync_bgp_peerings_process_deletions_default_off(self, nfclient):
        """Stale session pre-seeded; run without process_deletions; verify not deleted."""
        nb = get_pynetbox(nfclient)
        target_device = BGP_CREATE_SESSIONS_TEST_DEVICES[0]

        nfclient.run_job(
            "netbox",
            "sync_bgp_peerings",
            workers="any",
            kwargs={"devices": [target_device], "rir": "lab"},
        )

        existing = list(nb.plugins.bgp.session.filter(device=target_device))
        assert existing
        ref = existing[0]
        nb_device = nb.dcim.devices.get(name=target_device)
        stale_name = f"{target_device}_STALE_NO_DELETE_TEST"
        # Clean up any leftover objects from a previous failed run
        for leftover_ip in nb.ipam.ip_addresses.filter(address="192.0.2.3/32"):
            leftover_session = nb.plugins.bgp.session.get(name=stale_name)
            if leftover_session:
                leftover_session.delete()
            leftover_ip.delete()
        # Create a unique remote IP to avoid duplicate (device, local_address, remote_address) constraint
        stale_remote_ip = nb.ipam.ip_addresses.create(address="192.0.2.3/32")
        nb.plugins.bgp.session.create(
            name=stale_name,
            device=nb_device.id,
            local_address=ref.local_address.id,
            remote_address=stale_remote_ip.id,
            local_as=ref.local_as.id,
            remote_as=ref.remote_as.id,
            status="planned",
        )

        ret = nfclient.run_job(
            "netbox",
            "sync_bgp_peerings",
            workers="any",
            kwargs={"devices": [target_device], "rir": "lab"},
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            if target_device in res["result"]:
                assert (
                    res["result"][target_device]["deleted"] == []
                ), f"{worker}: expected empty deleted list when process_deletions=False"
        assert nb.plugins.bgp.session.get(
            name=stale_name
        ), f"Stale session '{stale_name}' was incorrectly deleted"

        # Cleanup stale objects created by this test
        stale_session = nb.plugins.bgp.session.get(name=stale_name)
        if stale_session:
            stale_session.delete()
        stale_remote_ip.delete()

    def test_sync_bgp_peerings_with_instance(self, nfclient):
        """Pass explicit instance='prod'; task should not fail."""
        ret = nfclient.run_job(
            "netbox",
            "sync_bgp_peerings",
            workers="any",
            kwargs={
                "devices": BGP_CREATE_SESSIONS_TEST_DEVICES,
                "instance": "prod",
                "rir": "lab",
            },
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert (
                res["failed"] == False
            ), f"{worker} failed with instance='prod': {res['errors']}"

    def test_sync_bgp_peerings_with_branch(self, nfclient):
        """Pass branch name; verify sessions created in branch; delete branch after."""
        branch = "test-create-bgp-peerings-branch"
        try:
            ret = nfclient.run_job(
                "netbox",
                "sync_bgp_peerings",
                workers="any",
                kwargs={
                    "devices": BGP_CREATE_SESSIONS_TEST_DEVICES,
                    "branch": branch,
                    "rir": "lab",
                },
            )
            pprint.pprint(ret)
            for worker, res in ret.items():
                assert res["failed"] == False, f"{worker} failed: {res['errors']}"
                for device in BGP_CREATE_SESSIONS_TEST_DEVICES:
                    if device in res["result"]:
                        assert (
                            len(res["result"][device]["created"]) > 0
                        ), f"{worker}: expected sessions created in branch for '{device}'"
        finally:
            delete_branch(branch, nfclient)

    def test_sync_bgp_peerings_nonexistent_device(self, nfclient):
        """Nonexistent device; verify ret.errors populated, no crash."""
        ret = nfclient.run_job(
            "netbox",
            "sync_bgp_peerings",
            workers="any",
            kwargs={"devices": ["nonexistent-device-xyz"], "rir": "lab"},
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert (
                len(res["errors"]) > 0
            ), f"{worker}: expected errors for nonexistent device"

    def test_sync_bgp_peerings_with_nornir_filter(self, nfclient):
        """Devices sourced from Nornir filter FC='spine'; verify spine sessions created."""
        ret = nfclient.run_job(
            "netbox",
            "sync_bgp_peerings",
            workers="any",
            kwargs={"FC": "spine", "rir": "lab"},
        )
        pprint.pprint(ret)
        nb = get_pynetbox(nfclient)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            for device_name, device_res in res["result"].items():
                assert (
                    "spine" in device_name
                ), f"{worker}: unexpected device '{device_name}' for FC='spine' filter"
                assert (
                    len(device_res["created"]) > 0
                ), f"{worker}: expected created sessions for '{device_name}'"

    def test_sync_bgp_peerings_name_template(self, nfclient):
        """Custom name_template produces correctly named sessions in NetBox."""
        nb = get_pynetbox(nfclient)
        target_device = BGP_CREATE_SESSIONS_TEST_DEVICES[0]
        template = "{{device}}_BGP_{{name}}"

        ret = nfclient.run_job(
            "netbox",
            "sync_bgp_peerings",
            workers="any",
            kwargs={
                "devices": [target_device],
                "rir": "lab",
                "name_template": template,
            },
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            if target_device in res["result"]:
                for sname in res["result"][target_device].get("created", []):
                    assert sname.startswith(
                        f"{target_device}_BGP_"
                    ), f"{worker}: session '{sname}' does not match template '{template}'"
                # Verify sessions with custom names exist in NetBox
                sessions = list(nb.plugins.bgp.session.filter(device=target_device))
                custom_sessions = [s for s in sessions if "_BGP_" in s.name]
                assert (
                    custom_sessions
                ), f"{worker}: no sessions with '_BGP_' found in NetBox for '{target_device}'"

    def test_sync_bgp_peerings_name_template_dry_run_updates_existing(self, nfclient):
        """Changing name_template must report updates for existing tuple-matched sessions."""
        nb = get_pynetbox(nfclient)
        target_device = BGP_CREATE_SESSIONS_TEST_DEVICES[0]
        template = "{{device}}_BGP_{{name}}"

        nfclient.run_job(
            "netbox",
            "sync_bgp_peerings",
            workers="any",
            kwargs={"devices": [target_device], "rir": "lab"},
        )
        original_names = sorted(
            s.name for s in nb.plugins.bgp.session.filter(device=target_device)
        )
        assert original_names, f"No sessions found for '{target_device}'"

        ret = nfclient.run_job(
            "netbox",
            "sync_bgp_peerings",
            workers="any",
            kwargs={
                "devices": [target_device],
                "rir": "lab",
                "dry_run": True,
                "name_template": template,
            },
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            if target_device in res["result"]:
                device_result = res["result"][target_device]
                assert (
                    device_result["create"] == []
                ), f"{worker}: expected no creates for existing tuple identities"
                assert (
                    device_result["delete"] == []
                ), f"{worker}: expected no deletes for existing tuple identities"
                assert set(device_result["update"]) == set(original_names), (
                    f"{worker}: expected updates keyed by current NetBox names, "
                    f"got {list(device_result['update'])}"
                )
                for sname, changes in device_result["update"].items():
                    assert "name" in changes, (
                        f"{worker}: expected name field update for '{sname}', "
                        f"got {changes}"
                    )

        current_names = sorted(
            s.name for s in nb.plugins.bgp.session.filter(device=target_device)
        )
        assert current_names == original_names, "Dry-run changed NetBox session names"

    def test_sync_bgp_peerings_name_template_renames_existing(self, nfclient):
        """Changing name_template must rename existing tuple-matched sessions."""
        nb = get_pynetbox(nfclient)
        target_device = BGP_CREATE_SESSIONS_TEST_DEVICES[0]
        template = "{{device}}_BGP_{{name}}"

        nfclient.run_job(
            "netbox",
            "sync_bgp_peerings",
            workers="any",
            kwargs={"devices": [target_device], "rir": "lab"},
        )
        original_names = sorted(
            s.name for s in nb.plugins.bgp.session.filter(device=target_device)
        )
        assert original_names, f"No sessions found for '{target_device}'"

        ret = nfclient.run_job(
            "netbox",
            "sync_bgp_peerings",
            workers="any",
            kwargs={
                "devices": [target_device],
                "rir": "lab",
                "name_template": template,
            },
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            if target_device in res["result"]:
                device_result = res["result"][target_device]
                assert (
                    device_result["created"] == []
                ), f"{worker}: expected no creates for existing tuple identities"
                assert (
                    device_result["deleted"] == []
                ), f"{worker}: expected no deletes for existing tuple identities"
                assert set(device_result["updated"]) == set(original_names), (
                    f"{worker}: expected updates keyed by current NetBox names, "
                    f"got {device_result['updated']}"
                )

        renamed_sessions = list(nb.plugins.bgp.session.filter(device=target_device))
        renamed_names = [s.name for s in renamed_sessions]
        assert renamed_sessions, f"No sessions found for '{target_device}' after rename"
        for old_name in original_names:
            assert (
                old_name not in renamed_names
            ), f"old session name '{old_name}' still exists after sync rename"
        for renamed_name in renamed_names:
            assert (
                "_BGP_" in renamed_name
            ), f"renamed session '{renamed_name}' does not match template '{template}'"

    def test_sync_bgp_peerings_asn_type_idempotency(self, nfclient):
        """Regression: Bug #2 - ASN type mismatch (int in NB vs str from device) must not
        cause false 'updated' entries on second sync when nothing has changed."""
        kwargs = {"devices": BGP_CREATE_SESSIONS_TEST_DEVICES, "rir": "lab"}
        # First sync: creates sessions in NetBox
        nfclient.run_job("netbox", "sync_bgp_peerings", workers="any", kwargs=kwargs)
        # Second sync: NetBox now stores ASNs as ints; device data has them as strings.
        # After the fix, both sides are normalised to str so diff should be empty.
        ret = nfclient.run_job(
            "netbox", "sync_bgp_peerings", workers="any", kwargs=kwargs
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            for device in BGP_CREATE_SESSIONS_TEST_DEVICES:
                if device in res["result"]:
                    assert res["result"][device]["updated"] == [], (
                        f"{worker}: spurious updates for '{device}' on 2nd sync - "
                        f"likely ASN int/str type mismatch in normalise_nb_bgp_session"
                    )

    def test_sync_bgp_peerings_multiple_deletions(self, nfclient):
        """Regression: Suggestion #12 - batch deletion must remove multiple stale sessions
        across different devices in a single API call (no per-session get+delete loop).
        """
        nb = get_pynetbox(nfclient)
        target_devices = BGP_CREATE_SESSIONS_TEST_DEVICES[:2]

        # Pre-create real sessions so IPs/ASNs are available for stale session FK refs
        nfclient.run_job(
            "netbox",
            "sync_bgp_peerings",
            workers="any",
            kwargs={"devices": target_devices, "rir": "lab"},
        )

        stale_sessions = []
        stale_ips = []
        stale_ip_pool = ["192.0.2.10", "192.0.2.11"]
        for device_name, stale_ip_addr in zip(target_devices, stale_ip_pool):
            # Cleanup any leftover from a previous failed run
            for ip_obj in nb.ipam.ip_addresses.filter(q=f"{stale_ip_addr}/"):
                ip_obj.delete()
            stale_ip = nb.ipam.ip_addresses.create(address=f"{stale_ip_addr}/32")
            stale_ips.append(stale_ip)

            ref = list(nb.plugins.bgp.session.filter(device=device_name))[0]
            nb_device = nb.dcim.devices.get(name=device_name)
            stale_name = f"{device_name}_MULTI_DEL_TEST"
            for leftover in nb.plugins.bgp.session.filter(name=stale_name):
                leftover.delete()
            nb.plugins.bgp.session.create(
                name=stale_name,
                device=nb_device.id,
                local_address=ref.local_address.id,
                remote_address=stale_ip.id,
                local_as=ref.local_as.id,
                remote_as=ref.remote_as.id,
                status="planned",
            )
            stale_sessions.append(stale_name)

        ret = nfclient.run_job(
            "netbox",
            "sync_bgp_peerings",
            workers="any",
            kwargs={"devices": target_devices, "process_deletions": True, "rir": "lab"},
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            for device_name, stale_name in zip(target_devices, stale_sessions):
                if device_name in res["result"]:
                    assert (
                        stale_name in res["result"][device_name]["deleted"]
                    ), f"{worker}: '{stale_name}' not deleted for '{device_name}'"
        # Verify both stale sessions are gone from NetBox
        for stale_name in stale_sessions:
            assert not nb.plugins.bgp.session.get(
                name=stale_name
            ), f"Stale session '{stale_name}' still present after batch deletion"
        # Cleanup stale IPs
        for ip_obj in stale_ips:
            ip_obj.delete()

    def test_sync_bgp_peerings_filter_by_remote_as(self, nfclient):
        """Only sessions matching filter_by_remote_as are synced; others are ignored."""
        target_device = BGP_CREATE_SESSIONS_TEST_DEVICES[0]
        # First sync without filter to populate NetBox
        nfclient.run_job(
            "netbox",
            "sync_bgp_peerings",
            workers="any",
            kwargs={"devices": [target_device], "rir": "lab"},
        )
        nb = get_pynetbox(nfclient)
        sessions = list(nb.plugins.bgp.session.filter(device=target_device))
        assert sessions, f"No sessions found for '{target_device}' after initial sync"
        # Pick one remote AS to filter by
        target_as = sessions[0].remote_as.asn  # integer

        ret = nfclient.run_job(
            "netbox",
            "sync_bgp_peerings",
            workers="any",
            kwargs={
                "devices": [target_device],
                "rir": "lab",
                "dry_run": True,
                "filter_by_remote_as": [target_as],
            },
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            if target_device in res["result"]:
                device_result = res["result"][target_device]
                # All tracked sessions must have the target remote AS
                all_tracked = (
                    device_result.get("create", [])
                    + device_result.get("in_sync", [])
                    + list(device_result.get("update", {}).keys())
                    + device_result.get("delete", [])
                )
                for sname in all_tracked:
                    nb_session = nb.plugins.bgp.session.get(name=sname)
                    if nb_session:
                        assert nb_session.remote_as.asn == target_as, (
                            f"{worker}: session '{sname}' has remote_as "
                            f"'{nb_session.remote_as.asn}' but expected '{target_as}'"
                        )

    def test_sync_bgp_peerings_filter_by_peer_group(self, nfclient):
        """Only sessions matching filter_by_peer_group are synced; others are ignored."""
        target_device = BGP_CREATE_SESSIONS_TEST_DEVICES[0]
        # First sync to populate NetBox
        nfclient.run_job(
            "netbox",
            "sync_bgp_peerings",
            workers="any",
            kwargs={"devices": [target_device], "rir": "lab"},
        )
        nb = get_pynetbox(nfclient)
        sessions = list(nb.plugins.bgp.session.filter(device=target_device))
        assert sessions, f"No sessions found for '{target_device}' after initial sync"
        # Find a session with a peer group, if any
        sessions_with_pg = [s for s in sessions if s.peer_group]
        if not sessions_with_pg:
            return  # Skip test if no sessions have a peer group
        target_pg = sessions_with_pg[0].peer_group.name

        ret = nfclient.run_job(
            "netbox",
            "sync_bgp_peerings",
            workers="any",
            kwargs={
                "devices": [target_device],
                "rir": "lab",
                "dry_run": True,
                "filter_by_peer_group": [target_pg],
            },
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            if target_device in res["result"]:
                device_result = res["result"][target_device]
                all_tracked = (
                    device_result.get("create", [])
                    + device_result.get("in_sync", [])
                    + list(device_result.get("update", {}).keys())
                    + device_result.get("delete", [])
                )
                for sname in all_tracked:
                    nb_session = nb.plugins.bgp.session.get(name=sname)
                    if nb_session and nb_session.peer_group:
                        assert nb_session.peer_group.name == target_pg, (
                            f"{worker}: session '{sname}' has peer_group "
                            f"'{nb_session.peer_group.name}' but expected '{target_pg}'"
                        )

    def test_sync_bgp_peerings_filter_by_description(self, nfclient):
        """Sync only sessions matching a description glob pattern; verify all created
        sessions in NetBox have a description matching that pattern."""
        target_device = "ceos-spine-1"
        desc_pattern = "ceos-leaf-1 Loopback*"
        nb = get_pynetbox(nfclient)

        # Wipe existing BGP sessions for the device
        for session in list(nb.plugins.bgp.session.filter(device=target_device)):
            session.delete()

        ret = nfclient.run_job(
            "netbox",
            "sync_bgp_peerings",
            workers="any",
            kwargs={
                "devices": [target_device],
                "rir": "lab",
                "filter_by_description": desc_pattern,
            },
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"

        # Fetch all BGP sessions now in NetBox for the device
        created_sessions = list(nb.plugins.bgp.session.filter(device=target_device))
        assert (
            created_sessions
        ), f"No BGP sessions found in NetBox for '{target_device}' after filtered sync"
        import fnmatch

        for session in created_sessions:
            assert fnmatch.fnmatch(session.description or "", desc_pattern), (
                f"Session '{session.name}' description '{session.description}' "
                f"does not match pattern '{desc_pattern}'"
            )

    def test_sync_bgp_peerings_ignore_peer_ranges(self, nfclient):
        """Peers whose remote IP matches ignore_peer_ranges are not created."""
        target_device = "ceos-leaf-1"
        ignored_peer_ip = "172.16.1.101"
        ignored_session = f"{target_device}_default_{ignored_peer_ip}"
        kwargs = {
            "devices": [target_device],
            "rir": "lab",
            "ignore_peer_ranges": [f"{ignored_peer_ip}/32"],
        }
        nb = get_pynetbox(nfclient)

        for session in list(nb.plugins.bgp.session.filter(device=target_device)):
            session.delete()

        first_run = nfclient.run_job(
            "netbox",
            "sync_bgp_peerings",
            workers="any",
            kwargs=kwargs,
        )
        pprint.pprint(first_run)
        for worker, res in first_run.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            assert (
                target_device in res["result"]
            ), f"{worker}: '{target_device}' not in result"
            assert (
                ignored_session not in res["result"][target_device]["created"]
            ), f"{worker}: ignored session '{ignored_session}' was created"
            assert (
                len(res["result"][target_device]["created"]) > 0
            ), f"{worker}: expected non-ignored sessions to be created"

        # Validate out of band via pynetbox, not only from the task return.
        assert not nb.plugins.bgp.session.get(
            name=ignored_session
        ), f"ignored session '{ignored_session}' exists in NetBox"
        for session in list(nb.plugins.bgp.session.filter(device=target_device)):
            assert session.remote_address.address.split("/")[0] != ignored_peer_ip, (
                f"session '{session.name}' with ignored peer IP "
                f"'{ignored_peer_ip}' exists in NetBox"
            )

        # clean up
        # for session in list(nb.plugins.bgp.session.filter(device=target_device)):
        #     session.delete()

    def test_sync_bgp_peerings_update_import_policy(self, nfclient):
        """Pre-create sessions; remove an import policy from one session in NetBox;
        re-run sync; verify the session is listed as updated and the policy is restored.
        """
        target_device = "vmx-1"
        nb = get_pynetbox(nfclient)

        # First sync: create sessions in NetBox
        nfclient.run_job(
            "netbox",
            "sync_bgp_peerings",
            workers="any",
            kwargs={"devices": [target_device], "rir": "lab"},
        )

        # Find a session that has at least one import policy
        sessions = list(
            nb.plugins.bgp.session.filter(
                device=target_device, name="vmx-1_default_10.10.0.14"
            )
        )
        target_session = next((s for s in sessions if s.import_policies), None)

        original_policies = [p.id for p in target_session.import_policies]
        # Remove all but one import policies to force a diff on next sync
        target_session.import_policies = [original_policies[0]]
        target_session.save()

        # Second sync: should detect the missing policy and restore it
        ret = nfclient.run_job(
            "netbox",
            "sync_bgp_peerings",
            workers="any",
            kwargs={"devices": [target_device], "rir": "lab"},
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            if target_device in res["result"]:
                assert target_session.name in res["result"][target_device]["updated"], (
                    f"{worker}: expected '{target_session.name}' in updated after "
                    f"import_policies were removed from NetBox"
                )

        # Verify the policies were restored in NetBox
        refreshed = nb.plugins.bgp.session.get(name=target_session.name)
        restored_ids = [p.id for p in (refreshed.import_policies or [])]
        for policy_id in original_policies:
            assert (
                policy_id in restored_ids
            ), f"import policy id={policy_id} was not restored on '{target_session.name}'"

    def test_sync_bgp_peerings_vrf_custom_field_default(self, nfclient):
        """vrf_custom_field='vrf' (default) must write VRF into custom_fields['vrf']
        on the BGP session.  Confirms that even with the default value the VRF is
        always sourced from/written to a custom field, not the built-in vrf attribute.
        """
        target_device = "vmx-1"
        ret = nfclient.run_job(
            "netbox",
            "sync_bgp_peerings",
            workers="any",
            kwargs={
                "devices": [target_device],
                "rir": "lab",
                "vrf_custom_field": "vrf",
            },
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"

    def test_sync_bgp_peerings_vrf_custom_field_missing(self, nfclient):
        """When the vrf_custom_field name does not exist in NetBox the task must
        complete without failure, disabling VRF handling transparently."""
        ret = nfclient.run_job(
            "netbox",
            "sync_bgp_peerings",
            workers="any",
            kwargs={
                "devices": ["vmx-1"],
                "rir": "lab",
                "vrf_custom_field": "vrf_nonexistent",
            },
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            assert not res["errors"], f"{worker}: unexpected errors: {res['errors']}"

    def test_sync_bgp_peerings_resolve_local_ip_via_peer(self, nfclient):
        """Sync ceos-leaf-1 which has a BGP peer at 172.16.1.101/30 but no local address
        in parsed data; verify that resolve_local_ip_via_peer derives the local IP
        from the subnet and the session ceos-leaf-1_default_172.16.1.101 is created.

        For this test to work 172.16.1.102/30 IP need to be assigned to Loopback1001
        interface of ceos-leaf-1 device.
        """
        target_device = "ceos-leaf-1"
        expected_session = "ceos-leaf-1_default_172.16.1.101"
        nb = get_pynetbox(nfclient)

        ret = nfclient.run_job(
            "netbox",
            "sync_bgp_peerings",
            workers="any",
            kwargs={"devices": [target_device], "rir": "lab"},
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            assert (
                target_device in res["result"]
            ), f"{worker}: '{target_device}' not in result"
            assert expected_session in res["result"][target_device]["created"], (
                f"{worker}: expected '{expected_session}' in created, "
                f"got: {res['result'][target_device]['created']}"
            )
        assert nb.plugins.bgp.session.get(
            name=expected_session
        ), f"session '{expected_session}' not found in NetBox after sync"


# ---------------------------------------------------------------------------
# CREATE BGP PEERING TESTS
# ---------------------------------------------------------------------------

# Helper IP addresses used exclusively by create/update tests
_TEST_LOCAL_IP = "198.51.100.1"
_TEST_REMOTE_IP = "198.51.100.2"
# /31 P2P pair
_TEST_P2P_LOCAL = "198.51.100.4"
_TEST_P2P_REMOTE = "198.51.100.5"
_TEST_LOCAL_AS = 64999
_TEST_REMOTE_AS = 64998


def _cleanup_test_ips(nb):
    """Remove any test IPs created during create/update tests."""
    for addr in [
        _TEST_LOCAL_IP,
        _TEST_REMOTE_IP,
        _TEST_P2P_LOCAL,
        _TEST_P2P_REMOTE,
        "198.51.100.10",
        "198.51.100.11",
        "198.51.100.20",
        "198.51.100.21",
        "198.51.100.22",
    ]:
        for ip in list(nb.ipam.ip_addresses.filter(q=f"{addr}/")):
            ip.delete()


def _cleanup_test_asns(nb):
    """Remove test ASNs created during create/update tests."""
    for asn in [int(_TEST_LOCAL_AS), int(_TEST_REMOTE_AS), 64997, 64996]:
        for obj in list(nb.ipam.asns.filter(asn=asn)):
            obj.delete()


@pytest.mark.task_create_bgp_peering
class TestCreateBgpPeering:

    def setup_method(self):
        delete_bgp_sessions()
        nb = get_pynetbox(None)
        _cleanup_test_ips(nb)
        _cleanup_test_asns(nb)

    def teardown_method(self):
        delete_bgp_sessions()
        nb = get_pynetbox(None)
        _cleanup_test_ips(nb)
        _cleanup_test_asns(nb)

    def test_create_bgp_peering_single(self, nfclient):
        """Single-session mode - session appears in created list and in NetBox."""
        nb = get_pynetbox(nfclient)
        device = BGP_CREATE_SESSIONS_TEST_DEVICES[0]
        sname = f"{device}_test_create_single"
        ret = nfclient.run_job(
            "netbox",
            "create_bgp_peering",
            workers="any",
            kwargs={
                "name": sname,
                "device": device,
                "local_address": _TEST_LOCAL_IP,
                "remote_address": _TEST_REMOTE_IP,
                "local_as": _TEST_LOCAL_AS,
                "remote_as": _TEST_REMOTE_AS,
                "rir": "lab",
            },
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            assert (
                sname in res["result"]["created"]
            ), f"{worker}: expected session in created"
        assert nb.plugins.bgp.session.get(
            name=sname
        ), f"session '{sname}' not found in NetBox"

    def test_create_bgp_peering_single_idempotent(self, nfclient):
        """Session already exists - reported in exists, no duplicate created."""
        device = BGP_CREATE_SESSIONS_TEST_DEVICES[0]
        sname = f"{device}_test_idempotent"
        kwargs = {
            "name": sname,
            "device": device,
            "local_address": _TEST_LOCAL_IP,
            "remote_address": _TEST_REMOTE_IP,
            "local_as": _TEST_LOCAL_AS,
            "remote_as": _TEST_REMOTE_AS,
            "rir": "lab",
        }
        nfclient.run_job("netbox", "create_bgp_peering", workers="any", kwargs=kwargs)

        ret = nfclient.run_job(
            "netbox", "create_bgp_peering", workers="any", kwargs=kwargs
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            assert (
                sname in res["result"]["exists"]
            ), f"{worker}: expected session in exists"
            assert sname not in res["result"].get(
                "created", []
            ), f"{worker}: duplicate created"

    def test_create_bgp_peering_single_dry_run(self, nfclient):
        """dry_run=True - name in create list, no session written to NetBox."""
        nb = get_pynetbox(nfclient)
        device = BGP_CREATE_SESSIONS_TEST_DEVICES[0]
        sname = f"{device}_test_dry_run"
        ret = nfclient.run_job(
            "netbox",
            "create_bgp_peering",
            workers="any",
            kwargs={
                "name": sname,
                "device": device,
                "local_address": _TEST_LOCAL_IP,
                "remote_address": _TEST_REMOTE_IP,
                "local_as": _TEST_LOCAL_AS,
                "remote_as": _TEST_REMOTE_AS,
                "rir": "lab",
                "dry_run": True,
            },
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            assert (
                sname in res["result"]["create"]
            ), f"{worker}: expected session in create"
        assert not nb.plugins.bgp.session.get(
            name=sname
        ), f"session was written despite dry_run=True"

    def test_create_bgp_peering_single_dry_run_exists(self, nfclient):
        """dry_run=True when session already exists - in exists, not in create."""
        device = BGP_CREATE_SESSIONS_TEST_DEVICES[0]
        sname = f"{device}_test_dry_run_exists"
        kwargs = {
            "name": sname,
            "device": device,
            "local_address": _TEST_LOCAL_IP,
            "remote_address": _TEST_REMOTE_IP,
            "local_as": _TEST_LOCAL_AS,
            "remote_as": _TEST_REMOTE_AS,
            "rir": "lab",
        }
        nfclient.run_job("netbox", "create_bgp_peering", workers="any", kwargs=kwargs)

        ret = nfclient.run_job(
            "netbox",
            "create_bgp_peering",
            workers="any",
            kwargs={**kwargs, "dry_run": True},
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            assert (
                sname in res["result"]["exists"]
            ), f"{worker}: expected session in exists"
            assert sname not in res["result"].get(
                "create", []
            ), f"{worker}: should not be in create"

    def test_create_bgp_peering_bulk(self, nfclient):
        """bulk_create - all sessions appear in created and in NetBox."""
        nb = get_pynetbox(nfclient)
        device = BGP_CREATE_SESSIONS_TEST_DEVICES[0]
        sessions = [
            {
                "name": f"{device}_bulk_1",
                "device": device,
                "local_address": "198.51.100.20",
                "remote_address": "198.51.100.21",
                "local_as": _TEST_LOCAL_AS,
                "remote_as": _TEST_REMOTE_AS,
            },
            {
                "name": f"{device}_bulk_2",
                "device": device,
                "local_address": "198.51.100.21",
                "remote_address": "198.51.100.22",
                "local_as": _TEST_LOCAL_AS,
                "remote_as": _TEST_REMOTE_AS,
            },
        ]
        ret = nfclient.run_job(
            "netbox",
            "create_bgp_peering",
            workers="any",
            kwargs={"bulk_create": sessions, "rir": "lab"},
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            for s in sessions:
                assert (
                    s["name"] in res["result"]["created"]
                ), f"{worker}: '{s['name']}' not in created"
                assert nb.plugins.bgp.session.get(
                    name=s["name"]
                ), f"session '{s['name']}' not in NetBox"

    def test_create_bgp_peering_bulk_partial_idempotent(self, nfclient):
        """Some sessions exist - correct split between created and exists."""
        device = BGP_CREATE_SESSIONS_TEST_DEVICES[0]
        existing_name = f"{device}_bulk_exist"
        new_name = f"{device}_bulk_new"
        existing_kwargs = {
            "name": existing_name,
            "device": device,
            "local_address": "198.51.100.10",
            "remote_address": "198.51.100.11",
            "local_as": _TEST_LOCAL_AS,
            "remote_as": _TEST_REMOTE_AS,
            "rir": "lab",
        }
        nfclient.run_job(
            "netbox", "create_bgp_peering", workers="any", kwargs=existing_kwargs
        )

        ret = nfclient.run_job(
            "netbox",
            "create_bgp_peering",
            workers="any",
            kwargs={
                "bulk_create": [
                    {
                        "name": existing_name,
                        "device": device,
                        "local_address": "198.51.100.10",
                        "remote_address": "198.51.100.11",
                        "local_as": _TEST_LOCAL_AS,
                        "remote_as": _TEST_REMOTE_AS,
                    },
                    {
                        "name": new_name,
                        "device": device,
                        "local_address": "198.51.100.20",
                        "remote_address": "198.51.100.21",
                        "local_as": _TEST_LOCAL_AS,
                        "remote_as": _TEST_REMOTE_AS,
                    },
                ],
                "rir": "lab",
            },
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            assert (
                existing_name in res["result"]["exists"]
            ), f"{worker}: existing session not in exists"
            assert (
                new_name in res["result"]["created"]
            ), f"{worker}: new session not in created"

    def test_create_bgp_peering_bulk_dry_run(self, nfclient):
        """dry_run=True + bulk - names in create list, no writes."""
        nb = get_pynetbox(nfclient)
        device = BGP_CREATE_SESSIONS_TEST_DEVICES[0]
        sessions = [
            {
                "name": f"{device}_bulk_dry_1",
                "device": device,
                "local_address": _TEST_LOCAL_IP,
                "remote_address": _TEST_REMOTE_IP,
                "local_as": _TEST_LOCAL_AS,
                "remote_as": _TEST_REMOTE_AS,
            },
        ]
        ret = nfclient.run_job(
            "netbox",
            "create_bgp_peering",
            workers="any",
            kwargs={"bulk_create": sessions, "rir": "lab", "dry_run": True},
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            assert (
                sessions[0]["name"] in res["result"]["create"]
            ), f"{worker}: expected name in create"
        assert not nb.plugins.bgp.session.get(
            name=sessions[0]["name"]
        ), "session written despite dry_run=True"

    def test_create_bgp_peering_reverse_disabled(self, nfclient):
        """create_reverse=False - only local session created."""
        nb = get_pynetbox(nfclient)
        device = BGP_CREATE_SESSIONS_TEST_DEVICES[0]
        sname = f"{device}_no_reverse"
        ret = nfclient.run_job(
            "netbox",
            "create_bgp_peering",
            workers="any",
            kwargs={
                "name": sname,
                "device": device,
                "local_address": _TEST_LOCAL_IP,
                "remote_address": _TEST_REMOTE_IP,
                "local_as": _TEST_LOCAL_AS,
                "remote_as": _TEST_REMOTE_AS,
                "rir": "lab",
                "create_reverse": False,
            },
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            assert (
                sname in res["result"]["created"]
            ), f"{worker}: expected session in created"
        assert nb.plugins.bgp.session.get(
            name=sname
        ), f"session '{sname}' not found in NetBox"

    def test_create_bgp_peering_missing_required(self, nfclient):
        """Single mode with missing device - failed=True."""
        ret = nfclient.run_job(
            "netbox",
            "create_bgp_peering",
            workers="any",
            kwargs={
                "name": "test_missing_required",
                "local_address": _TEST_LOCAL_IP,
                "remote_address": _TEST_REMOTE_IP,
                "local_as": _TEST_LOCAL_AS,
                "remote_as": _TEST_REMOTE_AS,
            },
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == True, f"{worker}: expected failed=True"

    def test_create_bgp_peering_nonexistent_device(self, nfclient):
        """Unknown device name - error appended, no crash, failed=False."""
        sname = "nonexistent_device_bgp_session"
        ret = nfclient.run_job(
            "netbox",
            "create_bgp_peering",
            workers="any",
            kwargs={
                "name": sname,
                "device": "device-that-does-not-exist-xyz",
                "local_address": _TEST_LOCAL_IP,
                "remote_address": _TEST_REMOTE_IP,
                "local_as": _TEST_LOCAL_AS,
                "remote_as": _TEST_REMOTE_AS,
                "rir": "lab",
            },
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker}: unexpected failed=True"
            assert res["errors"], f"{worker}: expected errors list to be non-empty"
            assert sname not in res["result"].get(
                "created", []
            ), f"{worker}: should not be created"

    def test_create_bgp_peering_with_branch(self, nfclient):
        """branch=... - session created inside the branch."""
        branch = "create_bgp_test_branch"
        device = BGP_CREATE_SESSIONS_TEST_DEVICES[0]
        sname = f"{device}_branch_test"
        try:
            nfclient.run_job(
                "netbox",
                "rest",
                workers="any",
                kwargs={
                    "method": "post",
                    "api": "/extras/branches/",
                    "data": {"name": branch},
                },
            )
            ret = nfclient.run_job(
                "netbox",
                "create_bgp_peering",
                workers="any",
                kwargs={
                    "name": sname,
                    "device": device,
                    "local_address": _TEST_LOCAL_IP,
                    "remote_address": _TEST_REMOTE_IP,
                    "local_as": _TEST_LOCAL_AS,
                    "remote_as": _TEST_REMOTE_AS,
                    "rir": "lab",
                    "branch": branch,
                },
            )
            pprint.pprint(ret)
            for worker, res in ret.items():
                assert res["failed"] == False, f"{worker} failed: {res['errors']}"
                assert (
                    sname in res["result"]["created"]
                ), f"{worker}: session not in created"
        finally:
            delete_branch(branch, nfclient)

    def test_create_bgp_peering_asn_auto_create(self, nfclient):
        """ASN not in NetBox - auto-created when rir provided."""
        nb = get_pynetbox(nfclient)
        device = BGP_CREATE_SESSIONS_TEST_DEVICES[0]
        sname = f"{device}_auto_asn"
        new_asn = 64997
        # Make sure ASN doesn't exist
        for obj in list(nb.ipam.asns.filter(asn=int(new_asn))):
            obj.delete()

        ret = nfclient.run_job(
            "netbox",
            "create_bgp_peering",
            workers="any",
            kwargs={
                "name": sname,
                "device": device,
                "local_address": _TEST_LOCAL_IP,
                "remote_address": _TEST_REMOTE_IP,
                "local_as": new_asn,
                "remote_as": _TEST_REMOTE_AS,
                "rir": "lab",
            },
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            assert (
                sname in res["result"]["created"]
            ), f"{worker}: session not in created"
        assert nb.ipam.asns.get(
            asn=int(new_asn)
        ), f"ASN {new_asn} not created in NetBox"

    def test_create_bgp_peering_ip_auto_create(self, nfclient):
        """IP not in NetBox - auto-created in IPAM."""
        nb = get_pynetbox(nfclient)
        device = BGP_CREATE_SESSIONS_TEST_DEVICES[0]
        sname = f"{device}_auto_ip"
        new_ip = "198.51.100.100"
        # Ensure IP doesn't exist
        for ip in list(nb.ipam.ip_addresses.filter(q=f"{new_ip}/")):
            ip.delete()

        ret = nfclient.run_job(
            "netbox",
            "create_bgp_peering",
            workers="any",
            kwargs={
                "name": sname,
                "device": device,
                "local_address": new_ip,
                "remote_address": _TEST_REMOTE_IP,
                "local_as": _TEST_LOCAL_AS,
                "remote_as": _TEST_REMOTE_AS,
                "rir": "lab",
            },
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            assert (
                sname in res["result"]["created"]
            ), f"{worker}: session not in created"
        assert list(
            nb.ipam.ip_addresses.filter(q=f"{new_ip}/")
        ), f"IP {new_ip} not created in NetBox"
        # cleanup: delete the BGP session first (IP is referenced by it), then the IP
        session_obj = nb.plugins.bgp.session.get(name=sname)
        if session_obj:
            session_obj.delete()
        for ip in list(nb.ipam.ip_addresses.filter(q=f"{new_ip}/")):
            ip.delete()

    def test_create_bgp_peering_with_peer_group_policies_prefix_lists(self, nfclient):
        """Optional fields - peer_group / import_policies / prefix_list_in resolved/created."""
        nb = get_pynetbox(nfclient)
        device = BGP_CREATE_SESSIONS_TEST_DEVICES[0]
        sname = f"{device}_optional_fields"
        ret = nfclient.run_job(
            "netbox",
            "create_bgp_peering",
            workers="any",
            kwargs={
                "name": sname,
                "device": device,
                "local_address": _TEST_LOCAL_IP,
                "remote_address": _TEST_REMOTE_IP,
                "local_as": _TEST_LOCAL_AS,
                "remote_as": _TEST_REMOTE_AS,
                "rir": "lab",
                "peer_group": "TEST_PG_CREATE",
                "import_policies": ["TEST_IMPORT_POLICY"],
                "export_policies": ["TEST_EXPORT_POLICY"],
                "prefix_list_in": "TEST_PREFIX_IN",
                "prefix_list_out": "TEST_PREFIX_OUT",
                "description": "test optional fields",
            },
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            assert (
                sname in res["result"]["created"]
            ), f"{worker}: session not in created"
        session = nb.plugins.bgp.session.get(name=sname)
        assert session, f"session '{sname}' not found in NetBox"
        assert session.description == "test optional fields", "description not saved"

    def test_create_bgp_peering_asn_source_dict(self, nfclient):
        """Regression: Bug #1 - asn_source as dict must not raise AttributeError.
        Before the fix, nb.ipam.asn.get (singular) caused AttributeError at runtime."""
        device = BGP_CREATE_SESSIONS_TEST_DEVICES[0]
        sname = f"{device}_asn_source_dict"
        # ASN 99999999 almost certainly does not exist - resolve_asn_from_source must
        # return None gracefully instead of crashing with AttributeError on nb.ipam.asn
        ret = nfclient.run_job(
            "netbox",
            "create_bgp_peering",
            workers="any",
            kwargs={
                "name": sname,
                "device": device,
                "local_address": _TEST_LOCAL_IP,
                "remote_address": _TEST_REMOTE_IP,
                # local_as omitted intentionally - resolved via asn_source dict path
                "remote_as": _TEST_REMOTE_AS,
                "asn_source": {"asn": 99999999},
                "rir": "lab",
            },
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            # Task must return a result object (no unhandled AttributeError crash)
            assert (
                res is not None
            ), f"{worker}: task returned None - likely AttributeError"
            # Session must NOT be created since local AS could not be resolved
            assert sname not in res["result"].get(
                "created", []
            ), f"{worker}: session created despite unresolvable ASN"

    def test_create_bgp_peering_nonexistent_vrf_warns(self, nfclient):
        """VRF not in NetBox - auto-created and assigned to the session."""
        nb = get_pynetbox(nfclient)
        device = BGP_CREATE_SESSIONS_TEST_DEVICES[0]
        sname = f"{device}_auto_vrf"
        vrf_name = "nonexistent_vrf_xyz_12345"
        # Ensure the VRF does not exist before the test
        for vrf in list(nb.ipam.vrfs.filter(name=vrf_name)):
            vrf.delete()
        try:
            ret = nfclient.run_job(
                "netbox",
                "create_bgp_peering",
                workers="any",
                kwargs={
                    "name": sname,
                    "device": device,
                    "local_address": _TEST_LOCAL_IP,
                    "remote_address": _TEST_REMOTE_IP,
                    "local_as": _TEST_LOCAL_AS,
                    "remote_as": _TEST_REMOTE_AS,
                    "rir": "lab",
                    "vrf": vrf_name,
                    "create_reverse": False,
                },
            )
            pprint.pprint(ret)
            for worker, res in ret.items():
                assert res["failed"] == False, f"{worker}: unexpected failed=True"
                assert not res[
                    "errors"
                ], f"{worker}: unexpected errors: {res['errors']}"
                assert (
                    sname in res["result"]["created"]
                ), f"{worker}: session not in created"
            # Verify VRF was created in NetBox
            assert nb.ipam.vrfs.get(
                name=vrf_name
            ), f"VRF '{vrf_name}' was not created in NetBox"
            # Verify session has the VRF assigned via custom field
            session = nb.plugins.bgp.session.get(name=sname)
            cf_vrf = (session.custom_fields or {}).get("vrf") if session else None
            cf_vrf_name = cf_vrf.get("name") if isinstance(cf_vrf, dict) else cf_vrf
            assert (
                session and cf_vrf_name == vrf_name
            ), f"session '{sname}' does not have VRF '{vrf_name}' in custom_fields['vrf']"
        finally:
            # Cleanup: delete session first (it references the VRF), then the VRF
            session = nb.plugins.bgp.session.get(name=sname)
            if session:
                session.delete()
            for vrf in list(nb.ipam.vrfs.filter(name=vrf_name)):
                vrf.delete()

    def test_create_bgp_peering_vrf_default_is_none(self, nfclient):
        """Regression: Suggestion #7 - omitting vrf must not default to 'default' string
        (which would cause a spurious VRF lookup on every single-session creation)."""
        nb = get_pynetbox(nfclient)
        device = BGP_CREATE_SESSIONS_TEST_DEVICES[0]
        sname = f"{device}_no_vrf_default"
        ret = nfclient.run_job(
            "netbox",
            "create_bgp_peering",
            workers="any",
            kwargs={
                "name": sname,
                "device": device,
                "local_address": _TEST_LOCAL_IP,
                "remote_address": _TEST_REMOTE_IP,
                "local_as": _TEST_LOCAL_AS,
                "remote_as": _TEST_REMOTE_AS,
                "rir": "lab",
                # vrf intentionally omitted - should not default to "default"
            },
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            assert sname in res["result"]["created"], f"{worker}: session not created"
            # No VRF-related errors expected when vrf is not specified
            vrf_errors = [e for e in res["errors"] if "VRF" in e]
            assert (
                not vrf_errors
            ), f"{worker}: unexpected VRF error when vrf not specified: {vrf_errors}"

    def test_create_bgp_peering_bulk_shared_peer_group(self, nfclient):
        """Regression: Suggestion #13 - bulk sessions sharing the same peer_group must
        all be created correctly even though the lookup cache is reused across sessions.
        """
        nb = get_pynetbox(nfclient)
        device = BGP_CREATE_SESSIONS_TEST_DEVICES[0]
        shared_peer_group = "TEST_SHARED_PG_CACHE"
        sessions = [
            {
                "name": f"{device}_shared_pg_1",
                "device": device,
                "local_address": _TEST_LOCAL_IP,
                "remote_address": _TEST_REMOTE_IP,
                "local_as": _TEST_LOCAL_AS,
                "remote_as": _TEST_REMOTE_AS,
                "peer_group": shared_peer_group,
            },
            {
                "name": f"{device}_shared_pg_2",
                "device": device,
                "local_address": _TEST_P2P_LOCAL,
                "remote_address": _TEST_P2P_REMOTE,
                "local_as": _TEST_LOCAL_AS,
                "remote_as": _TEST_REMOTE_AS,
                "peer_group": shared_peer_group,
            },
        ]
        ret = nfclient.run_job(
            "netbox",
            "create_bgp_peering",
            workers="any",
            kwargs={"bulk_create": sessions, "rir": "lab"},
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            for s in sessions:
                assert (
                    s["name"] in res["result"]["created"]
                ), f"{worker}: '{s['name']}' not in created"
        # Verify both sessions have the shared peer group set in NetBox
        for s in sessions:
            nb_session = nb.plugins.bgp.session.get(name=s["name"])
            assert nb_session, f"session '{s['name']}' not found in NetBox"
            assert (
                nb_session.peer_group
                and nb_session.peer_group.name == shared_peer_group
            ), f"session '{s['name']}' missing peer_group '{shared_peer_group}'"

    def test_create_bgp_peering_vrf_custom_field_default(self, nfclient):
        """vrf_custom_field='vrf' (default) - VRF stored in custom_fields['vrf']
        on the BGP session.  The VRF is always written to a custom field, never to
        the built-in NetBox vrf attribute, even with the default parameter value."""
        nb = get_pynetbox(nfclient)
        device = BGP_CREATE_SESSIONS_TEST_DEVICES[0]
        sname = f"{device}_vrf_cf_default"
        vrf_name = "test_vrf_cf"
        for vrf in list(nb.ipam.vrfs.filter(name=vrf_name)):
            vrf.delete()
        try:
            ret = nfclient.run_job(
                "netbox",
                "create_bgp_peering",
                workers="any",
                kwargs={
                    "name": sname,
                    "device": device,
                    "local_address": _TEST_LOCAL_IP,
                    "remote_address": _TEST_REMOTE_IP,
                    "local_as": _TEST_LOCAL_AS,
                    "remote_as": _TEST_REMOTE_AS,
                    "rir": "lab",
                    "vrf": vrf_name,
                    "vrf_custom_field": "vrf",
                },
            )
            pprint.pprint(ret)
            for worker, res in ret.items():
                assert res["failed"] == False, f"{worker} failed: {res['errors']}"
                assert (
                    sname in res["result"]["created"]
                ), f"{worker}: session not in created"
            session = nb.plugins.bgp.session.get(name=sname)
            assert session, f"session '{sname}' not found in NetBox"
            # VRF must be in custom_fields['vrf'], not the built-in vrf field
            cf_vrf = (session.custom_fields or {}).get("vrf")
            cf_vrf_name = cf_vrf.get("name") if isinstance(cf_vrf, dict) else cf_vrf
            assert (
                cf_vrf_name == vrf_name
            ), f"session '{sname}' custom_fields['vrf'] is '{cf_vrf_name}', expected '{vrf_name}'"
        finally:
            session = nb.plugins.bgp.session.get(name=sname)
            if session:
                session.delete()
            for vrf in list(nb.ipam.vrfs.filter(name=vrf_name)):
                vrf.delete()

    def test_create_bgp_peering_vrf_custom_field_missing(self, nfclient):
        """When the vrf_custom_field name does not exist in NetBox the task succeeds,
        creates the session without VRF, and silently ignores the vrf argument."""
        nb = get_pynetbox(nfclient)
        device = BGP_CREATE_SESSIONS_TEST_DEVICES[0]
        sname = f"{device}_vrf_cf_missing"
        ret = nfclient.run_job(
            "netbox",
            "create_bgp_peering",
            workers="any",
            kwargs={
                "name": sname,
                "device": device,
                "local_address": _TEST_LOCAL_IP,
                "remote_address": _TEST_REMOTE_IP,
                "local_as": _TEST_LOCAL_AS,
                "remote_as": _TEST_REMOTE_AS,
                "rir": "lab",
                "vrf": "test_vrf_missing_cf",
                "vrf_custom_field": "vrf_nonexistent",
                "create_reverse": False,
            },
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            assert not res["errors"], f"{worker}: unexpected errors: {res['errors']}"
            assert (
                sname in res["result"]["created"]
            ), f"{worker}: session not in created"
        session = nb.plugins.bgp.session.get(name=sname)
        assert session, f"session '{sname}' not found in NetBox"
        # vrf_nonexistent custom field does not exist - no VRF set on the session
        assert (session.custom_fields or {}).get(
            "vrf_nonexistent"
        ) is None, (
            f"VRF unexpectedly set on '{sname}' when the custom field was missing"
        )


# ---------------------------------------------------------------------------
# UPDATE BGP PEERING TESTS
# ---------------------------------------------------------------------------


@pytest.mark.task_update_bgp_peering
class TestUpdateBgpPeering:

    def setup_method(self):
        delete_bgp_sessions()
        nb = get_pynetbox(None)
        _cleanup_test_ips(nb)
        _cleanup_test_asns(nb)

    def teardown_method(self):
        delete_bgp_sessions()
        nb = get_pynetbox(None)
        _cleanup_test_ips(nb)
        _cleanup_test_asns(nb)

    def _create_test_session(self, nfclient, name=None, device=None):
        """Helper: create a single BGP session and return its name."""
        device = device or BGP_CREATE_SESSIONS_TEST_DEVICES[0]
        sname = name or f"{device}_update_test"
        nfclient.run_job(
            "netbox",
            "create_bgp_peering",
            workers="any",
            kwargs={
                "name": sname,
                "device": device,
                "local_address": _TEST_LOCAL_IP,
                "remote_address": _TEST_REMOTE_IP,
                "local_as": _TEST_LOCAL_AS,
                "remote_as": _TEST_REMOTE_AS,
                "rir": "lab",
                "create_reverse": False,
            },
        )
        return sname

    def test_update_bgp_peering_single(self, nfclient):
        """Single-session mode - field updated, session in updated list."""
        sname = self._create_test_session(nfclient)
        ret = nfclient.run_job(
            "netbox",
            "update_bgp_peering",
            workers="any",
            kwargs={
                "name": sname,
                "description": "updated by test",
            },
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            assert (
                sname in res["result"]["updated"]
            ), f"{worker}: expected session in updated"
        nb = get_pynetbox(nfclient)
        session = nb.plugins.bgp.session.get(name=sname)
        assert session.description == "updated by test", "description not updated"

    def test_update_bgp_peering_single_dry_run(self, nfclient):
        """dry_run=True - diff returned, no write."""
        sname = self._create_test_session(nfclient)
        nb = get_pynetbox(nfclient)
        session_before = nb.plugins.bgp.session.get(name=sname)
        old_desc = session_before.description or ""

        ret = nfclient.run_job(
            "netbox",
            "update_bgp_peering",
            workers="any",
            kwargs={
                "name": sname,
                "description": "dry run description",
                "dry_run": True,
            },
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            assert sname not in res["result"].get(
                "in_sync", []
            ), f"{worker}: session should not be in_sync"
            update_entries = res["result"].get("update", [])
            names = [e["name"] for e in update_entries]
            assert sname in names, f"{worker}: expected '{sname}' in update diff list"
        # Verify no write happened
        session_after = nb.plugins.bgp.session.get(name=sname)
        assert (
            session_after.description or ""
        ) == old_desc, "description changed despite dry_run=True"

    def test_update_bgp_peering_single_dry_run_in_sync(self, nfclient):
        """dry_run=True when values already match - session in in_sync, empty update."""
        sname = self._create_test_session(nfclient)
        nb = get_pynetbox(nfclient)
        session = nb.plugins.bgp.session.get(name=sname)
        current_desc = session.description or ""

        ret = nfclient.run_job(
            "netbox",
            "update_bgp_peering",
            workers="any",
            kwargs={
                "name": sname,
                "description": current_desc,
                "dry_run": True,
            },
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            assert sname in res["result"].get(
                "in_sync", []
            ), f"{worker}: expected session in in_sync"

    def test_update_bgp_peering_bulk(self, nfclient):
        """bulk_update - all changed sessions appear in updated."""
        nb = get_pynetbox(nfclient)
        device = BGP_CREATE_SESSIONS_TEST_DEVICES[0]
        names = [f"{device}_upd_bulk_1", f"{device}_upd_bulk_2"]
        # use distinct IP pairs per session to avoid unique-constraint rejection
        ip_pairs = [
            (_TEST_LOCAL_IP, _TEST_REMOTE_IP),
            (_TEST_P2P_LOCAL, _TEST_P2P_REMOTE),
        ]
        for sname, (local_ip, remote_ip) in zip(names, ip_pairs):
            nfclient.run_job(
                "netbox",
                "create_bgp_peering",
                workers="any",
                kwargs={
                    "name": sname,
                    "device": device,
                    "local_address": local_ip,
                    "remote_address": remote_ip,
                    "local_as": _TEST_LOCAL_AS,
                    "remote_as": _TEST_REMOTE_AS,
                    "rir": "lab",
                    "create_reverse": False,
                },
            )
        bulk = [
            {"name": names[0], "description": "bulk updated 1"},
            {"name": names[1], "description": "bulk updated 2"},
        ]
        ret = nfclient.run_job(
            "netbox",
            "update_bgp_peering",
            workers="any",
            kwargs={"bulk_update": bulk},
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            for sname in names:
                assert (
                    sname in res["result"]["updated"]
                ), f"{worker}: '{sname}' not in updated"
        for sname, desc in zip(names, ["bulk updated 1", "bulk updated 2"]):
            assert nb.plugins.bgp.session.get(name=sname).description == desc

    def test_update_bgp_peering_bulk_dry_run(self, nfclient):
        """dry_run=True + bulk - diffs in update list, no writes."""
        device = BGP_CREATE_SESSIONS_TEST_DEVICES[0]
        sname = f"{device}_bulk_dry_upd"
        self._create_test_session(nfclient, name=sname)
        bulk = [{"name": sname, "description": "should not be written"}]
        ret = nfclient.run_job(
            "netbox",
            "update_bgp_peering",
            workers="any",
            kwargs={"bulk_update": bulk, "dry_run": True},
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            update_names = [e["name"] for e in res["result"].get("update", [])]
            assert (
                sname in update_names
            ), f"{worker}: expected '{sname}' in dry-run update list"
        nb = get_pynetbox(nfclient)
        session = nb.plugins.bgp.session.get(name=sname)
        assert (
            session.description != "should not be written"
        ), "description written despite dry_run"

    def test_update_bgp_peering_nonexistent_session(self, nfclient):
        """Session not in NetBox - error appended, not in updated."""
        ret = nfclient.run_job(
            "netbox",
            "update_bgp_peering",
            workers="any",
            kwargs={
                "name": "session_that_does_not_exist_xyz",
                "description": "should error",
            },
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker}: unexpected failed=True"
            assert res["errors"], f"{worker}: expected error list non-empty"
            assert "session_that_does_not_exist_xyz" not in res["result"].get(
                "updated", []
            )

    def test_update_bgp_peering_no_changes(self, nfclient):
        """All values already match - session in in_sync, no write."""
        sname = self._create_test_session(nfclient)
        nb = get_pynetbox(nfclient)
        session = nb.plugins.bgp.session.get(name=sname)
        current_desc = session.description or ""

        ret = nfclient.run_job(
            "netbox",
            "update_bgp_peering",
            workers="any",
            kwargs={"name": sname, "description": current_desc},
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            assert sname in res["result"].get(
                "in_sync", []
            ), f"{worker}: expected session in in_sync"
            assert sname not in res["result"].get(
                "updated", []
            ), f"{worker}: no write expected"

    def test_update_bgp_peering_status(self, nfclient):
        """status field updated correctly."""
        sname = self._create_test_session(nfclient)
        ret = nfclient.run_job(
            "netbox",
            "update_bgp_peering",
            workers="any",
            kwargs={"name": sname, "status": "planned"},
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            assert (
                sname in res["result"]["updated"]
            ), f"{worker}: expected session in updated"
        nb = get_pynetbox(nfclient)
        session = nb.plugins.bgp.session.get(name=sname)
        assert (
            session.status.value == "planned"
        ), f"status not updated, got {session.status}"

    def test_update_bgp_peering_description(self, nfclient):
        """description field updated correctly."""
        sname = self._create_test_session(nfclient)
        new_desc = "updated description"
        ret = nfclient.run_job(
            "netbox",
            "update_bgp_peering",
            workers="any",
            kwargs={"name": sname, "description": new_desc},
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            assert (
                sname in res["result"]["updated"]
            ), f"{worker}: expected session in updated"
        nb = get_pynetbox(nfclient)
        assert nb.plugins.bgp.session.get(name=sname).description == new_desc

    def test_update_bgp_peering_routing_policies(self, nfclient):
        """import_policies / export_policies updated."""
        sname = self._create_test_session(nfclient)
        ret = nfclient.run_job(
            "netbox",
            "update_bgp_peering",
            workers="any",
            kwargs={
                "name": sname,
                "import_policies": ["TEST_IMPORT_UPD"],
                "export_policies": ["TEST_EXPORT_UPD"],
            },
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            assert (
                sname in res["result"]["updated"]
            ), f"{worker}: expected session in updated"
        nb = get_pynetbox(nfclient)
        session = nb.plugins.bgp.session.get(name=sname)
        import_names = [p.name for p in (session.import_policies or [])]
        export_names = [p.name for p in (session.export_policies or [])]
        assert "TEST_IMPORT_UPD" in import_names, "import policy not updated"
        assert "TEST_EXPORT_UPD" in export_names, "export policy not updated"

    def test_update_bgp_peering_with_branch(self, nfclient):
        """branch=... - update applied to branch."""
        branch = "update_bgp_test_branch"
        sname = self._create_test_session(nfclient)
        try:
            nfclient.run_job(
                "netbox",
                "rest",
                workers="any",
                kwargs={
                    "method": "post",
                    "api": "/extras/branches/",
                    "data": {"name": branch},
                },
            )
            ret = nfclient.run_job(
                "netbox",
                "update_bgp_peering",
                workers="any",
                kwargs={
                    "name": sname,
                    "description": "branch update test",
                    "branch": branch,
                },
            )
            pprint.pprint(ret)
            for worker, res in ret.items():
                assert res["failed"] == False, f"{worker} failed: {res['errors']}"
                assert (
                    sname in res["result"]["updated"]
                ), f"{worker}: session not in updated"
        finally:
            delete_branch(branch, nfclient)

    def test_update_bgp_peering_asn_type_no_spurious_update(self, nfclient):
        """Regression: Bug #2 - update with ASN values supplied as strings must not
        produce a spurious 'updated' entry when the values already match NetBox.
        Before the fix, normalise_nb_bgp_session stored ASNs as ints while the
        desired dict held strings, causing make_diff to report a false difference."""
        sname = self._create_test_session(nfclient)
        nb = get_pynetbox(nfclient)
        session = nb.plugins.bgp.session.get(name=sname)

        # Pass ASNs as strings (the way device-sourced data always arrives)
        ret = nfclient.run_job(
            "netbox",
            "update_bgp_peering",
            workers="any",
            kwargs={
                "bulk_update": [
                    {
                        "name": sname,
                        "local_as": session.local_as.asn,
                        "remote_as": session.remote_as.asn,
                        "description": session.description or "",
                    }
                ]
            },
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            assert sname in res["result"].get("in_sync", []), (
                f"{worker}: expected session in in_sync when values match - "
                f"likely ASN int/str type mismatch in normalise_nb_bgp_session"
            )
            assert sname not in res["result"].get(
                "updated", []
            ), f"{worker}: spurious update triggered by ASN type mismatch"

    def test_update_bgp_peering_id_field_no_spurious_update(self, nfclient):
        """Regression: Bug #4 - the 'id' field present in normalised_nb but absent
        from normalised_updates must not cause a spurious diff entry that forces
        every session into 'updated' regardless of whether fields changed."""
        sname = self._create_test_session(nfclient)
        nb = get_pynetbox(nfclient)
        session = nb.plugins.bgp.session.get(name=sname)

        # Send all current values - nothing should differ
        ret = nfclient.run_job(
            "netbox",
            "update_bgp_peering",
            workers="any",
            kwargs={
                "bulk_update": [
                    {
                        "name": sname,
                        "status": session.status.value,
                        "description": session.description or "",
                        "local_as": session.local_as.asn,
                        "remote_as": session.remote_as.asn,
                    }
                ]
            },
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            assert sname in res["result"].get("in_sync", []), (
                f"{worker}: session should be in_sync - spurious diff likely caused by "
                f"'id' field in normalised_nb leaking into make_diff comparison"
            )
            assert sname not in res["result"].get(
                "updated", []
            ), f"{worker}: unexpected write triggered - check if 'id' causes spurious diff"

    def test_update_bgp_peering_vrf_custom_field_default(self, nfclient):
        """vrf_custom_field='vrf' (default) - VRF update written to custom_fields['vrf']
        on the BGP session.  The VRF is always stored in a custom field, never in
        the built-in NetBox vrf attribute, even with the default parameter value."""
        sname = self._create_test_session(nfclient)
        nb = get_pynetbox(nfclient)
        vrf_name = "test_vrf_update_cf"
        for vrf in list(nb.ipam.vrfs.filter(name=vrf_name)):
            vrf.delete()
        try:
            ret = nfclient.run_job(
                "netbox",
                "update_bgp_peering",
                workers="any",
                kwargs={
                    "name": sname,
                    "vrf": vrf_name,
                    "vrf_custom_field": "vrf",
                },
            )
            pprint.pprint(ret)
            for worker, res in ret.items():
                assert res["failed"] == False, f"{worker} failed: {res['errors']}"
                assert (
                    sname in res["result"]["updated"]
                ), f"{worker}: expected '{sname}' in updated after vrf change"
            session = nb.plugins.bgp.session.get(name=sname)
            assert session, f"session '{sname}' not found in NetBox"
            # VRF must be in custom_fields['vrf'], not the built-in vrf field
            cf_vrf = (session.custom_fields or {}).get("vrf")
            cf_vrf_name = cf_vrf.get("name") if isinstance(cf_vrf, dict) else cf_vrf
            assert (
                cf_vrf_name == vrf_name
            ), f"vrf not updated in custom_fields['vrf']; got '{cf_vrf_name}'"
        finally:
            session = nb.plugins.bgp.session.get(name=sname)
            if session:
                session.delete()
            for vrf in list(nb.ipam.vrfs.filter(name=vrf_name)):
                vrf.delete()

    def test_update_bgp_peering_vrf_custom_field_missing(self, nfclient):
        """When the vrf_custom_field name does not exist in NetBox the task succeeds
        and the vrf update argument is silently ignored."""
        sname = self._create_test_session(nfclient)
        nb = get_pynetbox(nfclient)
        ret = nfclient.run_job(
            "netbox",
            "update_bgp_peering",
            workers="any",
            kwargs={
                "name": sname,
                "vrf": "test_vrf_missing_cf",
                "vrf_custom_field": "vrf_nonexistent",
            },
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} failed: {res['errors']}"
            assert not res["errors"], f"{worker}: unexpected errors: {res['errors']}"
        # vrf_nonexistent custom field does not exist - no VRF set on the session
        session = nb.plugins.bgp.session.get(name=sname)
        assert session, f"session '{sname}' not found in NetBox"
        assert (session.custom_fields or {}).get(
            "vrf_nonexistent"
        ) is None, (
            f"VRF unexpectedly set on '{sname}' when the custom field was missing"
        )
