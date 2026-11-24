# VRF sync: per-device comparison handover

Status: proposed implementation handover, 23 November 2026. This document does not indicate implementation or acceptance of unresolved choices.

Make `sync_vrfs` report independent device drift while preserving shared VRF writes. Start in `norfab/workers/netbox_worker/vrf_tasks.py`; related tests are `tests/services/netbox/test_vrfs.py` and `test_sync.py`.

## Current issue

The task merges observations by VRF name, unions route targets and policies, selects a description, and calculates one shared VRF diff. It then filters that diff by each device's VRF names. If A matches NetBox and B adds an import target to the same VRF, both receive the shared update. Conflicting descriptions can also hide the losing device's drift.

## Comparison structure

Use the same nested layout for live and NetBox data. This is an internal shape, not a new public output format:

```python
{
    "leaf-1": {
        "vrfs": {
            "BLUE": {
                "exists": True,
                "associated": True,
                "description": "users",
                "import_targets": ["65000:10"],
                "export_targets": ["65000:10"],
                # Configured routing-policy fields use normalized name lists.
            }
        },
        "interfaces": {"Ethernet1": {"vrf": "BLUE"}},
        "route_targets": {"65000:10": {"exists": True}},
        "routing_policies": {"IMPORT_BLUE": {"exists": True}},
    }
}
```

The VRF identity is device plus VRF name; interface identity is device plus mapped interface name. Keep the existing lowest-ID duplicate-name selection and warning. Reuse existing policy-field arguments rather than adding fixed policy fields.

## Ownership and collection

1. Gather live observations per device before merging anything. Live VRF observations establish association; live interface lists establish interface-to-VRF usage.
2. Bulk-load selected devices, their interfaces with assigned VRFs, and relevant VRFs with the configured `devices` custom field. Build device ownership from the union of explicit custom-field membership and interface VRF assignments.
3. Fetch all live-referenced VRFs as well, including existing but unassociated objects. Their existence must be distinguished from missing device association. Query custom-field-owned VRFs and interface-owned VRFs needed to recognize NetBox-only associations within the existing task's filtering scope.
4. For each relevant device/VRF pair, record physical existence, association, and normalized attributes separately. A catalog record without ownership is `exists=True`, `associated=False`; it must not look like a missing physical VRF. A missing physical record is `exists=False`, `associated=False`.
5. If the configured devices field is absent or disabled, use interface evidence. A VRF without interfaces then has no recoverable device ownership in NetBox: explicitly document the limitation and choose/report an unverified association rather than claiming that ownership was confirmed. Do not create a custom field implicitly.

Interface evidence proves VRF usage, but does not prove that an enabled devices custom field is complete. If maintaining that field is required, compare its membership for this device separately so an interface assignment does not hide a missing custom-field update.

## Reconciliation flow

1. Apply description policy separately to each device's observation against the selected current VRF.
2. Apply additive target/policy preservation separately per device: preserve existing NetBox values and add only that device's reported values. Do not introduce B's desired additions into A's comparable state.
3. Compare all devices together. Build dependency entries only for the targets/policies that the device itself requires, plus preservation required by current policy.
4. Format each device's public VRF, dependency, and interface diff from its own paths.
5. Build shared write payloads afterward using existing description precedence, target/policy unions, and devices-field merging. Deduplicate by selected physical object. Create dependencies, VRFs, and interface assignments in the existing order and batches.
6. Attribute completed actions only after their writes succeed. Preserve drift for devices whose requested shared value loses source selection.

## Required scenarios

- A matches BLUE; B adds a target or policy: A true, B false.
- A's description matches; B differs: neither source selection nor device ordering hides B's diff. Respect preservation options.
- Devices field contains A only while both use BLUE: only B needs that association; verify interface evidence does not mask required field maintenance.
- BLUE exists with no ownership, exists through interfaces only, exists through custom field only, and is entirely missing. Verify no duplicate VRF creation.
- A interface is correctly assigned; B interface is wrong or missing. Include interface mapping.
- Missing route target/policy affects only devices requiring it. Additive unrelated values survive.
- No-data B does not make A false or B true. Shared writes remain batched once.

## VRRP follow-up boundary

No fifth VRRP document was requested. When reviewing VRRP, derive devices from NetBox FHRP interface assignments, then traverse to their group and VIP; mirror live device/interface/group identity. Do not infer ownership from group name alone. Current `fhrp_tasks.py` already compares assignments per device and attaches shared group/VIP drift. Verify actual shared dependencies rather than assuming every shared change is misattribution. Address batch-wide failure propagation separately; unrelated healthy devices must retain their status.

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
