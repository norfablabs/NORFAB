"""Integration tests for NetBox CRUD tasks (netbox_crud.py).

Uses real NorFab and real NetBox — requires ``nfclient`` fixture from conftest.py
and a live NetBox at NB_URL with NB_API_TOKEN credentials.
"""

import pprint

import pynetbox
import pytest

from .netbox_data import NB_API_TOKEN, NB_URL

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_pynetbox():
    return pynetbox.api(url=NB_URL, token=NB_API_TOKEN)


def clear_nb_cache(keys, nfclient):
    return nfclient.run_job(
        "netbox",
        "cache_clear",
        workers="all",
        kwargs={"keys": keys},
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
def test_manufacturer(nfclient):
    """Create a temporary manufacturer in NetBox; yield its ID; delete after test."""
    nb = get_pynetbox()
    existing = nb.dcim.manufacturers.get(slug="norfab-crud-test-manufacturer")
    if existing:
        existing.delete()
    mfr = nb.dcim.manufacturers.create(
        {
            "name": "NorFab CRUD Test Manufacturer",
            "slug": "norfab-crud-test-manufacturer",
        }
    )
    yield mfr.id
    obj = nb.dcim.manufacturers.get(mfr.id)
    if obj:
        obj.delete()


# ---------------------------------------------------------------------------
# crud_list_objects
# ---------------------------------------------------------------------------


class TestCrudListObjects:
    def test_all_apps(self, nfclient):
        """Returns all NetBox apps with their object types and metadata."""
        clear_nb_cache("netbox_*_openapi_objects", nfclient)
        ret = nfclient.run_job(
            "netbox",
            "crud_list_objects",
            workers="any",
            kwargs={},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            result = res["result"]
            assert isinstance(result, dict), f"{worker} - result should be a dict"
            assert "dcim" in result, f"{worker} - 'dcim' app not found"
            assert "ipam" in result, f"{worker} - 'ipam' app not found"
            assert "extras" in result, f"{worker} - 'extras' app not found"
            for app, obj_types in result.items():
                assert isinstance(obj_types, dict), f"{worker} - {app} should be a dict"
                for obj_type, meta in obj_types.items():
                    assert "path" in meta, f"{worker} - {app}.{obj_type} missing 'path'"
                    assert (
                        "methods" in meta
                    ), f"{worker} - {app}.{obj_type} missing 'methods'"
                    assert isinstance(meta["methods"], list)
            assert "devices" in result["dcim"], f"{worker} - 'devices' missing in dcim"

    def test_app_filter_str(self, nfclient):
        """String app_filter restricts result to that app only."""
        ret = nfclient.run_job(
            "netbox",
            "crud_list_objects",
            workers="any",
            kwargs={"app_filter": "dcim"},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            result = res["result"]
            assert "dcim" in result, f"{worker} - 'dcim' should be present"
            assert (
                "ipam" not in result
            ), f"{worker} - 'ipam' should have been filtered out"
            assert (
                "extras" not in result
            ), f"{worker} - 'extras' should have been filtered out"
            assert "devices" in result["dcim"], f"{worker} - 'devices' missing in dcim"

    def test_app_filter_list(self, nfclient):
        """List app_filter restricts result to only those apps."""
        ret = nfclient.run_job(
            "netbox",
            "crud_list_objects",
            workers="any",
            kwargs={"app_filter": ["dcim", "ipam"]},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            result = res["result"]
            assert "dcim" in result, f"{worker} - 'dcim' should be present"
            assert "ipam" in result, f"{worker} - 'ipam' should be present"
            assert (
                "extras" not in result
            ), f"{worker} - 'extras' should have been filtered out"

    def test_include_metadata_false(self, nfclient):
        """include_metadata=False returns lists of object type name strings."""
        ret = nfclient.run_job(
            "netbox",
            "crud_list_objects",
            workers="any",
            kwargs={"include_metadata": False},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            result = res["result"]
            assert isinstance(result, dict), f"{worker} - result should be a dict"
            for app, obj_types in result.items():
                assert isinstance(
                    obj_types, list
                ), f"{worker} - {app} should be a list when include_metadata=False"
                for name in obj_types:
                    assert isinstance(
                        name, str
                    ), f"{worker} - {app} object type names should be strings"
            assert "devices" in result.get("dcim", [])

    def test_cache_hit(self, nfclient):
        """Second call returns identical data (served from cache)."""
        clear_nb_cache("netbox_*_openapi_objects", nfclient)
        ret1 = nfclient.run_job(
            "netbox",
            "crud_list_objects",
            workers="any",
            kwargs={},
        )
        ret2 = nfclient.run_job(
            "netbox",
            "crud_list_objects",
            workers="any",
            kwargs={},
        )
        pprint.pprint(ret2)

        _, res1 = next(iter(ret1.items()))
        result1 = res1["result"]

        for worker, res in ret2.items():
            assert not res["errors"], f"{worker} - received error on cached call"
            assert (
                res["result"] == result1
            ), f"{worker} - cached result differs from original"


# ---------------------------------------------------------------------------
# crud_search
# ---------------------------------------------------------------------------


class TestCrudSearch:
    def test_default_object_types(self, nfclient):
        """Search across default object types finds ceos1 device."""
        ret = nfclient.run_job(
            "netbox",
            "crud_search",
            workers="any",
            kwargs={"query": "ceos1"},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            result = res["result"]
            assert isinstance(result, dict), f"{worker} - result should be a dict"
            assert "dcim.devices" in result, f"{worker} - 'dcim.devices' key missing"
            device_results = result["dcim.devices"]
            assert any(
                d.get("name") == "ceos1" for d in device_results
            ), f"{worker} - ceos1 not found in device search results"

    def test_specific_object_types(self, nfclient):
        """Searching specific object_types returns only those types."""
        ret = nfclient.run_job(
            "netbox",
            "crud_search",
            workers="any",
            kwargs={
                "query": "ceos",
                "object_types": ["dcim.devices"],
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            result = res["result"]
            assert "dcim.devices" in result, f"{worker} - 'dcim.devices' key missing"
            assert len(result) == 1, f"{worker} - expected only dcim.devices in result"
            assert len(result["dcim.devices"]) > 0, f"{worker} - no devices found"

    def test_brief_mode(self, nfclient):
        """brief=True returns minimal fields per object."""
        ret = nfclient.run_job(
            "netbox",
            "crud_search",
            workers="any",
            kwargs={
                "query": "ceos",
                "object_types": ["dcim.devices"],
                "brief": True,
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            devices = res["result"].get("dcim.devices", [])
            assert len(devices) > 0, f"{worker} - no devices returned in brief mode"
            for device in devices:
                assert "id" in device, f"{worker} - 'id' missing from brief device"

    def test_fields_filter(self, nfclient):
        """fields parameter limits returned fields to those specified."""
        ret = nfclient.run_job(
            "netbox",
            "crud_search",
            workers="any",
            kwargs={
                "query": "ceos",
                "object_types": ["dcim.devices"],
                "fields": ["id", "name"],
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            devices = res["result"].get("dcim.devices", [])
            assert len(devices) > 0, f"{worker} - no devices returned"
            for device in devices:
                assert "id" in device, f"{worker} - 'id' missing"
                assert "name" in device, f"{worker} - 'name' missing"

    def test_limit(self, nfclient):
        """limit parameter restricts the number of results per object type."""
        ret = nfclient.run_job(
            "netbox",
            "crud_search",
            workers="any",
            kwargs={
                "query": "ceos",
                "object_types": ["dcim.devices"],
                "limit": 1,
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            devices = res["result"].get("dcim.devices", [])
            assert len(devices) <= 1, f"{worker} - limit=1 exceeded"

    def test_no_results(self, nfclient):
        """Searching a non-existent term returns empty lists, no errors."""
        ret = nfclient.run_job(
            "netbox",
            "crud_search",
            workers="any",
            kwargs={"query": "zzz_this_does_not_exist_xyz_12345"},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            result = res["result"]
            total_matches = sum(len(v) for v in result.values())
            assert (
                total_matches == 0
            ), f"{worker} - expected no matches for non-existent term"

    def test_multiple_object_types(self, nfclient):
        """Search across multiple object types returns keys for each."""
        ret = nfclient.run_job(
            "netbox",
            "crud_search",
            workers="any",
            kwargs={
                "query": "ceos",
                "object_types": ["dcim.devices", "dcim.interfaces"],
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            result = res["result"]
            assert "dcim.devices" in result, f"{worker} - 'dcim.devices' key missing"
            assert (
                "dcim.interfaces" in result
            ), f"{worker} - 'dcim.interfaces' key missing"


# ---------------------------------------------------------------------------
# crud_read
# ---------------------------------------------------------------------------


class TestCrudRead:
    def test_by_filters_dict(self, nfclient):
        """Read a device by name filter dict."""
        ret = nfclient.run_job(
            "netbox",
            "crud_read",
            workers="any",
            kwargs={
                "object_type": "dcim.devices",
                "filters": {"name": "ceos1"},
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            result = res["result"]
            assert "count" in result, f"{worker} - 'count' key missing"
            assert "results" in result, f"{worker} - 'results' key missing"
            assert result["count"] >= 1, f"{worker} - expected at least 1 result"
            assert any(
                d.get("name") == "ceos1" for d in result["results"]
            ), f"{worker} - ceos1 not found in results"

    def test_by_id_single(self, nfclient):
        """Read a device by its integer ID."""
        nb = get_pynetbox()
        ceos1 = nb.dcim.devices.get(name="ceos1")
        assert ceos1 is not None, "ceos1 not found in NetBox"

        ret = nfclient.run_job(
            "netbox",
            "crud_read",
            workers="any",
            kwargs={
                "object_type": "dcim.devices",
                "object_id": ceos1.id,
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            result = res["result"]
            assert result["count"] == 1, f"{worker} - expected exactly 1 result"
            assert result["results"][0]["id"] == ceos1.id, f"{worker} - wrong device id"
            assert (
                result["results"][0]["name"] == "ceos1"
            ), f"{worker} - wrong device name"

    def test_by_id_list(self, nfclient):
        """Read multiple devices by a list of IDs."""
        nb = get_pynetbox()
        ceos1 = nb.dcim.devices.get(name="ceos1")
        fceos4 = nb.dcim.devices.get(name="fceos4")
        assert ceos1 is not None and fceos4 is not None

        ret = nfclient.run_job(
            "netbox",
            "crud_read",
            workers="any",
            kwargs={
                "object_type": "dcim.devices",
                "object_id": [ceos1.id, fceos4.id],
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            result = res["result"]
            assert result["count"] == 2, f"{worker} - expected 2 results"
            names = {d["name"] for d in result["results"]}
            assert "ceos1" in names, f"{worker} - ceos1 missing"
            assert "fceos4" in names, f"{worker} - fceos4 missing"

    def test_by_filters_list(self, nfclient):
        """List of filter dicts returns union of results deduplicated by id."""
        ret = nfclient.run_job(
            "netbox",
            "crud_read",
            workers="any",
            kwargs={
                "object_type": "dcim.devices",
                "filters": [
                    {"name": "ceos1"},
                    {"name": "fceos4"},
                ],
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            result = res["result"]
            names = {d["name"] for d in result["results"]}
            assert "ceos1" in names, f"{worker} - ceos1 missing"
            assert "fceos4" in names, f"{worker} - fceos4 missing"

    def test_brief_mode(self, nfclient):
        """brief=True returns minimal fields."""
        ret = nfclient.run_job(
            "netbox",
            "crud_read",
            workers="any",
            kwargs={
                "object_type": "dcim.devices",
                "filters": {"name": "ceos1"},
                "brief": True,
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            result = res["result"]
            assert result["count"] >= 1
            for device in result["results"]:
                assert "id" in device, f"{worker} - 'id' missing in brief mode"

    def test_fields_filter(self, nfclient):
        """fields parameter limits returned fields."""
        ret = nfclient.run_job(
            "netbox",
            "crud_read",
            workers="any",
            kwargs={
                "object_type": "dcim.devices",
                "filters": {"name": "ceos1"},
                "fields": ["id", "name", "status"],
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            result = res["result"]
            assert result["count"] >= 1
            for device in result["results"]:
                assert "id" in device
                assert "name" in device
                assert "status" in device

    def test_pagination_offset(self, nfclient):
        """offset=1 returns one fewer result than offset=0."""
        ret_all = nfclient.run_job(
            "netbox",
            "crud_read",
            workers="any",
            kwargs={"object_type": "dcim.devices", "limit": 100, "offset": 0},
        )
        ret_offset = nfclient.run_job(
            "netbox",
            "crud_read",
            workers="any",
            kwargs={"object_type": "dcim.devices", "limit": 100, "offset": 1},
        )
        pprint.pprint(ret_offset)

        all_count = next(iter(ret_all.values()))["result"]["count"]
        for worker, res in ret_offset.items():
            assert not res["errors"], f"{worker} - received error"
            offset_count = res["result"]["count"]
            assert (
                offset_count == all_count - 1
            ), f"{worker} - offset=1 should return 1 fewer result"

    def test_ordering_ascending(self, nfclient):
        """ordering='name' returns results sorted alphabetically."""
        ret = nfclient.run_job(
            "netbox",
            "crud_read",
            workers="any",
            kwargs={
                "object_type": "dcim.devices",
                "limit": 50,
                "ordering": "name",
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            result = res["result"]
            names = [d["name"] for d in result["results"]]
            assert names == sorted(
                names, key=str.lower
            ), f"{worker} - results not sorted by name"

    def test_no_filters_returns_results(self, nfclient):
        """No filter returns all objects up to limit."""
        ret = nfclient.run_job(
            "netbox",
            "crud_read",
            workers="any",
            kwargs={"object_type": "dcim.devices", "limit": 100},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            result = res["result"]
            assert result["count"] > 0, f"{worker} - expected some devices"
            assert isinstance(result["results"], list)

    def test_result_structure(self, nfclient):
        """Result includes count, next, previous, results keys."""
        ret = nfclient.run_job(
            "netbox",
            "crud_read",
            workers="any",
            kwargs={
                "object_type": "dcim.devices",
                "filters": {"name": "ceos1"},
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            result = res["result"]
            assert all(
                k in result for k in ("count", "next", "previous", "results")
            ), f"{worker} - result missing expected keys"


# ---------------------------------------------------------------------------
# crud_create
# ---------------------------------------------------------------------------


class TestCrudCreate:
    def test_dry_run(self, nfclient):
        """dry_run=True returns preview without creating the object in NetBox."""
        manufacturer_data = {
            "name": "NorFab Dry Run Manufacturer",
            "slug": "norfab-dry-run-manufacturer",
        }
        ret = nfclient.run_job(
            "netbox",
            "crud_create",
            workers="any",
            kwargs={
                "object_type": "dcim.manufacturers",
                "data": manufacturer_data,
                "dry_run": True,
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            result = res["result"]
            assert result.get("dry_run") is True, f"{worker} - expected dry_run=True"
            assert result["count"] == 1, f"{worker} - expected count=1"
            assert result["preview"][0]["name"] == "NorFab Dry Run Manufacturer"

        # verify the object was NOT created in NetBox
        nb = get_pynetbox()
        obj = nb.dcim.manufacturers.get(slug="norfab-dry-run-manufacturer")
        assert obj is None, "dry_run should not create the manufacturer in NetBox"

    def test_single_object(self, nfclient):
        """Create a single manufacturer and verify it exists in NetBox."""
        slug = "norfab-crud-test-single"
        nb = get_pynetbox()
        existing = nb.dcim.manufacturers.get(slug=slug)
        if existing:
            existing.delete()

        ret = nfclient.run_job(
            "netbox",
            "crud_create",
            workers="any",
            kwargs={
                "object_type": "dcim.manufacturers",
                "data": {"name": "NorFab CRUD Test Single", "slug": slug},
            },
        )
        pprint.pprint(ret)

        created_id = None
        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            result = res["result"]
            assert result["created"] == 1, f"{worker} - expected created=1"
            assert len(result["objects"]) == 1, f"{worker} - expected 1 object"
            assert result["objects"][0]["slug"] == slug
            created_id = result["objects"][0]["id"]

        # verify creation and clean up
        if created_id:
            obj = nb.dcim.manufacturers.get(created_id)
            assert obj is not None, "manufacturer not found in NetBox after creation"
            obj.delete()

    def test_bulk_objects(self, nfclient):
        """Create multiple objects in a single bulk request."""
        slugs = ["norfab-crud-bulk-1", "norfab-crud-bulk-2"]
        nb = get_pynetbox()
        for slug in slugs:
            existing = nb.dcim.manufacturers.get(slug=slug)
            if existing:
                existing.delete()

        ret = nfclient.run_job(
            "netbox",
            "crud_create",
            workers="any",
            kwargs={
                "object_type": "dcim.manufacturers",
                "data": [
                    {"name": "NorFab CRUD Bulk 1", "slug": slugs[0]},
                    {"name": "NorFab CRUD Bulk 2", "slug": slugs[1]},
                ],
            },
        )
        pprint.pprint(ret)

        created_ids = []
        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            result = res["result"]
            assert result["created"] == 2, f"{worker} - expected created=2"
            assert len(result["objects"]) == 2, f"{worker} - expected 2 objects"
            created_ids = [obj["id"] for obj in result["objects"]]

        # cleanup
        for oid in created_ids:
            obj = nb.dcim.manufacturers.get(oid)
            if obj:
                obj.delete()


# ---------------------------------------------------------------------------
# crud_update
# ---------------------------------------------------------------------------


class TestCrudUpdate:
    def test_dry_run_diffs(self, nfclient, test_manufacturer):
        """dry_run=True computes diffs without modifying the object."""
        new_name = "NorFab CRUD Test Manufacturer UPDATED"
        ret = nfclient.run_job(
            "netbox",
            "crud_update",
            workers="any",
            kwargs={
                "object_type": "dcim.manufacturers",
                "data": {"id": test_manufacturer, "name": new_name},
                "dry_run": True,
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            result = res["result"]
            assert result.get("dry_run") is True, f"{worker} - expected dry_run=True"
            assert result["count"] == 1, f"{worker} - expected count=1"
            changes_entry = result["changes"][0]
            assert changes_entry["id"] == test_manufacturer
            assert (
                "name" in changes_entry["changes"]
            ), f"{worker} - expected 'name' in changes"
            assert changes_entry["changes"]["name"]["new"] == new_name

        # verify the object was NOT modified
        nb = get_pynetbox()
        obj = nb.dcim.manufacturers.get(test_manufacturer)
        assert obj.name != new_name, "dry_run should not modify the manufacturer"

    def test_single_object(self, nfclient, test_manufacturer):
        """Update a manufacturer's name and verify the change in NetBox."""
        new_name = "NorFab CRUD Test Manufacturer UPDATED"
        ret = nfclient.run_job(
            "netbox",
            "crud_update",
            workers="any",
            kwargs={
                "object_type": "dcim.manufacturers",
                "data": {"id": test_manufacturer, "name": new_name},
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            result = res["result"]
            assert result["updated"] == 1, f"{worker} - expected updated=1"
            assert result["objects"][0]["id"] == test_manufacturer
            assert result["objects"][0]["name"] == new_name

        # verify in NetBox
        nb = get_pynetbox()
        obj = nb.dcim.manufacturers.get(test_manufacturer)
        assert obj.name == new_name, "manufacturer name not updated in NetBox"

    def test_no_change_dry_run(self, nfclient, test_manufacturer):
        """dry_run with unchanged field returns empty changes dict."""
        nb = get_pynetbox()
        original = nb.dcim.manufacturers.get(test_manufacturer)

        ret = nfclient.run_job(
            "netbox",
            "crud_update",
            workers="any",
            kwargs={
                "object_type": "dcim.manufacturers",
                "data": {"id": test_manufacturer, "name": original.name},
                "dry_run": True,
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            result = res["result"]
            assert result.get("dry_run") is True
            changes = result["changes"][0]["changes"]
            assert (
                "name" not in changes
            ), f"{worker} - expected no name change when value is unchanged"


# ---------------------------------------------------------------------------
# crud_delete
# ---------------------------------------------------------------------------


class TestCrudDelete:
    def test_dry_run(self, nfclient, test_manufacturer):
        """dry_run=True returns what would be deleted without deleting."""
        ret = nfclient.run_job(
            "netbox",
            "crud_delete",
            workers="any",
            kwargs={
                "object_type": "dcim.manufacturers",
                "object_id": test_manufacturer,
                "dry_run": True,
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            result = res["result"]
            assert result.get("dry_run") is True
            assert result["count"] == 1
            assert result["would_delete"][0]["id"] == test_manufacturer

        # verify it was NOT deleted
        nb = get_pynetbox()
        obj = nb.dcim.manufacturers.get(test_manufacturer)
        assert obj is not None, "dry_run should not delete the manufacturer"

    def test_single_id(self, nfclient):
        """Delete a manufacturer by ID and verify it no longer exists."""
        nb = get_pynetbox()
        existing = nb.dcim.manufacturers.get(slug="norfab-crud-delete-test")
        if existing:
            existing.delete()
        mfr = nb.dcim.manufacturers.create(
            {"name": "NorFab CRUD Delete Test", "slug": "norfab-crud-delete-test"}
        )

        ret = nfclient.run_job(
            "netbox",
            "crud_delete",
            workers="any",
            kwargs={
                "object_type": "dcim.manufacturers",
                "object_id": mfr.id,
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            result = res["result"]
            assert result["deleted"] == 1, f"{worker} - expected deleted=1"
            assert mfr.id in result["deleted_ids"]

        # verify deletion in NetBox
        obj = nb.dcim.manufacturers.get(mfr.id)
        assert obj is None, "manufacturer should have been deleted from NetBox"

    def test_nonexistent_id(self, nfclient):
        """Deleting a non-existent ID returns deleted=0, no errors."""
        ret = nfclient.run_job(
            "netbox",
            "crud_delete",
            workers="any",
            kwargs={
                "object_type": "dcim.manufacturers",
                "object_id": 999999999,
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            assert (
                res["result"]["deleted"] == 0
            ), f"{worker} - expected deleted=0 for non-existent ID"

    def test_multiple_ids(self, nfclient):
        """Delete a list of IDs in a single call."""
        nb = get_pynetbox()
        slugs = ["norfab-crud-delete-multi-1", "norfab-crud-delete-multi-2"]
        ids = []
        for slug in slugs:
            existing = nb.dcim.manufacturers.get(slug=slug)
            if existing:
                existing.delete()
            mfr = nb.dcim.manufacturers.create(
                {"name": f"NorFab CRUD Delete Multi {slug[-1]}", "slug": slug}
            )
            ids.append(mfr.id)

        ret = nfclient.run_job(
            "netbox",
            "crud_delete",
            workers="any",
            kwargs={
                "object_type": "dcim.manufacturers",
                "object_id": ids,
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            result = res["result"]
            assert result["deleted"] == 2, f"{worker} - expected deleted=2"
            assert set(ids) == set(result["deleted_ids"])


# ---------------------------------------------------------------------------
# crud_get_changelogs
# ---------------------------------------------------------------------------


class TestCrudGetChangelogs:
    def test_no_filters(self, nfclient):
        """Get recent changelogs without any filter."""
        ret = nfclient.run_job(
            "netbox",
            "crud_get_changelogs",
            workers="any",
            kwargs={"limit": 10},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            result = res["result"]
            assert "count" in result
            assert "results" in result
            assert isinstance(result["results"], list)
            for entry in result["results"]:
                assert "id" in entry, f"{worker} - changelog entry missing 'id'"
                assert "action" in entry, f"{worker} - changelog entry missing 'action'"

    def test_result_structure(self, nfclient):
        """Result includes count, next, previous, results keys."""
        ret = nfclient.run_job(
            "netbox",
            "crud_get_changelogs",
            workers="any",
            kwargs={"limit": 5},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            result = res["result"]
            assert all(
                k in result for k in ("count", "next", "previous", "results")
            ), f"{worker} - result missing expected keys"

    def test_by_action_filter(self, nfclient):
        """Filter changelogs by action returns only matching entries."""
        ret = nfclient.run_job(
            "netbox",
            "crud_get_changelogs",
            workers="any",
            kwargs={"filters": {"action": "create"}, "limit": 10},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            result = res["result"]
            for entry in result["results"]:
                action = entry.get("action")
                # action may be a string or a dict with "value" key depending on NetBox version
                if isinstance(action, dict):
                    action = action.get("value")
                assert (
                    action == "create"
                ), f"{worker} - expected action=create, got {entry.get('action')}"

    def test_fields_filter(self, nfclient):
        """fields parameter restricts returned fields."""
        ret = nfclient.run_job(
            "netbox",
            "crud_get_changelogs",
            workers="any",
            kwargs={"fields": ["id", "action", "time"], "limit": 5},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            result = res["result"]
            for entry in result["results"]:
                assert "id" in entry
                assert "action" in entry
                assert "time" in entry

    def test_pagination_limit(self, nfclient):
        """limit parameter restricts number of returned results."""
        ret = nfclient.run_job(
            "netbox",
            "crud_get_changelogs",
            workers="any",
            kwargs={"limit": 3},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            assert len(res["result"]["results"]) <= 3

    def test_pagination_offset(self, nfclient):
        """offset skips results; first result with offset matches second without."""
        ret_all = nfclient.run_job(
            "netbox",
            "crud_get_changelogs",
            workers="any",
            kwargs={"limit": 10, "offset": 0},
        )
        ret_offset = nfclient.run_job(
            "netbox",
            "crud_get_changelogs",
            workers="any",
            kwargs={"limit": 10, "offset": 1},
        )
        pprint.pprint(ret_offset)

        all_results = next(iter(ret_all.values()))["result"]["results"]
        for worker, res in ret_offset.items():
            assert not res["errors"], f"{worker} - received error"
            offset_results = res["result"]["results"]
            if len(all_results) >= 2 and offset_results:
                assert (
                    offset_results[0]["id"] == all_results[1]["id"]
                ), f"{worker} - offset pagination not working correctly"

    def test_filter_list(self, nfclient):
        """List of filter dicts runs multiple queries and merges results."""
        ret = nfclient.run_job(
            "netbox",
            "crud_get_changelogs",
            workers="any",
            kwargs={
                "filters": [
                    {"action": "create"},
                    {"action": "update"},
                ],
                "limit": 10,
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            result = res["result"]
            assert isinstance(result["results"], list)
            for entry in result["results"]:
                action = entry.get("action")
                if isinstance(action, dict):
                    action = action.get("value")
                assert action in (
                    "create",
                    "update",
                ), f"{worker} - unexpected action '{action}'"

    def test_changelogs_reflect_created_object(self, nfclient):
        """Changelogs show the create action for a recently created object."""
        nb = get_pynetbox()
        slug = "norfab-crud-changelog-test"
        existing = nb.dcim.manufacturers.get(slug=slug)
        if existing:
            existing.delete()

        mfr = nb.dcim.manufacturers.create(
            {"name": "NorFab CRUD Changelog Test", "slug": slug}
        )
        mfr_id = mfr.id

        try:
            ret = nfclient.run_job(
                "netbox",
                "crud_get_changelogs",
                workers="any",
                kwargs={
                    "filters": {"changed_object_id": mfr_id, "action": "create"},
                    "limit": 5,
                },
            )
            pprint.pprint(ret)

            for worker, res in ret.items():
                assert not res["errors"], f"{worker} - received error"
                result = res["result"]
                assert (
                    result["count"] >= 1
                ), f"{worker} - expected at least 1 changelog entry for created manufacturer"
        finally:
            obj = nb.dcim.manufacturers.get(mfr_id)
            if obj:
                obj.delete()
