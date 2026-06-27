import pprint

import pytest

try:
    from tests.services.netbox.common import (
        cache_options,
        get_nb_version,
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
        get_nb_version,
    )

pytestmark = [pytest.mark.netbox, pytest.mark.circuits]


@pytest.mark.task_get_circuits
class TestGetCircuits:
    nb_version = None

    def test_get_circuits_dry_run(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        if self.nb_version[0] == 3:
            ret = nfclient.run_job(
                "netbox",
                "get_circuits",
                workers="any",
                kwargs={
                    "devices": ["fceos4", "fceos5"],
                    "dry_run": True,
                },
            )
            pprint.pprint(ret, width=200)
            for worker, res in ret.items():
                assert res["result"]["data"] == (
                    '{"query": "query {circuit_list(site: '
                    + '[\\"saltnornir-lab\\"]) {cid tags {name} '
                    + "provider {name} commit_rate description status "
                    + "type {name} provider_account {name} tenant "
                    + "{name} termination_a {id} termination_z {id} "
                    + 'custom_fields comments}}"}'
                ), f"{worker} did not return correct query string"

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
