# Device prefix sync: per-device comparison handover

Status: proposed implementation handover, 23 November 2026. Not implemented by this document.

Make `sync_device_prefixes` preserve device identity while comparing prefix existence, VRF, and site. Start in `norfab/workers/netbox_worker/ip_tasks.py`. Reuse the approach in `sync_device_ip` and `collect_live_interface_ip_data` where suitable. Related tests are `tests/services/netbox/test_ipam.py` and `test_sync.py`.

## Current issue

The task deduplicates live prefixes by prefix and VRF before comparing. It retains the first device's site and distributes that site's classification to every contributor. For the same prefix on A/site1 and B/site2, NetBox/site1 makes both appear in sync; selecting B first instead can make both appear out of sync. Sorting devices makes selection deterministic but does not make the comparison device-specific.

## Comparison structure

Use device-keyed prefix state and supporting interface observations:

```python
{
    "leaf-1": {
        "prefixes": {
            ("192.0.2.0/24", "BLUE"): {
                "exists": True,
                "site": 1,
                "used_by_device": True,
            }
        },
        # Supporting evidence, not interface updates owned by prefix sync.
        "interfaces": {
            "Ethernet1": {
                "vrf": "BLUE",
                "prefixes": ["192.0.2.0/24"],
            }
        },
    }
}
```

Identity is device plus canonical prefix plus effective VRF. If `ignore_vrf=True`, collapse the VRF component consistently on both sides. If `ignore_site=True`, omit site from comparison on both sides. Keep API object IDs outside comparable values. Interface names support ownership; multiple interfaces in the same subnet should still yield one prefix action per device.

## Ownership and collection

1. Build live interface/address state per device using the existing collector. Derive networks using `ip_interface(address).network`, preserving ignore ranges, prefix filters, interface filters, and VRF rules.
2. Bulk-load NetBox interfaces for selected devices and IP addresses assigned to those interfaces. Traverse address assignment to interface to device; do not infer device ownership from prefix site alone.
3. Normalize NetBox interface/address state with the same conventions used by IP sync, including address/VRF handling. Inspect the actual current IP sync implementation instead of copying its full reconciliation machinery.
4. Derive device prefix usage from assigned address networks. Explicitly distinguish the address's subnet from a containing IPAM prefix. Preserve exact-prefix matching currently used by prefix sync; do not replace it with longest-prefix matching.
5. Bulk-load physical IPAM prefix records for the derived networks and all live prefix identities. A physical prefix can exist without any assigned IP on the device; reuse that record, with usage evidence kept separate from existence.
6. Preserve the current lowest-ID selection for duplicate exact prefix/VRF records. Define effective VRF consistently using existing task semantics; do not silently substitute interface VRF for address VRF without checking existing behavior.

## Reconciliation flow

1. Keep each device's desired site and prefix set through comparison. Never use another device's selected site as this device's desired site.
2. Compare the two device-keyed structures globally. Compare prefix attributes independently from interface usage evidence so an existing physical record does not look missing merely because interface IP sync has not run yet.
3. Prefix sync owns IPAM prefix writes. Missing interface/address usage is relationship drift for IP/interface sync, not permission for prefix sync to create or modify interface addresses. If exposed, report that evidence separately without falsely claiming completion in prefix actions.
4. Build one physical write per prefix/VRF using the existing winner policy. If devices disagree on site, retain each device's own drift even if only one site can be written. Do not introduce conflict rejection or change the winner policy in this work.
5. A repeat run may retain site drift for a losing device because one physical prefix cannot represent multiple sites. Document that limitation; do not hide it by copying the winning site's state.
6. Preserve scope payload format, optional VRF behavior, ignores, approval, batching, and no-deletion behavior. Account for current `sync_all` ordering: prefixes can run before interface/IP sync, so association evidence may lag on the first run.

## Required scenarios

- Same subnet/VRF on A/site1 and B/site2, NetBox/site1: A true, B false, in both device orders. Repeat with NetBox/site2.
- `ignore_site=True` removes site drift; `ignore_vrf=True` preserves existing matching behavior.
- Same subnet in different VRFs remains distinct. Global/default VRF normalization remains consistent.
- Multiple interfaces share a subnet: one device prefix result and deduplicated physical write.
- Existing prefix without interface IP assignment is reused; missing physical prefix is created once. Missing IP/interface evidence does not trigger address writes here.
- Unrelated containing prefix must not satisfy an exact subnet requirement. Duplicate exact records retain lowest-ID selection.
- IPv4/IPv6, filters, ignored ranges, missing live collection, preserved unrelated records, and partial batch failures.

## Implementation rules

- Keep public arguments and current result/diff action keys unless a necessary factual change is documented. Preserve preservation policies, additive updates, filtering, approval, branches, and error reporting.
- Build matching `live[device][section][identity]` and `netbox[device][section][identity]` structures before comparison. Device identity must participate in DeepDiff paths; filtering a global diff by contributors afterward is insufficient.
- Use one batch-wide comparison for each distinct structure, through `make_diff` where suitable. Keep API IDs and write metadata outside comparable values. Normalize types, ordering, empty values, and identities equally on both sides.
- Keep a separate, small deduplicated write plan for shared NetBox records. Preserve existing source selection and conflict policies. A device diff describes its own desired state; a shared write describes the selected physical update. Do not copy a shared write's diff to every contributor.
- Retain observed drift when a write is skipped. Compare selected payload values with NetBox before scheduling updates. Preserve useful progress events and batch writes across all selected devices.
- A successful empty collection differs from a missing or failed collection. Track collection coverage; never turn absent data into an empty successful diff. Mark affected devices through `resources_failed` and avoid failing healthy devices for a local validation error.
- Keep changes simple and linear. Avoid new generic reconciliation frameworks or helpers used only once. Do not rewrite unrelated tasks.

## Coordinator and validation

Review `devices_tasks.py` methods `check_device_sync` and `sync_all`, the relevant result models, and task docs. Check-sync must read each device's own diff. Missing device data must not become `True` through `.get(device, {})`; a failure with no device attribution currently forces every device false. Preserve the existing ASN-before-peerings order.

Extend related tests where practical. Prefer public-client integration tests for ownership queries; retain focused fixture tests for edge cases. Update `tests/netbox_data_manifest.json` for actual NetBox records used, with isolated ownership and cleanup. Read the developing/testing guide before running commands; use its current working-directory and suite guidance. Do not weaken existing assertions to accommodate merged device state.

Verify mixed batches in both device orders, repeat runs, dry-run versus applied results, preserved fields, skipped writes, and partial batch failures. Confirm payloads remain deduplicated and globally batched. Update only factual task documentation and the draft changelog when implementing.
