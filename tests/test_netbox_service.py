import pprint
import pytest
import random

cache_options = [True, False, "refresh", "force"]


def get_nb_version(nfclient, instance=None) -> tuple:
    ret = nfclient.run_job("netbox", "get_version", workers="any")
    # pprint.pprint(f"Netbox Version: {ret}")
    for w, r in ret.items():
        if instance is None:
            for instance_name, instance_version in r["result"][
                "netbox_version"
            ].items():
                return tuple(instance_version)
        else:
            return tuple(r["result"]["netbox_version"][instance])


def delete_branch(branch, nfclient):
    resp = nfclient.run_job(
        "netbox",
        "delete_branch",
        workers="any",
        kwargs={"branch": branch},
    )
    print(f"Deleted branch '{branch}'")


def delete_prefixes_within(prefix, nfclient):
    resp = nfclient.run_job(
        "netbox",
        "rest",
        workers="any",
        kwargs={
            "method": "get",
            "api": "/ipam/prefixes/",
            "params": {"within": prefix},
        },
    )
    worker, prefixes = tuple(resp.items())[0]
    # pprint.pprint(prefixes)
    for pfx in prefixes["result"]["results"]:
        delete_pfx = nfclient.run_job(
            "netbox",
            "rest",
            workers="any",
            kwargs={
                "method": "delete",
                "api": f"/ipam/prefixes/{pfx['id']}/",
            },
        )
        # print("delete prefix:")
        # pprint.pprint(delete_pfx)


def delete_ips(prefix, nfclient):
    resp = nfclient.run_job(
        "netbox",
        "rest",
        workers="any",
        kwargs={
            "method": "get",
            "api": "/ipam/ip-addresses/",
            "params": {"parent": prefix},
        },
    )
    worker, ips = tuple(resp.items())[0]
    # pprint.pprint(ips)
    for ip in ips["result"]["results"]:
        delete_ip = nfclient.run_job(
            "netbox",
            "rest",
            workers="any",
            kwargs={
                "method": "delete",
                "api": f"/ipam/ip-addresses/{ip['id']}/",
            },
        )
        # print("delete ip address:")
        # pprint.pprint(delete_ip)


