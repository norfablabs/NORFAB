# ADR - NetBox `sync_vlans` Task Plan

## Status

Proposed — ready for implementation review.

Date: 19 August 2026

## Context

The NetBox service can discover VLAN IDs while synchronizing interfaces, but
`sync_device_interfaces` only resolves missing VLAN objects as a side effect. It
creates placeholder names such as `VLAN_410`; it does not reconcile the VLAN name
or description configured on a live device.

NORFAB already has the required live-data parser. The TTP getter
`get="vlans"` returns a normalized list for supported platforms:

```yaml
- vid: 100
  name: USERS
  description: User access VLAN
```

The current getter supports Arista EOS, Cisco IOS, Cisco NX-OS, and Juniper
Junos. The FakeNOS cEOS fixtures under
`tests/nf_tests_inventory/fakenos/custom_nos/` already implement the required
`show running-config section vlan` command and contain distinct VLAN datasets.

VLAN reconciliation cannot be copied literally from interface reconciliation.
An interface belongs to one device, while a NetBox VLAN is shared within a site
or VLAN group. Multiple selected devices can therefore report the same desired
VLAN. They can also report conflicting names or descriptions for the same VID.
The task must aggregate and validate live observations by NetBox scope before it
calculates or applies a diff.

NetBox 4.4 also deprecates direct site assignment for VLANs in favor of scoped
VLAN groups. NORFAB must retain site-scoped behavior for compatibility with the
current `sync_device_interfaces` implementation, while making VLAN groups the
recommended mode for new deployments.

## Decision

Add a standalone NetBox worker task named `sync_vlans` in a dedicated
`vlans_tasks.py` module. It will:

1. resolve devices from an explicit list and/or Nornir host filters;
2. collect live VLAN configuration with Nornir `parse_ttp`, using
   `get="vlans"`;
3. assign every selected device to one reconciliation scope:
   - the explicitly selected VLAN group; or
   - the device site when no group is supplied;
4. merge identical observations from devices in the same scope;
5. reject ambiguous live or NetBox records without choosing a winner;
6. compare normalized live and NetBox state with `self.make_diff`;
7. create and update VLANs in deterministic scope/VID order;
8. delete VLANs only when explicitly enabled and restricted to explicit VLAN ID
   ranges;
9. support dry-run, interactive approval, NetBox branches, NFCLI, FastAPI, and
   MCP in the same style as `sync_device_interfaces`.

The first implementation is standalone. It must not automatically add
`sync_vlans` to `sync_all` or `check_device_sync`; shared-scope deletion and
cross-device conflicts need operational experience before those workflows are
expanded.

## Goals

1. Make live VLAN name and description authoritative within an explicitly
   derived NetBox scope.
2. Preserve the normalized diff and result conventions used by current NetBox
   synchronization tasks.
3. Make repeated runs idempotent.
4. Prevent device ordering from deciding a shared VLAN's final state.
5. Keep deletion disabled by default and bounded when enabled.
6. Isolate failures to one scope or VID where possible.
7. Expose one consistent task contract through the Python API, FastAPI, MCP, and
   NFCLI.

## Non-goals

The first version will not:

- configure VLANs on network devices;
- create, update, or delete VLAN groups;
- infer a different VLAN group for each VID or device;
- manage VLAN status, role, tenant, tags, custom fields, Q-in-Q role, or Q-in-Q
  service VLAN;
- change interface tagged/untagged VLAN assignments;
- replace the VLAN resolution used by `sync_device_interfaces`;
- accept arbitrary custom parsers or transformer code;
- reconcile global, unscoped VLANs;
- join `sync_all` or `check_device_sync` in this change.

## File and Class Layout

Create the task implementation in:

```text
norfab/workers/netbox_worker/vlans_tasks.py
```

The module should contain:

```python
class NetboxVlansTasks:
    @Task(...)
    def sync_vlans(...):
        ...
```

Keep non-trivial reusable logic as plain module-level functions. Suggested
helpers are:

```python
def expand_vlan_id_ranges(vlan_ids: list[str] | None) -> set[int]: ...
def normalize_live_vlan(record: dict) -> dict: ...
def normalize_netbox_vlan(record: object) -> dict: ...
def resolve_vlan_group(nb: object, vlan_group: str | int) -> object | None: ...
```

Do not define Pydantic models in `vlans_tasks.py`. Per the repository model
guide, all task models belong in `netbox_models.py`.

