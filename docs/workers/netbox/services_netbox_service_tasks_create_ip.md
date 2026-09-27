---
tags:
  - netbox
---

# Netbox Create IP Task

> task api name: `create_ip`

Allocates the next available IP address from a parent prefix, or reuses an existing matching IP address. The task can assign the IP to a device interface, update metadata, set the address as primary, and optionally create an address for the connected peer interface.

The task can also be called from Nornir templates through the [netbox.create_ip Jinja2 filter](../nornir/services_nornir_service_jinja2_filters.md#netboxcreate_ip).

## VRRP virtual IP allocation

Supply `vrrp_group` with an existing, uniquely named VRRPv2 or VRRPv3 group.
The task assigns the address to that group and defaults its role to `vrrp`.
Repeated calls reuse the group's address within the selected prefix, optionally
matching `description`. Missing, ambiguous, or non-VRRP groups fail before allocation.

```yaml
create_ip:
  prefix:
    site: LAB
    role: MGMT
  vrrp_group: LAB-mgmt
```

Group allocation cannot accompany `device`, `interface`, or `is_primary: true`.
It disables peer allocation. Dry runs resolve the group without writing; the
existing dry-run limitation for `mask_len` still applies. Results include
`vrrp_group` when supplied. Omitting it preserves existing task behavior.

## Output

Returns the allocated or updated IP address data. When `create_peer_ip=True`, peer allocation details may be included in the result.

```python
{
    "address": "10.0.0.1/31",
    "device": "ceos-leaf-1",
    "interface": "Ethernet1",
    "description": "leaf-1 to spine-1",
    "...": "...",
}
```

## Notes / Gotchas

- `prefix` can be a network string, a prefix description, or a dictionary of pynetbox prefix filters.
- When `mask_len` differs from the parent prefix length, the task creates or reuses a child prefix through `create_prefix`.
- In dry-run mode, `mask_len` is ignored and the candidate IP is allocated directly from the parent prefix.
- IPv4 /32 and IPv6 /128 allocations automatically disable peer creation and peer-subnet reuse, including when the supplied parent is itself a host prefix.
- Branch writes require the [NetBox Branching Plugin](https://github.com/netboxlabs/netbox-branching).

## Examples

=== "CLI"

    Allocate an IP for an interface:

    ```bash
    nf#netbox create ip prefix 10.0.0.0/24 device ceos-leaf-1 interface Ethernet1 description "leaf-1 uplink"
    ```

    Allocate a `/31` link subnet and create the peer IP:

    ```bash
    nf#netbox create ip prefix 10.0.0.0/24 device ceos-leaf-1 interface Ethernet1 mask-len 31 create-peer-ip
    ```

    Set DNS name and mark the address as primary:

    ```bash
    nf#netbox create ip prefix loopbacks device ceos-leaf-1 interface Loopback0 dns-name ceos-leaf-1.example.net is-primary
    ```

    Preview allocation without writing:

    ```bash
    nf#netbox create ip prefix 10.0.0.0/24 device ceos-leaf-1 interface Ethernet1 dry-run
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    nf = NorFab(inventory="./inventory.yaml")
    nf.start()
    client = nf.make_client()

    # allocate an IP for an interface
    result = client.run_job(
        "netbox",
        "create_ip",
        workers="any",
        kwargs={
            "prefix": "10.0.0.0/24",
            "device": "ceos-leaf-1",
            "interface": "Ethernet1",
            "description": "leaf-1 uplink",
        },
    )

    # allocate a /31 link subnet and peer IP
    result = client.run_job(
        "netbox",
        "create_ip",
        workers="any",
        kwargs={
            "prefix": {"prefix": "10.0.0.0/24", "site": "lab"},
            "device": "ceos-leaf-1",
            "interface": "Ethernet1",
            "mask_len": 31,
            "create_peer_ip": True,
        },
    )

    nf.destroy()
    ```

## NORFAB Netbox Create IP Command Shell Reference

NorFab shell supports these command options for Netbox `create_ip` task:

```bash
nf# man tree netbox.create.ip
root
└── netbox:    Netbox service
    └── create:    Create objects in Netbox
        └── ip:    Allocate next available IP address from prefix
            ├── timeout:    Job timeout
            ├── workers:    Filter worker to target, default 'any'
            ├── verbose-result:    Control output details, default 'False'
            ├── progress:    Display progress events, default 'True'
            ├── instance:    Netbox instance name to target
            ├── dry-run:    Do not commit to database
            ├── prefix:    Prefix to allocate IP address from, can also provide prefix name or filters
            ├── device:    Device name to associate IP address with
            ├── interface:    Device interface name to associate IP address with
            ├── description:    IP address description
            ├── vrf:    VRF to associate with IP address
            ├── tags:    Tags to add to IP address
            ├── dns-name:    IP address DNS name
            ├── tenant:    Tenant name to associate with IP address
            ├── comments:    IP address comments field
            ├── role:    IP address functional role
            ├── status:    IP address status
            ├── is-primary:    Set the IP address as the primary IP for the device
            ├── mask-len:    Mask length to use for IP address
            ├── create-peer-ip:    Create link peer IP address as well
            └── branch:    Branching plugin branch name to use
nf#
```

## Python API Reference

::: norfab.workers.netbox_worker.ip_tasks.NetboxIpTasks.create_ip
