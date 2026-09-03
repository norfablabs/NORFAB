# NetBox Sync BGP ASNs

> task API name: `sync_bgp_asn`

The `sync_bgp_asn` task collects globally unique BGP ASNs from live devices
using the Nornir TTP `bgp_asn` getter and reconciles them with NetBox IPAM.
It updates descriptions only when requested and optionally records the devices
on which each local ASN was observed. It never deletes ASNs or device associations.

## Inputs

| Parameter | Required | Default | Description |
| --- | --- | --- | --- |
| `devices` | Conditional | `None` | NetBox and Nornir device names; a device or Nornir filter is required |
| `rir` | For creation | `None` | Existing NetBox RIR name used to create missing ASNs |
| `device_custom_field` | No | `devices` | Multi-object ASN custom field related to `dcim.device` |
| `ignore_asn_by_range` | No | `None` | ASN values or numerical ranges to exclude, such as `65000` or `65100-65200` |
| `preserve_description` | No | `True` | Keep existing NetBox ASN descriptions unchanged |
| `instance` | No | Worker default | NetBox instance to target |
| `branch` | No | `None` | NetBox Branching plugin branch |
| `dry_run` | No | `False` | Return the calculated diff without writing |
| `with_approval` | No | `False` | Request approval before writing |
| `timeout` | No | `600` | Host-resolution and parsing timeout in seconds |
| Nornir filters | Conditional | — | Select devices using `FB`, `FC`, `FG`, `FL`, and other FFun filters |

Existing ASNs can be updated without `rir`. If missing ASNs are discovered and
`rir` is omitted or does not exist, the task reports the issue, skips their
creation, and continues updating existing ASNs.

The device custom field must be assigned to `ipam.asn`, use the multi-object
type, and relate to `dcim.device`. A missing field is ignored.

By default, existing NetBox ASN descriptions are preserved. Set
`preserve_description=False` to replace them with parsed live descriptions.
Newly created ASNs still receive the parsed live description when available.

## Output

Results are grouped under `global` and contain `created`, `updated`, `deleted`,
and `in_sync` ASN lists. Dry-run output uses `create`, `update`, `delete`, and
`in_sync`. The `delete` list is always empty.

## Examples

=== "CLI"

    ```bash
    nf# netbox sync bgp-asn devices edge-1 edge-2 rir Private
    ```

    Ignore individual ASNs and ranges:

    ```bash
    nf# netbox sync bgp-asn devices edge-1 rir Private ignore-asn-by-range 65000 65100-65200
    ```

    Preview updates without supplying an RIR:

    ```bash
    nf# netbox sync bgp-asn devices edge-1 dry-run
    ```

    Override existing descriptions with parsed live values:

    ```bash
    nf# netbox sync bgp-asn devices edge-1 preserve-description false
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="./inventory.yaml") as nf:
        result = nf.make_client().run_job(
            "netbox",
            "sync_bgp_asn",
            workers="any",
            kwargs={
                "devices": ["edge-1", "edge-2"],
                "rir": "Private",
            },
        )
        print(result)
    ```

## Notes and Gotchas

- When several devices report the same ASN, the first non-empty description in
  device-name order is used.
- Device custom-field associations are added only for parser records where
  `local_asn` is `True`.
- Existing ASN descriptions are preserved unless `preserve_description` is
  disabled.
- Existing device associations are preserved and newly observed devices are
  appended.
- `with_approval` cannot be combined with the NFCLI `nowait` option.

## Python API Reference

::: norfab.workers.netbox_worker.bgp_asn_tasks.NetboxBgpAsnTasks.sync_bgp_asn
