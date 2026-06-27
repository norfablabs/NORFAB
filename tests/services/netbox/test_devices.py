import pprint

import pytest

try:
    from tests.services.netbox.common import (
        cache_options,
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
    )

pytestmark = [pytest.mark.netbox, pytest.mark.devices]


@pytest.mark.task_get_devices
class TestGetDevices:
    nb_version = None
    device_data_keys = [
        "last_updated",
        "custom_fields",
        "tags",
        "device_type",
        "config_context",
        "tenant",
        "platform",
        "serial",
        "asset_tag",
        "site",
        "location",
        "rack",
        "status",
        "primary_ip4",
        "primary_ip6",
        "airflow",
        "position",
    ]

    def test_with_devices_list(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_devices",
            workers="any",
            kwargs={"devices": ["ceos1", "fceos4"]},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert "ceos1" in res["result"], f"{worker} returned no results for ceos1"
            assert "fceos4" in res["result"], f"{worker} returned no results for fceos4"
            for device, device_data in res["result"].items():
                print(list(device_data.keys()))
                assert isinstance(
                    device_data, dict
                ), f"{worker}:{device} did not return device data as dictionary"
                assert all(
                    k in device_data for k in self.device_data_keys
                ), f"{worker}:{device} not all data returned"
                assert (
                    "role" in device_data
                ), f"{worker}:{device} nodevice role info returned"

    def test_with_filters(self, nfclient):
        # REST API filter syntax: plain dicts with standard query params
        ret = nfclient.run_job(
            "netbox",
            "get_devices",
            workers="any",
            kwargs={
                "filters": [
                    {"name": ["ceos1", "fceos4"]},
                    {"name__ic": "390"},
                ]
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert "ceos1" in res["result"], f"{worker} returned no results for ceos1"
            assert (
                "fceos3_390" in res["result"]
            ), f"{worker} returned no results for fceos3_390"
            assert "fceos4" in res["result"], f"{worker} returned no results for fceos4"
            for device, device_data in res["result"].items():
                assert isinstance(
                    device_data, dict
                ), f"{worker}:{device} did not return device data as dictionary"
                assert all(
                    k in device_data for k in self.device_data_keys
                ), f"{worker}:{device} not all data returned"
                assert (
                    "role" in device_data or "devcie_role" in device_data
                ), f"{worker}:{device} nodevice role info returned"

    def test_with_filters_dry_run(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_devices",
            workers="any",
            kwargs={
                "filters": [
                    {"name": ["ceos1", "fceos4"]},
                    {"name__ic": "390"},
                ],
                "dry_run": True,
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            assert (
                "get_devices_dry_run" in res["result"]
            ), f"{worker} - dry run key missing from result"
            dry_run_data = res["result"]["get_devices_dry_run"]
            assert (
                "filters" in dry_run_data
            ), f"{worker} - 'filters' key missing from dry run result"
            assert isinstance(
                dry_run_data["filters"], list
            ), f"{worker} - dry run filters should be a list"

    def test_dry_run_with_devices_only(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_devices",
            workers="any",
            kwargs={"devices": ["ceos1", "fceos4"], "dry_run": True},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            dry_run_data = res["result"]["get_devices_dry_run"]
            assert (
                "filters" in dry_run_data
            ), f"{worker} - 'filters' key missing from dry run result"
            # devices should be merged into filters as {"name": devices}
            filters = dry_run_data["filters"]
            assert any(
                "name" in f for f in filters
            ), f"{worker} - device names not merged into filters"

    @pytest.mark.parametrize("cache", cache_options)
    def test_get_devices_cache(self, nfclient, cache):
        # REST API filter syntax works across all Netbox versions
        ret = nfclient.run_job(
            "netbox",
            "get_devices",
            workers="any",
            kwargs={
                "devices": ["ceos1", "fceos4"],
                "filters": [
                    {"name": ["ceos1", "fceos4"]},
                    {"name__ic": "390"},
                ],
                "cache": cache,
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert "ceos1" in res["result"], f"{worker} returned no results for ceos1"
            assert "fceos4" in res["result"], f"{worker} returned no results for fceos4"
            for device, device_data in res["result"].items():
                assert isinstance(
                    device_data, dict
                ), f"{worker}:{device} did not return device data as dictionary"
                assert all(
                    k in device_data for k in self.device_data_keys
                ), f"{worker}:{device} not all data returned"
                assert (
                    "role" in device_data or "devcie_role" in device_data
                ), f"{worker}:{device} nodevice role info returned"

    def test_with_devices_list_data_structure(self, nfclient):
        """Verify the exact data format returned by get_devices."""
        ret = nfclient.run_job(
            "netbox",
            "get_devices",
            workers="any",
            kwargs={"devices": ["fceos4"]},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert "fceos4" in res["result"], f"{worker} returned no results for fceos4"
            d = res["result"]["fceos4"]
            # tags - list of strings
            assert isinstance(d["tags"], list), f"{worker}:fceos4 tags should be a list"
            if d["tags"]:
                assert all(
                    isinstance(t, dict) for t in d["tags"]
                ), f"{worker}:fceos4 each tag should be a dict"
            # device_type - flat string (model name)
            assert isinstance(
                d["device_type"], dict
            ), f"{worker}:fceos4 device_type should be a dict"
            # role - flat string
            assert isinstance(d["role"], dict), f"{worker}:fceos4 role should be a dict"
            # site - dict with name, slug, tags
            assert isinstance(d["site"], dict), f"{worker}:fceos4 site should be a dict"
            assert all(
                k in d["site"] for k in ["name", "slug", "tags"]
            ), f"{worker}:fceos4 site missing expected keys"
            # status - string value
            assert isinstance(
                d["status"], dict
            ), f"{worker}:fceos4 status should be a dict"
            # primary_ip4 when present - dict with address
            if d["primary_ip4"] is not None:
                assert isinstance(
                    d["primary_ip4"], dict
                ), f"{worker}:fceos4 primary_ip4 should be a dict"
                assert (
                    "address" in d["primary_ip4"]
                ), f"{worker}:fceos4 primary_ip4 missing 'address' key"
            # id - string
            assert isinstance(d["id"], int), f"{worker}:fceos4 id should be an int"

    def test_with_devices_and_filters_combined(self, nfclient):
        """Devices list and filters are merged; results contain union of matches."""
        ret = nfclient.run_job(
            "netbox",
            "get_devices",
            workers="any",
            kwargs={
                "devices": ["ceos1"],
                "filters": [{"name__ic": "390"}],
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            assert "ceos1" in res["result"], f"{worker} ceos1 missing from result"
            assert (
                "fceos3_390" in res["result"]
            ), f"{worker} fceos3_390 missing from result"

    def test_with_nonexistent_device(self, nfclient):
        """Querying a device that does not exist returns an empty result."""
        ret = nfclient.run_job(
            "netbox",
            "get_devices",
            workers="any",
            kwargs={"devices": ["nonexistent_device_xyz"]},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            assert (
                res["result"] == {}
            ), f"{worker} - expected empty result for nonexistent device"
