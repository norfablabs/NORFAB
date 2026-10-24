# BGP Peerings Tasks Split Plan

## Overview

Split the internal create-path and update-path of `sync_bgp_peerings` into two
standalone, directly-callable tasks:

- `create_bgp_peering` — creates one or many BGP sessions in NetBox
- `update_bgp_peering` — updates one or many existing BGP sessions in NetBox

`sync_bgp_peerings` is **refactored** to delegate its write phase to the new tasks
(see Section 5); its external interface and return structure remain unchanged.

---

## Coding Guidelines

These apply to all code written as part of this plan:

1. **Keep the codebase minimal** — write only what is needed. No speculative abstractions or future-proofing.
2. **Avoid excessive helper functions** — extract a helper when the logic is non-trivial or reused across two or more tasks. Keep extracted functions as plain module-level functions; do not use leading underscores.
3. **Linear, easy-to-follow logic** — code should read top-to-bottom with no surprising jumps. Prefer flat `if/elif/else` chains over layered function calls.
4. **No difficult constructs** — avoid metaclasses, decorators-on-decorators, `functools` tricks, nested closures, generator pipelines, or anything that makes stepping through a debugger awkward.
5. **Simple is better than clever** — if two approaches produce the same result, always choose the one a junior engineer can understand without context.
6. **No unnecessary classes** — do not wrap logic in a class just for the sake of grouping. Module-level functions are fine.
7. Use descriptive human readable names for variables, avoid using short name like s, or plo, exception could be list or dict comprehensions though.

---

## Design Goals

1. Both tasks follow the exact same conventions as all other netbox worker tasks
   (`@Task`, Pydantic `Input` model, `Result` return, `job.event` + `log.*` casing rules).
2. Each task accepts **single-object mode** (individual keyword arguments) AND
   **bulk mode** (`bulk_create` / `bulk_update` list of dicts) — matching the pattern
   used by `create_ip_bulk`.
3. Shared resolution helpers (`resolve_ip`, `resolve_asn`, `resolve_or_create`,
   `get_addr_family`, `get_p2p_peer_ip`, `resolve_asn_from_source`) are defined at
   the **top of `bgp_peerings_tasks.py`** as plain module-level functions (no leading
   underscore) and reused by `create_bgp_peering`, `update_bgp_peering`, and the
   refactored `sync_bgp_peerings`.
4. Input validation handled by Pydantic models defined in `bgp_peerings_tasks.py` (alongside the existing `SyncBgpPeeringsInput` and `BgpSessionStatusEnum`).
5. New tests added to `TestSyncBgpPeerings` class (or a new sibling class) in
   `tests/test_netbox_service.py`.

---

## Feature: `expand_interface_range` Utility (`norfab/utils/text.py`)

A general-purpose string-expansion utility, modelled after the bracket-expansion
functions in the NetBox codebase, placed in `norfab/utils/text.py` so it is
reusable by any part of the codebase (not just the BGP tasks).

### Function signature

```python
def expand_interface_range(pattern: str) -> list[str]:
    """
    Expand a bracket-notation pattern into a list of concrete strings.

    Bracket groups ``[...]`` may contain:
    - A comma-separated list of alternatives: ``[ge,xe]``
    - A numeric range:                         ``[0-3]``
    - A mix of both:                            ``[ge,xe,0-3]``  (each token is
      treated as a literal unless it matches ``N-M`` with integer N and M)

    Multiple bracket groups in one pattern are expanded as a cartesian product.
    A pattern with no bracket groups is returned as a single-element list.

    Examples::

        expand_interface_range("[ge,xe]-0/0/[0-1]")
        # ["ge-0/0/0", "ge-0/0/1", "xe-0/0/0", "xe-0/0/1"]

        expand_interface_range("Ethernet[1-4]/1.101")
        # ["Ethernet1/1.101", "Ethernet2/1.101", "Ethernet3/1.101", "Ethernet4/1.101"]

        expand_interface_range("eth0")
        # ["eth0"]
    """
```

### Algorithm

```python
import re
from itertools import product

BRACKET_RE = re.compile(r"\[([^\]]+)\]")

def expand_bracket(group: str) -> list[str]:
    """Expand a single bracket group content into a list of string alternatives."""
    results = []
    for token in group.split(","):
        token = token.strip()
        m = re.fullmatch(r"(\d+)-(\d+)", token)
        if m:
            start, end = int(m.group(1)), int(m.group(2))
            step = 1 if end >= start else -1
            width = len(m.group(1))  # preserve leading zeros e.g. [00-03]
            results.extend(str(i).zfill(width) for i in range(start, end + step, step))
        else:
            results.append(token)
    return results

def expand_interface_range(pattern: str) -> list[str]:
    parts = BRACKET_RE.split(pattern)   # alternates: literal, group, literal, group, ...
    literals = parts[0::2]               # even indices are literal segments
    groups   = parts[1::2]               # odd indices are bracket group contents

    if not groups:
        return [pattern]

    expanded_groups = [expand_bracket(g) for g in groups]

    results = []
    for combo in product(*expanded_groups):
        s = literals[0]
        for i, val in enumerate(combo):
            s += val + literals[i + 1]
        results.append(s)
    return results
```

### Key properties

- No external dependencies — pure stdlib (`re`, `itertools.product`).
- Leading-zero preservation: `[00-03]` → `"00"`, `"01"`, `"02"`, `"03"`.
- Descending ranges: `[3-1]` → `"3"`, `"2"`, `"1"`.
- Mixed token bracket: `[ge,xe,0-2]` → `"ge"`, `"xe"`, `"0"`, `"1"`, `"2"`.
- No nested brackets (YAGNI; can be added later).

### Usage in BGP tasks

Imported directly at the top of `bgp_peerings_tasks.py`:

```python
from norfab.utils.text import expand_interface_range
```