Wire the mixin into `netbox_worker.py`:

```python
from .vlans_tasks import NetboxVlansTasks


class NetboxWorker(
    NFPWorker,
    ...,
    NetboxVlansTasks,
    ...,
):
    ...
```

## Public Task Contract

The public task signature is:

```python
def sync_vlans(
    self,
    job: Job,
    instance: Union[None, str] = None,
    dry_run: bool = False,
    with_approval: bool = False,
    timeout: int = 600,
    devices: Union[None, list] = None,
    process_deletions: bool = False,
    branch: Union[None, str] = None,
    vlan_group: Union[None, str, int] = None,
    vlan_ids: Union[None, list[str]] = None,
    **kwargs: Any,
) -> Result:
    ...
```

Arguments:

- `instance`: NetBox instance; default to `self.default_instance`.
- `dry_run`: calculate and return the plan without NetBox writes.
- `with_approval`: present the complete plan through
  `review_sync_task_result` before writing.
- `timeout`: timeout in seconds for host resolution and Nornir parsing.
- `devices`: explicit NetBox/Nornir device names.
- `process_deletions`: allow deletion of NetBox VLANs absent from live data.
- `branch`: NetBox Branching plugin branch name.
- `vlan_group`: one VLAN group name, slug, or numeric ID. When set, all
  selected devices contribute to that group.
- `vlan_ids`: VLAN IDs or inclusive range strings such as `100`, `200-299`.
  Apply the same expanded set to live and NetBox state.
- `kwargs`: Nornir `FFun` host filters (`FO`, `FB`, `FH`, `FC`, `FR`, `FG`,
  `FP`, `FL`, `FM`, `FX`, and `FN`). The input model must expose these fields
  explicitly even though the implementation receives them through `**kwargs`.

At least one device selector must be supplied: `devices` or a non-empty Nornir
host filter.

### Deletion Contract

`process_deletions=True` is valid only when `vlan_ids` is non-empty. The
explicit VID set is the task's deletion boundary. This prevents a selected
device subset from accidentally treating every VLAN in a site or group as
managed.

The VID boundary does not prove that the selected devices represent every use
of those VLANs. Operators enabling deletion are responsible for selecting the
authoritative device set for the scope and reviewing a dry-run first.

The task must also suppress deletion for an entire scope when any selected
device assigned to that scope:

- failed live collection;
- is missing from the Nornir result; or
- returned a malformed result that could not be validated.

Create and update actions from valid observations may still proceed. The result
must list suppressed candidates under `delete_skipped` and explain why in
`messages` or `errors`.

An empty, successfully parsed list is authoritative only for the requested
`vlan_ids`. A missing host result is not equivalent to an empty list.

## Pydantic Models

Add the following models to the IPAM section of
`norfab/workers/netbox_worker/netbox_models.py`.

### `VlanRecord`

Use this model to validate the normalized TTP contract before aggregation:

```python
class VlanRecord(BaseModel, extra="forbid"):
    vid: StrictInt = Field(..., ge=1, le=4094, description="IEEE 802.1Q VLAN ID")
    name: StrictStr = Field(..., min_length=1, description="VLAN name")
    description: Union[None, StrictStr] = Field(
        None,
        description="VLAN description",
    )
```

The implementation should convert the model to the canonical comparison shape
after validation.

### `SyncVlansInput`

```python
class SyncVlansInput(
    NetboxNornirHostsFilters,
    NetboxCommonArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    dry_run: StrictBool = Field(
        False,
        description="Calculate the VLAN diff without writing to NetBox",
        alias="dry-run",
        json_schema_extra={"presence": True},
    )
    devices: Union[None, List[StrictStr]] = Field(
        None,
        description="List of NetBox device names to collect VLANs from",
    )
    timeout: StrictInt = Field(
        600,
        gt=0,
        description="Timeout in seconds for Nornir host resolution and VLAN parsing",
    )
    with_approval: StrictBool = Field(
        False,
        description="Preview VLAN changes and ask for review before writing to NetBox",
        alias="with-approval",
        json_schema_extra={"presence": True},
    )
    process_deletions: StrictBool = Field(
        False,
        description="Delete in-range NetBox VLANs absent from successfully collected live state",
        alias="process-deletions",
        json_schema_extra={"presence": True},
    )
    vlan_group: Union[None, StrictStr, StrictInt] = Field(
        None,
        description="VLAN group name, slug, or ID used as the reconciliation scope",
        alias="vlan-group",
    )
    vlan_ids: Union[None, List[StrictStr]] = Field(
        None,
        description="VLAN IDs or inclusive ranges to reconcile, for example 100 or 200-299",
        alias="vlan-ids",
        examples=[["100", "200-299"]],
    )
```

