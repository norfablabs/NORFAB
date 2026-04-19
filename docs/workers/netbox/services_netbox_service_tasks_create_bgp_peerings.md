# create_bgp_peerings

## Overview

`create_bgp_peerings` synchronises BGP sessions between live network devices and NetBox.

The task:

1. Collects BGP session data from devices via the Nornir `parse_ttp` task with `get="bgp_neighbors"`.
2. Fetches existing BGP sessions from NetBox for the same devices.
3. Normalises both datasets to a flat comparable format and runs `deepdiff.DeepDiff` to classify sessions as `missing_in_netbox`, `missing_on_device`, `needs_update`, or `in_sync`.
4. Uses the diff output to drive selective NetBox API calls: create, update, or (optionally) delete sessions.
5. Returns a per-device result with lists of `created`, `updated`, `deleted`, and `skipped` session names.

The same gather-and-compare phase is used for both `dry_run=True` (returns diff only, no writes) and normal runs.

---

## Prerequisites

- **NetBox BGP plugin** (`netbox-bgp`) must be installed and enabled in the target NetBox instance.
- **Nornir service** must be running with a TTP getter that handles `get="bgp_neighbors"` and returns session data in the expected format.

## Behaviour and Idempotency

Sessions are matched by name. The naming convention is `{device_name}_{parsed_session_name}`.

On each run:

- Sessions present on the device but absent in NetBox → **created**.
- Sessions present in both but with differing fields → **updated** (only changed fields sent to NetBox).
- Sessions identical in both → **skipped** (in `in_sync` during dry run).
- Sessions present in NetBox but absent on the device → **ignored** unless `process_deletions=True`.

Running the task twice against the same unchanged device state produces an empty `created` / `updated` list on the second run, confirming idempotency.

---

## Dry Run Mode

When `dry_run=True`:

- No writes are made to NetBox.
- Returns a diff report per device:

```python
{
    "<device>": {
        "missing_in_netbox": ["<session_name>", ...],   # would be created on a normal run
        "missing_on_device": ["<session_name>", ...],   # would be deleted with process_deletions=True
        "needs_update": {
            "<session_name>": <deepdiff_delta_dict>,    # field-level diff
        },
        "in_sync": ["<session_name>", ...],             # identical, no action needed
    }
}
```

---

## Deletion Behaviour

By default (`process_deletions=False`) sessions found in NetBox but not on the device are silently ignored — the `deleted` list is always empty.

Set `process_deletions=True` to enable deletion. Only sessions belonging to the explicitly targeted devices are considered; sessions for devices outside the current call scope are never touched.

!!! warning
    Enable `process_deletions` with care. Any session present in NetBox but not returned by the TTP getter (e.g. due to a parser gap or device unreachability) will be deleted.

---

## Session Naming Convention

Session names in NetBox are constructed as:

```
{device_name}_{parsed_session_name}
```

For example, if `parse_ttp` returns `{"name": "to-spine-1"}` for device `ceos-leaf-1`, the NetBox session name will be `ceos-leaf-1_to-spine-1`.

---

## Return Value

**Normal run** — keyed by device name:

```python
{
    "<device>": {
        "created": ["<session_name>", ...],
        "updated": ["<session_name>", ...],
        "deleted": ["<session_name>", ...],   # always present; empty unless process_deletions=True
        "skipped": ["<session_name>", ...],
    }
}
```

**Dry run** — keyed by device name (diff report, see [Dry Run Mode](#dry-run-mode)).

---

## Python API Example

```python
from norfab.core.nfapi import NorFab

nf = NorFab(inventory="./inventory.yaml")
nf.start()
client = nf.make_client()

# Normal run — create/update sessions for two spine devices
result = client.run_job(
    service="netbox",
    task="create_bgp_peerings",
    workers="any",
    kwargs={
        "devices": ["ceos-spine-1", "ceos-spine-2"],
        "status": "active",
    },
)

# Dry run — inspect diff without writing anything
dry_result = client.run_job(
    service="netbox",
    task="create_bgp_peerings",
    workers="any",
    kwargs={
        "devices": ["ceos-spine-1"],
        "dry_run": True,
    },
)

nf.destroy()
```

---

## CLI (nfcli) Example

```
# Create BGP peerings for all spine devices
nf# netbox create bgp-peerings devices ceos-spine-1 ceos-spine-2

# Dry run to see what would change
nf# netbox create bgp-peerings devices ceos-spine-1 dry-run

# Enable deletion of stale sessions - present in Netbox but not on device
nf# netbox create bgp-peerings devices ceos-spine-1 process-deletions
```

---

## Notes on IP and ASN Resolution

When creating a new BGP session the task resolves `local_address`, `remote_address`, `local_as`, and `remote_as` from IPAM as follows:

**IP addresses** (`local_address` / `remote_address`):

1. Search for an existing IP object whose address starts with the given value (`address__isw`). Use it if found.
2. If not found, search for a containing prefix (`prefixes.filter(contains=address)`). If a prefix exists, reuse its mask length when creating the new IP.
3. If no containing prefix exists, fall back to `/32` (IPv4) or `/128` (IPv6).
4. If creation fails (e.g. due to a concurrent write), retry the lookup. If the IP still cannot be obtained, the session is added to `skipped`.

**ASNs** (`local_as` / `remote_as`):

1. Search for an existing ASN object (`asns.filter(asn=int(value))`). Use it if found.
2. If not found, create it (`asns.create(asn=int(value))`).
3. On a `RequestError` (e.g. race condition), retry the lookup.

**Peer group, routing policies, prefix lists** are resolved or created by name using the same retry-on-conflict pattern.
