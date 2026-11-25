# NetBox Sync BGP ASNs

> task API name: `sync_bgp_asn`

The `sync_bgp_asn` task collects globally unique BGP ASNs from live devices
using the Nornir TTP `bgp_asn` getter and reconciles them with NetBox IPAM.
It updates descriptions only when requested and optionally records the devices
on which each local ASN was observed. It never deletes ASNs or device associations.

Existing local ASNs can be updated without `rir`. Creating missing ASNs
requires an existing RIR. If you supply an invalid RIR, the task stops before
collecting data.

The device custom field must be assigned to `ipam.asn`, use the multi-object
type, and relate to `dcim.device`. The task accepts either field membership or
an ASN reference on a NetBox BGP session for that device as association evidence.
The task only writes field memberships for local ASNs. If a device has
neither a configured field nor session evidence, the task only compares ASN
existence and can create missing ASNs.

By default, existing NetBox ASN descriptions are preserved. Set
`preserve_description=False` to apply the selected peer-group label to the
shared ASN when it is observed locally and association evidence is available.
New ASNs receive a parsed label when available.

## Output

Results are keyed by reporting device and contain `created`, `updated`, `deleted`,
and `in_sync` ASN lists. Dry-run output uses `create`, `update`, `delete`, and
`in_sync`. The `delete` list is always empty.
Observed ASNs appear under each reporting device. Shared ASNs are written once.
Association updates show a boolean change for that device. The diff uses
`device_associated` when only sessions provide association evidence.

```json
{
  "edge-1": {
    "created": [65001],
    "updated": [],
    "deleted": [],
    "in_sync": [65002]
  }
}
```


## Bulk Request Batching

List-based NetBox writes are sent as sequential requests containing at most
`batch_size` objects. The default is 1000; set any integer greater than zero to
tune the request size. Each batch emits matching progress event and log messages. If
a request fails, the task stops and returns the results recorded for earlier
successful batches.

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

    Apply the selected peer-group label to existing ASN descriptions:

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

- When several devices report the same ASN, the first non-empty peer-group
  label in device-name order is used.
- Existing device associations are preserved and newly observed devices are
  appended.
- `with_approval` cannot be combined with the NFCLI `nowait` option.

## Python API Reference

::: norfab.workers.netbox_worker.bgp_asn_tasks.NetboxBgpAsnTasks.sync_bgp_asn
