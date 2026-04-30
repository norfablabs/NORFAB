# NetBox sync_device_interfaces Refactor Plan

## Overview

Refactor `sync_device_interfaces` to follow the same architecture style as
`sync_bgp_peerings`: collect live and NetBox state, normalize both into a common
schema, use `deepdiff` to compute intent, then apply deterministic create/update/delete
operations.

The refactor keeps the current task entrypoint (`sync_device_interfaces`) but
changes its internal workflow from inline field checks to diff-driven reconciliation.

Primary data source for live state:
- Nornir `ttp` parsing via `get_interfaces`

Primary data source for NetBox state:
- `self.get_interfaces(...)` with additional data required for interface, MAC,
  and IP reconciliation

---

## Coding Guidelines

1. Keep the implementation minimal and linear.
2. Prefer plain module-level helper functions for non-trivial reusable logic.
3. Avoid nested closures and implicit state capture.
4. Use clear, descriptive variable names.
5. Reuse existing worker conventions for `Task`, `Result`, `job.event`, and logging.
6. Keep event message casing consistent with repository rules.
7. Preserve existing public API behavior where possible; add options only when
   required for safe delete behavior.

---

## Design Goals

1. Normalize live and NetBox data into the same per-interface schema.
2. Use `deepdiff` as the single source of truth for change detection.
3. Generate an explicit action plan for:
   - interfaces: create, update, delete
   - interface MACs: create, update, delete
   - interface IPs: create, update
4. Support dry-run with detailed planned operations and diffs.
5. Preserve branch support and cache behavior.
6. Keep the task idempotent and safe by default.

---

## Normalized Interface Schema

Both live and NetBox states are normalized to this structure per interface:

- `name`: interface name string (e.g. Ethernet1, Ethernet1.10)
- `type`: `other` by default; `bridge` if "vlan" in name; `lag` if
  "port-channel" in name; `virtual` if "loopback" in name or if name contains `.`
- `enabled`: boolean
- `parent`: parent interface name or `null`
- `lag`: lag identifier integer or `null`
- `lag_type`: `lag`, `mlag`, or `null`
- `lacp_mode`: string or `null`
- `mtu`: integer or `null`
- `mac_address`: list of `MAC` strings
- `speed`: integer or `null`
- `duplex`: string or `null`
- `description`: string (`""` when not set)
- `mode`: `tagged` / `access` or `null`
- `untagged_vlan`: integer or `null`
- `tagged_vlans`: list of integers
- `qinq_svlan`: integer or `null`
- `vrf`: string or `null`
- `ipv4_addresses`: list of `IP/prefix` strings
- `ipv6_addresses`: list of `IP/prefix` strings

Normalization must enforce deterministic defaults (`null`, `""`, `[]`) and
stable ordering for list fields (`tagged_vlans`, `ipv4_addresses`, `ipv6_addresses`).

Example normalized object:

```yaml
- description: Router ID
  duplex: null
  enabled: true
  ipv4_addresses: []
  ipv6_addresses: []
  lacp_mode: null
  lag: null
  lag_type: null
  mac_address: null
  mode: null
  mtu: null
  name: Loopback0
  parent: null
  qinq_svlan: null
  speed: null
  tagged_vlans: []
  type: virtual
  untagged_vlan: null
  vrf: null
```

---

## Proposed Refactor Flow for sync_device_interfaces

1. Resolve target devices.
2. Collect live interface data from Nornir TTP parser (`get_interfaces`).
3. Collect NetBox state via `self.get_interfaces(...)`, including data needed
   to derive MAC and IP state.
4. Live data already normalized to canonical schema.
5. Normalize NetBox data to the same canonical schema.
6. Build per-device dictionaries keyed by interface name.
7. Run `deepdiff` on normalized dictionaries and translate diffs to
   concrete create/delete/update payloads.
9. Build action plans for interfaces, MACs, and IPs.
10. Execute in deterministic order (or return plan for dry-run).
11. Record per-device create, update, delete in `Result`, record errors in `Result.errors` list attribute.

---

## Action Planning Model

For each device, create an internal plan structure:

```python
{
  "interfaces": {
    "create": [...],
    "update": [...],
    "delete": [...]
  },
  "mac_addresses": {
    "create": [...],
    "update": [...],
    "delete": [...]
  },
  "ip_addresses": {
    "create": [...],
    "update": [...],
    "delete": [...]
  }
}
```

Notes:
- MAC and IP reconciliation is interface-scoped but executed through NetBox IPAM/DCIM
  endpoints.
- For list-like values, compare as sets semantically but emit deterministic,
  ordered payloads.
- Avoid write operations when the computed payload is empty.

---

## Interface Create/Update/Delete Rules

Create:
- Interface exists in live normalized state but not in NetBox normalized state.
- Create payload includes canonical fields accepted by NetBox.

Update:
- Interface exists on both sides and `deepdiff` reports meaningful field changes.
- Translate changed normalized keys to NetBox interface update payload keys.

Delete:
- Interface exists in NetBox normalized state but not in live normalized state.
- Controlled by explicit delete flag (safe default is no delete).

---

## MAC Address Reconciliation Rules

Create:
- Live has MAC and NetBox has none for target interface.

Update:
- Direct update for assigned MAC object, update in place.