No separate re-implementation in `bgp_peerings_tasks.py`.

---

## Feature: Interface-Driven Address and ASN Resolution

### `local_interface` argument

Allows the user to specify a **local interface name** (or a name pattern with range
expansion, e.g. `Ethernet[1-10]/1.101`) instead of an explicit `local_address` IP.

Resolution logic:

1. Look up the interface(s) in NetBox (`nb.dcim.interfaces.filter(device=device, name=local_interface)`).
2. Fetch the IP address(es) assigned to the interface from IPAM
   (`nb.ipam.ip_addresses.filter(interface_id=intf.id)`).
3. Use the IP address (without prefix length) as `local_address`.
4. If the prefix length indicates a **point-to-point subnet** (`/30`, `/31` for IPv4;
   `/127`, `/128` for IPv6), automatically derive `remote_address` as the peer IP in
   the same subnet (e.g. for `10.0.0.1/31` the peer is `10.0.0.0`; for `10.0.0.1/30`
   the peer is the other usable host in the /30).
5. With `remote_address` known, optionally look up which NetBox device owns that IP
   (`nb.ipam.ip_addresses.filter(address=remote_address)` → `assigned_object`) to
   identify the **remote device** — this is later used by `asn_source` resolution.

When `local_interface` is provided together with `bulk_create`, each item in the
bulk list may also carry its own `local_interface` to override on a per-session basis.

**P2P prefix-length detection table:**

| Prefix length | Family | Treated as P2P |
|---|---|---|
| /30 | IPv4 | yes — peer is the other usable host |
| /31 | IPv4 | yes — peer is the other address |
| /127 | IPv6 | yes — peer is the other address |
| /128 | IPv6 | yes — loopback-style; peer lookup via NetBox only |
| other | any | no — `remote_address` must be supplied explicitly |

### `asn_source` argument

Controls automatic ASN resolution when `local_as` or `remote_as` are not supplied
explicitly (if either value is already provided, `asn_source` is not invoked for
that side).  Supports two input forms:

- **`str`** — dot-separated path through the NetBox device data dict/list.
- **`dict`** — kwargs passed directly to `nb.ipam.asn.get(**asn_source)` to look up
  an ASN object from the NetBox REST API; the `asn` attribute of the returned
  object is used (e.g. `{"tenant": "lab", "rir": "RFC 1918"}`).

Examples:

```
asn_source="custom_fields.asn"                          # str: path through device data
asn_source="config_context.bgp.local_as"                # str: nested path
asn_source="custom_fields.asn.0"                        # str: first element of a list
asn_source={"tenant": "lab", "rir": "RFC 1918"}         # dict: IPAM ASN query
```

Resolution logic (module-level function `resolve_asn_from_source`):

```python
def resolve_asn_from_source(device_data: dict, asn_source, nb) -> str | None:
    """
    Resolve an ASN from device data or a NetBox IPAM query.

    asn_source can be:
    - str  → dot-separated path through device_data dict/list
    - dict → kwargs passed to nb.ipam.asn.get(**asn_source); uses asn_obj.asn
    """
    if isinstance(asn_source, dict):
        asn_obj = nb.ipam.asn.get(**asn_source)
        if asn_obj is not None:
            return str(asn_obj.asn)
    else:
        node = device_data
        for key in asn_source.split("."):
            if isinstance(node, dict):
                node = node.get(key)
            elif isinstance(node, list):
                try:
                    node = node[int(key)]
                except (ValueError, IndexError):
                    node = None
            else:
                node = None
            if node is None:
                break
        if node is not None:
            return str(node)
    return None
```

When `asn_source` is provided:

- If `local_as` is already supplied by the caller, `asn_source` is **not** invoked for the local side.
- If `remote_as` is already supplied by the caller, `asn_source` is **not** invoked for the remote side.
- For a missing `local_as`: `resolve_asn_from_source(local_device_data, asn_source, nb)` is called.
- For a missing `remote_as`: `resolve_asn_from_source(remote_device_data, asn_source, nb)` is called
  (remote device identified via the P2P peer IP lookup described above).
- If the remote device cannot be identified from IPAM and `remote_as` is not provided
  explicitly, this is treated as an **error**: `log.error` is called, `job.event` is emitted
  with `severity="ERROR"`, the message is appended to `ret.errors`, and the session is skipped.
- If `resolve_asn_from_source` returns `None` for either side: same ERROR treatment.

This enables the minimal-input usage pattern:

```python
create_bgp_peering(
    device="ceos-leaf-1",
    local_interface="Ethernet[1-4]/1.101",  # range expansion → 4 interfaces
    asn_source="custom_fields.asn",          # str path or dict query
    rir="lab",
    name_template="{device}_BGP_{name}",
)
```

This creates one BGP session per interface, resolving IPs from the interface IPAM
record, the peer IP from the /31 subnet, and both ASNs from the device/peer device
fields — without the user providing any IP addresses or AS numbers directly.

---

## 1. Shared Helper Extraction

### Current state

The resolution helpers are nested closures inside `sync_bgp_peerings`, relying on
the enclosing `nb`, `rir_id`, `job`, `ret`, and `self` variables via closure.

### Proposed refactor

All helpers are moved to the **top of `bgp_peerings_tasks.py`** as plain module-level
functions with no leading underscore.  Each function receives every value it needs as
an explicit argument — no closures, no implicit state.

