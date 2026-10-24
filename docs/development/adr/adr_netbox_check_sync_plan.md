# ADR - NetBox check_device_sync Task Implementation Plan

## Overview

Implement the `check_device_sync` task in `NetboxDevicesTasks`. The task checks whether
NetBox device data is in sync with live device state by calling each existing sync
sub-task in dry-run mode and aggregating their results into a single per-device
sync report.

No new sync logic is written; all comparison work is delegated to existing tasks.

---

## Approach

Call the following tasks in `dry_run=True` mode for the specified devices:

1. `sync_device_interfaces`
2. `sync_mac_addresses`
3. `sync_device_ip`
4. `sync_bgp_peerings`

Collect each sub-task's result and diff, then merge them into a unified
per-device report.

---

## Task Signature

```python
def check_device_sync(
    self,
    job: Job,
    instance: Union[None, str] = None,
    timeout: int = 60,
    devices: Union[None, list] = None,
    branch: str = None,
    check_interfaces: bool = True,
    check_mac_addresses: bool = True,
    check_ip_addresses: bool = True,
    check_bgp_peerings: bool = True,
    **kwargs: Any,
) -> Result:
```

`**kwargs` are passed as Nornir host filters (same convention as other sync tasks).

---

## Result Format

`Result.result` — per-device sync summary:

```python
{
    "<device>": {
        "interfaces": {
            "in_sync": True | False
        },
        "mac_addresses": {
            "in_sync": True | False
        },
        "ip_addresses": {
            "in_sync": True | False
        },
        "bgp_peerings": {
            "in_sync": True | False
        },
    }
}
```

`Result.diff` — sub-task diff details keyed by sub-task name then device name,
sourced from each sub-task's `Result.diff`.

Top-level `in_sync` per device is `True` only if all checked sub-tasks report no
pending changes.

---

## Input Pydantic Model

Create `CheckDeviceSyncInput` in `devices_tasks.py` (above the class body), following the
pattern of `SyncDeviceInterfacesInput` in `interfaces_tasks.py`:

```python
class CheckDeviceSyncInput(NetboxCommonArgs, use_enum_values=True, populate_by_name=True):
    devices: Union[None, list[StrictStr]] = Field(None, ...)
    timeout: StrictInt = Field(60, ...)
    check_interfaces: StrictBool = Field(True, alias="check-interfaces", ...)
    check_mac_addresses: StrictBool = Field(True, alias="check-mac-addresses", ...)
    check_ip_addresses: StrictBool = Field(True, alias="check-ip-addresses", ...)
    check_bgp_peerings: StrictBool = Field(True, alias="check-bgp-peerings", ...)
```

---

## PICLE Shell

Add `netbox_picle_shell_check_sync.py` following the pattern of
`netbox_picle_shell_sync_device.py`. Wire it into `netbox_picle_shell.py` under a
`CheckSyncCommands` model as a `devices` sub-command:

```
nf[netbox]# check-sync devices ...
```

Shell class `CheckSyncDevicesShell` exposes all `CheckDeviceSyncInput` fields plus the
standard Nornir host filter args. `CheckSyncCommands` is registered on `NetboxShell`
as `check-sync`.

---

## Implementation Steps

1. Add `CheckDeviceSyncInput` pydantic model to `devices_tasks.py`.
2. Implement `check_device_sync` task body — call the four sub-tasks in dry-run, merge
   results into the unified format.
3. Wire `input=CheckDeviceSyncInput` into the `@Task` decorator.
4. Create `netbox_picle_shell_check_sync.py` with `CheckSyncDevicesShell` and
   `CheckSyncCommands`.
5. Import and register `CheckSyncCommands` in `netbox_picle_shell.py` as
   `check-sync`.

---

## Error Handling

- Sub-task errors are appended to `ret.errors`; remaining sub-tasks still run.
- Per-device missing data (device not in NetBox, Nornir unreachable) is surfaced
  via `job.event(..., severity="ERROR")` and skipped.

---

## Testing

Add tests in `tests/test_netbox_service.py` under a `TestCheckSync` class:

1. `test_check_device_sync_all_in_sync` — all sub-tasks return no diffs.
2. `test_check_device_sync_interfaces_out_of_sync` — interfaces have pending changes.
3. `test_check_device_sync_selective_checks` — use `check_interfaces=False` etc.
4. `test_check_device_sync_dry_run_only` — verify no writes occur.

---

## Files to Change

- `norfab/workers/netbox_worker/devices_tasks.py` — add model + implement task
- `norfab/clients/nfcli_shell/netbox/netbox_picle_shell_check_sync.py` — new file
- `norfab/clients/nfcli_shell/netbox/netbox_picle_shell.py` — wire `CheckSyncCommands` as `check-sync`
- `tests/test_netbox_service.py` — add `TestCheckSync`