class TestNetboxWorker:
    def test_get_netbox_inventory(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_inventory",
            workers="any",
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            assert all(
                k in res["result"] for k in ["service", "instances"]
            ), f"{worker} - not all netbox inventory data returned"
            assert all(
                k in res["result"]["instances"] for k in ["dev", "preprod", "prod"]
            ), f"{worker} - not all netbox instances inventory data returned"

    def test_get_netbox_version(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_version",
            workers="any",
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            assert all(
                k in res["result"]
                for k in ["platform", "pynetbox", "python", "requests"]
            ), f"{worker} - not all netbox version data returned"

    def test_get_netbox_status(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_netbox_status",
            workers="any",
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            assert all(
                k in res["result"] for k in ["dev", "preprod", "prod"]
            ), f"{worker} - not all netbox instances inventory data returned"
            for instance, status_data in res["result"].items():
                assert all(
                    k in status_data
                    for k in [
                        "django-version",
                        "error",
                        "netbox-version",
                        "plugins",
                        "python-version",
                        "rq-workers-running",
                        "status",
                    ]
                ), f"{worker}:{instance} - not all netbox instances status data returned"

    def test_get_netbox_compatibility(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_compatibility",
            workers="any",
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            assert all(
                k in res["result"] for k in ["dev", "preprod", "prod"]
            ), f"{worker} - not all netbox instances inventory data returned"
            for instance, compatible in res["result"].items():
                assert compatible == True, f"{worker}:{instance} - not compatible"


class TestNetboxGrapQL:
    nb_version = None

    def test_graphql_query_string(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "graphql",
            workers="any",
            kwargs={"query_string": "query DeviceListQuery { device_list { name } }"},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            assert "device_list" in res["result"], f"{worker} no device list returned"
            assert isinstance(
                res["result"]["device_list"], list
            ), f"{worker} unexpected device list payload type, was expecting list"
            assert (
                len(res["result"]["device_list"]) > 0
            ), f"{worker} returned no devices in device list"

    def test_graphql_query_string_with_instance(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "graphql",
            workers="any",
            kwargs={
                "query_string": "query DeviceListQuery { device_list { name } }",
                "instance": "prod",
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            assert "device_list" in res["result"], f"{worker} no device list returned"
            assert isinstance(
                res["result"]["device_list"], list
            ), f"{worker} unexpected device list payload type, was expecting list"
            assert (
                len(res["result"]["device_list"]) > 0
            ), f"{worker} returned no devices in device list"

    def test_graphql_query_string_dry_run(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "graphql",
            workers="any",
            kwargs={
                "query_string": "query DeviceListQuery { device_list { name } }",
                "dry_run": True,
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            assert all(
                k in res["result"] for k in ["headers", "data", "verify", "url"]
            ), f"{worker} - not all dry run data returned"

    def test_graphql_query_string_error(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "graphql",
            workers="any",
            kwargs={
                "query_string": "query DeviceListQuery { device_list { name } ",
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert res[
                "errors"
            ], f"{worker} did not return errors fro malformed graphql query"

    def test_form_graphql_query_dry_run(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        if self.nb_version[0] == 4:
            ret = nfclient.run_job(
                "netbox",
                "graphql",
                workers="any",
                kwargs={
                    "obj": "device_list",
                    "fields": ["name", "platform {name}"],
                    "filters": {"q": "ceos", "platform": "arista_eos"},
                    "dry_run": True,
                },
            )
            pprint.pprint(ret, width=200)
            for worker, res in ret.items():
                assert res["result"]["data"] == (
                    '{"query": "query {device_list(filters: {q: \\"ceos\\", platform: \\"arista_eos\\"}) {name platform {name}}}"}'
                ), f"{worker} did not return correct query string"
        elif self.nb_version[0] == 3:
            ret = nfclient.run_job(
                "netbox",
                "graphql",
                workers="any",
                kwargs={
                    "obj": "device_list",
                    "fields": ["name", "platform {name}"],
                    "filters": {"name__ic": "ceos", "platform": "arista_eos"},
                    "dry_run": True,
                },
            )
            pprint.pprint(ret, width=200)
            for worker, res in ret.items():
                assert res["result"]["data"] == (
                    '{"query": "query {device_list(name__ic: \\"ceos\\", platform: \\"arista_eos\\") {name platform {name}}}"}'
                ), f"{worker} did not return correct query string"

    def test_form_graphql_query_dry_run_composite_filter(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        if self.nb_version[0] == 4:
            ret = nfclient.run_job(
                "netbox",
                "graphql",
                workers="any",
                kwargs={
                    "obj": "interface_list",
                    "fields": ["name"],
                    "filters": {"q": "eth", "type": '{exact: "virtual"}'},
                    "dry_run": True,
                },
            )
            pprint.pprint(ret, width=200)

            for worker, res in ret.items():
                assert res["result"]["data"] == (
                    '{"query": "query {interface_list(filters: {q: \\"eth\\", type: {exact: \\"virtual\\"}}) {name}}"}'
                ), f"{worker} did not return correct query string"
        elif self.nb_version[0] == 3:
            pytest.skip("Only for Netbox v4")

    def test_form_graphql_query_dry_run_list_filter(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        if self.nb_version[0] == 4:
            ret = nfclient.run_job(
                "netbox",
                "graphql",
                workers="any",
                kwargs={
                    "obj": "ip_address_list",
                    "fields": ["address"],
                    "filters": {"address": ["1.0.10.3/32", "1.0.10.1/32"]},
                    "dry_run": True,
                },
            )
            pprint.pprint(ret, width=200)

            for worker, res in ret.items():
                assert res["result"]["data"] == (
                    '{"query": "query {ip_address_list(filters: {address: [\\"1.0.10.3/32\\", \\"1.0.10.1/32\\"]}) {address}}"}'
                ), f"{worker} did not return correct query string"
        elif self.nb_version[0] == 3:
            ret = nfclient.run_job(
                "netbox",
                "graphql",
                workers="any",
                kwargs={
                    "obj": "ip_address_list",
                    "fields": ["address"],
                    "filters": {"address": ["1.0.10.3/32", "1.0.10.1/32"]},
                    "dry_run": True,
                },
            )
            pprint.pprint(ret, width=200)

            for worker, res in ret.items():
                assert res["result"]["data"] == (
                    '{"query": "query {ip_address_list(address: [\\"1.0.10.3/32\\", \\"1.0.10.1/32\\"]) {address}}"}'
                ), f"{worker} did not return correct query string"

    def test_form_graphql_query(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        if (4, 0, 0) < self.nb_version < (4, 3, 0):
            ret = nfclient.run_job(
                "netbox",
                "graphql",
                workers="any",
                kwargs={
                    "obj": "device_list",
                    "fields": ["name", "platform {name}"],
                    "filters": {"q": "ceos", "platform": "arista_eos"},
                },
            )
            pprint.pprint(ret)

            for worker, res in ret.items():
                assert isinstance(
                    res["result"], list
                ), f"{worker} - unexpected result type"
                for item in res["result"]:
                    assert (
                        "name" in item and "platform" in item
                    ), f"{worker} - no name and platform returned: {item}"
        elif self.nb_version >= (4, 3, 0):
            ret = nfclient.run_job(
                "netbox",
                "graphql",
                workers="any",
                kwargs={
                    "obj": "device_list",
                    "fields": ["name", "platform {name}"],
                    "filters": '{name: {i_contains: "ceos"}}',
                },
            )
            pprint.pprint(ret)

            for worker, res in ret.items():
                assert isinstance(
                    res["result"], list
                ), f"{worker} - unexpected result type"
                for item in res["result"]:
                    assert (
                        "name" in item and "platform" in item
                    ), f"{worker} - no name and platform returned: {item}"
        elif self.nb_version[0] == 3:
            ret = nfclient.run_job(
                "netbox",
                "graphql",
                workers="any",
                kwargs={
                    "obj": "device_list",
                    "fields": ["name", "platform {name}"],
                    "filters": {"name__ic": "ceos", "platform": "arista_eos"},
                },
            )
            pprint.pprint(ret)

            for worker, res in ret.items():
                assert isinstance(
                    res["result"], list
                ), f"{worker} - unexpected result type"
                for item in res["result"]:
                    assert (
                        "name" in item and "platform" in item
                    ), f"{worker} - no name and platform returned: {item}"

    def test_form_graphql_queries_with_aliases_dry_run(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        if self.nb_version[0] == 4:
            ret = nfclient.run_job(
                "netbox",
                "graphql",
                workers="any",
                kwargs={
                    "queries": {
                        "devices": {
                            "obj": "device_list",
                            "fields": ["name", "platform {name}"],
                            "filters": {"q": "ceos", "platform": "arista_eos"},
                        },
                        "interfaces": {
                            "obj": "interface_list",
                            "fields": ["name"],
                            "filters": {"q": "eth", "type": '{exact: "virtual"}'},
                        },
                        "addresses": {
                            "obj": "ip_address_list",
                            "fields": ["address"],
                            "filters": {"address": ["1.0.10.3/32", "1.0.10.1/32"]},
                        },
                    },
                    "dry_run": True,
                },
            )
            pprint.pprint(ret, width=200)

            for worker, res in ret.items():
                assert res["result"]["data"] == (
                    '{"query": "query {devices: device_list(filters: {q: \\"ceos\\", platform: '
                    + '\\"arista_eos\\"}) {name platform {name}}    interfaces: interface_list(filters: '
                    + '{q: \\"eth\\", type: {exact: \\"virtual\\"}}) {name}    addresses: '
                    + 'ip_address_list(filters: {address: [\\"1.0.10.3/32\\", \\"1.0.10.1/32\\"]}) {address}}"}'
                ), f"{worker} did not return correct query string"
        elif self.nb_version[0] == 3:
            ret = nfclient.run_job(
                "netbox",
                "graphql",
                workers="any",
                kwargs={
                    "queries": {
                        "devices": {
                            "obj": "device_list",
                            "fields": ["name", "platform {name}"],
                            "filters": {"name__ic": "ceos", "platform": "arista_eos"},
                        },
                        "interfaces": {
                            "obj": "interface_list",
                            "fields": ["name"],
                            "filters": {"name__ic": "eth", "type": "virtual"},
                        },
                        "addresses": {
                            "obj": "ip_address_list",
                            "fields": ["address"],
                            "filters": {"address": ["1.0.10.3/32", "1.0.10.1/32"]},
                        },
                    },
                    "dry_run": True,
                },
            )
            pprint.pprint(ret, width=200)

            for worker, res in ret.items():
                assert res["result"]["data"] == (
                    '{"query": "query {devices: device_list(name__ic: \\"ceos\\", platform: \\"arista_eos\\") '
                    + '{name platform {name}}    interfaces: interface_list(name__ic: \\"eth\\", type: \\"virtual\\") '
                    + '{name}    addresses: ip_address_list(address: [\\"1.0.10.3/32\\", \\"1.0.10.1/32\\"]) {address}}"}'
                ), f"{worker} did not return correct query string"

    def test_form_graphql_queries_with_aliases(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        if (4, 0, 0) <= self.nb_version < (4, 3, 0):
            ret = nfclient.run_job(
                "netbox",
                "graphql",
                workers="any",
                kwargs={
                    "queries": {
                        "devices": {
                            "obj": "device_list",
                            "fields": ["name", "platform {name}"],
                            "filters": {"q": "ceos", "platform": "arista_eos"},
                        },
                        "interfaces": {
                            "obj": "interface_list",
                            "fields": ["name"],
                            "filters": {"q": "eth", "type": '{exact: "virtual"}'},
                        },
                        "addresses": {
                            "obj": "ip_address_list",
                            "fields": ["address"],
                            "filters": {
                                "address": '{in_list: ["1.0.10.3/32", "1.0.10.1/32"]}'
                            },
                        },
                    },
                },
            )
            pprint.pprint(ret, width=200)

            for worker, res in ret.items():
                assert all(
                    k in res["result"] for k in ["devices", "interfaces", "addresses"]
                ), f"{worker} - did not return some data"
        elif self.nb_version >= (4, 3, 0):
            ret = nfclient.run_job(
                "netbox",
                "graphql",
                workers="any",
                kwargs={
                    "queries": {
                        "devices": {
                            "obj": "device_list",
                            "fields": ["name", "platform {name}"],
                            "filters": '{name: {i_contains: "ceos"}}',
                        },
                        "interfaces": {
                            "obj": "interface_list",
                            "fields": ["name"],
                            "filters": '{name: {i_contains: "eth"}, type: TYPE_VIRTUAL}',
                        },
                        "addresses": {
                            "obj": "ip_address_list",
                            "fields": ["address"],
                            "filters": '{address: {in_list: ["1.0.10.3/32", "1.0.10.1/32"]}}',
                        },
                    },
                },
            )
            pprint.pprint(ret, width=200)

            for worker, res in ret.items():
                assert all(
                    k in res["result"] for k in ["devices", "interfaces", "addresses"]
                ), f"{worker} - did not return some data"
        elif self.nb_version[0] == 3:
            ret = nfclient.run_job(
                "netbox",
                "graphql",
                workers="any",
                kwargs={
                    "queries": {
                        "devices": {
                            "obj": "device_list",
                            "fields": ["name", "platform {name}"],
                            "filters": {"name__ic": "ceos", "platform": "arista_eos"},
                        },
                        "interfaces": {
                            "obj": "interface_list",
                            "fields": ["name"],
                            "filters": {"name__ic": "eth", "type": "virtual"},
                        },
                        "addresses": {
                            "obj": "ip_address_list",
                            "fields": ["address"],
                            "filters": {"address": ["1.0.10.3/32", "1.0.10.1/32"]},
                        },
                    },
                },
            )
            pprint.pprint(ret, width=200)

            for worker, res in ret.items():
                assert all(
                    k in res["result"] for k in ["devices", "interfaces", "addresses"]
                ), f"{worker} - did not return some data"


class TestGetInterfaces:
    nb_version = None

    def test_get_interfaces(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)
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

        if (4, 0, 0) <= self.nb_version < (4, 3, 0):
            for worker, res in ret.items():
                assert res["result"]["data"] == (
                    '{"query": "query {interfaces: interface_list(filters: {device: [\\"ceos1\\", '
                    + '\\"fceos4\\"]}) {name enabled description mtu parent {name} mode '
                    + "untagged_vlan {vid name} vrf {name} tagged_vlans {vid name} tags {name} "
                    + "custom_fields last_updated bridge {name} child_interfaces {name} bridge_interfaces "
                    + '{name} member_interfaces {name} wwn duplex speed id device {name} mac_addresses {mac_address}}}"}'
                ), f"{worker} did not return correct query string"
        elif self.nb_version >= (4, 3, 0):
            for worker, res in ret.items():
                assert res["result"]["data"] == (
                    '{"query": "query {interfaces: interface_list(filters: {device: {name: {in_list: [\\"ceos1\\", \\"fceos4\\"]}}}) '
                    + "{name enabled description mtu parent {name} mode untagged_vlan {vid name} vrf {name} tagged_vlans {vid name} "
                    + "tags {name} custom_fields last_updated bridge {name} child_interfaces {name} bridge_interfaces {name} "
                    + 'member_interfaces {name} wwn duplex speed id device {name} mac_addresses {mac_address}}}"}'
                ), f"{worker} did not return correct query string"
        elif self.nb_version[0] == 4:
            for worker, res in ret.items():
                assert res["result"]["data"] == (
                    '{"query": "query {interfaces: interface_list(filters: {device: [\\"ceos1\\", '
                    + '\\"fceos4\\"]}) {name enabled description mtu parent {name} mode '
                    + "untagged_vlan {vid name} vrf {name} tagged_vlans {vid name} tags {name} "
                    + "custom_fields last_updated bridge {name} child_interfaces {name} bridge_interfaces "
                    + '{name} member_interfaces {name} wwn duplex speed id device {name} mac_address}}"}'
                ), f"{worker} did not return correct query string"
        elif self.nb_version[0] == 3:
            for worker, res in ret.items():
                assert res["result"]["data"] == (
                    '{"query": "query {interfaces: interface_list(device: [\\"ceos1\\", \\"fceos4\\"]) '
                    + "{name enabled description mtu parent {name} mode untagged_vlan {vid name} "
                    + "vrf {name} tagged_vlans {vid name} tags {name} custom_fields last_updated bridge "
                    + "{name} child_interfaces {name} bridge_interfaces {name} member_interfaces {name} wwn "
                    + 'duplex speed id device {name} mac_address}}"}'
                ), f"{worker} did not return correct query string"

    def test_get_interfaces_add_ip(self, nfclient):
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
                                "status",
                                "role",
                                "dns_name",
                                "description",
                                "custom_fields",
                                "last_updated",
                                "tenant",
                                "tags",
                            ]
                        ), f"{worker}:{device}:{intf_name} not all IP data returned"

    def test_get_interfaces_add_inventory_items(self, nfclient):
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
                                "label",
                                "description",
                                "tags",
                                "asset_tag",
                                "serial",
                                "part_id",
                            ]
                        ), f"{worker}:{device}:{intf_name} not all inventory item data returned"

    def test_get_interfaces_with_interface_regex(self, nfclient):
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


class TestGetDevices:
    nb_version = None

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
                assert isinstance(
                    device_data, dict
                ), f"{worker}:{device} did not return device data as dictionary"
                assert all(
                    k in device_data
                    for k in [
                        "last_updated",
                        "custom_field_data",
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
                ), f"{worker}:{device} not all data returned"
                assert (
                    "role" in device_data or "devcie_role" in device_data
                ), f"{worker}:{device} nodevice role info returned"

    def test_with_filters(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        if (4, 0, 0) <= self.nb_version < (4, 3, 0):
            ret = nfclient.run_job(
                "netbox",
                "get_devices",
                workers="any",
                kwargs={
                    "filters": [
                        {"name": '{in_list: ["ceos1", "fceos4"]}'},
                        {"q": "390"},
                    ]
                },
            )
        elif self.nb_version >= (4, 3, 0):
            ret = nfclient.run_job(
                "netbox",
                "get_devices",
                workers="any",
                kwargs={
                    "filters": [
                        {"name": '{in_list: ["ceos1", "fceos4"]}'},
                        {"name": '{i_contains: "390"}'},
                    ]
                },
            )
        elif self.nb_version[0] == 3:
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
                    k in device_data
                    for k in [
                        "last_updated",
                        "custom_field_data",
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
                ), f"{worker}:{device} not all data returned"
                assert (
                    "role" in device_data or "devcie_role" in device_data
                ), f"{worker}:{device} nodevice role info returned"

    def test_with_filters_dry_run(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        ret = nfclient.run_job(
            "netbox",
            "get_devices",
            workers="any",
            kwargs={
                "filters": [
                    {"name": ["ceos1", "fceos4"]},
                    {"q": "390"},
                ],
                "dry_run": True,
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            assert all(
                k in res["result"]["get_devices_dry_run"]
                for k in ["headers", "data", "verify", "url"]
            ), f"{worker} - not all dry run data returned"

    @pytest.mark.parametrize("cache", cache_options)
    def test_get_devices_cache(self, nfclient, cache):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        if (4, 0, 0) <= self.nb_version < (4, 3, 0):
            ret = nfclient.run_job(
                "netbox",
                "get_devices",
                workers="any",
                kwargs={
                    "devices": ["ceos1", "fceos4"],
                    "filters": [
                        {"name": '{in_list: ["ceos1", "fceos4"]}'},
                        {"q": "390"},
                    ],
                    "cache": cache,
                },
            )
        elif self.nb_version >= (4, 3, 0):
            ret = nfclient.run_job(
                "netbox",
                "get_devices",
                workers="any",
                kwargs={
                    "devices": ["ceos1", "fceos4"],
                    "filters": [
                        {"name": '{in_list: ["ceos1", "fceos4"]}'},
                        {"name": '{i_contains: "390"}'},
                    ],
                    "cache": cache,
                },
            )
        elif self.nb_version[0] == 3:
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
                    k in device_data
                    for k in [
                        "last_updated",
                        "custom_field_data",
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
                ), f"{worker}:{device} not all data returned"
                assert (
                    "role" in device_data or "devcie_role" in device_data
                ), f"{worker}:{device} nodevice role info returned"


class TestGetConnections:
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
                        assert intf_data["remote_interface"] == "eth11.123"
                        assert intf_data["termination_type"] == "virtual"
                    # verify lag ports handling
                    if device == "fceos4" and intf_name == "Port-Channel1":
                        assert intf_data["remote_device"] == "fceos5"
                        assert intf_data["remote_interface"] == "ae5"
                        assert intf_data["termination_type"] == "lag"
                    # verify lag virtual interfaces handling
                    if device == "fceos4" and intf_name == "Port-Channel1.101":
                        assert intf_data["remote_device"] == "fceos5"
                        assert intf_data["remote_interface"] == "ae5.101"
                        assert intf_data["termination_type"] == "virtual"
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

    def test_get_connections_physical_interface_regex(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_connections",
            workers="any",
            kwargs={
                "devices": ["fceos4", "fceos5"],
                "interface_regex": "eth10.*",
                "include_virtual": False,
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
            ), f"Unexpected interface name"
            assert (
                res["result"]["fceos5"]["ae5.101"]["remote_interface"]
                == "Port-Channel1.101"
            ), f"Unexpected interface name"

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
            assert all(
                k in res["result"] for k in ["headers", "data", "verify", "url"]
            ), f"{worker} - not all dry run data returned"

    def test_get_connections_and_cables(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_connections",
            workers="any",
            kwargs={"devices": ["fceos4", "fceos5"], "cables": True},
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
                            "length",
                            "length_unit",
                            "peer_device",
                            "peer_interface",
                            "peer_termination_type",
                            "status",
                            "tags",
                            "tenant",
                            "type",
                        ]
                    ), f"{worker}:{device}:{intf_name} not all cable data returned"


class TestGetNornirInventory:
    nb_version = None

    def test_with_devices(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_nornir_inventory",
            workers="any",
            kwargs={"devices": ["ceos1", "fceos4", "nonexist"]},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert (
                "ceos1" in res["result"]["hosts"]
            ), f"{worker} returned no results for ceos1"
            assert (
                "fceos4" in res["result"]["hosts"]
            ), f"{worker} returned no results for fceos4"
            for device, data in res["result"]["hosts"].items():
                assert all(
                    k in data for k in ["data", "hostname", "platform"]
                ), f"{worker}:{device} not all data returned"

    def test_with_filters(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        if self.nb_version[0] == 4:
            ret = nfclient.run_job(
                "netbox",
                "get_nornir_inventory",
                workers="any",
                kwargs={
                    "filters": [
                        {"name": '{in_list: ["ceos1"]}'},
                        {"name": '{contains: "fceos"}'},
                    ]
                },
            )
        elif self.nb_version[0] == 3:
            ret = nfclient.run_job(
                "netbox",
                "get_nornir_inventory",
                workers="any",
                kwargs={
                    "filters": [
                        {"name": ["ceos1"]},
                        {"name__ic": "fceos"},
                    ]
                },
            )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert (
                "ceos1" in res["result"]["hosts"]
            ), f"{worker} returned no results for ceos1"
            assert (
                "fceos4" in res["result"]["hosts"]
            ), f"{worker} returned no results for fceos4"
            for device, data in res["result"]["hosts"].items():
                assert all(
                    k in data for k in ["data", "hostname", "platform"]
                ), f"{worker}:{device} not all data returned"

    def test_source_platform_from_config_context(self, nfclient):
        # for iosxr1 platform data encoded in config context
        ret = nfclient.run_job(
            "netbox",
            "get_nornir_inventory",
            workers="any",
            kwargs={"devices": ["iosxr1"]},
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert (
                "iosxr1" in res["result"]["hosts"]
            ), f"{worker} returned no results for iosxr1"
            for device, data in res["result"]["hosts"].items():
                assert all(
                    k in data for k in ["data", "hostname", "platform"]
                ), f"{worker}:{device} not all data returned"

    def test_with_devices_nbdata_is_true(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_nornir_inventory",
            workers="any",
            kwargs={"devices": ["ceos1", "fceos4"], "nbdata": True},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert (
                "ceos1" in res["result"]["hosts"]
            ), f"{worker} returned no results for ceos1"
            assert (
                "fceos4" in res["result"]["hosts"]
            ), f"{worker} returned no results for fceos4"
            for device, data in res["result"]["hosts"].items():
                assert all(
                    k in data for k in ["data", "hostname", "platform"]
                ), f"{worker}:{device} not all device data returned"
                assert all(
                    k in data["data"]
                    for k in [
                        "airflow",
                        "asset_tag",
                        "config_context",
                        "custom_field_data",
                        "device_type",
                        "last_updated",
                        "location",
                        "platform",
                        "position",
                        "primary_ip4",
                        "primary_ip6",
                        "rack",
                        "role",
                        "serial",
                        "site",
                        "status",
                        "tags",
                        "tenant",
                    ]
                ), f"{worker}:{device} not all nbdata returned"

    def test_with_devices_add_interfaces(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_nornir_inventory",
            workers="any",
            kwargs={"devices": ["ceos1", "fceos4"], "interfaces": True},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert (
                "ceos1" in res["result"]["hosts"]
            ), f"{worker} returned no results for ceos1"
            assert (
                "fceos4" in res["result"]["hosts"]
            ), f"{worker} returned no results for fceos4"
            for device, data in res["result"]["hosts"].items():
                assert data["data"][
                    "interfaces"
                ], f"{worker}:{device} no interfaces data returned"
                for intf_name, intf_data in data["data"]["interfaces"].items():
                    assert all(
                        k in intf_data
                        for k in [
                            "vrf",
                            "mode",
                            "description",
                        ]
                    ), f"{worker}:{device}:{intf_name} not all interface data returned"

    def test_with_devices_add_interfaces_with_ip_and_inventory(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_nornir_inventory",
            workers="any",
            kwargs={
                "devices": ["ceos1", "fceos4"],
                "interfaces": {"ip_addresses": True, "inventory_items": True},
            },
        )
        pprint.pprint(ret)
        for worker, res in ret.items():
            assert (
                "ceos1" in res["result"]["hosts"]
            ), f"{worker} returned no results for ceos1"
            assert (
                "fceos4" in res["result"]["hosts"]
            ), f"{worker} returned no results for fceos4"
            for device, data in res["result"]["hosts"].items():
                assert data["data"][
                    "interfaces"
                ], f"{worker}:{device} no interfaces data returned"
                for intf_name, intf_data in data["data"]["interfaces"].items():
                    assert (
                        "ip_addresses" in intf_data
                    ), f"{worker}:{device}:{intf_name} no ip addresses data returned"
                    assert (
                        "inventory_items" in intf_data
                    ), f"{worker}:{device}:{intf_name} no invetnory data returned"

    def test_with_devices_add_connections(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_nornir_inventory",
            workers="any",
            kwargs={"devices": ["fceos4", "fceos5"], "connections": True},
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert (
                "fceos5" in res["result"]["hosts"]
            ), f"{worker} returned no results for fceos5"
            assert (
                "fceos4" in res["result"]["hosts"]
            ), f"{worker} returned no results for fceos4"
            for device, data in res["result"]["hosts"].items():
                assert data["data"][
                    "connections"
                ], f"{worker}:{device} no connections data returned"
                for intf_name, intf_data in data["data"]["connections"].items():
                    assert all(
                        k in intf_data
                        for k in [
                            "remote_interface",
                            "remote_device",
                        ]
                    ), f"{worker}:{device}:{intf_name} not all connection data returned"


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


class TestSyncDeviceFacts:
    def test_sync_device_facts_datasource_nornir(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "sync_device_facts",
            workers="any",
            kwargs={
                "datasource": "nornir",
                "devices": ["ceos-spine-1", "ceos-spine-2"],
            },
        )
        pprint.pprint(ret, width=200)
        for worker, res in ret.items():
            assert (
                "ceos-spine-1" in res["result"]
            ), f"{worker} returned no results for ceos-spine-1"
            assert (
                "ceos-spine-2" in res["result"]
            ), f"{worker} returned no results for ceos-spine-2"
            for device, device_data in res["result"].items():
                assert device_data["sync_device_facts"][
                    "serial"
                ], f"{worker}:{device} no serial number updated"

    def test_sync_device_facts_datasource_nornir_with_filters(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "sync_device_facts",
            workers="any",
            kwargs={
                "datasource": "nornir",
                "FC": "spine",
            },
        )
        pprint.pprint(ret, width=200)
        for worker, res in ret.items():
            assert (
                "ceos-spine-1" in res["result"]
            ), f"{worker} returned no results for ceos-spine-1"
            assert (
                "ceos-spine-2" in res["result"]
            ), f"{worker} returned no results for ceos-spine-2"
            for device, device_data in res["result"].items():
                assert device_data["sync_device_facts"][
                    "serial"
                ], f"{worker}:{device} no serial number updated"

    @pytest.mark.skip(reason="TBD")
    def test_sync_device_facts_non_existing_device(self, nfclient):
        pass

    def test_sync_device_facts_datasource_nornir_with_branch(self, nfclient):
        delete_branch("update_devices_branch_1", nfclient)

        ret = nfclient.run_job(
            "netbox",
            "sync_device_facts",
            workers="any",
            kwargs={
                "datasource": "nornir",
                "devices": ["ceos-spine-1", "ceos-spine-2"],
                "branch": "update_devices_branch_1",
            },
        )
        pprint.pprint(ret, width=200)
        for worker, res in ret.items():
            assert (
                "ceos-spine-1" in res["result"]
            ), f"{worker} returned no results for ceos-spine-1"
            assert (
                "ceos-spine-2" in res["result"]
            ), f"{worker} returned no results for ceos-spine-2"
            for device, device_data in res["result"].items():
                assert device_data["sync_device_facts"][
                    "serial"
                ], f"{worker}:{device} no serial number updated"
                assert device_data["branch"] == "update_devices_branch_1"


class TestSyncDeviceInterfaces:
    def test_sync_device_interfaces(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "sync_device_interfaces",
            workers="any",
            kwargs={
                "datasource": "nornir",
                "devices": ["ceos-spine-1", "ceos-spine-2"],
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
            for device, device_data in res["result"].items():
                assert device_data[
                    "sync_device_interfaces"
                ], f"{worker}:{device} no interfaces updated"

    @pytest.mark.skip(reason="TBD")
    def test_sync_device_interfaces_non_exisintg_device(self, nfclient):
        pass

    def test_sync_device_interfaces_with_branch(self, nfclient):
        delete_branch("update_interfaces_branch_1", nfclient)

        ret = nfclient.run_job(
            "netbox",
            "sync_device_interfaces",
            workers="any",
            kwargs={
                "datasource": "nornir",
                "devices": ["ceos-spine-1", "ceos-spine-2"],
                "branch": "update_interfaces_branch_1",
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
            for device, device_data in res["result"].items():
                assert device_data[
                    "sync_device_interfaces"
                ], f"{worker}:{device} no interfaces updated"
                assert device_data["branch"] == "update_interfaces_branch_1"


class TestSyncDeviceIP:
    def test_sync_device_ip(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "sync_device_ip",
            workers="any",
            kwargs={
                "datasource": "nornir",
                "devices": ["ceos-spine-1", "ceos-spine-2"],
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
            for device, device_data in res["result"].items():
                assert (
                    "created_ip" in device_data
                ), f"{worker}:{device} no create ip data"
                assert "sync_ip" in device_data, f"{worker}:{device} no update ip data"

    def test_sync_device_ip_dry_run(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "sync_device_ip",
            workers="any",
            kwargs={
                "datasource": "nornir",
                "devices": ["ceos-spine-1", "ceos-spine-2"],
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
                "ceos-spine-2" in res["result"]
            ), f"{worker} returned no results for ceos-spine-2"
            for device, device_data in res["result"].items():
                assert (
                    "created_ip_dry_run" in device_data
                ), f"{worker}:{device} no create ip data"
                assert (
                    "sync_ip_dry_run" in device_data
                ), f"{worker}:{device} no update ip data"

    def test_sync_device_ip_with_branch(self, nfclient):
        delete_branch("sync_device_ip_1", nfclient)
        ret = nfclient.run_job(
            "netbox",
            "sync_device_ip",
            workers="any",
            kwargs={
                "datasource": "nornir",
                "devices": ["ceos-spine-1", "ceos-spine-2"],
                "branch": "sync_device_ip_1",
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
            for device, device_data in res["result"].items():
                assert (
                    "created_ip" in device_data
                ), f"{worker}:{device} no create ip data"
                assert "sync_ip" in device_data, f"{worker}:{device} no update ip data"
                assert (
                    device_data["branch"] == "sync_device_ip_1"
                ), f"{worker}:{device} has no branch info"


class TestCreateIP:
    nb_version = None

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
            ), f"Should have been same IP address"
            assert (
                res1["result"]["description"] == res2["result"]["description"]
            ), f"Should have been same IP description"

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
            ), f"Should have been same IP address"
            assert (
                res1["result"]["description"] == res2["result"]["description"]
            ), f"Should have been same IP description"

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
            assert res1["result"]["address"], f"No ip allocated"

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
            assert res1["result"]["address"], f"No ip allocated"

    def test_create_ip_dry_run_new_ip(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        delete_ips("10.0.0.0/24", nfclient)

        if self.nb_version[0] == 4:
            # test dry rin for new ip
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
            assert res1["result"]["address"], f"No ip allocated"
            assert res1["dry_run"] is True, "No dry run flag set to true"
            assert res1["status"] == "unchanged", "Unexpected status"

            assert res2["failed"] == False, "Allocation failed"
            assert res2["result"]["address"], f"No ip allocated"
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
            assert res1["result"]["address"], f"No ip allocated"
            assert res1["dry_run"] is False, "No dry run flag set to true"
            assert res1["status"] == "created", "Unexpected status"

            assert res2["failed"] == False, "Allocation failed"
            assert res2["result"]["address"], f"No ip allocated"
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
            assert res1["result"]["address"], f"No ip allocated"
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
            assert res1["result"]["address"], f"No ip allocated"
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
        assert res1["result"]["address"] == "10.0.0.0/31", f"Wrong ip allocated"

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
        assert res1["result"]["address"] == "10.0.0.1/24", f"Wrong ip allocated"

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

        assert res1["result"]["address"] == "10.0.0.0/31", f"Wrong ip allocated"
        assert (
            res1["result"]["peer"]["address"] == "10.0.0.1/31"
        ), f"Wrong ip allocated for peer"
        assert (
            res1["result"]["peer"]["device"] == "fceos5"
        ), f"Wrong ip allocated for peer"
        assert (
            res1["result"]["peer"]["interface"] == "ae5.101"
        ), f"Wrong ip allocated for peer"

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

        assert res1["result"]["address"] == "10.0.0.0/31", f"Wrong ip allocated"
        assert res1["result"]["branch"] == "create_ip_with_peer", f"Wrong branch"
        assert (
            res1["result"]["peer"]["address"] == "10.0.0.1/31"
        ), f"Wrong ip allocated for peer"
        assert (
            res1["result"]["peer"]["device"] == "fceos5"
        ), f"Wrong ip allocated for peer"
        assert (
            res1["result"]["peer"]["interface"] == "ae5.101"
        ), f"Wrong ip allocated for peer"

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

        assert res1["result"]["address"] == "10.0.0.0/31", f"Wrong ip allocated"
        assert (
            "peer" not in res1["result"]
        ), f"SHould have been skipping peer ip creation"

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

        assert res1["result"]["address"] == "10.0.0.0/31", f"Wrong ip allocated"
        assert res2["result"]["address"] == "10.0.0.1/31", f"Wrong ip allocated"

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

        assert res1["result"]["address"] == "10.0.0.0/31", f"Wrong ip allocated"
        assert res2["result"]["address"] == "10.0.0.1/31", f"Wrong ip allocated"

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

        assert res1["result"]["address"] == "10.0.0.1/24", f"Wrong ip allocated"
        assert res2["result"]["address"] == "10.0.0.2/24", f"Wrong ip allocated"


class TestNetboxCache:
    def test_cache_list(self, nfclient):
        # populate the cache
        ret = nfclient.run_job(
            "netbox",
            "get_devices",
            workers="all",
            kwargs={"cache": True, "devices": ["ceos1", "fceos4", "fceos5"]},
        )

        # verify cache is present
        ret = nfclient.run_job(
            "netbox",
            "cache_list",
            workers="all",
            kwargs={},
        )

        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} - cache operation failed"
            assert len(res["result"]) > 0, f"{worker} - cache is empty"
            assert isinstance(
                res["result"], list
            ), f"{worker} - cache list result is not a list"
            assert "get_devices::fceos5" in res["result"]
            assert "get_devices::ceos1" in res["result"]
            assert "get_devices::fceos4" in res["result"]

    def test_cache_list_details(self, nfclient):
        # populate the cache
        ret = nfclient.run_job(
            "netbox",
            "get_devices",
            workers="all",
            kwargs={"cache": True, "devices": ["ceos1", "fceos4", "fceos5"]},
        )

        # verify cache is present
        ret = nfclient.run_job(
            "netbox",
            "cache_list",
            workers="all",
            kwargs={"details": True},
        )

        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} - cache operation failed"
            assert len(res["result"]) > 0, f"{worker} - cache is empty"
            assert isinstance(
                res["result"], list
            ), f"{worker} - cache list result is not a list"
            for item in res["result"]:
                assert all(
                    key in item for key in ["age", "creation", "expires", "key"]
                ), f"{worker} - not all cache list data details returned"

    def test_cache_list_filter(self, nfclient):
        # populate the cache
        ret = nfclient.run_job(
            "netbox",
            "get_devices",
            workers="all",
            kwargs={"cache": True, "devices": ["ceos1", "fceos4", "fceos5"]},
        )

        # verify cache is present
        ret = nfclient.run_job(
            "netbox",
            "cache_list",
            workers="all",
            kwargs={"keys": "*ceos1*"},
        )

        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} - cache operation failed"
            assert len(res["result"]) > 0, f"{worker} - cache is empty"
            assert isinstance(
                res["result"], list
            ), f"{worker} - cache list result is not a list"
            for key in res["result"]:
                assert (
                    "ceos1" in key
                ), f"{worker} - key '{key}' does not contain 'ceos1' patter "

    def test_cache_clear_all(self, nfclient):
        # populate the cache
        ret_populate = nfclient.run_job(
            "netbox",
            "get_devices",
            workers="all",
            kwargs={"cache": True, "devices": ["ceos1", "fceos4", "fceos5"]},
        )

        # clear cache
        ret_clear = nfclient.run_job(
            "netbox",
            "cache_clear",
            workers="all",
            kwargs={"keys": "*"},
        )

        # list cache
        ret_list = nfclient.run_job(
            "netbox",
            "cache_list",
            workers="all",
            kwargs={"keys": "*"},
        )

        print("\nret_populate:")
        pprint.pprint(ret_populate, width=150)

        print("\nret_clear:")
        pprint.pprint(ret_clear, width=150)

        print("\nret_list:")
        pprint.pprint(ret_list, width=150)

        for worker, res in ret_populate.items():
            assert (
                res["failed"] == False
            ), f"{worker} - get_devices populate operation failed"

        for worker, res in ret_clear.items():
            assert res["failed"] == False, f"{worker} - cache clear operation failed"
            assert (
                len(res["result"]) > 0
            ), f"{worker} - did not return list of cleared keys"
            assert isinstance(
                res["result"], list
            ), f"{worker} - cache clear result is not a list"

        for worker, res in ret_list.items():
            assert res["failed"] == False, f"{worker} - cache list operation failed"
            assert len(res["result"]) == 0, f"{worker} - cache is not empty"

    def test_cache_clear_key(self, nfclient):
        # populate the cache
        ret_populate = nfclient.run_job(
            "netbox",
            "get_devices",
            workers="all",
            kwargs={"cache": True, "devices": ["ceos1", "fceos4", "fceos5"]},
        )

        # list cache
        ret_list_before = nfclient.run_job(
            "netbox",
            "cache_list",
            workers="all",
            kwargs={"keys": "*"},
        )

        # clear cache
        ret_clear = nfclient.run_job(
            "netbox",
            "cache_clear",
            workers="all",
            kwargs={"key": "get_devices::ceos1"},
        )

        # list cache
        ret_list_after = nfclient.run_job(
            "netbox",
            "cache_list",
            workers="all",
            kwargs={"keys": "*"},
        )

        print("\nret_populate:")
        pprint.pprint(ret_populate, width=150)

        print("\nret_list_before:")
        pprint.pprint(ret_list_before, width=150)

        print("\nret_clear:")
        pprint.pprint(ret_clear, width=150)

        print("\nret_list_after:")
        pprint.pprint(ret_list_after, width=150)

        for worker, res in ret_populate.items():
            assert (
                res["failed"] == False
            ), f"{worker} - get_devices populate operation failed"

        for worker, res in ret_list_before.items():
            assert res["failed"] == False, f"{worker} - cache list operation failed"
            assert len(res["result"]) > 0, f"{worker} - cache is empty"
            assert (
                "get_devices::ceos1" in res["result"]
            ), f"{worker} - cache does not have get_devices::ceos1 key"

        for worker, res in ret_clear.items():
            assert res["failed"] == False, f"{worker} - cache clear operation failed"
            assert (
                len(res["result"]) > 0
            ), f"{worker} - did not return list of cleared keys"
            assert isinstance(
                res["result"], list
            ), f"{worker} - cache clear result is not a list"

        for worker, res in ret_list_after.items():
            assert res["failed"] == False, f"{worker} - cache list operation failed"
            assert len(res["result"]) > 0, f"{worker} - cache is empty"
            assert (
                "get_devices::ceos1" not in res["result"]
            ), f"{worker} - cache still has get_devices::ceos1 key"

    def test_cache_get_key(self, nfclient):
        # populate the cache
        ret = nfclient.run_job(
            "netbox",
            "get_devices",
            workers="all",
            kwargs={"cache": True, "devices": ["ceos1", "fceos4", "fceos5"]},
        )

        # verify cache is present
        ret = nfclient.run_job(
            "netbox",
            "cache_get",
            workers="all",
            kwargs={"key": "get_devices::ceos1"},
        )

        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} - cache operation failed"
            assert len(res["result"]) > 0, f"{worker} - cache is empty"
            assert isinstance(
                res["result"], dict
            ), f"{worker} - cache get result is not a dict"
            assert res["result"][
                "get_devices::ceos1"
            ], f"{worker} - cache get result key data is empty"

    def test_cache_get_keys(self, nfclient):
        # populate the cache
        ret = nfclient.run_job(
            "netbox",
            "get_devices",
            workers="all",
            kwargs={"cache": True, "devices": ["ceos1", "fceos4", "fceos5"]},
        )

        # verify cache is present
        ret = nfclient.run_job(
            "netbox",
            "cache_get",
            workers="all",
            kwargs={"keys": "*ceos1*"},
        )

        pprint.pprint(ret, width=200)

        for worker, res in ret.items():
            assert res["failed"] == False, f"{worker} - cache operation failed"
            assert len(res["result"]) > 0, f"{worker} - cache is empty"
            assert isinstance(
                res["result"], dict
            ), f"{worker} - cache get result is not a dict"
            for key in res["result"].keys():
                assert (
                    "ceos1" in key
                ), f"{worker} - cache key '{key}' does not contain ceos1 pattern"

    def test_cache_false(self, nfclient):
        # clear cache
        ret_clear = nfclient.run_job(
            "netbox",
            "cache_clear",
            workers="all",
            kwargs={"keys": "*"},
        )

        # query data with cache set to False
        ret_query = nfclient.run_job(
            "netbox",
            "get_devices",
            workers="all",
            kwargs={"cache": False, "devices": ["ceos1", "fceos4", "fceos5"]},
        )

        # verify cache is emty
        ret_list = nfclient.run_job(
            "netbox",
            "cache_list",
            workers="all",
            kwargs={"keys": "*"},
        )

        print("\nret_clear:")
        pprint.pprint(ret_clear, width=150)

        print("\nret_query:")
        pprint.pprint(ret_query, width=150)

        print("\nret_list:")
        pprint.pprint(ret_list, width=150)

        for worker, res in ret_clear.items():
            assert res["failed"] == False, f"{worker} - cache clear operation failed"

        for worker, res in ret_query.items():
            assert res["failed"] == False, f"{worker} - query netbox operation failed"

        for worker, res in ret_list.items():
            assert res["failed"] == False, f"{worker} - cache list operation failed"
            assert isinstance(
                res["result"], list
            ), f"{worker} - cache get result is not a dict"
            assert len(res["result"]) == 0, f"{worker} - cache is not empty"

    def test_cache_refresh(self, nfclient):
        # clear cache
        ret_clear = nfclient.run_job(
            "netbox",
            "cache_clear",
            workers="all",
            kwargs={"keys": "*"},
        )

        # query data with cache set to True
        ret_query_true = nfclient.run_job(
            "netbox",
            "get_devices",
            workers="all",
            kwargs={"cache": True, "devices": ["ceos1", "fceos4", "fceos5"]},
        )

        # get cache creation time
        ret_list_1st = nfclient.run_job(
            "netbox",
            "cache_list",
            workers="all",
            kwargs={"keys": "*", "details": True},
        )

        # query data with cache set to refresh
        ret_query_refresh = nfclient.run_job(
            "netbox",
            "get_devices",
            workers="all",
            kwargs={"cache": "refresh", "devices": ["ceos1", "fceos4", "fceos5"]},
        )

        # get cache creation time
        ret_list_2nd = nfclient.run_job(
            "netbox",
            "cache_list",
            workers="all",
            kwargs={"keys": "*", "details": True},
        )

        print("\nret_clear:")
        pprint.pprint(ret_clear, width=150)

        print("\nret_query_true:")
        pprint.pprint(ret_query_true, width=150)

        print("\nret_list_1st:")
        pprint.pprint(ret_list_1st, width=150)

        print("\nret_query_refresh:")
        pprint.pprint(ret_query_refresh, width=150)

        print("\nret_list_2nd:")
        pprint.pprint(ret_list_2nd, width=150)

        # verify no errors
        for worker, res in ret_clear.items():
            assert res["failed"] == False, f"{worker} - cache clear operation failed"

        for worker, res in ret_query_true.items():
            assert res["failed"] == False, f"{worker} - query netbox operation failed"

        for worker, res in ret_list_1st.items():
            assert res["failed"] == False, f"{worker} - ret_list_1st operation failed"

        for worker, res in ret_query_refresh.items():
            assert (
                res["failed"] == False
            ), f"{worker} - ret_query_refresh operation failed"

        for worker, res in ret_list_2nd.items():
            assert res["failed"] == False, f"{worker} - ret_list_2nd operation failed"

        # compare 2nd list items expiration time is after the 1st one
        for worker_2nd, res_2nd in ret_list_2nd.items():
            for item_2nd in res_2nd["result"]:
                for item_1st in ret_list_1st[worker_2nd]["result"]:
                    if item_2nd["key"] == item_1st["key"]:
                        assert item_2nd["expires"] > item_1st["expires"]


class TestGetContainerlabInventory:
    nb_version = None

    def test_get_containerlab_inventory_devices(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_containerlab_inventory",
            workers="any",
            kwargs={
                "devices": ["fceos4", "fceos5"],
                "lab_name": "foobar",
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            assert all(
                k in res["result"] for k in ["mgmt", "name", "topology"]
            ), f"{worker} - not all clab inventory data returned"
            assert res["result"]["topology"][
                "links"
            ], f"{worker} - no clab inventory links data returned"
            assert res["result"]["topology"][
                "nodes"
            ], f"{worker} - no clab inventory nodes data returned"
            assert (
                res["result"]["name"] == "foobar"
            ), f"{worker} - clab inventory name is not foobar"

    def test_get_containerlab_inventory_non_existing_devices(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_containerlab_inventory",
            workers="any",
            kwargs={
                "devices": ["fceosabc", "fceosxyz"],
                "lab_name": "foobar",
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert res["errors"], f"{worker} - received no error"
            assert res["failed"] == True, f"{worker} - should have failed"
            assert all(
                k in res["result"] for k in ["mgmt", "name", "topology"]
            ), f"{worker} - not all clab inventory data returned"
            assert (
                res["result"]["topology"]["links"] == []
            ), f"{worker} - clab inventory links data returned"
            assert (
                res["result"]["topology"]["nodes"] == {}
            ), f"{worker} - clab inventory nodes data returned"

    def test_get_containerlab_inventory_by_tenant(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        if self.nb_version >= (4, 3, 0):
            ret = nfclient.run_job(
                "netbox",
                "get_containerlab_inventory",
                workers="any",
                kwargs={
                    "tenant": "NORFAB",
                    "lab_name": "foobar",
                },
            )
        else:
            ret = nfclient.run_job(
                "netbox",
                "get_containerlab_inventory",
                workers="any",
                kwargs={
                    "tenant": "norfab",
                    "lab_name": "foobar",
                },
            )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            assert all(
                k in res["result"] for k in ["mgmt", "name", "topology"]
            ), f"{worker} - not all clab inventory data returned"
            assert res["result"]["topology"][
                "links"
            ], f"{worker} - no clab inventory links data returned"
            assert res["result"]["topology"][
                "nodes"
            ], f"{worker} - no clab inventory nodes data returned"
            assert (
                res["result"]["name"] == "foobar"
            ), f"{worker} - clab inventory name is not foobar"

    def test_get_containerlab_inventory_by_filters(self, nfclient):
        if self.nb_version is None:
            self.nb_version = get_nb_version(nfclient)

        if self.nb_version >= (4, 3, 0):
            ret = nfclient.run_job(
                "netbox",
                "get_containerlab_inventory",
                workers="any",
                kwargs={
                    "filters": [
                        '{name: {i_contains: "ceos-spine"}, status: STATUS_ACTIVE}'
                    ],
                    "lab_name": "foobar",
                },
            )
        else:
            ret = nfclient.run_job(
                "netbox",
                "get_containerlab_inventory",
                workers="any",
                kwargs={
                    "filters": [{"q": "ceos-spine", "status": "active"}],
                    "lab_name": "foobar",
                },
            )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            assert all(
                k in res["result"] for k in ["mgmt", "name", "topology"]
            ), f"{worker} - not all clab inventory data returned"
            assert res["result"]["topology"][
                "links"
            ], f"{worker} - no clab inventory links data returned"
            assert (
                len(res["result"]["topology"]["nodes"]) == 2
            ), f"{worker} - clab inventory nodes data wromg"
            assert (
                res["result"]["name"] == "foobar"
            ), f"{worker} - clab inventory name is not foobar"

    def test_get_containerlab_inventory_with_nb_instance(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_containerlab_inventory",
            workers="any",
            kwargs={
                "devices": ["fceos4", "fceos5"],
                "lab_name": "foobar",
                "instance": "preprod",
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            assert all(
                k in res["result"] for k in ["mgmt", "name", "topology"]
            ), f"{worker} - not all clab inventory data returned"
            assert res["result"]["topology"][
                "links"
            ], f"{worker} - no clab inventory links data returned"
            assert res["result"]["topology"][
                "nodes"
            ], f"{worker} - no clab inventory nodes data returned"
            assert (
                res["result"]["name"] == "foobar"
            ), f"{worker} - clab inventory name is not foobar"

    def test_get_containerlab_inventory_with_image(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_containerlab_inventory",
            workers="any",
            kwargs={
                "devices": ["ceos1"],
                "lab_name": "foobar",
                "image": "ceos:latest",
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            assert all(
                k in res["result"] for k in ["mgmt", "name", "topology"]
            ), f"{worker} - not all clab inventory data returned"
            assert res["result"]["topology"][
                "nodes"
            ], f"{worker} - no clab inventory nodes data returned"
            for node_name, node_data in res["result"]["topology"]["nodes"].items():
                assert (
                    node_data["image"] == "ceos:latest"
                ), f"{worker} - node {node_name} image is not ceos:latest"

    def test_get_containerlab_inventory_run_out_of_ports(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_containerlab_inventory",
            workers="any",
            kwargs={
                "devices": ["fceos4", "fceos5"],
                "lab_name": "foobar",
                "ports": [10000, 10005],
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert res["errors"], f"{worker} - received no error"
            assert res["failed"] == True, f"{worker} - should have failed"

    def test_get_containerlab_inventory_run_out_of_ips(self, nfclient):
        ret = nfclient.run_job(
            "netbox",
            "get_containerlab_inventory",
            workers="any",
            kwargs={
                "devices": ["fceos4", "fceos5", "ceos1"],
                "lab_name": "foobar",
                "ipv4_subnet": "172.100.100.0/30",
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert res["errors"], f"{worker} - received no error"
            assert res["failed"] == True, f"{worker} - should have failed"

    def test_get_containerlab_inventory_with_ports_map(self, nfclient):
        ports_map = {
            "fceos4": [
                "10007:22/tcp",
                "10008:23/tcp",
                "10009:80/tcp",
                "10010:161/udp",
                "10011:443/tcp",
                "10012:830/tcp",
                "10013:8080/tcp",
            ]
        }
        ret = nfclient.run_job(
            "netbox",
            "get_containerlab_inventory",
            workers="any",
            kwargs={
                "devices": ["fceos4", "fceos5"],
                "lab_name": "foobar",
                "ports_map": ports_map,
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            assert all(
                k in res["result"] for k in ["mgmt", "name", "topology"]
            ), f"{worker} - not all clab inventory data returned"
            assert res["result"]["topology"][
                "nodes"
            ], f"{worker} - no clab inventory nodes data returned"
            assert (
                res["result"]["topology"]["nodes"]["fceos4"]["ports"]
                == ports_map["fceos4"]
            ), f"{worker} - ports map not applied for fceos4"
            assert res["result"]["topology"]["nodes"]["fceos5"][
                "ports"
            ], f"{worker} - no ports allocated for fceos5"
            assert all(
                p.startswith("1200")
                for p in res["result"]["topology"]["nodes"]["fceos5"]["ports"]
            ), f"{worker} - ports for fceos5 allocated correctly"

    @pytest.mark.parametrize("cache", cache_options)
    def test_get_containerlab_inventory_with_cache(self, nfclient, cache):
        ret = nfclient.run_job(
            "netbox",
            "get_containerlab_inventory",
            workers="any",
            kwargs={
                "devices": ["fceos4", "fceos5"],
                "lab_name": "foobar",
                "cache": cache,
            },
        )
        pprint.pprint(ret)

        for worker, res in ret.items():
            assert not res["errors"], f"{worker} - received error"
            assert all(
                k in res["result"] for k in ["mgmt", "name", "topology"]
            ), f"{worker} - not all clab inventory data returned"
            assert res["result"]["topology"][
                "links"
            ], f"{worker} - no clab inventory links data returned"
            assert res["result"]["topology"][
                "nodes"
            ], f"{worker} - no clab inventory nodes data returned"
            assert (
                res["result"]["name"] == "foobar"
            ), f"{worker} - clab inventory name is not foobar"


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
            ), f"Should have been same prefix"
            assert (
                res1["result"]["description"] == res2["result"]["description"]
            ), f"Should have been same prefix description"

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
            ), f"Should have been different prefix"

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
                ), f"Result has no errors"

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
            ), f"Should have been same prefix"
            assert (
                res1["result"]["prefix"] != res3["result"]["prefix"]
            ), f"Should have been different prefix"

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
            ), f"Should have been same prefix"
            assert (
                res1["result"]["description"] == res2["result"]["description"]
            ), f"Should have been same prefix description"

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
            ), f"Should have been same prefix"
            assert (
                res1["result"]["description"] == res2["result"]["description"]
            ), f"Should have been same prefix description"
            assert (
                res1["result"]["prefix"] != res3["result"]["prefix"]
            ), f"Should have been different prefix"

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