Add `model_validator(mode="after")` validation that:

1. requires `devices` or at least one Nornir host filter;
2. requires `vlan_ids` when `process_deletions=True`;
3. rejects brackets, descending ranges, non-numeric values, and values outside
   `1..4094`;
4. accepts overlapping input ranges but normalizes them to one set in the task;
5. does not reject `dry_run=True` with `with_approval=True`; runtime dry-run
   behavior takes precedence and must not prompt.

Use `expand_alphanumeric_range(f"[{value}]")` only after the model has rejected
embedded brackets. Do not duplicate a second, subtly different VLAN-range
grammar.

### `SyncVlansResult`

Dry-run and live-run payloads intentionally use different action verbs, matching
current sync task conventions. Keep the output broad but documented:

```python
class SyncVlansResult(Result):
    result: Dict[StrictStr, Any] = Field(
        {},
        description="VLAN sync actions keyed by NetBox VLAN scope",
    )
```

Do not claim a per-device result: one VLAN action can represent observations
from several devices.

## Task Registration

Register the task with the same API and MCP posture as other mutating,
idempotent sync tasks:

```python
@Task(
    fastapi={"methods": ["POST"], "schema": NetboxFastApiArgs.model_json_schema()},
    input=SyncVlansInput,
    output=SyncVlansResult,
    mcp={
        "annotations": {
            "title": "Sync VLANs",
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": True,
            "openWorldHint": True,
        }
    },
)
```

The task must return a `Result` initialized with:

```python
Result(
    task=f"{self.name}:sync_vlans",
    result={},
    resources=[instance],
    dry_run=dry_run,
    diff={},
)
```

## Scope and Object Identity

### Explicit VLAN group

When `vlan_group` is set:

1. resolve by numeric ID first when the value is an integer or numeric string;
2. otherwise try exact name, then exact slug;
3. fail before live collection if no group is found;
4. use that group for every selected device;
5. fetch and create VLANs with `group_id`/`group` respectively.

The result scope key should be deterministic and human-readable:

```text
group:<id>:<name>
```

### Site compatibility mode

When `vlan_group` is not set:

1. fetch each selected NetBox device's `id`, `name`, and `site`;
2. reject a device that has no usable site;
3. group devices by site ID;
4. fetch and create VLANs with `site_id`/`site` respectively.

The result scope key should be:

```text
site:<id>:<name>
```

Task documentation must label this as compatibility behavior and recommend a
scoped VLAN group because direct site assignment is deprecated in NetBox 4.4.

Within a scope, the reconciliation identity is `vid`. Internally use:

```python
{
    "group:12:CAMPUS": {
        100: {"vid": 100, "name": "USERS", "description": "User access"},
    }
}
```

NetBox permits duplicate VIDs outside a VLAN group. If more than one current
NetBox VLAN has the same VID in a site compatibility scope, record a target
conflict and omit that VID from create, update, and delete processing. Never
select the first record returned by the API.

## Live Data Collection

Use one Nornir job for the complete resolved device set:

```python
parse_data = self.client.run_job(
    "nornir",
    "parse_ttp",
    kwargs={"get": "vlans", "FL": devices},
    workers="all",
    timeout=timeout,
)
```

Do not use NAPALM `get_vlans` in this task. The TTP getter is already normalized,
matches the current interface sync architecture, and is covered by the FakeNOS
fixtures.

Multiple Nornir workers may return data. Track host names already accepted. If
two workers return the same host with different VLAN data, treat the host as
ambiguous and exclude it; do not let worker iteration order choose the source.
Identical duplicate host results may be collapsed.

## Normalization and Aggregation

Normalize both sources to exactly these managed fields:

```python
{
    "vid": 100,
    "name": "USERS",
    "description": "",
}
```

Rules:

- `vid` is an integer in `1..4094`;
- trim leading and trailing whitespace from `name` and `description`;
- reject an empty name after trimming;
- normalize a missing or null description to `""`;
- preserve name and description case;
- do not compare NetBox IDs or display fields;
- apply the expanded `vlan_ids` set to both live and NetBox data before diffing;
- sort scopes lexically and VIDs numerically for payloads, events, and results.

