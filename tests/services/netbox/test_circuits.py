import json
import pprint

import pytest

try:
    from tests.services.netbox.common import (
        cache_options,
        delete_branch,
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
        delete_branch,
    )

pytestmark = [
    pytest.mark.netbox,
    pytest.mark.netbox_get_circuits,
]


class TestGetCircuits:
    def test_get_circuits_dry_run(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_circuits",
            workers="any",
            kwargs={
                "devices": ["fceos4", "fceos5"],
                "cid": ["CID1"],
                "cache": False,
                "dry_run": True,
            },
        )
        pprint.pprint(ret, width=200)
        for worker, res in ret.items():
            payload = json.loads(res["result"]["data"])
            assert "query CircuitsQuery" in payload["query"]
            assert payload["variables"]["sites"] == ["saltnornir-lab"]
            assert payload["variables"]["cids"] == ["CID1"]

    def test_get_circuits_cache_dry_run(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_circuits",
            workers="any",
            kwargs={
                "devices": ["fceos4", "fceos5"],
                "cache": True,
                "dry_run": True,
            },
        )
        pprint.pprint(ret, width=200)
        for worker, res in ret.items():
            dry_run = res["result"]["get_circuits_dry_run"]
            payload = json.loads(dry_run["data"])
            assert "query CircuitsFreshnessQuery" in payload["query"]
            assert payload["variables"]["sites"] == ["saltnornir-lab"]
            assert payload["variables"]["cids"] is None

    def test_get_circuits(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_circuits",
            workers="any",
            kwargs={
                "devices": ["fceos4", "fceos5"],
            },
        )
        pprint.pprint(ret, width=200)
        for worker, res in ret.items():
            assert "fceos5" in res["result"], f"{worker} returned no results for fceos5"
            assert "fceos4" in res["result"], f"{worker} returned no results for fceos4"
            for device, device_data in res["result"].items():
                assert device_data, f"{worker}:{device} no circuit data returned"
                for cid, cid_data in device_data.items():
                    if cid == "CID3":
                        assert all(
                            k in cid_data
                            for k in [
                                "tags",
                                "provider",
                                "commit_rate",
                                "description",
                                "status",
                                "type",
                                "provider_account",
                                "tenant",
                                "custom_fields",
                                "comments",
                                "provider_account",
                                "provider_network",
                            ]
                        ), f"{worker}:{device}:{cid} not all circuit data returned"
                    else:
                        assert all(
                            k in cid_data
                            for k in [
                                "tags",
                                "provider",
                                "commit_rate",
                                "description",
                                "status",
                                "type",
                                "provider_account",
                                "tenant",
                                "custom_fields",
                                "comments",
                                "remote_device",
                                "remote_interface",
                            ]
                        ), f"{worker}:{device}:{cid} not all circuit data returned"

    def test_get_circuits_with_interface_details(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_circuits",
            workers="any",
            kwargs={
                "devices": ["fceos4"],
                "add_interface_details": True,
            },
        )
        pprint.pprint(ret, width=200)
        for worker, res in ret.items():
            assert all(
                k in res["result"]["fceos4"]["CID2"]
                for k in [
                    "child_interfaces",
                    "vrf",
                    "ip_addresses",
                ]
            ), f"{worker}:fcoes4:CID2 no interface details data returned"

    def test_get_circuits_by_cid(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_circuits",
            workers="any",
            kwargs={"devices": ["fceos4", "fceos5"], "cid": ["CID1"]},
        )
        pprint.pprint(ret, width=200)
        for worker, res in ret.items():
            assert "fceos5" in res["result"], f"{worker} returned no results for fceos5"
            assert "fceos4" in res["result"], f"{worker} returned no results for fceos4"
            for device, device_data in res["result"].items():
                assert device_data, f"{worker}:{device} no circuit data returned"
                for cid, cid_data in device_data.items():
                    assert (
                        cid == "CID1"
                    ), f"{worker}:{device}:{cid} wrong circuit returned, was expecting 'CID1' only"

    def test_get_circuits_with_branch(self, nfclient):
        branch = "get-circuits-branch-test"
        branch_description = "Circuit description from branch"
        delete_branch(branch, nfclient)

        try:
            main_result = nfclient.run_job(
                "netbox",
                "get_circuits",
                workers="any",
                kwargs={
                    "devices": ["fceos4"],
                    "cid": ["CID2"],
                    "cache": "refresh",
                },
            )
            original_description = next(iter(main_result.values()))["result"]["fceos4"][
                "CID2"
            ]["description"]

            circuit_lookup = nfclient.run_job(
                "netbox",
                "rest",
                workers="any",
                kwargs={
                    "api": "circuits/circuits",
                    "params": {"cid": "CID2"},
                },
            )
            circuit_id = next(iter(circuit_lookup.values()))["result"]["results"][0][
                "id"
            ]

            updated = nfclient.run_job(
                "netbox",
                "rest",
                workers="any",
                kwargs={
                    "branch": branch,
                    "method": "patch",
                    "api": f"circuits/circuits/{circuit_id}",
                    "json": {"description": branch_description},
                },
            )
            for worker, result in updated.items():
                assert not result["errors"], f"{worker} - received REST error"
                assert result["result"]["description"] == branch_description

            branch_result = nfclient.run_job(
                "netbox",
                "get_circuits",
                workers="any",
                kwargs={
                    "devices": ["fceos4"],
                    "cid": ["CID2"],
                    "branch": branch,
                    "cache": "force",
                    "add_interface_details": True,
                },
            )
            for worker, result in branch_result.items():
                assert not result["errors"], f"{worker} - received circuit error"
                circuit = result["result"]["fceos4"]["CID2"]
                assert circuit["description"] == branch_description
                assert circuit["remote_device"] == "fceos5"
                assert "ip_addresses" in circuit

            main_result = nfclient.run_job(
                "netbox",
                "get_circuits",
                workers="any",
                kwargs={
                    "devices": ["fceos4"],
                    "cid": ["CID2"],
                    "cache": "force",
                },
            )
            for worker, result in main_result.items():
                assert not result["errors"], f"{worker} - received circuit error"
                assert (
                    result["result"]["fceos4"]["CID2"]["description"]
                    == original_description
                )
        finally:
            delete_branch(branch, nfclient)

    @pytest.mark.parametrize("cache", cache_options)
    def test_get_circuits_cache(self, nfclient, cache):
        print(f"cache: {cache}")
        ret = nfclient.run_job(
            "netbox",
            "get_circuits",
            workers="any",
            kwargs={"devices": ["fceos4", "fceos5"], "cache": cache},
        )
        pprint.pprint(ret, width=200)
        for worker, res in ret.items():
            assert "fceos5" in res["result"], f"{worker} returned no results for fceos5"
            assert "fceos4" in res["result"], f"{worker} returned no results for fceos4"
            for device, device_data in res["result"].items():
                assert device_data, f"{worker}:{device} no circuit data returned"
                for cid, cid_data in device_data.items():
                    if cid == "CID3":
                        assert all(
                            k in cid_data
                            for k in [
                                "tags",
                                "provider",
                                "commit_rate",
                                "description",
                                "status",
                                "type",
                                "provider_account",
                                "tenant",
                                "custom_fields",
                                "comments",
                                "provider_account",
                                "provider_network",
                            ]
                        ), f"{worker}:{device}:{cid} not all circuit data returned"
                    else:
                        assert all(
                            k in cid_data
                            for k in [
                                "tags",
                                "provider",
                                "commit_rate",
                                "description",
                                "status",
                                "type",
                                "provider_account",
                                "tenant",
                                "custom_fields",
                                "comments",
                                "remote_device",
                                "remote_interface",
                            ]
                        ), f"{worker}:{device}:{cid} not all circuit data returned"

    def test_get_circuits_cache_content(self, nfclient):
        circuits_cache = nfclient.run_job(
            "netbox",
            "cache_get",
            workers="all",
            kwargs={"keys": "get_circuits*"},
        )

        pprint.pprint(circuits_cache)

        for worker, res in circuits_cache.items():
            if "get_circuits::CID1" in res["result"]:
                assert (
                    res["result"]["get_circuits::CID1"]["fceos4"]["remote_device"]
                    == "fceos5"
                )
                assert (
                    res["result"]["get_circuits::CID1"]["fceos5"]["remote_device"]
                    == "fceos4"
                )
            if "get_circuits::CID2" in res["result"]:
                assert (
                    res["result"]["get_circuits::CID2"]["fceos4"]["remote_device"]
                    == "fceos5"
                )
                assert (
                    res["result"]["get_circuits::CID2"]["fceos5"]["remote_device"]
                    == "fceos4"
                )
            if "get_circuits::CID3" in res["result"]:
                assert (
                    res["result"]["get_circuits::CID3"]["fceos4"]["provider_network"]
                    == "Provider1-Net1"
                )