Delete:
- NetBox has MAC linked to interface but live has no MAC (when delete enabled)

Canonicalization:
- Normalize MAC to lowercase EUI string before comparison.

---

## IP Address Reconciliation Rules

Create:
- IP in live list not present in NetBox.

Delete:
- IP in NetBox list not present in live list (when delete enabled).

Update:
- Direct update for assigned IP object.

Canonicalization:
- Store and compare as normalized CIDR list of strings.
- Split IPv4 and IPv6 lists in normalized schema, but reconcile against combined
  NetBox assignment map for writes.

---

## DeepDiff Strategy

Use `deepdiff.DeepDiff` on normalized dictionaries with:
- `ignore_order=True` for list fields
- deterministic pre-sorting to reduce noisy diffs

Diff output is used for:
1. deciding if interface is in sync
2. building update payloads
3. dry-run reporting
4. audit detail in `Result.diff`

---

## Execution Order

Recommended order to minimize dependency failures:

1. Interface create
2. Interface update
3. MAC reconcile (create/update/delete)
4. IP reconcile (create/update/delete)
5. Interface delete

Rationale:
- MAC/IP objects depend on interface existence.
- Deleting interfaces should be last to avoid orphan resolution issues.

---

## Task Interface Changes

Keep existing signature where possible and add explicit safety toggles:

- `delete`: bool = False

---

## Dry-Run Behavior

Dry-run returns planned actions only, with no NetBox writes:

```python
{
  "device1": {
    "interfaces": {
      "create": ["Ethernet10"],
      "update": ["diff"],
      "delete": []
    },
    "mac_addresses": {
      "create": ["Ethernet1"],
      "update": ["diff"],
      "delete": []
    },
    "ip_addresses": {
      "create": ["Ethernet1:10.0.0.1/31"],
      "update": ["diff"],
      "delete": []
    },
    "in_sync": ["Loopback0"],
  }
}
```

---

## Error Handling

- Per-device and per-interface failures append to `ret.errors` and continue.
- Use `job.event(..., severity="ERROR")` for data-resolution failures.
- Preserve partial progress; do not fail entire sync for one bad object.

---

## Caching and Branching

Caching:
- Keep current `self.get_interfaces(..., cache=...)` behavior.
- For authoritative sync passes, use fresh NetBox reads (`cache="refresh"`).

Branching:
- Keep `branch` argument and pass it to all pynetbox calls.
- Include branch information in result metadata when branch is used.

---

## Testing Plan (tests/test_netbox_service.py)

Add or expand `TestSyncDeviceInterfaces` coverage:

1. `test_sync_device_interfaces_create_only`
2. `test_sync_device_interfaces_update_only`
3. `test_sync_device_interfaces_delete_disabled`
4. `test_sync_device_interfaces_delete_enabled`
5. `test_sync_device_interfaces_mac_create_update_delete`
6. `test_sync_device_interfaces_ip_create_delete`
7. `test_sync_device_interfaces_parent_subinterface_logic`
8. `test_sync_device_interfaces_lag_and_lag_type_logic`
9. `test_sync_device_interfaces_type_inference`
10. `test_sync_device_interfaces_dry_run`
11. `test_sync_device_interfaces_branch`
12. `test_sync_device_interfaces_idempotent_second_run`
13. `test_sync_device_interfaces_partial_device_failure`

Each test should:
- prepare explicit NetBox and live fixtures
- print result for diagnostics
- assert action plan and final NetBox state
- clean up side effects

---

## Documentation Updates

1. Update task docs for `sync_device_interfaces` to document:
   - normalization schema
   - diff-based behavior
   - create/update/delete semantics
   - dry-run output format
2. Add examples for:
   - create+update only run
   - delete-enabled run
   - branch run
   - dry-run with diff output

---

## File Change Summary (Planned)

- `norfab/workers/netbox_worker/interfaces_tasks.py`
  - refactor `sync_device_interfaces` to normalization + deepdiff + action plan
- `tests/test_netbox_service.py`
  - add/extend sync interface reconciliation tests
- `docs/workers/netbox/...sync_device_interfaces...md`
  - update behavior and examples
- `docs/development/adr_netbox_sync_device_interfaces_plan.md`
  - this ADR plan

---

## Resolved Decisions

1. Keep `sync_device_interfaces` as the primary task entrypoint.
2. Use Nornir TTP parse `get_interfaces` as live source of truth.
3. Use `self.get_interfaces` as NetBox source of truth.
4. Normalize both sides to the same schema before comparison.
5. Use `deepdiff` for all update/in-sync decisions.
6. Include interface, MAC, and IP reconciliation in one unified sync.
7. Keep deletion disabled by default for safety.
8. Dry-run reports planned actions and diffs without resolving writes.
9. Should interface deletions be split into a separate explicit task for stronger
   operational safety, while sync defaults to create/update only? - no
10. Should MAC replacement be always delete+create, or try update-in-place where
   API supports it? - update in place API supports it fo sure
11. Should IP reconciliation manage only primary assignments or all secondary
   addresses as well? - all IP addresses
12. Should protected interface patterns (for example `mgmt`, `lo`, `vlan`) be
   hardcoded defaults or inventory-configurable? - no harcoded protected patterns