```python
# --- top of bgp_peerings_tasks.py, above all classes ---

def resolve_ip(address, nb, job, ret, worker_name) -> int | None:
    """Resolve or create an IP address in IPAM, return its NetBox ID or None."""
    ...

def resolve_asn(asn_str, nb, rir_id, job, ret, worker_name) -> int | None:
    """Resolve or create an ASN, return its NetBox ID or None."""
    ...

def resolve_or_create(endpoint, name, obj_type, nb, job, ret, worker_name, family=None) -> int | None:
    """Resolve or create a named BGP object (peer group / routing policy / prefix list)."""
    ...

def get_addr_family(address) -> str:
    """Return 'ipv4' or 'ipv6' based on the IP address version."""
    ...

def get_p2p_peer_ip(cidr: str) -> str | None:
    """Return the peer IP for a P2P subnet (/30, /31, /127) or None for other prefixes."""
    ...

def resolve_asn_from_source(device_data: dict, asn_source, nb) -> str | None:
    """Resolve ASN from device data (dot-path str) or NetBox IPAM query (dict); return ASN string or None."""
    ...
```

All three tasks (`create_bgp_peering`, `update_bgp_peering`, `sync_bgp_peerings`)
call these module-level functions directly, passing their local `nb`, `rir_id`,
`job`, `ret`, and `self.name` as arguments.

`expand_interface_range` lives in `norfab/utils/text.py` and is imported at the
top of `bgp_peerings_tasks.py`:

```python
from norfab.utils.text import expand_interface_range
```

---

## 2. New Pydantic Models (added to `bgp_peerings_tasks.py`)

All models live in `bgp_peerings_tasks.py` alongside the existing `SyncBgpPeeringsInput`
and `BgpSessionStatusEnum`. No changes to `netbox_models.py`.

### `BgpSessionFields` — shared base for a single BGP session's data fields

```python
class BgpSessionFields(BaseModel):
    name: StrictStr          # session name as it will appear in NetBox
    device: StrictStr        # device name (used to resolve device ID)
    local_address: Optional[StrictStr] = None   # derived from local_interface when omitted
    remote_address: Optional[StrictStr] = None  # derived from P2P peer when omitted
    local_as: Optional[StrictStr] = None        # derived from asn_source when omitted
    remote_as: Optional[StrictStr] = None       # derived from asn_source on remote device
    status: BgpSessionStatusEnum = "active"
    description: Optional[StrictStr] = None
    vrf: Optional[StrictStr] = None
    peer_group: Optional[StrictStr] = None
    import_policies: Optional[List[StrictStr]] = None
    export_policies: Optional[List[StrictStr]] = None
    prefix_list_in: Optional[List[StrictStr]] = None
    prefix_list_out: Optional[List[StrictStr]] = None
    local_interface: Optional[StrictStr] = None # per-session interface override
```

`BgpSessionStatusEnum` already exists in `bgp_peerings_tasks.py` and stays there.

### `CreateBgpPeeringInput(NetboxCommonArgs)`

```python
class CreateBgpPeeringInput(NetboxCommonArgs, use_enum_values=True):
    # --- Single-session mode ---
    name: Optional[StrictStr] = None
    device: Optional[StrictStr] = None
    local_address: Optional[StrictStr] = None   # explicit IP string
    remote_address: Optional[StrictStr] = None  # explicit IP string; derived when local_interface + P2P
    local_as: Optional[StrictStr] = None        # explicit AS string; derived when asn_source set
    remote_as: Optional[StrictStr] = None       # explicit AS string; derived when asn_source set
    status: BgpSessionStatusEnum = "active"
    description: Optional[StrictStr] = None
    vrf: Optional[StrictStr] = None
    peer_group: Optional[StrictStr] = None
    import_policies: Optional[List[StrictStr]] = None
    export_policies: Optional[List[StrictStr]] = None
    prefix_list_in: Optional[List[StrictStr]] = None
    prefix_list_out: Optional[List[StrictStr]] = None

    # --- Interface-driven resolution ---
    local_interface: Optional[StrictStr] = Field(...)
    asn_source: Optional[Union[StrictStr, Dict[StrictStr, Any]]] = Field(
        None,
        description="Dot-path string or IPAM query dict for automatic ASN resolution.",
        examples=[
            "str: dot-separated path through device data, e.g. 'custom_fields.asn'. "
            "dict: kwargs for nb.ipam.asn.get, e.g. {'tenant': 'lab', 'rir': 'RFC 1918'}."
        ],
    )
    name_template: Optional[StrictStr] = Field(...)

    # --- Mirror session ---
    create_reverse: bool = Field(
        True,
        description="When True, also create a reverse BGP session on the remote device with local and remote IPs/ASNs swapped.",
        examples=[
            "Set to False to create only the local-device session and skip the automatic "
            "mirror session on the remote device."
        ],
    )

    # --- Bulk mode ---
    bulk_create: Optional[List[BgpSessionFields]] = Field(
        None,
        description="List of BGP session objects to create in bulk.",
        examples=[
            "List of BgpSessionFields dicts, each requiring at minimum 'name', 'device', "
            "and either 'local_address' or 'local_interface'. "
            "Example: [{'name': 'leaf1_10.0.0.1_10.0.0.0', 'device': 'leaf1', "
            "'local_address': '10.0.0.1', 'remote_address': '10.0.0.0', "
            "'local_as': '65001', 'remote_as': '65002'}]."
        ],
    )

    # --- Shared resolution options ---
    rir: Optional[StrictStr] = Field(
        None,
        description="RIR name used when auto-creating ASNs in NetBox.",
        examples=["RIR name as it appears in NetBox, e.g. 'RFC 1918', 'ARIN', 'RIPE'."],
    )
    message: Optional[StrictStr] = Field(
        None,
        description="Changelog message recorded on every NetBox write.",
        examples=["Free-text string written to the NetBox changelog, e.g. 'Provisioned by NorFab'."],
    )

    @model_validator(mode="after")
    def validate_single_or_bulk(self):
        if self.bulk_create is None:
            # In single-session mode device is always required.
            # local_address OR local_interface must be provided.
            # remote_address may be omitted when local_interface resolves a P2P subnet.
            # local_as / remote_as may be omitted when asn_source is provided.
            if not self.device:
                raise ValueError("Single-session mode requires 'device'.")
            if not self.local_address and not self.local_interface:
                raise ValueError(
                    "Single-session mode requires either 'local_address' or 'local_interface'."
                )
        return self
```

