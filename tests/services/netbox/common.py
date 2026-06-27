import pynetbox

try:
    from tests.netbox_data import NB_API_TOKEN, NB_URL
except ModuleNotFoundError as exc:
    if exc.name not in {"tests", "tests.netbox_data"}:
        raise
    from netbox_data import NB_API_TOKEN, NB_URL

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


def delete_interfaces(nfclient, device, interface):
    resp_get = nfclient.run_job(
        "netbox",
        "rest",
        workers="any",
        kwargs={
            "method": "get",
            "api": "/dcim/interfaces/",
            "params": {"device": device, "name": interface},
        },
    )
    print(f"Retrieved interface '{device}:{interface}' - {resp_get}")
    worker, interfaces = tuple(resp_get.items())[0]
    if interfaces["result"]["results"]:
        resp = nfclient.run_job(
            "netbox",
            "rest",
            workers="any",
            kwargs={
                "method": "delete",
                "api": f"/dcim/interfaces/{interfaces['result']['results'][0]['id']}",
            },
        )
        print(f"Deleted interface '{device}:{interface}'")
    else:
        print(f"Interface '{device}:{interface}' does not exist in Netbox")


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
        # pprint.pprint(delete_ip)'


def clear_nb_cache(keys, nfclient):
    return nfclient.run_job(
        "netbox",
        "cache_clear",
        workers="all",
        kwargs={"keys": keys},
    )


def delete_ip_address(nfclient, address):
    """Delete a specific IP address (e.g. '10.3.4.1/32') from NetBox IPAM."""
    resp = nfclient.run_job(
        "netbox",
        "rest",
        workers="any",
        kwargs={
            "method": "get",
            "api": "/ipam/ip-addresses/",
            "params": {"address": address},
        },
    )
    worker, result = tuple(resp.items())[0]
    for ip in result["result"]["results"]:
        nfclient.run_job(
            "netbox",
            "rest",
            workers="any",
            kwargs={
                "method": "delete",
                "api": f"/ipam/ip-addresses/{ip['id']}/",
            },
        )
    print(f"Deleted IP address '{address}'")


def delete_mac_addresses_from_interface(nfclient, device, interface):
    """Delete all MAC addresses assigned to a given device interface."""
    resp = nfclient.run_job(
        "netbox",
        "rest",
        workers="any",
        kwargs={
            "method": "get",
            "api": "/dcim/mac-addresses/",
            "params": {
                "assigned_object_type": "dcim.interface",
                "device": device,
                "interface": interface,
            },
        },
    )
    worker, result = tuple(resp.items())[0]
    for mac in result["result"]["results"]:
        nfclient.run_job(
            "netbox",
            "rest",
            workers="any",
            kwargs={
                "method": "delete",
                "api": f"/dcim/mac-addresses/{mac['id']}/",
            },
        )
    print(f"Deleted MAC addresses from '{device}:{interface}'")


def delete_test_sync_ips(nfclient, devices):
    """Delete IPs in 10.3.0.0/16 and 2001:beef::/32 ranges that are assigned to
    interfaces with TEST_SYNC in their description on the given devices."""
    pynb = get_pynetbox(nfclient)
    for parent_prefix in ["10.3.0.0/16", "2001:beef::/32"]:
        for ip in pynb.ipam.ip_addresses.filter(parent=parent_prefix):
            ip.delete()
    print(f"Deleted TEST_SYNC IPs in 10.3.0.0/16 and 2001:beef::/32")


def delete_all_mac_addresses(nfclient, devices):
    """Delete all MAC addresses assigned to any interface on the given devices."""
    devices = devices if isinstance(devices, list) else [devices]
    for device in devices:
        resp = nfclient.run_job(
            "netbox",
            "rest",
            workers="any",
            kwargs={
                "method": "get",
                "api": "/dcim/mac-addresses/",
                "params": {"device": device, "limit": 200},
            },
        )
        worker, result = tuple(resp.items())[0]
        for mac in result["result"]["results"]:
            nfclient.run_job(
                "netbox",
                "rest",
                workers="any",
                kwargs={
                    "method": "delete",
                    "api": f"/dcim/mac-addresses/{mac['id']}/",
                },
            )
        print(f"Deleted all MAC addresses for device '{device}'")


def delete_interfaces_with_description(nfclient, devices, description_contains):
    """Delete all NetBox interfaces whose description contains the given substring."""
    devices = devices if isinstance(devices, list) else [devices]
    for device in devices:
        resp = nfclient.run_job(
            "netbox",
            "rest",
            workers="any",
            kwargs={
                "method": "get",
                "api": "/dcim/interfaces/",
                "params": {"device": device, "description__ic": description_contains},
            },
        )
        worker, result = tuple(resp.items())[0]
        for intf in result["result"]["results"]:
            nfclient.run_job(
                "netbox",
                "rest",
                workers="any",
                kwargs={
                    "method": "delete",
                    "api": f"/dcim/interfaces/{intf['id']}/",
                },
            )
        print(
            f"Deleted interfaces with description containing '{description_contains}' on '{device}'"
        )


def get_pynetbox(nfclient):
    return pynetbox.api(url=NB_URL, token=NB_API_TOKEN)