The bundled TTP getter supplies a default name such as `VLAN100` when a
platform configuration has no explicit name. Treat that parser output as the
desired name. Do not replace it with the interface task's `VLAN_100` convention.

### Cross-device aggregation

For each `(scope, vid)`:

- one observation is authoritative;
- multiple identical observations collapse to one desired record;
- observations that differ in `name` or `description` form a source conflict.

A conflict entry must include every contributing device and normalized record:

```json
{
    "100": [
        {"device": "leaf-1", "name": "USERS", "description": "User access"},
        {"device": "leaf-2", "name": "CLIENTS", "description": "User access"}
    ]
}
```

Omit a conflicting VID from both sides before calling `self.make_diff`. This
prevents a conflict from being misclassified as a create, update, or delete.
Continue processing non-conflicting VIDs in the same scope.

## NetBox Data Collection

Use `self.bulk_filter(nb.ipam.vlans, ...)` once per scope and request only the
fields needed for identity, comparison, and writes:

```text
id,vid,name,description,group,site
```

Use `group_id=<id>` for group scopes and `site_id=<id>` for site scopes. Do not
silently include global VLANs or VLANs from another scope.

The task is an authoritative comparison and must not use disk-cached VLAN data.
Use the branch-aware client returned by:

```python
nb = self._get_pynetbox(instance, branch=branch, job=job)
```

## Diff and Result Shapes

Call:

```python
full_diff = self.make_diff(normalized_live, normalized_netbox)
```

### Dry-run result

Dry-run returns the planned diff with scope metadata and conflicts:

```json
{
    "site:1:NORFAB-LAB": {
        "devices": ["ceos-leaf-1", "ceos-leaf-2"],
        "create": [110, 111],
        "update": {
            "210": {
                "name": {
                    "old_value": "VLAN210",
                    "new_value": "TEST_L1_ACCESS"
                }
            }
        },
        "delete": [999],
        "delete_skipped": [],
        "in_sync": [310],
        "conflicts": {}
    }
}
```

`dry_run=True` always performs zero writes and never requests approval, even if
`with_approval=True` was also supplied.

### Live-run result

Live-run returns applied and skipped actions:

```json
{
    "site:1:NORFAB-LAB": {
        "devices": ["ceos-leaf-1", "ceos-leaf-2"],
        "created": [110, 111],
        "updated": [210],
        "deleted": [],
        "delete_skipped": [999],
        "in_sync": [310],
        "conflicts": {}
    }
}
```

Set `ret.diff` to the complete prepared diff for live runs. If approval is
declined, set `ret.status = "skipped"`, return the dry-run shape, set
`ret.dry_run = True`, and append `review declined; changes were not applied`.

## Write Payloads and Execution Order

### Create

Create payload:

```python
{
    "vid": desired["vid"],
    "name": desired["name"],
    "description": desired["description"],
    "group": group_id,  # group scope only
    "site": site_id,    # site compatibility scope only
}
```

Do not set fields the live parser cannot authoritatively supply. NetBox should
apply its default VLAN status.

### Update

Update payload contains the NetBox object `id` and only changed managed fields:

```python
{
    "id": current["id"],
    "name": desired["name"],       # only when changed
    "description": desired["description"],  # only when changed
}
```

Never move an existing VLAN between a site and group or between groups. Scope
selection is an identity boundary, not a mutable field.

### Delete

Delete by NetBox object ID only when all deletion contract checks pass.
Otherwise record the VID under `delete_skipped`.

### Ordering and transaction isolation

Execute in this order:

1. create VLANs;
2. update VLANs;
3. delete VLANs.

Batch writes per scope, not across all scopes. NetBox REST bulk update and bulk
delete operations are all-or-none. Per-scope batching prevents one invalid
scope from blocking unrelated sites or groups. Catch each scope operation,
record the error, and continue with later scopes where safe.

Do not send an empty bulk request.

## Error and Event Handling

Follow repository casing rules:

- `job.event` messages start with lowercase letters;
- `log.*` messages start with uppercase letters.

Expected per-device or per-VID errors include:

- selected device is absent from NetBox;
- selected device has no site in compatibility mode;
- VLAN group cannot be resolved;
- Nornir worker or host collection failure;
- malformed TTP record;
- duplicate host data differs across Nornir workers;
- live devices disagree on name or description for one scoped VID;
- duplicate current NetBox VLANs make a site-scoped VID ambiguous;
- create, update, or delete request fails.