### `BgpSessionUpdateFields` — changeable fields for a single update

```python
class BgpSessionUpdateFields(BaseModel):
    name: StrictStr          # existing session name to update (required)
    description: Optional[StrictStr] = None
    status: Optional[BgpSessionStatusEnum] = None
    local_address: Optional[StrictStr] = None
    remote_address: Optional[StrictStr] = None
    local_as: Optional[StrictStr] = None
    remote_as: Optional[StrictStr] = None
    vrf: Optional[StrictStr] = None
    peer_group: Optional[StrictStr] = None
    import_policies: Optional[List[StrictStr]] = None
    export_policies: Optional[List[StrictStr]] = None
    prefix_list_in: Optional[List[StrictStr]] = None
    prefix_list_out: Optional[List[StrictStr]] = None
```

### `UpdateBgpPeeringInput(NetboxCommonArgs)`

```python
class UpdateBgpPeeringInput(NetboxCommonArgs, use_enum_values=True):
    # --- Single-session mode ---
    name: Optional[StrictStr] = Field(
        None,
        description="Existing session name to update.",
        examples=["Name of the BGP session as stored in NetBox, e.g. 'leaf1_10.0.0.1_10.0.0.0'."],
    )
    description: Optional[StrictStr] = None
    status: Optional[BgpSessionStatusEnum] = None
    local_address: Optional[StrictStr] = None
    remote_address: Optional[StrictStr] = None
    local_as: Optional[StrictStr] = None
    remote_as: Optional[StrictStr] = None
    vrf: Optional[StrictStr] = None
    peer_group: Optional[StrictStr] = None
    import_policies: Optional[List[StrictStr]] = None
    export_policies: Optional[List[StrictStr]] = None
    prefix_list_in: Optional[List[StrictStr]] = None
    prefix_list_out: Optional[List[StrictStr]] = None

    # --- Bulk mode ---
    bulk_update: Optional[List[BgpSessionUpdateFields]] = Field(
        None,
        description="List of BGP sessions to update in bulk.",
        examples=[
            "List of BgpSessionUpdateFields dicts, each requiring 'name' plus any fields to change. "
            "Example: [{'name': 'leaf1_10.0.0.1_10.0.0.0', 'description': 'uplink', 'status': 'active'}]."
        ],
    )

    # --- Shared resolution options ---
    rir: Optional[StrictStr] = None
    message: Optional[StrictStr] = None

    @model_validator(mode="after")
    def validate_single_or_bulk(self):
        if self.bulk_update is None and self.name is None:
            raise ValueError(
                "Either 'name' (single-session mode) or 'bulk_update' (bulk mode) is required."
            )
        return self
```

---

## 3. New Task: `create_bgp_peering`

**Location:** `norfab/workers/netbox_worker/bgp_peerings_tasks.py` — new method on
`NetboxBgpPeeringsTasks`.

**Decorator:**

```python
@Task(fastapi={"methods": ["POST"], "schema": NetboxFastApiArgs.model_json_schema()})
```

**Signature:**

```python
def create_bgp_peering(
    self,
    job: Job,
    instance: Union[None, str] = None,
    # single-session mode
    name: Union[None, str] = None,
    device: Union[None, str] = None,
    local_address: Union[None, str] = None,
    remote_address: Union[None, str] = None,
    local_as: Union[None, str] = None,
    remote_as: Union[None, str] = None,
    status: str = "active",
    description: Union[None, str] = None,
    vrf: Union[None, str] = None,
    peer_group: Union[None, str] = None,
    import_policies: Union[None, list] = None,
    export_policies: Union[None, list] = None,
    prefix_list_in: Union[None, list] = None,
    prefix_list_out: Union[None, list] = None,
    # interface-driven resolution
    local_interface: Union[None, str] = None,
    asn_source: Union[None, str, dict] = None,
    name_template: Union[None, str] = None,
    # mirror session
    create_reverse: bool = True,
    # bulk mode
    bulk_create: Union[None, list] = None,
    # shared
    rir: Union[None, str] = None,
    message: Union[None, str] = None,
    branch: Union[None, str] = None,
    dry_run: bool = False,
) -> Result:
```

**Logic flow:**

1. Validate BGP plugin is installed (`has_plugin`).
2. Connect pynetbox: `nb = self._get_pynetbox(instance, branch=branch)`.
3. Set changelog message header if `message` provided.
4. Resolve `rir_id` once.
5. Build the list of session specs to process:
   - **Single-session mode** (`bulk_create is None`): one spec from keyword arguments.
   - **Bulk mode**: iterate `bulk_create` list.
5a. **Resolve interfaces, IPs, and devices for every spec in one pass** (before any
    idempotency pre-fetch). For each spec:
    - Record the local device name in `all_device_names`.
    - If `local_interface` is set (spec-level or task-level):
      - Expand any range pattern via `expand_interface_range`.
      - For each expanded interface name, look it up in NetBox
        (`nb.dcim.interfaces.filter(device=device, name=intf_name)`) and fetch the
        assigned IP from IPAM (`nb.ipam.ip_addresses.filter(interface_id=intf.id)`).
      - Store the IP address portion (without prefix length) as `local_address` on the spec.
      - Call `get_p2p_peer_ip` on the full CIDR string. If it returns a peer IP:
        - Store the peer IP as `remote_address` on the spec.
        - Look up that peer IP in IPAM (`nb.ipam.ip_addresses.filter(address=remote_ip)`)
          to find its `assigned_object.device.name` — store this as `remote_device` on
          the spec and add it to `all_device_names`.
    - After processing the spec, `all_device_names` contains every local device name plus
      every remote device name discovered via P2P resolution.
