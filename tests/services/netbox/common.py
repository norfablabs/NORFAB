import ipaddress

import pynetbox
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from tests.netbox_data import NB_API_TOKEN, NB_URL
except ModuleNotFoundError as exc:
    if exc.name not in {"tests", "tests.netbox_data"}:
        raise
    from netbox_data import NB_API_TOKEN, NB_URL

cache_options = [True, False, "refresh", "force"]


class TimeoutHTTPAdapter(HTTPAdapter):
    """Apply bounded connect/read timeouts to pynetbox requests."""

    def send(self, request, **kwargs):
        kwargs.setdefault("timeout", (10, 60))
        return super().send(request, **kwargs)


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
    nb = get_pynetbox(nfclient)
    for record in list(nb.dcim.interfaces.filter(device=device, name=interface)):
        record.delete()


def delete_prefixes_within(prefix, nfclient):
    nb = get_pynetbox(nfclient)
    for record in list(nb.ipam.prefixes.filter(within=prefix)):
        record.delete()


def delete_ips(prefix, nfclient):
    nb = get_pynetbox(nfclient)
    for record in list(nb.ipam.ip_addresses.filter(parent=prefix)):
        record.delete()


def clear_nb_cache(keys, nfclient):
    return nfclient.run_job(
        "netbox",
        "cache_clear",
        workers="all",
        kwargs={"keys": keys},
    )


def delete_ip_address(nfclient, address):
    """Delete a specific IP address (e.g. '10.3.4.1/32') from NetBox IPAM."""
    nb = get_pynetbox(nfclient)
    for record in list(nb.ipam.ip_addresses.filter(address=address)):
        record.delete()


def delete_mac_addresses_from_interface(nfclient, device, interface):
    """Delete all MAC addresses assigned to a given device interface."""
    nb = get_pynetbox(nfclient)
    for record in list(
        nb.dcim.mac_addresses.filter(device=device, interface=interface)
    ):
        record.delete()


def delete_test_sync_ips(nfclient, devices):
    """Delete test-range IPs assigned to interfaces on the given devices."""
    pynb = get_pynetbox(nfclient)
    devices = devices if isinstance(devices, list) else [devices]
    networks = (
        ipaddress.ip_network("10.3.0.0/16"),
        ipaddress.ip_network("10.83.0.0/16"),
        ipaddress.ip_network("10.84.0.0/16"),
        ipaddress.ip_network("10.184.0.0/16"),
        ipaddress.ip_network("172.83.0.0/16"),
        ipaddress.ip_network("172.183.0.0/16"),
        ipaddress.ip_network("198.21.0.0/16"),
        ipaddress.ip_network("198.51.83.0/24"),
        ipaddress.ip_network("198.51.183.0/24"),
        ipaddress.ip_network("2001:beef::/32"),
        ipaddress.ip_network("2001:83::/32"),
        ipaddress.ip_network("2001:83ef::/32"),
        ipaddress.ip_network("2001:83b8::/32"),
    )
    for device in devices:
        for ip in pynb.ipam.ip_addresses.filter(device=device):
            address = ipaddress.ip_interface(ip.address).ip
            if any(address in network for network in networks):
                ip.delete()
    print(f"Deleted TEST_SYNC IPs on {devices}")


def delete_all_mac_addresses(nfclient, devices):
    """Delete all MAC addresses assigned to any interface on the given devices."""
    devices = devices if isinstance(devices, list) else [devices]
    nb = get_pynetbox(nfclient)
    for device in devices:
        for record in list(nb.dcim.mac_addresses.filter(device=device)):
            record.delete()


def delete_interfaces_with_description(nfclient, devices, description_contains):
    """Delete all NetBox interfaces whose description contains the given substring."""
    devices = devices if isinstance(devices, list) else [devices]
    nb = get_pynetbox(nfclient)
    for device in devices:
        records = list(
            nb.dcim.interfaces.filter(
                device=device, description__ic=description_contains
            )
        )
        records.sort(
            key=lambda item: (
                0 if getattr(item, "parent", None) else 1,
                0 if getattr(item, "lag", None) else 1,
                item.name,
            )
        )
        for record in records:
            record.delete()


def get_pynetbox(nfclient):
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(
            {"DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "PUT", "TRACE"}
        ),
    )
    session = requests.Session()
    adapter = TimeoutHTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    api = pynetbox.api(url=NB_URL, token=NB_API_TOKEN, threading=True)
    api.http_session = session
    return api