Set `ret.failed = True` when no valid scope can be processed or live collection
fails for every selected device. Partial conflicts should populate
`ret.errors` but should not discard successful actions for unrelated VIDs.

Events should report at least:

- selected and validated device counts;
- resolved scope count;
- parsed live record count;
- source and target conflict counts;
- create/update/delete/in-sync counts;
- deletion suppression reason;
- per-scope write start and completion;
- task completion.

## NFCLI Shell

Create:

```text
norfab/clients/nfcli_shell/netbox/netbox_picle_shell_sync_vlans.py
```

Define:

```python
class SyncVlansShell(
    NetboxClientRunJobArgs,
    SyncVlansInput,
    use_enum_values=True,
    populate_by_name=True,
):
    ...
```

CLI-specific behavior:

- override `devices` to accept `Union[List[StrictStr], StrictStr]`;
- override `vlan_ids` to accept `Union[List[StrictStr], StrictStr]`;
- convert either string to a one-item list in `run`;
- default outer timeout to 600 seconds and pass `int(timeout * 0.9)` to the
  worker task;
- reject `nowait` with `with_approval`;
- call `run_future_job("netbox", "sync_vlans", ...)`;
- return nested output and preserve the existing `verbose_result` behavior;
- optionally expose `source_FL` by delegating to
  `NorniHostsFilters.source_hosts` without redeclaring all filter fields.

Match the other sync shells' output and pipe behavior:

```python
class PicleConfig:
    outputter = Outputters.outputter_nested
    pipe = PipeFunctionsModel
```

Import `SyncVlansShell` in `netbox_picle_shell.py` and add:

```python
class SyncCommands(BaseModel):
    ...
    vlans: SyncVlansShell = Field(
        None,
        description="Sync live VLAN configuration with NetBox",
    )
```

The command path is:

```text
netbox sync vlans
```

Examples:

```bash
nf# netbox sync vlans devices ceos-leaf-1 dry-run
nf# netbox sync vlans devices ceos-leaf-1 vlan-group CAMPUS
nf# netbox sync vlans FC leaf vlan-ids 100 200-299
nf# netbox sync vlans devices ceos-leaf-1 vlan-ids 900-999 process-deletions
```

## Documentation

Create:

```text
docs/workers/netbox/services_netbox_service_tasks_sync_vlans.md
```

Follow `docs/development/documentation_style_guide.md` and include:

1. purpose and the site/group scope distinction;
2. complete inputs and defaults;
3. live parser support and normalized fields;
4. dry-run and live output examples keyed by scope;
5. cross-device deduplication and conflict behavior;
6. deletion requirements and incomplete-collection suppression;
7. VLAN group recommendation and site assignment deprecation;
8. branch behavior;
9. tabbed CLI and Python examples;
10. troubleshooting for missing parser data, conflicts, duplicate site VLANs,
    group resolution, and NetBox bulk failures;
11. `nf# man tree netbox.sync.vlans` command reference;
12. the concrete API directive:

```markdown
::: norfab.workers.netbox_worker.vlans_tasks.NetboxVlansTasks.sync_vlans
```

Add the page to the NetBox task list in `mkdocs.yml` as `Sync VLANs`.

Update `docs/norfab_features.md` with a concise **Live VLAN reconciliation**
entry, link the new task page, and update the page's `Last updated` date.

The task doc must distinguish this task from `sync_device_interfaces`:

- `sync_vlans` manages VLAN object names and descriptions;
- `sync_device_interfaces` manages interface objects and their VLAN
  associations, and may still create placeholder VLANs as a side effect.

Recommended operator order is `sync_vlans` followed by
`sync_device_interfaces`. If `sync_device_interfaces` created placeholders
first, a later `sync_vlans` run should update their names and descriptions.

## Tests

Create a dedicated test module:

```text
tests/services/netbox/test_vlans.py
```

Set:

```python
pytestmark = pytest.mark.netbox
```

Register and use `netbox_sync_vlans` in `pyproject.toml`.

Integration tests should use the existing FakeNOS cEOS VLAN command output.
The current fixtures cover parsed names and null descriptions. Cover synthetic
conflicts, malformed records, non-null descriptions, duplicate worker results,
and API failures with focused helper tests or mocked Nornir/NetBox responses;
do not distort the shared device fixtures solely to manufacture error states.
Use idempotent setup and `try/finally` cleanup for every NetBox mutation. Never
depend on test execution order.