5b. **Pre-fetch existing sessions for idempotency** (single API call):
    - Call `nb.plugins.bgp.session.filter(device=list(all_device_names), fields="name,id")`
      once using the complete set built in step 5a.
    - Build `existing_session_names: set[str]` from the results.
    - This set is used in steps 6i and 6k; no additional API calls are made per spec.
6. For each spec, **resolve ASNs and NetBox IDs**:
   a. `local_address`, `remote_address`, and `remote_device` are already resolved from
      step 5a; no further interface or IP lookup is needed here.
   b. If `asn_source` set and `local_as` is not yet resolved (not supplied by caller):
      - Fetch full device data for the local device from NetBox.
      - Call `resolve_asn_from_source(device_data, asn_source, nb)`; use result as
        `local_as`.
      - If `resolve_asn_from_source` returns `None`: call `log.error`, emit
        `job.event(severity="ERROR")`, append to `ret.errors`, skip session.
   c. If `asn_source` set and `remote_as` is not yet resolved (not supplied by caller):
      - If `remote_device` was not found in step 5a (peer IP not in IPAM
        and `remote_as` not supplied explicitly): call `log.error`, emit
        `job.event(severity="ERROR")`, append to `ret.errors`, skip session.
      - Otherwise fetch full device data for the remote device and call
        `resolve_asn_from_source(remote_device_data, asn_source, nb)`; use result as
        `remote_as`.
      - If `resolve_asn_from_source` returns `None`: call `log.error`, emit
        `job.event(severity="ERROR")`, append to `ret.errors`, skip session.
   d. Call `resolve_ip` for `local_address` and `remote_address` (creates in IPAM
      if missing).
   e. Call `resolve_asn` for `local_as` and `remote_as` (creates ASN if `rir_id`
      available).
   f. Resolve device ID and **site ID** via `nb.dcim.devices.get(name=device)`. Site is
      always taken from the device object — it is never accepted as a task argument.
   g. If any required field is still missing: append to `ret.errors`, skip session,
      emit `job.event` with `severity="WARNING"`.
   h. Optionally resolve `vrf`, `peer_group`, `import_policies`, `export_policies`,
      `prefix_list_in`, `prefix_list_out` using `resolve_or_create`. Policy and
      prefix-list fields are accepted as `List[str]`; each element is resolved or
      created individually in NetBox and its ID collected. When `sync_bgp_peerings`
      delegates, it must split any pipe-separated strings into lists before building
      the `bulk_create` payload.
   i. **Idempotency check**: look up `sname` in `existing_session_names` (the set
      pre-fetched in step 5a). If present, add `sname` to `exists` list, emit a
      `job.event` (no severity), and skip — do **not** create a duplicate.
      No additional API call is made per spec.
   j. If `dry_run`: append `sname` (the resolved session name string) to the
      `dry_run` list. No NetBox IDs are resolved in dry-run mode — the check only
      produces the list of names that *would* be created.
   k. **Mirror (reverse) session** — only when `create_reverse=True` and the remote
      device was successfully identified from IPAM (step 5a):
      - Build a mirror spec by swapping every resolved value:
        - `device` = remote device name
        - `local_address` / `local_as` = original `remote_address` / `remote_as`
        - `remote_address` / `remote_as` = original `local_address` / `local_as`
        - All other fields (`vrf`, `peer_group`, policies, prefix lists) copied as-is.
      - Derive `mirror_name` using `name_template` (same template, swapped values);
        default: `"{device}_{local_address}_{remote_address}"` with swapped IPs.
      - Resolve device ID and site ID for the remote device via
        `nb.dcim.devices.get(name=remote_device_name)`. If not found: emit
        `job.event` WARNING, append to `ret.errors`, skip mirror session.
      - Run idempotency check: look up `mirror_name` in `existing_session_names`.
        If already exists: add to `exists`, skip.
      - If `dry_run`: append `mirror_name` to `dry_run` list.
      - Otherwise: add the mirror payload to the same `payloads` list for bulk
        creation in step 7.
7. If not dry_run: call `nb.plugins.bgp.session.create(payloads)` in bulk.
8. Return `Result`.

**Note on `local_interface` + range expansion:** when a range pattern expands to
multiple interfaces (e.g. `Ethernet[1-4]/1.101` → 4 interfaces), the task creates
one BGP session per interface.  Session `name` is derived from `name_template` if
provided, otherwise defaults to `"{device}_{local_address}_{remote_address}"`.

**Return structure (normal run):**

```python
{
    "created": ["session-name-1", "session-name-2"],
    "exists":  ["session-name-3"],  # already in NetBox, not re-created
}
```

**Return structure (dry run):**

```python
{
    "create": ["session-name-1", "session-name-2"],  # names that would be created
    "exists":  ["session-name-3"],                     # names that already exist
}
```

---

## 4. New Task: `update_bgp_peering`

**Location:** same file, new method on `NetboxBgpPeeringsTasks`.

**Decorator:**

```python
@Task(fastapi={"methods": ["PATCH"], "schema": NetboxFastApiArgs.model_json_schema()})
```

**Signature:**

```python
def update_bgp_peering(
    self,
    job: Job,
    instance: Union[None, str] = None,
    # single-session mode
    name: Union[None, str] = None,
    description: Union[None, str] = None,
    status: Union[None, str] = None,
    local_address: Union[None, str] = None,
    remote_address: Union[None, str] = None,
    local_as: Union[None, str] = None,
    remote_as: Union[None, str] = None,
    vrf: Union[None, str] = None,
    peer_group: Union[None, str] = None,
    import_policies: Union[None, list] = None,
    export_policies: Union[None, list] = None,
    prefix_list_in: Union[None, list] = None,
    prefix_list_out: Union[None, list] = None,
    # bulk mode
    bulk_update: Union[None, list] = None,
    # shared
    rir: Union[None, str] = None,
    message: Union[None, str] = None,
    branch: Union[None, str] = None,
    dry_run: bool = False,
) -> Result:
```

