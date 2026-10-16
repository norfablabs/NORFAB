---
tags:
  - netbox
---

# Netbox Move IP Task

> task api name: `move_ip`

Moves every IPv4 and IPv6 address assigned directly to a source device interface
to a destination device interface. Existing destination addresses stay assigned.
The task preserves IP record IDs, address masks, VRFs, roles, and metadata.
It does not change device configuration or move addresses assigned to FHRP groups.

## Output

The result contains source and destination names, `ip_addresses` (a list of
`id` and `address` dictionaries), `source_primary_updates`, and
`destination_primary_updates`. Primary updates map `primary_ip4` or `primary_ip6`
to an IP record ID or `null` for clearing. An empty dictionary means no change.
Status is `updated` for a move, including a planned dry-run move, or `unchanged`
for an empty source or identical source/destination interfaces.

## Examples

=== "CLI"

    ```bash
    nf# netbox move ip from-device router-1 from-interface Ethernet1 device router-2 interface Ethernet2 dry-run
    nf# netbox move ip from-device router-1 from-interface Ethernet1 device router-2 interface Ethernet2 is-primary
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="./inventory.yaml") as nf:
        client = nf.make_client()
        result = client.run_job(
            "netbox", "move_ip", workers="any",
            kwargs={
                "from_device": "router-1", "from_interface": "Ethernet1",
                "device": "router-2", "interface": "Ethernet2",
                "is_primary": True, "dry_run": True,
            },
        )
    ```

## Primary IP behavior

Primary IPs are references on devices. The task clears source `primary_ip4` and
`primary_ip6` references that point to moved IPs, including same-device moves.
By default, `is_primary=False`: the task does not set destination primaries.
For a same-device move this clears the affected primaries.

With `is_primary=True`, moved addresses become destination primaries, replacing
any existing primary for each moved address family. Families with no moved
addresses retain their destination primary. One address in a family selects
that address. With multiple addresses, the moved source primary is selected;
if none is the source primary, the task fails before writing.

## Notes / Gotchas

- Empty sources and identical interfaces return unchanged without modifying primaries.
- Repeating a successful move normally finds an empty source.
- Dry runs resolve objects and report proposed changes without writes.
- Writes clear source primaries, bulk-update assignments, then set destination
  primaries. A later request failure leaves earlier successful writes applied.
- Branch operations require the Netbox branching plugin.
- Design moves execute before explicit IP writes and allocations. Avoid chained
  moves within one design: dry runs do not simulate preceding moves.
- Concurrent changes to the same interfaces are not locked by this task.

## Troubleshooting

Missing or non-unique device/interface lookups fail. Check exact device and port
names. For ambiguous primary selection, arrange a source primary before the move
or use `is_primary=False`. Netbox validation and permission errors propagate;
inspect current assignments and primary references before retrying failed writes.

## Task Command Shell Reference

```bash
nf# man tree netbox move ip
```

## Python API Reference

::: norfab.workers.netbox_worker.ip_tasks.NetboxIpTasks.move_ip