Required coverage:

1. model defaults and aliases;
2. model accepts a device selector or Nornir filter;
3. model rejects no selector;
4. VLAN range expansion accepts single IDs and ascending ranges;
5. VLAN range validation rejects brackets, descending ranges, non-numeric
   values, zero, and values above 4094;
6. `process_deletions=True` requires `vlan_ids`;
7. dry-run reports create actions and performs no writes;
8. live run creates VLANs with parsed names and descriptions;
9. live run updates a placeholder VLAN name and description;
10. a null live description normalizes to an empty string and clears a stale
    NetBox description;
11. a second run reports VLANs in sync;
12. `vlan_ids` applies to both live and NetBox data;
13. deletion is skipped by default;
14. deletion runs only for explicit in-range VIDs;
15. an out-of-range NetBox VLAN is never deleted;
16. deletion is suppressed when one device in the scope fails collection;
17. identical observations from multiple devices are deduplicated;
18. conflicting live names for one scoped VID skip that VID and report every
    contributing device;
19. conflicting live descriptions behave the same way;
20. two sites are reconciled independently;
21. a VLAN group is resolved by name;
22. a VLAN group is resolved by slug;
23. a VLAN group is resolved by ID;
24. an unknown VLAN group fails before writes;
25. duplicate current VIDs in site compatibility mode are reported as
    ambiguous and skipped;
26. a non-existent NetBox device is reported without blocking valid devices;
27. malformed parser data is rejected without producing a write payload;
28. differing duplicate host results from Nornir workers are rejected;
29. branch is passed to `_get_pynetbox` and changes remain branch-scoped;
30. approval decline returns a skipped dry-run result;
31. approval acceptance applies the prepared plan without recollecting live
    data;
32. `dry_run=True` with `with_approval=True` performs no prompt and no writes;
33. create failure in one scope does not block another scope;
34. update failure in one scope does not block another scope;
35. delete failure is reported and does not claim the VLAN was deleted;
36. task decorator uses `SyncVlansInput` and `SyncVlansResult`;
37. NFCLI converts scalar `devices` and `vlan-ids` values to lists;
38. NFCLI submits service `netbox`, task `sync_vlans`;
39. NFCLI rejects `nowait` with `with-approval`;
40. NFCLI command tree exposes `netbox sync vlans`.

Focused commands:

```bash
cd tests
poetry run pytest -s -v services/netbox/test_vlans.py
poetry run pytest -m netbox_sync_vlans
poetry run pytest -m nfcli
```

Static and documentation verification:

```bash
poetry run python -m compileall -q norfab/workers/netbox_worker norfab/clients/nfcli_shell/netbox
poetry run ruff check norfab/workers/netbox_worker/vlans_tasks.py norfab/workers/netbox_worker/netbox_models.py norfab/clients/nfcli_shell/netbox/netbox_picle_shell_sync_vlans.py tests/services/netbox/test_vlans.py
poetry run mkdocs build
```

Do not leave new `__pycache__` artifacts after verification.

## Planned File Changes

Implementation should be limited to:

- `norfab/workers/netbox_worker/vlans_tasks.py` — new task and helpers;
- `norfab/workers/netbox_worker/netbox_models.py` — VLAN record, input, and
  result models;
- `norfab/workers/netbox_worker/netbox_worker.py` — import and mix in
  `NetboxVlansTasks`;
- `norfab/clients/nfcli_shell/netbox/netbox_picle_shell_sync_vlans.py` — new
  NFCLI model;
- `norfab/clients/nfcli_shell/netbox/netbox_picle_shell.py` — register the
  `vlans` sync command;
- `tests/services/netbox/test_vlans.py` — task, model, and shell coverage;
- `pyproject.toml` — register `netbox_sync_vlans` marker;
- `docs/workers/netbox/services_netbox_service_tasks_sync_vlans.md` — user
  documentation;
- `docs/norfab_features.md` — feature catalogue entry and date;
- `mkdocs.yml` — user documentation navigation.

The implementation should not modify the current FakeNOS VLAN outputs unless a
test identifies an actual fixture defect.

This ADR is the only file created by the planning change.

## Acceptance Criteria

Implementation is complete when:

1. `sync_vlans` is callable through the Python client, FastAPI/MCP task schema,
   and `netbox sync vlans` NFCLI path;