**Logic flow:**

1. Validate BGP plugin is installed.
2. Connect pynetbox.
3. Set changelog message header.
4. Resolve `rir_id`.
5. Build list of (session_name, changed_fields) pairs:
   - **Single-session mode** (`bulk_update is None`): `name` is required; build one
     dict from any non-None keyword arguments excluding `name`.
   - **Bulk mode**: iterate `bulk_update` list, each item has `name` plus optional fields.
6. For each session to update:
   a. Fetch existing session from NetBox: `nb.plugins.bgp.session.get(name=sname)`.
   b. If not found: append to `ret.errors`, emit `job.event` `WARNING`, continue.
   c. Determine `addr_family` using `get_addr_family` on existing session's local IP.
   d. Build `changed_payload` — a dict of field → new resolved value — using the
      same field-dispatch logic as the current update block in `sync_bgp_peerings`
      (calls `resolve_ip`, `resolve_asn`, `resolve_or_create` as appropriate).
      Only include fields that are actually provided in the update spec (non-None).
   e. **Idempotency / dry-run diff:** normalise the existing session's current values
      into a comparable dict (same field names as `changed_payload`). Run
      `deepdiff.DeepDiff(current_normalised, changed_payload, ignore_order=True)`.
      - If `dry_run`: append `{"name": sname, "diff": deepdiff_result}` to
        `dry_run` list and skip the write. If diff is empty, add to `in_sync`
        instead.
      - If not dry_run and diff is empty: add `sname` to `in_sync` list, skip write.
   f. If not dry_run and diff non-empty: call `session.update(changed_payload)`,
      add `sname` to `updated` list.
7. Return `Result`.

**Return structure (normal run):**

```python
{
    "updated": ["session-name-1"],
    "in_sync": ["session-name-2"],  # no changes needed
}
```

**Return structure (dry run):**

```python
{
    "update": [
        {
            "name": "session-name-1",
            "diff": {"values_changed": {"root['description']": {"new_value": "new", "old_value": "old"}}}
        }
    ],
    "in_sync": ["session-name-2"],
}
```

---

## 5. `sync_bgp_peerings` Refactor

`sync_bgp_peerings` is refactored to delegate the entire write phase to the new
tasks.  After computing `full_diff`, it builds two flat lists and calls:

```python
# Build bulk_create list from full_diff
bulk_create = []
for device_name, actions in full_diff.items():
    for sname in actions["create"]:
        s = normalised_live[device_name][sname]
        bulk_create.append({"name": sname, "device": device_name, **s})

# Build bulk_update list from full_diff
bulk_update = []
for device_name, actions in full_diff.items():
    for sname, field_changes in actions["update"].items():
        entry = {"name": sname}
        for field, change in field_changes.items():
            entry[field] = change["new_value"]
        bulk_update.append(entry)

# Delegate writes
if bulk_create:
    create_result = self.create_bgp_peering(
        job=job, instance=instance, bulk_create=bulk_create,
        rir=rir, message=message, branch=branch,
    )
    ret.errors.extend(create_result.errors)

if bulk_update:
    update_result = self.update_bgp_peering(
        job=job, instance=instance, bulk_update=bulk_update,
        rir=rir, message=message, branch=branch,
    )
    ret.errors.extend(update_result.errors)
```

The deletion loop remains inline in `sync_bgp_peerings` (it is a simple
`session.delete()` loop not shared with any other task).

The existing nested-closure helpers inside `sync_bgp_peerings` are **removed**;
the task now calls the module-level functions directly.

External behaviour of `sync_bgp_peerings` is unchanged — the return structure
(`created`, `updated`, `deleted`, `in_sync` per device) is assembled from the
results of the delegated calls and the existing diff data.

---

## 6. CLI Shell Registration

Find how `sync_bgp_peerings` is registered in `norfab/clients/nfcli_shell/nfcli_shell_client.py`
and mirror the exact same pattern for the two new tasks.

Expected command paths:

```
nf# netbox create bgp-peering ...
nf# netbox update bgp-peering ...
```

Each parameter of the task function maps to one CLI argument. Follow the same
argument-naming conventions already used (hyphen-separated, e.g. `dry-run`,
`bulk-create`, `local-interface`, `asn-source`, `name-template`).

```
netbox.create.bgp-peering
            ├── ...
            ├── local-interface
            ├── asn-source
            ├── name-template
            ├── create-reverse
            ├── bulk-create
            ├── rir
            └── message
```

Full expected `man tree` output:
nf# man tree netbox.create.bgp-peering
root
└── netbox:    Netbox service
    └── create:    Create Netbox objects
        └── bgp-peering:    Create BGP peering session(s)
            ├── timeout
            ├── workers
            ├── verbose-result
            ├── progress
            ├── instance
            ├── branch
            ├── dry-run
            ├── name
            ├── device
            ├── local-address
            ├── remote-address
            ├── local-as
            ├── remote-as
            ├── status
            ├── description
            ├── vrf
            ├── peer-group
            ├── import-policies
            ├── export-policies
            ├── prefix-list-in
            ├── prefix-list-out
            ├── local-interface
            ├── asn-source
            ├── name-template
            ├── create-reverse
            ├── bulk-create
            ├── rir
            └── message

nf# man tree netbox.update.bgp-peering
root
└── netbox:    Netbox service
    └── update:    Update Netbox objects
        └── bgp-peering:    Update BGP peering session(s)
            ├── timeout
            ├── workers
            ├── verbose-result
            ├── progress
            ├── instance
            ├── branch
            ├── dry-run
            ├── name
            ├── description
            ├── status
            ├── local-address
            ├── remote-address
            ├── local-as
            ├── remote-as
            ├── vrf
            ├── peer-group
            ├── import-policies
            ├── export-policies
            ├── prefix-list-in
            ├── prefix-list-out
            ├── bulk-update
            ├── rir
            └── message
