---
tags:
  - netbox
---

# NetBox Create BGP Peering Task

> task api name: `create_bgp_peering`

Creates one or many BGP sessions in NetBox. Supports single-session mode (individual keyword arguments) and bulk mode (`bulk_create` list of dicts). IP addresses and ASNs are resolved from IPAM or created on-demand. When `local_interface` is provided the local address is resolved from IPAM; for P2P subnets (/30, /31, /127) the remote address is derived automatically. Optionally creates a mirror (reverse) session on the remote device.

## How It Works

1. Client submits `create_bgp_peering` request to NetBox worker
2. NetBox worker validates that the BGP plugin is installed
3. Worker resolves the RIR ID once (when `rir` is provided) for on-demand ASN creation
4. For each spec — when `local_interface` is supplied, the interface is looked up in IPAM to derive `local_address`; P2P peer IP and remote device are derived from the subnet
5. Worker pre-fetches all existing sessions for targeted devices (single API call) to support idempotency
6. For each session spec:
    - Idempotency check — if the session name already exists, it is added to `exists` and skipped
    - In dry-run mode — the name is added to `create` and processing continues
    - Local and remote IPs are resolved from IPAM (or created when not found)
    - Local and remote ASNs are resolved from IPAM (or created when `rir` is provided)
    - Optional fields (peer group, routing policies, prefix lists) are resolved or created by name
    - When `create_reverse=True` a mirror session is built by swapping local/remote IPs and ASNs
7. All prepared payloads are sent to NetBox in a single bulk-create call

## Prerequisites

- **NetBox BGP plugin** (`netbox-bgp`) must be installed and enabled on the NetBox instance.

## Branching Support