2. model defaults match the task signature and every public argument is modeled;
3. one parse request collects VLANs from all resolved devices;
4. results and diffs are keyed by NetBox scope, not device;
5. identical observations deduplicate and conflicting observations never use a
   last-writer-wins rule;
6. only `name` and `description` are updated on existing VLANs;
7. deletion is disabled by default, requires explicit VID ranges, and is
   suppressed for incomplete scopes;
8. dry-run and declined approval perform no NetBox writes;
9. create, update, delete, conflict, failure, branch, idempotency, model, and
   shell tests pass;
10. focused Ruff, compile, and MkDocs checks pass;
11. the feature catalogue and task documentation accurately describe the
    shipped behavior.

## Consequences

### Positive

- VLAN names and descriptions can be synchronized independently of interfaces.
- Shared VLANs have deterministic, auditable conflict handling.
- Existing TTP templates and FakeNOS data are reused.
- Group-scoped operation aligns with current NetBox modeling direction.
- Deletion has an explicit, narrow management boundary.

### Trade-offs

- Results are scope-keyed, which differs from device-keyed interface results.
- Site compatibility mode must handle ambiguous duplicate VIDs.
- Requiring `vlan_ids` for deletion is less convenient than deleting every
  absent VLAN, but it materially reduces risk.
- Status, role, tenant, tags, and other NetBox-only policy fields remain manual.
- The task will not automatically run as part of `sync_all` in its first
  release.

## Alternatives Considered

### Extend `sync_device_interfaces`

Rejected. VLAN objects are shared across interfaces and devices, so embedding
full VLAN reconciliation in an already large interface task would obscure
scope aggregation, conflicts, and deletion safety.

### Use NAPALM `get_vlans`

Rejected for this task. NORFAB already ships a multi-platform TTP `vlans`
getter with the exact desired normalized fields and matching FakeNOS commands.

### Key the diff by device

Rejected. It would generate duplicate writes and allow device processing order
to decide shared VLAN names and descriptions.

### Delete every absent VLAN in a selected site or group

Rejected. A partial device selection does not prove that an unused or
unobserved shared VLAN is stale.

### Automatically create VLAN groups

Rejected. VLAN group scope and ID ranges are NetBox design policy, not facts
that can be derived safely from the live three-field parser output.

## Resolved Decisions

1. Public task name: `sync_vlans`.
2. Implementation file: `vlans_tasks.py`.
3. Worker mixin: `NetboxVlansTasks`.
4. Live source: Nornir `parse_ttp` with `get="vlans"`.
5. Managed fields: `vid` identity plus authoritative `name` and `description`.
6. Preferred scope: one caller-selected VLAN group.
7. Compatibility scope: each selected device's NetBox site.
8. Diff key: NetBox scope and VID, not device and VID.
9. Identical cross-device observations are deduplicated.
10. Conflicting observations are reported and skipped.
11. Duplicate target VIDs in a site scope are reported and skipped.
12. VLAN groups must already exist.
13. Site/global/group moves are outside the task.
14. Deletions default to disabled.
15. Enabled deletion requires explicit `vlan_ids`.
16. Incomplete live collection suppresses deletion for the affected scope.
17. Dry-run takes precedence over approval and never prompts.
18. Bulk operations are isolated per scope.
19. The first version does not join `sync_all` or `check_device_sync`.
20. The task gets a dedicated NFCLI file, user documentation page, and test
    module.

## References

- `CLAUDE.md`
- `docs/development/adr_tasks_pydantic_models_guide.md`
- `docs/development/documentation_style_guide.md`
- `docs/testing/netbox_service_tests.md`
- `docs/development/adr_netbox_sync_device_interfaces_plan.md`
- `norfab/workers/netbox_worker/interfaces_tasks.py`
- `norfab/workers/netbox_worker/netbox_models.py`
- `norfab/workers/netbox_worker/netbox_worker_utilities.py`
- `norfab/clients/nfcli_shell/netbox/netbox_picle_shell_sync_interfaces.py`
- `tests/services/netbox/test_interfaces.py`
- [NetBox 4.4 VLAN model](https://netboxlabs.com/docs/netbox/v4.4/models/ipam/vlan/)
- [NetBox 4.4 VLAN group model](https://netboxlabs.com/docs/netbox/v4.4/models/ipam/vlangroup/)
- [NetBox 4.4 REST API bulk operations](https://netboxlabs.com/docs/netbox/v4.4/integrations/rest-api/)