```

---

## 7. Test Plan (additions to `tests/test_netbox_service.py`)

Follow the same structure as `TestSyncBgpPeerings`:
- `setup_method` / `teardown_method` call `delete_bgp_sessions()` to ensure a clean state.
- Each test is self-contained: it creates whatever NetBox state it needs, runs the
  task, asserts on the result, and cleans up any side-effect objects it created.
- Use `get_pynetbox(nfclient)` for direct NetBox verification.
- Print the raw result with `pprint.pprint(ret)` before assertions for easier debugging.

### New test class: `TestCreateBgpPeering`

| Test | What it verifies |
|---|---|
| `test_create_bgp_peering_single` | Single-session mode — `created=[name]`, session appears in NetBox |
| `test_create_bgp_peering_single_idempotent` | Session already exists — `exists=[name]`, no duplicate created |
| `test_create_bgp_peering_single_dry_run` | `dry_run=True` — `dry_run=[name]` returned, no session in NetBox |
| `test_create_bgp_peering_single_dry_run_exists` | `dry_run=True`, session already exists — `dry_run=[]`, `exists=[name]` |
| `test_create_bgp_peering_bulk` | `bulk_create=[...]` — all sessions in `created`, appear in NetBox |
| `test_create_bgp_peering_bulk_partial_idempotent` | Some sessions already exist — correct split between `created` and `exists` |
| `test_create_bgp_peering_bulk_dry_run` | `dry_run=True` + bulk — `dry_run=[names]`, no writes |
| `test_create_bgp_peering_reverse_session` | `create_reverse=True` — both local and remote sessions created |
| `test_create_bgp_peering_reverse_session_idempotent` | Remote session already exists — in `exists`, local session still created |
| `test_create_bgp_peering_reverse_disabled` | `create_reverse=False` — only local session created |
| `test_create_bgp_peering_reverse_dry_run` | `dry_run=True`, `create_reverse=True` — both names in `dry_run` |
| `test_create_bgp_peering_reverse_unknown_remote_device` | Remote device not in NetBox — mirror skipped with error, local session still created |
| `test_create_bgp_peering_missing_required` | Single mode with missing field — `failed=True` + error message |
| `test_create_bgp_peering_nonexistent_device` | Unknown device name — error appended, no crash |
| `test_create_bgp_peering_with_branch` | `branch=...` — session created in branch |
| `test_create_bgp_peering_with_peer_group_policies_prefix_lists` | Optional fields resolved/created in NetBox |
| `test_create_bgp_peering_asn_auto_create` | ASN not in NetBox — auto-created when `rir` provided |
| `test_create_bgp_peering_ip_auto_create` | IP not in NetBox — auto-created in IPAM |
| `test_create_bgp_peering_local_interface` | `local_interface` resolves `local_address` from IPAM |
| `test_create_bgp_peering_local_interface_p2p_derives_remote` | P2P /31 — `remote_address` derived automatically |
| `test_create_bgp_peering_local_interface_range` | Range pattern expands to multiple sessions |
| `test_create_bgp_peering_asn_source_custom_fields` | `asn_source="custom_fields.asn"` resolves both ASNs |
| `test_create_bgp_peering_asn_source_config_context` | `asn_source="config_context.bgp.local_as"` resolves ASNs |
| `test_create_bgp_peering_asn_source_ipam_dict` | `asn_source={"tenant": "lab"}` queries IPAM directly |
| `test_create_bgp_peering_interface_and_asn_source_combined` | Minimal input: device + interface range + asn_source |
| `test_create_bgp_peering_non_p2p_interface_requires_remote` | Non-P2P prefix — error if `remote_address` missing |

### New test class: `TestUpdateBgpPeering`

| Test | What it verifies |
|---|---|
| `test_update_bgp_peering_single` | Single-session mode — field updated, in `updated` list |
| `test_update_bgp_peering_single_dry_run` | `dry_run=True` — deepdiff returned in `dry_run`, no write |
| `test_update_bgp_peering_single_dry_run_in_sync` | `dry_run=True`, values already match — `in_sync=[name]`, empty `dry_run` |
| `test_update_bgp_peering_bulk` | `bulk_update=[...]` — all changed sessions in `updated` |
| `test_update_bgp_peering_bulk_dry_run` | `dry_run=True` + bulk — diffs in `dry_run` list |
| `test_update_bgp_peering_nonexistent_session` | Session not in NetBox — error appended, not in `updated` |
| `test_update_bgp_peering_no_changes` | All values already match — `in_sync=[name]`, `updated=[]`, no write |
| `test_update_bgp_peering_status` | `status` field updated correctly |
| `test_update_bgp_peering_description` | `description` field updated correctly |
| `test_update_bgp_peering_routing_policies` | `import_policies` / `export_policies` updated |
| `test_update_bgp_peering_with_branch` | `branch=...` — update applied to branch |

---

## 8. Documentation

Create two new files modelled **exactly** on
`docs/workers/netbox/services_netbox_service_tasks_sync_bgp_peerings.md`.

### Files to create

- `docs/workers/netbox/services_netbox_service_tasks_create_bgp_peering.md`
- `docs/workers/netbox/services_netbox_service_tasks_update_bgp_peering.md`

### Required sections (same order as the reference doc)

1. **YAML front-matter** — `tags: [netbox]`
2. **Title and task API name** — e.g. `> task api name: create_bgp_peering`
3. **One-paragraph description** of what the task does.
4. **How it Works** — numbered steps matching the logic flow in section 3 / 4 of
   this plan.
5. **Prerequisites** — BGP plugin requirement, any other hard dependencies.
6. **Branching Support** paragraph (same boilerplate as sync doc).
7. **Dry Run Mode** — describe return structure with a fenced code block.
8. **Examples** — tabbed `=== "CLI"` / `=== "Python"` blocks covering:
   - Single-session mode
   - Bulk mode
   - Dry-run
   - With `branch`
   - With `local_interface` + `asn_source` (create doc only)
9. **NORFAB Shell Reference** — paste the `man tree` output from section 6.
10. **Python API Reference** — MkDocs autodoc directive:

```markdown
::: norfab.workers.netbox_worker.bgp_peerings_tasks.NetboxBgpPeeringsTasks.create_bgp_peering
```

```markdown
::: norfab.workers.netbox_worker.bgp_peerings_tasks.NetboxBgpPeeringsTasks.update_bgp_peering
```

Also add both new pages to `mkdocs.yml` nav under the Netbox worker section,
following the same ordering as the sync page.

---

## 9. File Change Summary

| File | Change |
|---|---|
| `norfab/utils/text.py` | Add `expand_interface_range` and `expand_bracket` utilities |
| `norfab/workers/netbox_worker/bgp_peerings_tasks.py` | Add module-level helpers (`resolve_ip`, `resolve_asn`, `resolve_or_create`, `get_addr_family`, `get_p2p_peer_ip`, `resolve_asn_from_source`) at top of file; add Pydantic models; add `create_bgp_peering` and `update_bgp_peering` methods; refactor `sync_bgp_peerings` to delegate writes and use module-level helpers |
| `norfab/workers/netbox_worker/netbox_models.py` | No changes |
| `norfab/clients/nfcli_shell/nfcli_shell_client.py` | Register `create bgp-peering` and `update bgp-peering` commands |
| `tests/test_netbox_service.py` | Add `TestCreateBgpPeering` and `TestUpdateBgpPeering` classes |
| `docs/workers/netbox/services_netbox_service_tasks_create_bgp_peering.md` | New doc file (modelled on sync_bgp_peerings doc) |
| `docs/workers/netbox/services_netbox_service_tasks_update_bgp_peering.md` | New doc file (modelled on sync_bgp_peerings doc) |
| `mkdocs.yml` | Add both new doc pages to nav under Netbox worker section |

---

## 10. Resolved Decisions

| # | Question | Decision |
|---|---|---|
| 1 | Should `sync_bgp_peerings` delegate writes to the new tasks? | **Yes** — refactored in Section 5. Single source of truth for write logic. |
| 2 | Should `site` be an accepted argument? | **No** — always inferred from the device object; removed from all models, signatures, and CLI. |
| 3 | Should policies be `List[str]`? | **Yes** — all four policy/prefix-list fields (`import_policies`, `export_policies`, `prefix_list_in`, `prefix_list_out`) are `List[str]`. `sync_bgp_peerings` must split pipe-separated strings before delegating. |
| 4 | Bulk error granularity — fail all or skip bad session? | **Skip and append to errors** — same behaviour as `sync_bgp_peerings`. |
| 5 | `asn_source` on `update_bgp_peering`? | **No for now** — `create_bgp_peering` only; add to update as a follow-up. |
| 6 | Failure when remote ASN unresolvable via `asn_source`? | **ERROR** — call `log.error`, emit `job.event(severity="ERROR")`, append to `ret.errors`, skip session. Same applies when remote device cannot be identified from IPAM and `remote_as` was not provided explicitly. |
| 7 | Where does `sync_bgp_peerings` split pipe-separated policy strings? | **Inside `sync_bgp_peerings`**, just before building the `bulk_create` / `bulk_update` payload; no Pydantic validator needed. |
| 8 | Should `name_template` be added to `create_bgp_peering`? | **Yes** — added to signature, `CreateBgpPeeringInput`, and CLI tree. Used only when `local_interface` range expansion produces multiple sessions; default is `"{device}_{local_address}_{remote_address}"`. |
| 9 | `asn_source` type — string paths only, or also NetBox REST query? | **Both** — `asn_source` accepts `str` (dot-path through device data) or `dict` (kwargs for `nb.ipam.asn.get`). No list fallback. `resolve_asn_from_source` takes `nb` as a third argument. |
| 10 | Idempotency on `create_bgp_peering`? | **Yes** — existing sessions are pre-fetched once with `nb.plugins.bgp.session.filter(device=[...], fields="name,id")` before the per-spec loop (step 5a). The idempotency check inside the loop is a `set` lookup — no extra API call per spec. Sessions already in NetBox are added to `exists` and skipped. Both normal and dry-run modes report `exists`. |
| 11 | Dry-run behaviour for `create_bgp_peering`? | Returns `{"dry_run": [names_that_would_be_created], "exists": [names_already_in_netbox]}`. No ID resolution is performed in dry-run mode; only names are reported. |
| 12 | Dry-run behaviour for `update_bgp_peering`? | Uses `deepdiff.DeepDiff` to compare the normalised current NetBox values against the proposed update. Returns `{"dry_run": [{"name": ..., "diff": ...}], "in_sync": [...]}`. Sessions with no diff go to `in_sync`. |
| 13 | Idempotency on `update_bgp_peering`? | **Yes** — if `deepdiff` returns empty, session is added to `in_sync` and no write is performed (in both normal run and dry-run). |
| 14 | Should `create_bgp_peering` also create a reverse (mirror) session on the remote device? | **Yes by default** — when `create_reverse=True` (default) and the remote device is identified from IPAM, a second session is built by swapping local↔remote IPs and ASNs. `name_template` is applied with the swapped values. The mirror session goes through the same idempotency check. Set `create_reverse=False` to suppress. `sync_bgp_peerings` passes `create_reverse=False` when delegating (it manages both sides via diff independently). |

---

## 11. Open Questions

No open questions at this time.
