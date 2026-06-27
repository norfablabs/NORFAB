import pprint
from time import perf_counter

import pytest

pytestmark = [pytest.mark.netbox, pytest.mark.connections]


@pytest.mark.task_get_connections
class TestGetConnections:
    def test_get_connections_eth101_remote_mac_addresses(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_connections",
            workers="any",
            kwargs={
                "devices": ["fceos5"],
                "interface_regex": "^eth101$",
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            assert "fceos5" in res["result"], f"{worker} returned no results for fceos5"
            assert (
                "eth101" in res["result"]["fceos5"]
            ), f"{worker}:fceos5 missing eth101"

            intf_data = res["result"]["fceos5"]["eth101"]
            assert intf_data["remote_device"] == "fceos4"
            assert intf_data["remote_interface"] == "eth101"
            assert isinstance(intf_data["remote_mac_addresses"], list)
            assert intf_data["remote_mac_addresses"] == [
                "00:11:22:33:44:01"
            ], f"{worker}:fceos5:eth101 expected populated remote_mac_addresses"

    def test_get_connections_port_channel_subif_remote_mac_addresses(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_connections",
            workers="any",
            kwargs={
                "devices": ["fceos5"],
                "interface_regex": "^ae5\\.101$",
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            assert "fceos5" in res["result"], f"{worker} returned no results for fceos5"
            assert (
                "ae5.101" in res["result"]["fceos5"]
            ), f"{worker}:fceos5 missing ae5.101"

            intf_data = res["result"]["fceos5"]["ae5.101"]
            assert intf_data["remote_device"] == "fceos4"
            assert intf_data["remote_interface"] == "Port-Channel1.101"
            assert "remote_mac_addresses" in intf_data
            assert isinstance(intf_data["remote_mac_addresses"], list)
            assert intf_data["remote_mac_addresses"] == [
                "00:11:22:33:44:02"
            ], f"{worker}:fceos5:ae5.101 expected populated remote_mac_addresses"

    def test_get_connections_port_channel_remote_mac_addresses(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_connections",
            workers="any",
            kwargs={
                "devices": ["fceos5"],
                "interface_regex": "^ae5$",
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            assert "fceos5" in res["result"], f"{worker} returned no results for fceos5"
            assert "ae5" in res["result"]["fceos5"], f"{worker}:fceos5 missing ae5"

            intf_data = res["result"]["fceos5"]["ae5"]
            assert intf_data["remote_device"] == "fceos4"
            assert intf_data["remote_interface"] == "Port-Channel1"
            assert "remote_mac_addresses" in intf_data
            assert isinstance(intf_data["remote_mac_addresses"], list)
            assert intf_data["remote_mac_addresses"] == [
                "00:11:22:33:44:03"
            ], f"{worker}:fceos5:ae5 expected populated remote_mac_addresses"

    def test_get_connections_two_remote_mac_addresses(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_connections",
            workers="any",
            kwargs={
                "devices": ["fceos4"],
                "interface_regex": "^eth103$",
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            assert "fceos4" in res["result"], f"{worker} returned no results for fceos4"
            assert (
                "eth103" in res["result"]["fceos4"]
            ), f"{worker}:fceos4 missing eth103"

            intf_data = res["result"]["fceos4"]["eth103"]
            assert intf_data["remote_device"] == "fceos5"
            assert intf_data["remote_interface"] == "eth103"
            assert "remote_mac_addresses" in intf_data
            assert isinstance(intf_data["remote_mac_addresses"], list)
            assert intf_data["remote_mac_addresses"] == [
                "00:11:22:33:44:04",
                "00:11:22:33:44:05",
            ], f"{worker}:fceos4:eth103 expected exactly two remote_mac_addresses"

    def test_get_connections_eth11_123_remote_mac_addresses(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_connections",
            workers="any",
            kwargs={
                "devices": ["fceos5"],
                "interface_regex": "^eth11\\.123$",
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            assert "fceos5" in res["result"], f"{worker} returned no results for fceos5"
            assert (
                "eth11.123" in res["result"]["fceos5"]
            ), f"{worker}:fceos5 missing eth3.13"

            intf_data = res["result"]["fceos5"]["eth11.123"]
            assert intf_data["remote_device"] == "fceos4"
            assert intf_data["remote_interface"] == "eth11.123"
            assert "remote_mac_addresses" in intf_data
            assert isinstance(intf_data["remote_mac_addresses"], list)
            assert intf_data["remote_mac_addresses"] == [
                "00:11:22:33:44:06"
            ], f"{worker}:fceos5:eth11.123 expected populated remote_mac_addresses"

    def test_get_connections(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_connections",
            workers="any",
            kwargs={
                "devices": ["fceos4", "fceos5"],
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert "fceos5" in res["result"], f"{worker} returned no results for fceos5"
            assert "fceos4" in res["result"], f"{worker} returned no results for fceos4"
            assert (
                "ConsolePort1" in res["result"]["fceos4"]
            ), f"{worker}:fceos4 no console ports data returned"
            assert (
                "ConsoleServerPort1" in res["result"]["fceos5"]
            ), f"{worker}:fceos5 no console server ports data returned"
            assert (
                "eth11.123" in res["result"]["fceos5"]
            ), f"{worker}:fceos5 no virtual ports data returned"
            assert (
                "Port-Channel1" in res["result"]["fceos4"]
            ), f"{worker}:fceos5 no lag ports data returned"
            assert (
                "Port-Channel1.101" in res["result"]["fceos4"]
            ), f"{worker}:fceos5 no lag virtual ports data returned"
            for device, interfaces in res["result"].items():
                assert isinstance(
                    interfaces, dict
                ), f"{worker}:{device} did not return interfaces dictionary"
                for intf_name, intf_data in interfaces.items():
                    assert all(
                        k in intf_data
                        for k in [
                            "remote_device",
                            "remote_interface",
                            "remote_termination_type",
                            "termination_type",
                        ]
                    ), f"{worker}:{device}:{intf_name} not all data returned"
                    # verify provider network connection handling
                    if device == "fceos4" and intf_name == "eth201":
                        assert (
                            "provider" in intf_data
                        ), f"{worker}:{device}:{intf_name} no provider data"
                        assert intf_data["remote_termination_type"] == "providernetwork"
                        assert intf_data["remote_device"] == None
                        assert intf_data["remote_interface"] == None
                        assert intf_data["remote_interface_label"] == None
                    # verify breakout handling
                    if device == "fceos5" and intf_name == "eth1":
                        assert (
                            intf_data["breakout"] == True
                        ), f"{worker}:{device}:{intf_name} was expecting breakout connection"
                        assert isinstance(intf_data["remote_interface"], list)
                        assert len(intf_data["remote_interface"]) > 1
                    # verify virtual ports handling
                    if device == "fceos5" and intf_name == "eth11.123":
                        assert intf_data["remote_device"] == "fceos4"
                        assert intf_data["remote_device_status"] == "active"
                        assert intf_data["remote_interface"] == "eth11.123"
                        assert intf_data["termination_type"] == "virtual"
                    # verify lag ports handling
                    if device == "fceos4" and intf_name == "Port-Channel1":
                        assert intf_data["remote_device"] == "fceos5"
                        assert intf_data["remote_interface"] == "ae5"
                        assert intf_data["termination_type"] == "lag"
                        assert "remote_interface_label" not in intf_data
                    # verify lag virtual interfaces handling
                    if device == "fceos4" and intf_name == "Port-Channel1.101":
                        assert intf_data["remote_device"] == "fceos5"
                        assert intf_data["remote_interface"] == "ae5.101"
                        assert intf_data["termination_type"] == "virtual"
                        assert "remote_interface_label" not in intf_data
                    if device == "fceos5" and intf_name == "ae6.0":
                        assert intf_data["remote_device"] == "fceos4"
                        assert intf_data["remote_interface"] == "Port-Channel2"
                        assert intf_data["termination_type"] == "virtual"
                        assert intf_data["remote_termination_type"] == "lag"
                    if device == "fceos4" and intf_name == "eth103.0":
                        assert intf_data["remote_device"] == "fceos5"
                        assert intf_data["remote_interface"] == "eth103"
                        assert intf_data["termination_type"] == "virtual"
                        assert intf_data["remote_termination_type"] == "interface"
                        assert intf_data["remote_interface_label"] == ""
                    if device == "fceos4" and intf_name == "ConsolePort2":
                        assert intf_data["remote_device"] == "fceos5"
                        assert intf_data["remote_interface"] == "ConsoleServerPort2"
                        assert intf_data["termination_type"] == "consoleport"
                        assert (
                            intf_data["remote_termination_type"] == "consoleserverport"
                        )
                        assert intf_data["remote_interface_label"] == ""

    def test_get_connections_physical_interface_regex(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_connections",
            workers="any",
            kwargs={
                "devices": ["fceos4", "fceos5"],
                "interface_regex": "eth10.*",
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert "fceos5" in res["result"], f"{worker} returned no results for fceos5"
            assert "fceos4" in res["result"], f"{worker} returned no results for fceos4"
            for device, interfaces in res["result"].items():
                assert interfaces, f"{worker}:{device} no connections data returned"
                for intf_name, intf_data in interfaces.items():
                    assert intf_name.startswith(
                        "eth10"
                    ), f"{worker}:{device}:{intf_name} not matching regex"

    def test_get_connections_virtual_interface_regex(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_connections",
            workers="any",
            kwargs={
                "devices": ["fceos4", "fceos5"],
                "interface_regex": "(Port-Channel1|ae5).101",  # match Port-Channel1.101 and ae5.101
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert "fceos5" in res["result"], f"{worker} returned no results for fceos5"
            assert "fceos4" in res["result"], f"{worker} returned no results for fceos4"
            assert (
                res["result"]["fceos4"]["Port-Channel1.101"]["remote_interface"]
                == "ae5.101"
            ), "Unexpected interface name"
            assert (
                res["result"]["fceos5"]["ae5.101"]["remote_interface"]
                == "Port-Channel1.101"
            ), "Unexpected interface name"

    def test_get_connections_dry_run(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_connections",
            workers="any",
            kwargs={"devices": ["fceos4", "fceos5"], "dry_run": True},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            dry_run_payload = res["result"]
            assert all(
                k in dry_run_payload for k in ["headers", "data", "verify", "url"]
            ), f"{worker} - not all dry run data returned"

    def test_get_connections_and_cables(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_connections",
            workers="any",
            kwargs={"devices": ["fceos4", "fceos5"]},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert "fceos5" in res["result"], f"{worker} returned no results for fceos5"
            assert "fceos4" in res["result"], f"{worker} returned no results for fceos4"
            for device, interfaces in res["result"].items():
                assert isinstance(
                    interfaces, dict
                ), f"{worker}:{device} did not return interfaces dictionary"
                for intf_name, intf_data in interfaces.items():
                    if intf_data["termination_type"] in ["virtual", "lag"]:
                        continue
                    assert (
                        "cable" in intf_data
                    ), f"{worker}:{device}:{intf_name} no cable data returned"
                    assert all(
                        k in intf_data["cable"]
                        for k in [
                            "custom_fields",
                            "label",
                            "peer_device",
                            "peer_interface",
                            "peer_termination_type",
                            "status",
                            "tags",
                            "tenant",
                            "type",
                        ]
                    ), f"{worker}:{device}:{intf_name} not all cable data returned"

    def test_get_connectionstest_preformance(self, nfclient):
        devices = ["bulk-conn-01", "bulk-conn-02", "bulk-conn-03"]

        started_at = perf_counter()
        ret = nfclient.run_job(
            "netbox",
            "get_connections",
            workers="any",
            kwargs={"devices": devices},
        )
        elapsed_seconds = perf_counter() - started_at
        pprint.pprint(ret)

        assert (
            elapsed_seconds < 15
        ), f"get_connections took {elapsed_seconds:.2f}s, expected under 15s"

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            for device in devices:
                assert (
                    device in res["result"]
                ), f"{worker} returned no results for {device}"

            total_connections = sum(len(res["result"][device]) for device in devices)
            assert (
                total_connections == 600
            ), f"{worker} returned {total_connections} connections, expected 600"


@pytest.mark.task_get_topology
class TestGetTopology:
    devices = ["bulk-conn-01", "bulk-conn-02", "bulk-conn-03"]

    def test_get_topology(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_topology",
            workers="any",
            kwargs={"devices": self.devices},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            assert "nodes" in res["result"], f"{worker} - no nodes in result"
            assert "links" in res["result"], f"{worker} - no links in result"
            assert isinstance(
                res["result"]["nodes"], list
            ), f"{worker} - nodes should be a list"
            assert isinstance(
                res["result"]["links"], list
            ), f"{worker} - links should be a list"
            assert (
                len(res["result"]["nodes"]) >= 3
            ), f"{worker} - expected at least 3 nodes, got {len(res['result']['nodes'])}"
            assert (
                len(res["result"]["links"]) > 0
            ), f"{worker} - expected at least one link"
            node_ids = {n["id"] for n in res["result"]["nodes"]}
            for device in self.devices:
                assert device in node_ids, f"{worker} - {device} missing from nodes"

    def test_get_topology_node_structure(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_topology",
            workers="any",
            kwargs={"devices": self.devices},
        )
        pprint.pprint(ret)

        node_keys = [
            "id",
            "name",
            "type",
            "ip",
            "status",
            "role",
            "site",
            "tags",
            "manufacturer",
            "device_type",
        ]
        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            for node in res["result"]["nodes"]:
                assert all(
                    k in node for k in node_keys
                ), f"{worker} - node missing required keys: {node}"
                assert isinstance(
                    node["id"], str
                ), f"{worker} - node id should be a string"
                assert isinstance(
                    node["name"], str
                ), f"{worker} - node name should be a string"
                assert isinstance(
                    node["tags"], list
                ), f"{worker} - node tags should be a list"

    def test_get_topology_link_structure(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_topology",
            workers="any",
            kwargs={"devices": self.devices},
        )
        pprint.pprint(ret)

        link_keys = ["source", "target", "src_iface", "dst_iface", "tags"]
        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            node_ids = {n["id"] for n in res["result"]["nodes"]}
            for link in res["result"]["links"]:
                assert all(
                    k in link for k in link_keys
                ), f"{worker} - link missing required keys: {link}"
                assert (
                    link["source"] in node_ids
                ), f"{worker} - link source '{link['source']}' not in nodes"
                assert (
                    link["target"] in node_ids
                ), f"{worker} - link target '{link['target']}' not in nodes"
                assert isinstance(
                    link["tags"], list
                ), f"{worker} - link tags should be a list"

    def test_get_topology_links_deduplicated(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_topology",
            workers="any",
            kwargs={"devices": self.devices},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            seen = set()
            for link in res["result"]["links"]:
                key = tuple(
                    sorted(
                        [
                            (link["source"], link["src_iface"]),
                            (link["target"], link["dst_iface"]),
                        ]
                    )
                )
                assert key not in seen, f"{worker} - duplicate link found: {link}"
                seen.add(key)

    def test_get_topology_dry_run(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_topology",
            workers="any",
            kwargs={"devices": self.devices, "dry_run": True},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            assert (
                "device_filter" in res["result"]
            ), f"{worker} - no device_filter in dry run result"
            assert (
                "graphql" in res["result"]
            ), f"{worker} - no graphql in dry run result"

    def test_get_topology_adjacent_nodes(self, nfclient):
        """Devices connected to the filtered set must also appear as nodes."""
        ret = nfclient.run_job(
            "netbox",
            "get_topology",
            workers="any",
            kwargs={"devices": self.devices},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            node_ids = {n["id"] for n in res["result"]["nodes"]}
            # every link endpoint must have a corresponding node entry
            for link in res["result"]["links"]:
                assert (
                    link["source"] in node_ids
                ), f"{worker} - link source '{link['source']}' has no node entry"
                assert (
                    link["target"] in node_ids
                ), f"{worker} - link target '{link['target']}' has no node entry"

    def test_get_topology_with_instance(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_topology",
            workers="any",
            kwargs={"devices": self.devices, "instance": "prod"},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            assert "nodes" in res["result"], f"{worker} - no nodes in result"
            assert "links" in res["result"], f"{worker} - no links in result"
            assert (
                len(res["result"]["nodes"]) >= 3
            ), f"{worker} - expected at least 3 nodes"

    def test_get_topology_only_internal_links(self, nfclient):
        """Links should only reference devices present in the nodes list."""
        ret = nfclient.run_job(
            "netbox",
            "get_topology",
            workers="any",
            kwargs={"devices": self.devices},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            node_ids = {n["id"] for n in res["result"]["nodes"]}
            for link in res["result"]["links"]:
                assert (
                    link["source"] in node_ids and link["target"] in node_ids
                ), f"{worker} - link references device outside topology: {link}"

    def test_get_topology_device_contains(self, nfclient):
        """device_contains filter must return devices whose names contain the substring."""
        ret = nfclient.run_job(
            "netbox",
            "get_topology",
            workers="any",
            kwargs={"device_contains": "bulk-conn-0"},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            assert "nodes" in res["result"], f"{worker} - no nodes in result"
            assert "links" in res["result"], f"{worker} - no links in result"
            assert (
                len(res["result"]["nodes"]) > 0
            ), f"{worker} - expected at least one node"
            for node in res["result"]["nodes"]:
                assert (
                    "bulk-conn" in node["name"]
                ), f"{worker} - node '{node['name']}' does not match device_contains filter"
            # all link endpoints must have a node entry
            node_ids = {n["id"] for n in res["result"]["nodes"]}
            for link in res["result"]["links"]:
                assert (
                    link["source"] in node_ids
                ), f"{worker} - link source '{link['source']}' has no node entry"
                assert (
                    link["target"] in node_ids
                ), f"{worker} - link target '{link['target']}' has no node entry"

    def test_get_topology_device_regex(self, nfclient):
        """device_regex filter must return only devices whose names match the pattern."""
        ret = nfclient.run_job(
            "netbox",
            "get_topology",
            workers="any",
            kwargs={"device_regex": "^bulk-conn-0[123]$"},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            assert "nodes" in res["result"], f"{worker} - no nodes in result"
            assert "links" in res["result"], f"{worker} - no links in result"
            assert (
                len(res["result"]["nodes"]) >= 3
            ), f"{worker} - expected at least 3 nodes, got {len(res['result']['nodes'])}"
            # the 3 explicitly matched devices must all be present
            node_ids = {n["id"] for n in res["result"]["nodes"]}
            for device in self.devices:
                assert device in node_ids, f"{worker} - {device} missing from nodes"
            # all link endpoints must have a node entry
            for link in res["result"]["links"]:
                assert (
                    link["source"] in node_ids
                ), f"{worker} - link source '{link['source']}' has no node entry"
                assert (
                    link["target"] in node_ids
                ), f"{worker} - link target '{link['target']}' has no node entry"

    def test_get_topology_filter_role(self, nfclient):
        """role filter must return only devices with the given role slug."""
        ret = nfclient.run_job(
            "netbox",
            "get_topology",
            workers="any",
            kwargs={"role": ["virtualrouter"]},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            assert "nodes" in res["result"], f"{worker} - no nodes in result"
            assert (
                len(res["result"]["nodes"]) > 0
            ), f"{worker} - expected at least one node"
            for node in res["result"]["nodes"]:
                assert (
                    node["role"].lower() == "virtualrouter"
                ), f"{worker} - node '{node['name']}' has unexpected role '{node['role']}'"
            node_ids = {n["id"] for n in res["result"]["nodes"]}
            for link in res["result"]["links"]:
                assert (
                    link["source"] in node_ids
                ), f"{worker} - link source '{link['source']}' has no node entry"
                assert (
                    link["target"] in node_ids
                ), f"{worker} - link target '{link['target']}' has no node entry"

    def test_get_topology_filter_platform(self, nfclient):
        """platform filter must return only devices with the given platform slug."""
        ret = nfclient.run_job(
            "netbox",
            "get_topology",
            workers="any",
            kwargs={"platform": ["arista_eos"]},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            assert "nodes" in res["result"], f"{worker} - no nodes in result"
            assert (
                len(res["result"]["nodes"]) > 0
            ), f"{worker} - expected at least one node"
            for node in res["result"]["nodes"]:
                assert (
                    node["type"] == "arista_eos"
                ), f"{worker} - node '{node['name']}' has unexpected platform '{node['type']}'"
            node_ids = {n["id"] for n in res["result"]["nodes"]}
            for link in res["result"]["links"]:
                assert (
                    link["source"] in node_ids
                ), f"{worker} - link source '{link['source']}' has no node entry"
                assert (
                    link["target"] in node_ids
                ), f"{worker} - link target '{link['target']}' has no node entry"

    def test_get_topology_filter_manufacturer(self, nfclient):
        """manufacturers filter must return only devices from the given manufacturer."""
        ret = nfclient.run_job(
            "netbox",
            "get_topology",
            workers="any",
            kwargs={"manufacturers": ["arista"]},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            assert "nodes" in res["result"], f"{worker} - no nodes in result"
            assert (
                len(res["result"]["nodes"]) > 0
            ), f"{worker} - expected at least one node"
            for node in res["result"]["nodes"]:
                assert (
                    node["manufacturer"].lower() == "arista"
                ), f"{worker} - node '{node['name']}' has unexpected manufacturer '{node['manufacturer']}'"
            node_ids = {n["id"] for n in res["result"]["nodes"]}
            for link in res["result"]["links"]:
                assert (
                    link["source"] in node_ids
                ), f"{worker} - link source '{link['source']}' has no node entry"
                assert (
                    link["target"] in node_ids
                ), f"{worker} - link target '{link['target']}' has no node entry"

    def test_get_topology_filter_status(self, nfclient):
        """status filter must return only devices with the given status."""
        ret = nfclient.run_job(
            "netbox",
            "get_topology",
            workers="any",
            kwargs={"status": ["active"]},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            assert "nodes" in res["result"], f"{worker} - no nodes in result"
            assert (
                len(res["result"]["nodes"]) > 0
            ), f"{worker} - expected at least one node"
            for node in res["result"]["nodes"]:
                assert (
                    node["status"] == "active"
                ), f"{worker} - node '{node['name']}' has unexpected status '{node['status']}'"
            node_ids = {n["id"] for n in res["result"]["nodes"]}
            for link in res["result"]["links"]:
                assert (
                    link["source"] in node_ids
                ), f"{worker} - link source '{link['source']}' has no node entry"
                assert (
                    link["target"] in node_ids
                ), f"{worker} - link target '{link['target']}' has no node entry"

    def test_get_topology_filter_sites(self, nfclient):
        """sites filter must return only devices from the given site slug."""
        ret = nfclient.run_job(
            "netbox",
            "get_topology",
            workers="any",
            kwargs={"sites": ["saltnornir-lab"]},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            assert "nodes" in res["result"], f"{worker} - no nodes in result"
            assert (
                len(res["result"]["nodes"]) > 0
            ), f"{worker} - expected at least one node"
            for node in res["result"]["nodes"]:
                assert (
                    node["site"].upper() == "SALTNORNIR-LAB"
                ), f"{worker} - node '{node['name']}' has unexpected site '{node['site']}'"
            node_ids = {n["id"] for n in res["result"]["nodes"]}
            for link in res["result"]["links"]:
                assert (
                    link["source"] in node_ids
                ), f"{worker} - link source '{link['source']}' has no node entry"
                assert (
                    link["target"] in node_ids
                ), f"{worker} - link target '{link['target']}' has no node entry"
