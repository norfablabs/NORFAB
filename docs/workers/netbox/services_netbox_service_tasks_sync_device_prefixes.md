---
tags:
  - netbox
---

# Netbox Sync Device Prefixes Task

> task api name: `sync_device_prefixes`

The task derives IPv4 and IPv6 networks from live device interface addresses
and reconciles those prefixes with NetBox. It is independent from
`sync_device_ip`: it does not require NetBox interfaces and does not create or
update IP address records.

## How It Works

1. Resolve the selected devices and validate that they exist in NetBox.
2. Run Nornir `parse_ttp` with `get="interfaces"` for the selected devices.
3. Apply interface, prefix, and ignore-range filters.
4. Convert each address to its canonical network, for example
   `10.0.0.1/31` to `10.0.0.0/31`.
5. Deduplicate observations, compare them with NetBox, and create missing or
   update out-of-sync prefixes.

NetBox interface presence is never checked. A prefix can therefore be
synchronized before its source interface exists in NetBox.

## Output

The result is global because the same prefix can be reported by several
devices:

```json
{
    "created": ["10.0.0.0/31"],
    "updated": ["10.0.1.0/31"],
    "in_sync": ["2001:db8::1/128"]
}
```

Dry-run returns the same structure without writing to NetBox. With
`with_approval=True`, the prepared result is shown for approval before any
prefixes are written.

## VRF Handling

`ignore_vrf=True` is the default:

- Prefixes are matched by canonical prefix alone.
- Existing VRF associations are preserved.
- New prefixes are created without a VRF.

With `ignore_vrf=False`:

- The live interface VRF is resolved by name; a missing VRF is created.
- Prefixes are matched by canonical prefix and VRF.
- If the same prefix exists in another VRF, that object is preserved and a new
  prefix is created in the live VRF.
- `global` and `default` interface VRFs are treated as the global table.

## Site Handling

`ignore_site=True` is the default:

- Device sites are not written to prefixes.
- Existing prefix scope/site associations are preserved.

With `ignore_site=False`:

- New prefixes are associated with the reporting device's site.
- Existing matching prefixes are updated when their site differs.
- When several devices report the same prefix identity, the site from the
  alphabetically first device name is authoritative.

Prefix identity is the prefix alone when VRFs are ignored, otherwise it is the
prefix and resolved VRF together.

## Filtering

Interface filters are applied to live data before prefix derivation. Prefix
filters are applied to the derived canonical prefixes:

- `filter_by_name` — interface-name glob, such as `Loopback*`.
- `filter_by_description` — interface-description glob.
- `filter_by_prefix` — include prefixes contained within one IPv4 or IPv6 network.
- `ignore_ranges` — exclude derived prefixes fully contained within any supplied
  IPv4 or IPv6 network. A narrower ignored network does not exclude a broader
  live prefix containing it.

The default ignored ranges are:

```text
127.0.0.0/8
224.0.0.0/24
fe80::/10
ff02::/16
::ffff:0:0/96
::1/128
```

Filters combine using intersection.

For example, `ignore_ranges="10.3.15.33/32"` does not exclude the live prefix
`10.3.15.32/30`, while `ignore_ranges="10.3.15.0/24"` does.

## Deletion Behavior

The task never deletes prefixes. A prefix absent from the selected live device
data is left unchanged in NetBox.

## Branching Support

Pass `branch=<name>` to create or update prefixes in a NetBox Branching Plugin
branch. The task creates the branch when it does not already exist.

## Examples

=== "CLI"

    Synchronize prefixes from one device:

    ```
    nf#netbox sync prefixes devices ceos-spine-1
    ```

    Preview prefixes derived from loopbacks:

    ```
    nf#netbox sync prefixes devices ceos-spine-1 filter-by-name "Loopback*" dry-run
    ```

    Associate prefixes with live VRFs and device sites:

    ```
    nf#netbox sync prefixes devices ceos-spine-1 ignore-vrf false ignore-site false
    ```

    Select devices with a Nornir filter:

    ```
    nf#netbox sync prefixes FC spine
    ```

=== "Python"

    ```python
    result = client.run_job(
        "netbox",
        "sync_device_prefixes",
        workers="any",
        kwargs={
            "devices": ["ceos-spine-1", "ceos-spine-2"],
            "dry_run": True,
        },
    )
    ```

    ```python
    result = client.run_job(
        "netbox",
        "sync_device_prefixes",
        workers="any",
        kwargs={
            "devices": ["ceos-spine-1"],
            "ignore_vrf": False,
            "ignore_site": False,
            "filter_by_prefix": "10.0.0.0/8",
        },
    )
    ```

## NORFAB Netbox Sync Device Prefixes Command Shell Reference

```text
nf# man tree netbox.sync.prefixes
root
└── netbox
    └── sync
        └── prefixes
            ├── timeout
            ├── workers
            ├── verbose-result
            ├── progress
            ├── instance
            ├── dry-run
            ├── with-approval
            ├── devices
            ├── ignore-ranges
            ├── ignore-vrf
            ├── ignore-site
            ├── filter-by-name
            ├── filter-by-description
            ├── filter-by-prefix
            ├── branch
            └── Nornir host filters
```

## Python API Reference

::: norfab.workers.netbox_worker.netbox_worker.NetboxWorker.sync_device_prefixes
