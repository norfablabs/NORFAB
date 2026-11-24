# BGP ASN sync: per-device comparison handover

Status: proposed implementation handover, 23 November 2026. Not implemented by this document.

Make `sync_bgp_asn` compare each device's local and remote ASN requirements independently. Start in `norfab/workers/netbox_worker/bgp_asn_tasks.py`; inspect `bgp_peerings_tasks.py` for NetBox session loading. Related tests are `tests/services/netbox/test_bgp_asn.py` and `test_sync.py`.

## Current issue

Observations are merged by ASN, descriptions use a selected source, and the devices custom field unions local contributors with existing memberships. A global diff is copied to every observing device. If ASN 65000 already associates A but not B, both A and B receive B's association update. Remote ASN observers are also included in attribution even though only local observations contribute to the custom field.

## Comparison structure

Use equivalent live and NetBox structures:

```python
{
    "leaf-1": {
        "asns": {
            65000: {
                "exists": True,
                "local": True,
                "remote": False,
                "device_associated": True,
                "description": "campus",
            },
            65100: {
                "exists": True,
                "local": False,
                "remote": True,
                "device_associated": False,
                "description": "upstream",
            },
        }
    }
}
```

Identity is device plus numeric ASN. Local and remote are independent booleans because the same ASN may occur in both roles. Normalize the same way on both sides. Keep object existence separate from role evidence and custom-field membership.

## Ownership and collection

1. Retain live observations per device and their `local_asn` role. Preserve ignored ASN handling and description policy.
2. Bulk-load relevant ASN objects and configured devices custom-field memberships. That field provides local device association, not proof of a remote ASN relationship.
3. Load NetBox BGP sessions for selected devices and resolve their local/remote ASN references. Use the existing peerings loader and plugin conventions; verify actual API field names before implementation. Session ownership supplies device identity for both local and remote ASN roles.
4. Combine custom-field and session evidence to discover relevant device/ASN pairs, without treating one as proof of the other. A session can prove local use while the configured devices custom field still needs updating.
5. Also load the physical catalog for every live ASN. An existing ASN lacking device/session association must be reused, not created again.
6. When the BGP plugin or devices field is unavailable, explicitly retain only the evidence available. Do not label an unobservable role as verified. Document fallback behavior without introducing a mandatory plugin requirement.

## Reconciliation flow

1. Construct comparable per-device observations, apply description preservation independently, then compare the complete device-keyed structures.
2. Missing physical ASN produces a create requirement. Missing enabled local custom-field association produces an ASN update for that device only.
3. A remote ASN missing from a session is relationship drift, not a request to add that device to the ASN's local devices field. Session creation/update remains owned by peerings sync. Keep relationship diff separate enough that ASN result actions never claim a session write.
4. Keep ASN sync before peerings in `sync_all` and check-sync. This means ASN relationship drift can legitimately remain until peerings run; a second overall check should converge.
5. Build one selected description and merged local devices list per physical ASN for writes, keeping current source precedence and RIR requirements. Compare selected values before scheduling a batch update.
6. Format per-device public actions and diffs from their own comparisons. Resolve necessary model/docs changes explicitly if relationship-only drift cannot fit the current shape; do not silently change public keys.

## Required scenarios

- Existing ASN associates A only; A and B use it locally: A true, B false; one deduplicated update.
- A local and B remote use the same ASN: B is not added to the local devices field.
- Same ASN used locally and remotely on one device preserves both role facts.
- A matches description; B differs, with preservation enabled and disabled.
- Session-only ownership, field-only ownership, unassociated existing ASN, missing ASN, and unavailable plugin/field.
- Existing session on A and missing session on B: device-specific relationship drift, no session writes by ASN task.
- Ignored ASNs, absent live data, duplicate observations, RIR errors, approval, and partial batch failures retain current behavior.

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