`create_bgp_peering` is branch-aware. Pass `branch=<name>` to write all sessions into a [NetBox Branching Plugin](https://github.com/netboxlabs/netbox-branching) branch instead of main.

## Output

Normal mode returns the created, existing, and skipped BGP session details. In dry-run mode, the task returns the session names that would be created and the sessions that already exist.

## Dry Run Mode

`dry_run=True` returns session names without any NetBox writes:

```python
{
    "create": ["<session_name>", ...],
    "exists": ["<session_name>", ...],
}
```

Sessions that already exist in NetBox appear in `exists` regardless of dry-run mode.

## Session Naming

By default, sessions are named using:

```text
{device}_{local_address}_{remote_address}
```

Use the `name_template` parameter for a custom naming scheme. The template is a Python format string with the variables `device`, `local_address`, and `remote_address`.

Example:

```text
name_template="{device}_BGP_{local_address}"
# ceos-spine-1_BGP_10.0.0.1
```

## Reverse (Mirror) Session

When `create_reverse=True` (the default), the task also creates a mirror session on the remote device by swapping local and remote IPs and ASNs. The remote device is identified from IPAM by looking up the interface that holds the remote address.

Set `create_reverse=False` to suppress mirror session creation.

!!! note
    `sync_bgp_peerings` passes `create_reverse=False` when delegating to `create_bgp_peering` because it manages both sides of a session independently via the diff.

## VRF Custom Field

The VRF reference is **always** stored in a BGP session custom field that must be
configured as type **Object** in NetBox pointing to the VRF content-type.  This means
NetBox stores a reference to a single VRF object, not a plain string.

By default `vrf_custom_field="vrf"` means the VRF object reference is written into
`custom_fields["vrf"]`.  Pass a different name to target a different custom field:

```python
result = client.run_job(
    "netbox",
    "create_bgp_peering",
    workers="any",
    kwargs={
        "name": "ceos-spine-1_10.0.0.1_10.0.0.2",
        "device": "ceos-spine-1",
        "local_address": "10.0.0.1",
        "remote_address": "10.0.0.2",
        "local_as": 65001,
        "remote_as": 65002,
        "rir": "lab",
        "vrf": "PROD_VRF",
        "vrf_custom_field": "tenant_vrf",  # Object-type custom field -> VRF
    },
)
```

The `vrf` parameter accepts a VRF name which is resolved to a NetBox VRF object ID before
being stored as an object reference in the custom field.

## Examples

=== "CLI"

    Create a single BGP session:

    ```bash
    nf#netbox create bgp-peering name ceos-spine-1_10.0.0.1_10.0.0.2 device ceos-spine-1 local-address 10.0.0.1 remote-address 10.0.0.2 local-as 65001 remote-as 65002 rir lab
    ```

    Dry run - preview what would be created:

    ```bash
    nf#netbox create bgp-peering name ceos-spine-1_10.0.0.1_10.0.0.2 device ceos-spine-1 local-address 10.0.0.1 remote-address 10.0.0.2 local-as 65001 remote-as 65002 dry-run
    ```

    Create session from interface (P2P peer derived automatically):

    ```bash
    nf#netbox create bgp-peering device ceos-spine-1 local-interface Ethernet1 local-as 65001 rir lab
    ```

    Create session into a NetBox branch:

    ```bash
    nf#netbox create bgp-peering name ceos-spine-1_10.0.0.1_10.0.0.2 device ceos-spine-1 local-address 10.0.0.1 remote-address 10.0.0.2 local-as 65001 remote-as 65002 rir lab branch my-bgp-branch
    ```

=== "Python"

    Context manager - create a single session:

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="./inventory.yaml") as nf:
        client = nf.make_client()

        result = client.run_job(
            "netbox",
            "create_bgp_peering",
            workers="any",
            kwargs={
                "name": "ceos-spine-1_10.0.0.1_10.0.0.2",
                "device": "ceos-spine-1",
                "local_address": "10.0.0.1",
                "remote_address": "10.0.0.2",
                "local_as": 65001,
                "remote_as": 65002,
                "rir": "lab",
            },
        )
    ```

    Context manager - bulk create several sessions:

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="./inventory.yaml") as nf:
        client = nf.make_client()

        result = client.run_job(
            "netbox",
            "create_bgp_peering",
            workers="any",
            kwargs={
                "bulk_create": [
                    {
                        "name": "ceos-spine-1_10.0.0.1_10.0.0.2",
                        "device": "ceos-spine-1",
                        "local_address": "10.0.0.1",
                        "remote_address": "10.0.0.2",
                        "local_as": 65001,
                        "remote_as": 65002,
                        "description": "spine-1 to leaf-1",
                    },
                    {
                        "name": "ceos-spine-2_10.0.0.5_10.0.0.6",
                        "device": "ceos-spine-2",
                        "local_address": "10.0.0.5",
                        "remote_address": "10.0.0.6",
                        "local_as": 65001,
                        "remote_as": 65003,
                        "description": "spine-2 to leaf-1",
                    },
                ],
                "peer_group": "EBGP_LEAFS",
                "import_policies": ["IMPORT_FROM_LEAFS"],
                "export_policies": ["EXPORT_TO_LEAFS"],
                "prefix_list_in": "PL-IN-LEAFS",
                "prefix_list_out": "PL-OUT-LEAFS",
                "rir": "lab",
                "message": "Create leaf BGP peerings",
            },
        )
    ```

    Context manager - create from local interfaces:

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="./inventory.yaml") as nf:
        client = nf.make_client()

        result = client.run_job(
            "netbox",
            "create_bgp_peering",
            workers="any",
            kwargs={
                "bulk_create": [
                    {
                        "name": "ceos-spine-1_Ethernet1",
                        "device": "ceos-spine-1",
                        "local_interface": "Ethernet1",
                        "local_as": 65001,
                    },
                    {
                        "name": "ceos-spine-1_Ethernet2",
                        "device": "ceos-spine-1",
                        "local_interface": "Ethernet2",
                        "local_as": 65001,
                    },
                ],
                "rir": "lab",
                "create_reverse": True,
            },
        )
    ```

    Direct lifecycle - dry run and then create from interface data:

    ```python
    from norfab.core.nfapi import NorFab

    nf = NorFab(inventory="./inventory.yaml")
    try:
        nf.start()
        client = nf.make_client()

        preview = client.run_job(
            "netbox",
            "create_bgp_peering",
            workers="any",
            kwargs={
                "name": "ceos-spine-1_10.0.0.1_10.0.0.2",
                "device": "ceos-spine-1",
                "local_address": "10.0.0.1",
                "remote_address": "10.0.0.2",
                "local_as": 65001,
                "remote_as": 65002,
                "dry_run": True,
            },
        )

        result = client.run_job(
            "netbox",
            "create_bgp_peering",
            workers="any",
            kwargs={
                "device": "ceos-spine-1",
                "local_interface": "Ethernet1",
                "local_as": 65001,
                "asn_source": "custom_fields.asn",
                "rir": "lab",
                "branch": "my-bgp-branch",
            },
        )
    finally:
        nf.destroy()
    ```

    Direct lifecycle - use a custom name template and VRF custom field:

    ```python
    from norfab.core.nfapi import NorFab

    nf = NorFab(inventory="./inventory.yaml")
    try:
        nf.start()
        client = nf.make_client()

        result = client.run_job(
            "netbox",
            "create_bgp_peering",
            workers="any",
            kwargs={
                "device": "ceos-spine-1",
                "local_interface": "Ethernet[1-2]",
                "local_as": 65001,
                "asn_source": "custom_fields.asn",
                "name_template": "{{ device }}_{{ vrf }}_{{ remote_address }}",
                "vrf": "PROD",
                "vrf_custom_field": "tenant_vrf",
                "peer_group": "EBGP_LEAFS",
                "create_reverse": False,
                "rir": "lab",
                "message": "Create PROD BGP peerings from interface range",
            },
        )
    finally:
        nf.destroy()
    ```

    Direct lifecycle - resolve ASNs from an IPAM ASN query:

    ```python
    from norfab.core.nfapi import NorFab

    nf = NorFab(inventory="./inventory.yaml")
    try:
        nf.start()
        client = nf.make_client()

        result = client.run_job(
            "netbox",
            "create_bgp_peering",
            workers="any",
            kwargs={
                "device": "ceos-spine-1",
                "local_interface": "Ethernet1",
                "asn_source": {"asn": 65001},
                "name_template": "{{ device }}_ASN{{ local_as }}_{{ remote_address }}",
                "rir": "lab",
                "dry_run": True,
            },
        )
    finally:
        nf.destroy()
    ```

## NORFAB NetBox Create BGP Peering Command Shell Reference

NorFab shell supports these command options for the NetBox `create_bgp_peering` task:

```bash
nf# man tree netbox.create.bgp-peering
root
└── netbox:    Netbox service
    └── create:    Create Netbox objects
        └── bgp-peering:    Create BGP peering session(s)
            ├── timeout:    Job timeout
            ├── workers:    Filter worker to target, default 'any'
            ├── verbose-result:    Control output details, default 'False'
            ├── progress:    Display progress events, default 'True'
            ├── instance:    Netbox instance name to target
            ├── branch:    Branching plugin branch name to use
            ├── dry-run:    Return names without writing to NetBox
            ├── name:    Session name (single mode)
            ├── device:    Local device name (single mode)
            ├── local-address:    Local IP address string
            ├── remote-address:    Remote IP address string
            ├── local-as:    Local AS number string
            ├── remote-as:    Remote AS number string
            ├── status:    Session status, default 'active'
            ├── description:    Session description
            ├── vrf:    VRF name
            ├── peer-group:    Peer group name
            ├── import-policies:    Import routing policy names
            ├── export-policies:    Export routing policy names
            ├── prefix-list-in:    Inbound prefix list name
            ├── prefix-list-out:    Outbound prefix list name
            ├── local-interface:    Local interface name or bracket-range pattern
            ├── asn-source:    Dot-path or IPAM query dict for ASN resolution
            ├── name-template:    Format string for session names
            ├── create-reverse:    Also create mirror session on remote device, default 'True'
            ├── bulk-create:    JSON list of session dicts for bulk creation
            ├── rir:    RIR name for ASN creation
            ├── vrf-custom-field:    BGP session field for VRF reference, default 'vrf'
            └── message:    Changelog message for NetBox write operations
nf#
```

## Python API Reference

::: norfab.workers.netbox_worker.bgp_peerings_tasks.NetboxBgpPeeringsTasks.create_bgp_peering
