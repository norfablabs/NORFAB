# BGP community sync: per-device comparison handover

Status: proposed implementation handover, 23 November 2026. Not implemented by this document.

Make `sync_bgp_community` compare independent device requirements for IPAM route targets and BGP plugin communities. Start in `norfab/workers/netbox_worker/bgp_community_tasks.py`; related tests are `tests/services/netbox/test_bgp_community.py` and `test_sync.py`.

## Current issue

The task correctly tracks contributors but compares merged names and devices-field memberships first. It copies a shared object's resulting action to all contributors. An existing association for A and missing association for B therefore marks both out of sync. Route-target names are merged across devices; standard community matching also depends on value and live community-set name.

## Comparison structure

Use matching internal snapshots:

```python
{
    "leaf-1": {
        "route_targets": {
            "65000:10": {
                "exists": True,
                "device_associated": True,
                "names": ["BLUE_RT"],
            }
        },
        "communities": {
            ("65000:20", "CUSTOMERS"): {
                "exists": True,
                "device_associated": True,
                "names": ["CUSTOMERS"],
            }
        },
    }
}
```

Keep existing community type handling and exact plugin identity rules. The example tuple illustrates value/name identity; reuse the current encoded identity if that avoids a public change. Never collapse standard communities solely by value: different names can identify separate physical records. API IDs remain outside the comparable state.

## Ownership and collection

1. Preserve device-specific live names and values before any union. Keep route-target observations separate from plugin community observations.
2. Bulk-load selected devices and relevant objects with the configured devices and community-name fields. Use devices-field membership to reconstruct NetBox ownership for both families.
3. Query by live identities even when ownership is absent, so existing unassociated objects are reused. Include relevant selected-device-owned objects within existing filtering rules, without adding deletion behavior.
4. Preserve the existing candidate matching precedence: community-name containment, description fallback, then eligible unlabeled record. Resolve the physical object before constructing its comparable representation.
5. When the configured devices field is absent/disabled, physical object existence and names remain observable, but device ownership is not independently verifiable. Do not infer NetBox ownership from the live contributor list. State and test this limitation. Do not invent a session relationship: current community data does not establish direct session ownership.
6. A shared name list cannot identify which device contributed each stored name. Compare additive requirements: each device requires only its own names to be present. Do not claim that NetBox proves a particular name originated on that device.

## Reconciliation flow

1. For a device, compare its own names and association against the matched NetBox object. Preserve existing stored names under the additive policy, but add only that device's missing names to its desired snapshot.
2. Compare all device-keyed data together, separately by family if needed. A missing association is an update to an existing object, not creation of another object.
3. Build per-device public diffs from these paths. A's names and membership already present must remain in sync when B needs a new name or association.
4. Build physical writes afterward: union names and associated devices across desired changes while retaining existing values; deduplicate by matched physical record. Keep current plugin availability behavior, matching, batch size, and no-deletion policy.
5. If several logical keys resolve to one physical record, merge its write once without borrowing another device's diff. Exclude selected values already matching NetBox.

## Required scenarios

- A and B report the same community; only A is associated: A true, B false.
- A route-target name already exists; B contributes a new name: only B reports the missing name.
- Different values on A and B remain independent; same value with different standard community names retains distinct identity.
- Stored names contain extra values: additive preservation does not create false drift.
- Description fallback and unlabeled fallback reuse existing records without duplicate creation.
- Both families, plugin unavailable, field disabled/missing, existing unassociated objects, no-data devices, and partial failure.
- Physical updates remain globally batched and completed actions correspond to successful writes only.

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
