# ADR - NetBox sync_device_inventory Task Plan

## Overview

Add a new NetBox worker task named `sync_device_inventory` in
`norfab/workers/netbox_worker/devices_tasks.py`.

The task is the device inventory-sync path. It uses the Nornir service with the
TTP `inventory` getter, reconciles chassis serial numbers and installed
modules, and follows the same sync pattern used by `sync_device_interfaces`
and `sync_bgp_peerings`.

The task should:

- fetch current NetBox data for devices, module bays, and installed modules;
- fetch live inventory from devices using Nornir `parse_ttp` with
  `get="inventory"`;
- normalize NetBox and live inventory into comparable dictionaries;
- compare both states using `self.make_diff`, which wraps DeepDiff;
- update the NetBox device serial number from the chassis inventory record;
- create, update, or delete NetBox modules installed in module bays;
- keep module deletions disabled by default for safety.

## Coding Guidelines

- Keep the implementation close to the patterns in `interfaces_tasks.py` and
  `bgp_peerings_tasks.py`.
- Keep helper functions module-local unless another task needs them.
- Put Pydantic models in
  `norfab/workers/netbox_worker/netbox_models.py`, not in the task module.
- Use `Result` consistently and report partial failures through
  `ret.errors`.
- Use lowercase `job.event` messages and uppercase logging messages, following
  the project guidance in `CLAUDE.md`.
- Prefer readable, linear flow over broad abstractions.
- Do not change unrelated device, interface, IP, MAC, or BGP sync behavior.

Additional coding guidelines:

1. **Keep the codebase minimal** - write only what is needed. No speculative abstractions or future-proofing.
2. **Avoid excessive helper functions** - extract a helper when the logic is non-trivial or reused across two or more tasks. Keep extracted functions as plain module-level functions; do not use leading underscores.
3. **Linear, easy-to-follow logic** - code should read top-to-bottom with no surprising jumps. Prefer flat `if/elif/else` chains over layered function calls.
4. **No difficult constructs** - avoid metaclasses, decorators-on-decorators, `functools` tricks, nested closures, generator pipelines, or anything that makes stepping through a debugger awkward.
5. **Simple is better than clever** - if two approaches produce the same result, always choose the one a junior engineer can understand without context.
6. **No unnecessary classes** - do not wrap logic in a class just for the sake of grouping. Module-level functions are fine.
7. Use descriptive human readable names for variables, avoid using short name like s, or plo, exception could be list or dict comprehensions though.

## Design Goals

1. Add a richer inventory workflow alongside the serial-only NAPALM workflow.
2. Use Nornir `parse_ttp` as the live inventory source.
3. Update NetBox device serial number from the chassis serial only.
4. Manage installed modules in existing NetBox module bays.
5. Produce a dry-run action plan before writing changes.
6. Use the same normalized-state and DeepDiff approach as the newer sync tasks.
7. Keep deletion behavior explicit through `process_deletions=False`.
8. Continue processing other devices when one device has incomplete data or an
   execution error.
9. Preserve branch-aware NetBox access.
10. Model transceivers, optics, and SFPs as NetBox modules rather than
    inventory items.

## Scope

Managed by this task:

- `dcim.device.serial`, sourced from the chassis inventory record.
- `dcim.module_bays`, when `create_module_bays=True`.
- `dcim.modules`, installed in existing or newly created `dcim.module_bays`.
- transceivers, optics, and SFPs as `dcim.modules` when their live inventory
  record can be mapped to a module bay.
- module serial numbers.
- module type, part/model, description, and status where the parser and NetBox
  schema provide enough data.

Not managed by this task:

- creating NetBox devices;
- creating module bays when `create_module_bays=False`;
- directly creating or updating interfaces outside NetBox module install
  behavior;
- creating or updating legacy inventory items;
- cables, IP addresses, MAC addresses, VLANs, or BGP objects;
- virtual chassis membership;
- arbitrary inventory records that cannot be mapped to a NetBox module bay.

This follows the NetBox modules-first direction for SFP modeling. NetBox Labs'
2025 guidance, [Moving SFP Modeling from Inventory Items to Modules in
NetBox](https://netboxlabs.com/blog/sfp-modeling-modules-over-inventory-items/),
recommends moving SFP modeling away from Inventory Items and into Modules and
Module Types because modules provide proper hardware relationships and support
nested modular hardware.

## Proposed Task Interface

Proposed task signature:

```python
@Task(
    fastapi={"methods": ["PATCH"], "response_model": SyncDeviceInventoryResult},
    input=SyncDeviceInventoryInput,
)
def sync_device_inventory(
    self,
    job,
    instance=None,
    dry_run=False,
    timeout=60,
    devices=None,
    branch=None,
    process_deletions=False,
    create_module_types=False,
    create_module_bays=False,
    inventory_map: InventoryPatternMap = None,
    inventory_transform=None,
    message=None,
    **kwargs,
):
    ...
```

Notes:

- `devices`, `timeout`, `branch`, and `dry_run` should behave like the newer
  sync tasks where possible.
- `process_deletions` should default to `False`, matching the safety model from
  interface and BGP sync.
- `create_module_types` and `create_module_bays` default to `False`. They are
  explicit opt-ins so inventory sync can report missing NetBox modeling objects
  without creating them accidentally.
- `inventory_map` contains pattern-based replacement rules for translating live
  module and slot names to existing NetBox module type and module bay names. Its
  value is validated by `InventoryPatternMap`.
- `inventory_transform` is an `nf://` reference to a trusted Python file
  containing a `transform` function. The function processes one device's parsed
  inventory data before pattern replacement and built-in normalization.
- `message` should be kept in the task interface. NetBox write helpers should
  be extended where needed so pynetbox operations can pass the message through
  to NetBox changelog support.
- `**kwargs` should be passed to the Nornir job so callers can continue using
  Nornir filters such as `FL`, `FC`, platform filters, or connection options.

## NetBox Data Collection

The task should collect current NetBox device, module bay, and installed module
state before collecting live data. Module types should be resolved after live
inventory is normalized, because the required models come from live inventory.

Required NetBox data:

- devices keyed by device name;
- device manufacturer name and device type model for selecting pattern mapping
  scopes;
- module bays keyed by device name and bay name;
- installed modules keyed by device name and module bay name;
- module type lookup cache keyed by manufacturer and model or part number.

Proposed calls and behavior:

1. Resolve the NetBox API object with `_get_pynetbox(instance, branch=branch)`.
2. Resolve the target devices:
   - if `devices` is provided, use it directly;
   - if Nornir filters are provided in `kwargs`, resolve hosts from Nornir in
     the same way as `sync_device_interfaces`;
   - otherwise raise an error because callers must provide either `devices` or
     Nornir filters, matching the other sync tasks.
3. Fetch NetBox devices with `get_devices(..., cache="refresh")`.
4. Drop devices that are missing in NetBox and record an error or warning.
5. Fetch `dcim.module_bays` for the target devices.
6. Fetch `dcim.modules` for the target devices.
7. Prepare module type lookup cache. Resolve specific module types after live
   inventory is normalized.
8. Prepare lookup maps for device IDs, module bay IDs, installed module IDs,
   and module type IDs. Missing module bays can only be created later, after
   live inventory is normalized.

The task should keep lookup maps separate from normalized comparison data. This
makes the diff small and keeps NetBox object IDs out of the DeepDiff input.

## Live Data Collection

Live data should come from the Nornir service:

```python
nornir_kwargs = {**kwargs, "get": "inventory"}
if devices:
    nornir_kwargs["FL"] = devices

self.client.run_job(
    "nornir",
    "parse_ttp",
    workers="all",
    timeout=timeout,
    kwargs=nornir_kwargs,
)
```

Implementation notes:

- Preserve the Nornir worker result shape and parse failures per device.
- Treat empty or failed parser results as per-device errors, not as a signal to
  delete all NetBox modules for that device.
- Callers must provide either `devices` or Nornir filters in `**kwargs`.
- If `devices` is provided, use it as `FL` for the Nornir call.

### Expected Parser Output Shape

The TTP `inventory` getter returns data keyed by Nornir worker name, then by
host name. Each host value is a list of inventory records:

```python
{
    "nornir-worker-6": {
        "vmx-1": [
            {
                "description": "VMX",
                "module": "VMX",
                "serial": "VM6A249F9D10",
                "slot": "Chassis",
            },
            {
                "description": "Virtual FPC",
                "module": "Virtual FPC",
                "serial": "BUILTIN",
                "slot": "FPC 0",
            },
            {
                "description": "Virtual",
                "module": "Virtual",
                "serial": "BUILTIN",
                "slot": "PIC 0",
            },
            {
                "description": "",
                "module": "RIOT-LITE",
                "serial": "BUILTIN",
                "slot": "CPU",
            },
        ]
    }
}
```

Another expected parser shape is a direct list of records for IOS-XR style
inventory:

```yaml
- description: "ASR9K Route Switch Processor with 440G/slot Fabric and 6GB"
  slot: "module 0/RSP0/CPU0"
  module: "A9K-RSP440-TR"
  serial: "M9YXCZV9QF"
- description: "ASR-9006 Fan Tray V2"
  slot: "fantray 0/FT0/SP"
  module: "ASR-9006-FAN-V2"
  serial: "PDANV9GYV8H"
- description: "ASR9K Generic Fan"
  slot: "fan0 0/FT0/SP"
  module: "N/A"
  serial: ""
- description: "160G Modular Linecard, Packet Transport Optimized"
  slot: "module 0/1/CPU0"
  module: "A9K-MOD160-TR"
  serial: "94TU4CACM47Y"
- description: "ASR 9000 8-port 10GE Modular Port Adapter"
  slot: "module 0/1/0"
  module: "A9K-MPA-8X10GE"
  serial: "2ZZQVPHZCJ5"
- description: "10GBASE-LR SFP+ Module for SMF"
  slot: "module mau 0/1/0/0"
  module: "SFP-10G-LR"
  serial: "QMXQLS9GKS"
- description: "10GBASE-LR SFP+ Module for SMF"
  slot: "module mau TenGigE0/2/CPU0/0"
  module: "SFP-10G-LR"
  serial: "CB7HHMVC"
- description: "3kW AC V2 Power Module"
  slot: "power-module 0/PS0/M0/SP"
  module: "PWR-3KW-AC-V2"
  serial: "ZP7K5XBV9KE"
- description: "ASR 9006 4 Line Card Slot Chassis with V2 AC PEM"
  slot: "chassis ASR-9006"
  module: "ASR-9006"
  serial: "JCY98XR393D"
```

The task should flatten the worker-level result into a device-keyed structure
before normalization. For each inventory record:

- `slot` is the live slot name and should map to the NetBox module bay name;
- `module` is the live module model/name and should be used to resolve the
  NetBox module type;
- `description` should populate the normalized module description when present;
- `serial` should populate either the device serial for the chassis record or
  the module serial for non-chassis records.
- records with `module` equal to `N/A`, empty module values, empty serials, or
  serial value `BUILTIN` should be skipped;
- `module mau` records are interface optics or transceivers and should be
  normalized as module candidates, not inventory items.

## Normalized State

Use one normalized comparison map for both chassis serial and installed
modules. The chassis record should use `chassis` as a synthetic slot name.

The `chassis` slot participates in the same DeepDiff comparison as module
slots, but it is not a NetBox module bay and should never create, update, or
delete a NetBox module. It only drives `dcim.device.serial` updates.

Example live state:

```python
{
    "asr9k-1": {
        "chassis": {
            "slot": "chassis",
            "inventory_type": "chassis",
            "serial": "JCY98XR393D",
        },
        "module 0/RSP0/CPU0": {
            "slot": "module 0/RSP0/CPU0",
            "inventory_type": "module",
            "manufacturer": "Cisco",
            "module_type": "A9K-RSP440-TR",
            "part_number": "A9K-RSP440-TR",
            "serial": "M9YXCZV9QF",
            "description": "ASR9K Route Switch Processor with 440G/slot Fabric and 6GB",
            "status": "active",
        },
        "module 0/1/0": {
            "slot": "module 0/1/0",
            "inventory_type": "module",
            "manufacturer": "Cisco",
            "module_type": "A9K-MPA-8X10GE",
            "part_number": "A9K-MPA-8X10GE",
            "serial": "2ZZQVPHZCJ5",
            "description": "ASR 9000 8-port 10GE Modular Port Adapter",
            "status": "active",
        },
        "module mau 0/1/0/0": {
            "slot": "module mau 0/1/0/0",
            "inventory_type": "module",
            "manufacturer": "Cisco",
            "module_type": "SFP-10G-LR",
            "part_number": "SFP-10G-LR",
            "serial": "QMXQLS9GKS",
            "description": "10GBASE-LR SFP+ Module for SMF",
            "status": "active",
        }
    }
}
```

Example NetBox state:

```python
{
    "asr9k-1": {
        "chassis": {
            "slot": "chassis",
            "inventory_type": "chassis",
            "serial": "OLD123",
        },
        "module 0/RSP0/CPU0": {
            "slot": "module 0/RSP0/CPU0",
            "inventory_type": "module",
            "manufacturer": "Cisco",
            "module_type": "A9K-RSP440-TR",
            "part_number": "A9K-RSP440-TR",
            "serial": "OLDMOD123",
            "description": "ASR9K Route Switch Processor with 440G/slot Fabric and 6GB",
            "status": "active",
        }
    }
}
```

Normalization rules:

- Key all inventory records by normalized slot name.
- Always use `chassis` as the normalized slot name for the selected chassis
  record, even if the live parser reports `Chassis` or `chassis ASR-9006`.
- Add a synthetic NetBox `chassis` record only when live data contains a
  chassis candidate. This avoids treating a missing live chassis record as a
  request to clear or delete the NetBox device serial.
- Key non-chassis modules by NetBox module bay name.
- Strip whitespace from serial numbers and slot names.
- Keep serial numbers as strings.
- Do not uppercase or otherwise transform serial numbers unless the parser
  already does so.
- Ignore serial values equal to `BUILTIN`, case-insensitive. Treat these as
  empty serials for sync purposes.
- Use the parser `module` field as both `module_type` and `part_number` when no
  separate part number is available.
- Use the live manufacturer when the parser provides one. If live inventory has
  no manufacturer, use the NetBox device type manufacturer.
- Preserve prefixed slot names such as `module 0/RSP0/CPU0`,
  `fantray 0/FT0/SP`, `module mau 0/1/0/0`, and
  `power-module 0/PS0/M0/SP` as the default module bay key when no
  user-supplied mapping is provided.
- Apply user-supplied inventory mappings before building the normalized live
  state. The normalized slot key should become the NetBox module bay name, and
  the normalized module type should become the matched NetBox module type
  model.
- Treat `module mau ...` records as transceiver or optic module candidates.
  They should use the same module bay and module type flow as chassis-installed
  cards, fan trays, and power modules.
- Skip records where `module` is empty, `N/A`, or otherwise not a real module
  identity.
- Skip module records that have no usable serial after normalization, including
  records where the only serial value is `BUILTIN`. Skipped slots should be
  excluded from create, update, and delete planning so incomplete live data does
  not remove existing NetBox modules.
- Use deterministic `None` or empty string values for missing optional fields.
- Ignore live records that do not contain enough information to map to a module
  bay or identify module hardware.
- Keep ignored records in the task result for operator visibility.
- Treat the `chassis` slot as a device serial update action only. It must not
  participate in module bay creation, module type resolution, module creation,
  module update, or module deletion.
- Flatten nested hardware for the first implementation. Line cards, MPAs,
  power modules, fan trays, and transceivers should all be modeled as modules
  installed in device-level module bays using their normalized slot names.

## User-Supplied Inventory Mapping

Live inventory names frequently do not match NetBox modeling names. Examples:

- a live slot such as `module 0/RSP0/CPU0` may map to an existing NetBox module
  bay named `0/RSP0`;
- a live optic slot such as `module mau TenGigE0/2/CPU0/0` may map to a bay
  named `TenGigE0/2/CPU0/0`;
- a live module value such as `A9K-RSP440-TR` may map to a NetBox module type
  whose model is `ASR 9000 RSP440`;
- the same live module value may match a NetBox module type part number rather
  than its model.

NorFab should not embed vendor, platform, or operator-specific aliases. The
operator should supply pattern mappings at task run time or supply an `nf://`
Python transformer file. Raw parser names remain the default behavior when
neither option is provided.

### Mapping Goals

- Keep mapping policy in user space.
- Support pattern-based replacement using glob, regex, and trusted Python
  `eval` conditions.
- Scope module type patterns by NetBox manufacturer.
- Scope module bay patterns by NetBox manufacturer and device type.
- Support a custom Python transformer for cases that cannot be expressed with
  pattern conditions.
- Keep dry-run useful by showing missing mapped names before any write happens.
- Preserve raw live values in error messages so operators can fix mappings.
- Avoid adding hardcoded platform-specific transforms to the worker.

### Option 1 - Pattern-Based Replacements

Pattern replacement maps are keyed by the desired NetBox object name. Each
target contains a list of conditions that can match the live value. When a live
value matches one target, it is renamed to that target before normalization and
diff calculation.

Required shape:

```yaml
module_types:
  <manufacturer>:
    <netbox_module_type_name>:
      - glob: <glob pattern matching live module name>
      - regex: <regex pattern matching live module name>
      - eval: <Python expression with a "value" variable>

module_bays:
  <manufacturer>:
    <netbox_device_type>:
      <netbox_module_bay_name>:
        - glob: <glob pattern matching live slot name>
        - regex: <regex pattern matching live slot name>
        - eval: <Python expression with a "value" variable>
```

This is the value supplied to the task's `inventory_map` argument. It must not
contain another nested `inventory_map` key.

Example:

```yaml
module_types:
  Cisco:
    "ASR 9000 RSP440":
      - glob: "A9K-RSP440-*"
      - regex: "^A9K-RSP440-(TR|SE)$"
      - eval: "value.upper() == 'A9K-RSP440-TR'"
    "10GBASE-LR SFP+":
      - glob: "SFP-10G-LR*"
      - regex: "^SFP-10G-LR(=)?$"

module_bays:
  Cisco:
    "ASR-9006":
      "0/RSP0":
        - glob: "module 0/RSP0/*"
        - regex: "^module 0/RSP0(/CPU0)?$"
      "0/1":
        - glob: "module 0/1/CPU*"
      "TenGigE0/2/CPU0/0":
        - eval: "value == 'module mau TenGigE0/2/CPU0/0'"
```

Scoping rules:

- `module_types` first key is the NetBox manufacturer name from
  `device.device_type.manufacturer.name`;
- each module type target key is the existing NetBox module type `model`;
- conditions match the live record `module` value;
- `module_bays` first key is the NetBox manufacturer name from
  `device.device_type.manufacturer.name`;
- `module_bays` second key is the NetBox device type model from
  `device.device_type.model`;
- each module bay target key is the existing NetBox module bay `name`;
- conditions match the live record `slot` value;
- manufacturer and device type keys are exact, case-sensitive values from
  NetBox;
- if no manufacturer or device type scope exists in the mapping, no pattern
  replacement is attempted for that category and the raw live value remains
  unchanged;
- chassis records do not participate in module type or module bay replacement.

Condition rules:

- the condition list for one target uses OR logic;
- each condition item must contain exactly one of `glob`, `regex`, or `eval`;
- `glob` uses case-sensitive `fnmatch.fnmatchcase(value, pattern)`;
- `regex` uses `re.fullmatch(pattern, value)`, so partial matching must be
  written explicitly with `.*`;
- `eval` evaluates an expression with only `value` supplied as a local
  variable, and its result is converted to `bool`;
- condition order within a target does not change the outcome;
- all module type targets in the selected manufacturer scope are evaluated;
- all module bay targets in the selected manufacturer and device type scope are
  evaluated.

Resolution behavior:

1. Read device manufacturer and device type directly from the selected NetBox
   device.
2. Select `module_types[manufacturer]` for module type matching.
3. Select `module_bays[manufacturer][device_type]` for module bay matching.
4. Evaluate the live module name against every module type target.
5. Evaluate the live slot name against every module bay target.
6. If exactly one target matches, replace the live value with the target key.
7. If no target matches, leave the live value unchanged.
8. If multiple targets match, add an ambiguity error to `ret.errors` and skip
   that live record.
9. Preserve the raw live module and slot values for error and event messages.

All patterns should be validated once before processing live records:

- verify the top-level and scoped values are dictionaries;
- verify every target contains a non-empty list of conditions;
- reject condition dictionaries containing zero or multiple condition types;
- compile all regex conditions;
- compile all `eval` expressions;
- fail task input validation before NetBox writes when the mapping shape,
  regex, or expression syntax is invalid.

### Pattern Mapping Pydantic Models

Add the mapping models to
`norfab/workers/netbox_worker/netbox_models.py`. The task input should use the
model directly:

```python
class InventoryPatternCondition(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    glob: Union[StrictStr, None] = None
    regex: Union[StrictStr, None] = None
    eval_expression: Union[StrictStr, None] = Field(None, alias="eval")

    @model_validator(mode="after")
    def validate_condition(self):
        conditions = [self.glob, self.regex, self.eval_expression]
        if sum(value is not None for value in conditions) != 1:
            raise ValueError("exactly one of glob, regex, or eval is required")
        return self


InventoryPatternTargets = dict[
    StrictStr,
    list[InventoryPatternCondition],
]


class InventoryPatternMap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_types: dict[
        StrictStr,  # NetBox manufacturer name
        InventoryPatternTargets,
    ] = Field(default_factory=dict)
    module_bays: dict[
        StrictStr,  # NetBox manufacturer name
        dict[
            StrictStr,  # NetBox device type model
            InventoryPatternTargets,
        ],
    ] = Field(default_factory=dict)
```

`SyncDeviceInventoryInput.inventory_map` should be declared as:

```python
inventory_map: Union[InventoryPatternMap, None] = None
```

Additional model validation should:

- reject empty manufacturer and device type keys;
- reject empty NetBox module type and module bay target names;
- reject empty condition lists;
- compile each regex with `re.compile`;
- compile each `eval` expression with `compile(expression, "<inventory-map>",
  "eval")`;
- report the full nested Pydantic location so the operator can identify the
  invalid manufacturer, device type, target, and condition index.

Pydantic validates the payload beginning directly with `module_types` and
`module_bays`. Passing `{"inventory_map": {...}}` as the value of the
`inventory_map` field is rejected because `extra="forbid"` does not allow that
additional wrapper.

The `eval` condition is trusted executable configuration. A minimal execution
form is:

```python
matched = bool(
    eval(
        compiled_expression,
        {"__builtins__": {}},
        {"value": value},
    )
)
```

Removing builtins reduces accidental access but is not a complete security
sandbox. `eval` mappings must only be accepted from trusted operators and
should not be exposed to untrusted API users.

Application order:

- apply module type and module bay replacements after optional Python
  transformation;
- apply replacements before building `live_state`;
- use the replaced slot as the normalized key and NetBox module bay lookup
  value;
- use the replaced module name as the normalized module type model and NetBox
  module type lookup value;
- use mapped values when creating missing module bays or module types;
- include raw and mapped values in errors when they differ.

Pros:

- NetBox object names remain authoritative because they are dictionary keys;
- supports simple glob matching, precise regex matching, and custom boolean
  expressions in one shape;
- easy to inspect in dry-run output;
- avoids hardcoded vendor mappings in NorFab.

Cons:

- `eval` is trusted code and must be treated accordingly;
- broad conditions can create ambiguous matches;
- matching cannot restructure the entire parsed record;
- mappings are scoped to manufacturer and device type, so shared patterns may
  be repeated.

### Option 2 - Custom Python Parsed Data Transformer

The second option is a trusted Python file referenced with an `nf://` URL. The
worker downloads the file from the NorFab File Service and executes a function
named `transform`.

Example task input:

```yaml
inventory_transform: "nf://netbox/inventory_transformers/iosxr.py"
```

Required function contract:

```python
def transform(device_name, parsed_data, worker):
    """Return normalized parsed inventory data for one device."""
    transformed_data = []

    for record in parsed_data:
        item = dict(record)

        if item["slot"].startswith("module mau "):
            item["slot"] = item["slot"].replace("module mau ", "", 1)

        if item["module"] == "A9K-RSP440-TR":
            item["module"] = "ASR 9000 RSP440"

        transformed_data.append(item)

    return transformed_data
```

Arguments:

- `device_name`: current NetBox/Nornir device name;
- `parsed_data`: list of parsed inventory dictionaries for that device;
- `worker`: the active NetBox worker object.

The worker argument intentionally gives trusted user code access to worker
configuration and existing worker helpers. It also means the transformer is
fully trusted code and must only come from a controlled File Service location.

Loading flow:

Reuse the existing custom Python loading implementation from
`norfab/workers/nornir_worker/task_task.py`. Do not introduce another loader,
temporary module, `importlib` flow, compile wrapper, or sandbox.

The existing Nornir implementation:

1. verifies the reference starts with `nf://`;
2. downloads source text using `self.fetch_file`;
3. raises `FileNotFoundError` when `fetch_file` returns `None`;
4. executes the source with the same dictionary for globals and locals;
5. retrieves the expected function from that dictionary.

The inventory transformer should use the same code pattern, changing only the
argument name, error description, and exported function name:

```python
if inventory_transform.startswith("nf://"):
    function_text = self.fetch_file(inventory_transform)
    if function_text is None:
        raise FileNotFoundError(
            f"{self.name} - '{inventory_transform}' "
            "inventory transformer download failed"
        )

    globals_dict = {}
    exec(function_text, globals_dict, globals_dict)
    transform_function = globals_dict["transform"]
else:
    raise RuntimeError(
        f"{self.name} - '{inventory_transform}' inventory transformer "
        "should be an nf:// file reference"
    )
```

Load `transform_function` once per task, then call it once for each device after
parsed data is collected. Missing `transform` follows the same dictionary-key
failure behavior as a missing `task` function in the existing Nornir loader.

Return contract:

- return a `list[dict]`;
- each dictionary must contain `description`, `slot`, `module`, and `serial`;
- each value must be a string or `None`;
- returning an empty list means the device has no usable parsed inventory;
- the function may rename, remove, add, split, or combine records;
- the function must not perform NetBox writes; reconciliation remains owned by
  `sync_device_inventory`.

Execution order:

```text
parse_ttp per-device records
  -> optional Python transform(device_name, parsed_data, worker)
  -> optional pattern-based replacements
  -> built-in normalization and validation
  -> make_diff
  -> NetBox preflight validation and writes
```

If both options are supplied, the transformer runs first and pattern
replacements run against the transformed `module` and `slot` values.

Error handling:

- invalid URL, download, source execution, or missing `transform` errors fail
  the task before any NetBox writes;
- a transformer exception for one device adds an error and skips that device;
- an invalid return type adds an error and skips that device;
- invalid returned records add errors and are skipped;
- raw parser data should remain available for logging when transformed data
  fails validation.

Security:

- the transformer is arbitrary Python code;
- passing the worker object provides broad access to worker state and methods;
- only trusted users should be allowed to select transformer files;
- File Service permissions and task authorization are the security boundary;
- this option should not attempt to sandbox Python execution.

Pros:

- can implement any platform-specific normalization logic;
- has access to the complete per-device record list;
- can use worker configuration and helpers when necessary;
- keeps custom policy outside NorFab source code.

Cons:

- executes arbitrary trusted Python;
- behavior is less visible than declarative patterns;
- malformed code can affect the worker process;
- requires separate unit testing of the transformer file.

### Recommended Implementation

Implement only the two options described above:

1. `inventory_map` for manufacturer-scoped module type patterns and
   manufacturer/device-type scoped module bay patterns;
2. `inventory_transform` for an `nf://` Python file with a `transform`
   function.

Recommended processing order:

1. Validate `inventory_map` with `InventoryPatternMap`, then compile regex and
   `eval` conditions.
2. Download and load `inventory_transform` once using the exact
   `task_task.py` `self.fetch_file` and `exec` pattern.
3. Collect per-device parsed inventory through Nornir `parse_ttp`.
4. Call `transform(device_name, parsed_data, worker)` when supplied.
5. Validate transformed records.
6. Apply module type and module bay pattern replacements.
7. Build normalized live state.
8. Calculate the diff and perform existing NetBox preflight/write logic.

The two options can be used independently or together. When both are supplied,
the Python transformer runs first and pattern replacements run second.

The implementation should remain linear:

- one block to prepare pattern conditions;
- one block to download and load the transformer;
- one transformer call per device;
- one module type matcher and one module bay matcher while iterating records;
- no additional extension framework.

Dry-run and errors should expose mappings clearly:

- use mapped names in the normalized diff;
- include raw and mapped names in ambiguity and missing-object errors;
- report transformer URL, download, source execution, and return-shape errors;
- perform no NetBox writes if input preparation fails.

## Chassis Detection

The parser output may vary by platform, so chassis detection should be tolerant.

Suggested chassis detection signals:

- an explicit role or type equal to `chassis`;
- a slot equal to `chassis`, case-insensitive, as shown by the current
  inventory parser output;
- a slot starting with `chassis `, case-insensitive, as shown by IOS-XR style
  inventory output such as `chassis ASR-9006`;
- a platform-specific inventory record that represents the base device rather
  than an installed module;
- a record with a serial number and device model but no module slot, when there
  is no better chassis candidate.

If multiple chassis candidates are found, the task should raise a per-device
error and skip that device's inventory sync. A future implementation can add
platform-specific refinements if needed.

## Diff Strategy

Use the existing worker helper:

```python
inventory_diff = self.make_diff(live_inventory_state, netbox_inventory_state)
```

By convention:

- live data is the desired source state;
- NetBox data is the current target state;
- objects present only in live data become `create`;
- objects present only in NetBox become `delete`;
- field differences become `update`;
- equal objects become `in_sync`.

The dry-run response should expose the combined inventory diff without applying
changes. Action execution should route the `chassis` slot to device serial
updates and all other slots to module reconciliation.

Skipped incomplete live slots must be tracked separately. If NetBox has a
module in a skipped slot, the task should suppress the delete action for that
slot because the live record proved the slot exists but did not contain enough
data to sync safely.

## Action Planning Model

Dry-run result shape should be easy to inspect:

```python
{
    "asr9k-1": {
        "inventory": {
            "create": ["module 0/1/0", "module mau 0/1/0/0"],
            "update": {
                "chassis": {
                    "serial": {
                        "old_value": "OLD123",
                        "new_value": "JCY98XR393D",
                    }
                },
                "module 0/RSP0/CPU0": {
                    "serial": {
                        "old_value": "OLDMOD123",
                        "new_value": "M9YXCZV9QF",
                    },
                }
            },
            "delete": ["fantray 0/FT0/SP"],
            "in_sync": [],
        },
        "missing_module_bays": [],
        "ignored": [],
    }
}
```

Live-run result shape should report applied actions:

```python
{
    "asr9k-1": {
        "inventory": {
            "created": ["module 0/1/0", "module mau 0/1/0/0"],
            "updated": ["chassis", "module 0/RSP0/CPU0"],
            "deleted": [],
            "in_sync": [],
            "delete_skipped": ["fantray 0/FT0/SP"],
        },
        "missing_module_bays": [],
        "ignored": [],
    }
}
```

`ret.diff` should contain the complete normalized diff for devices that are not
fully in sync.

In these result shapes, `chassis` means "NetBox device serial was changed" or
"NetBox device serial would change". It does not refer to a NetBox module.

## Create Rules

Create a NetBox module when:

- the live module exists;
- the normalized slot is not `chassis`;
- the live module has a usable serial after normalization;
- the matching NetBox module bay exists, or can be created because
  `create_module_bays=True`;
- no NetBox module is installed in that bay;
- the module type can be resolved or created.

Required create payload fields:

- `device`;
- `module_bay`;
- `module_type`;
- `status`;
- `serial` when present.

Optional create payload fields:

- `description`;
- custom fields, only if future parser data and project conventions justify
  them.

If the module bay is missing and `create_module_bays=False`, the task should
not create the module. It should report the missing bay and continue.

## Module Bay Creation

When `create_module_bays=True`, the task should create missing module bays for
live records that are in scope for module sync.

Module bay create payload:

- `device`;
- `name`, using the normalized live `slot` value;
- `label`, using the same value as `name`;
- `position`, only if the live slot can be parsed safely and NetBox accepts it.

Module bay creation rules:

- Create bays only for records that are not chassis records and not ignored.
- Create bays only for records with a usable serial after normalization.
- Preserve the live slot string by default, for example `module 0/RSP0/CPU0`,
  `fantray 0/FT0/SP`, `module mau 0/1/0/0`, or
  `power-module 0/PS0/M0/SP`.
- Create module bays for transceiver records such as `module mau ...` when
  `create_module_bays=True` and the record has a usable serial.
- Do not create module bays for records with no usable module identity.
- Create module bays before module type resolution and module creation.
- Include created bays in the task result so operators can see that NetBox
  modeling was extended.

## Update Rules

Update a NetBox module when:

- the normalized slot is not `chassis`;
- the live module has a usable serial after normalization;
- the live module maps to an existing NetBox module by device and bay;
- one or more managed fields differ.

Managed fields should include:

- `serial`;
- `module_type`;
- `status`;
- `description`.

The update payload should include the NetBox module ID and only the fields that
changed.

The task should not clear a NetBox module serial number when the live parser
returns an empty serial. Empty live serials, including `BUILTIN`, should cause
the live record to be skipped and reported as ignored or incomplete data.

## Delete Rules

Delete a NetBox module when:

- the normalized slot is not `chassis`;
- a module exists in NetBox;
- the module's bay is in scope for the target device;
- the live inventory does not contain a module for that bay;
- the live parser did not return a skipped incomplete record for that bay;
- `process_deletions=True`.

When `process_deletions=False`, the task should report planned deletes as
`delete_skipped` or leave them in the dry-run diff, but it should not delete
anything.

Deletes should run after creates and updates.

## Device Serial Rules

Update a NetBox device serial when:

- the combined inventory diff contains an `update` for the `chassis` slot
  serial;
- the NetBox device exists;
- the live serial differs from `dcim.device.serial`.

Do not update the NetBox device serial when:

- the live chassis serial is empty;
- no chassis record can be identified;
- multiple chassis records exist. This is a per-device error.

The task should report skipped serial updates clearly, because chassis serial
sync is one of its main behaviors.

The `chassis` slot is synthetic comparison data. It must not trigger module bay
creation, module type resolution, module creation, module update, or module
deletion.

## Module Type Resolution

Before creating or updating a module, the task must resolve a NetBox
`dcim.module_type`.

Suggested lookup keys:

- manufacturer plus model, where manufacturer comes from live data or falls
  back to the NetBox device type manufacturer;
- manufacturer plus part number, using the same manufacturer rule;
- model alone only as a fallback when it is unique.

If a module type is missing:

- with `create_module_types=False`, skip the module create/update and record an
  error;
- with `create_module_types=True`, create a minimal module type and then create
  or update the installed module.

When creating module types and the live parser does not provide manufacturer,
use the NetBox device type manufacturer. If the device manufacturer cannot be
resolved, record an error and skip module type creation for that record.

For transceivers, the live `module` value, for example `SFP-10G-LR`, should be
used as the module type model and part number when no more specific fields are
available. The task should not create interface templates automatically; those
belong to NetBox modeling policy and can be pre-created on module types or
added by a later, dedicated enhancement.

Minimal module type creation should include only the resolved manufacturer,
model, and part number. Interface templates, profiles, and custom fields are
outside this task's first implementation.

## Execution Order

1. Resolve target devices.
2. Fetch NetBox devices, module bays, installed modules, and prepare the module
   type lookup cache.
3. Fetch live inventory from Nornir for the full resolved device set in one
   collection request.
4. Normalize live and NetBox inventory state, including the synthetic `chassis`
   slot.
5. Build the combined inventory diff with `self.make_diff`.
6. Return the action plan immediately when `dry_run=True`.
7. Update device serial numbers from `chassis` slot updates.
8. Create missing module bays when `create_module_bays=True`.
9. Resolve required module types, creating missing ones only when
   `create_module_types=True`.
10. Create missing modules.
11. Update changed modules.
12. Delete stale modules only when `process_deletions=True`.
13. Return applied actions and full diff.

## Error Handling

The task should continue per device where possible.

Expected non-fatal errors:

- device exists in Nornir but not NetBox;
- Nornir parser failed for one device;
- live inventory is empty for one device;
- no chassis serial found;
- multiple chassis records found for one device;
- module bay missing in NetBox and `create_module_bays=False`;
- module type missing and `create_module_types=False`;
- device manufacturer cannot be resolved for missing module type creation;
- NetBox create, update, or delete failure for a single module.

Fatal errors:

- no target devices resolved;
- NetBox API initialization failure;
- Nornir service call failure that prevents all live data collection.

## Branching, Caching, and Messages

- Use `_get_pynetbox(instance, branch=branch)` for all NetBox access.
- Pass `branch` into existing helper calls where they support it.
- Use `cache="refresh"` for NetBox device and inventory collection, because
  this task is expected to compare against current NetBox state.
- If `message` is provided, pass it to NetBox write operations. Add or extend
  pynetbox integration support where needed so device updates, module bay
  creates, module type creates, module creates, module updates, and module
  deletes can include the message.

## CLI and API Model Updates

Future implementation should add:

- `InventoryPatternCondition`;
- `InventoryPatternMap`;
- `SyncDeviceInventoryInput`;
- `SyncDeviceInventoryResult`;
- FastAPI task registration for `sync_device_inventory`;
- CLI shell update in
  `norfab/clients/nfcli_shell/netbox/netbox_picle_shell_sync_device.py`.

The CLI path uses the name `netbox sync device-inventory` and calls
`sync_device_inventory` with `SyncDeviceInventoryInput`.

## Dry-run Behavior

When `dry_run=True`, the task should:

- collect NetBox data;
- collect live data;
- normalize both states;
- build the combined inventory diff;
- return the action plan;
- not write to NetBox.

Dry-run output should include enough data to answer:

- which device serials would change;
- which modules, including transceivers, would be created;
- which modules, including transceivers, would be updated;
- which modules, including transceivers, would be deleted if deletion
  processing were enabled;
- which live inventory records were ignored;
- which live inventory records were skipped because serial was empty or
  `BUILTIN`;
- which module bays or module types are missing.

## Testing Plan

Update `tests/test_netbox_service.py` with a new
`TestSyncDeviceInventory` group.

Suggested tests:

1. dry-run reports device serial update from chassis record;
2. live run updates NetBox device serial;
3. no serial update when chassis serial is missing;
4. module create in an existing module bay;
5. module update when serial changes;
6. module update when module type changes;
7. module delete is skipped by default;
8. module delete runs when `process_deletions=True`;
9. missing module bay is reported and skipped when `create_module_bays=False`;
10. missing module bay is created when `create_module_bays=True`;
11. missing module type is reported when `create_module_types=False`;
12. missing module type is created when `create_module_types=True`;
13. transceiver record such as `module mau 0/1/0/0` creates or updates a
    NetBox module;
14. transceiver module bay is created when `create_module_bays=True`;
15. transceiver module type is created when `create_module_types=True`;
16. transceiver module bay uses the raw parser slot name;
17. `BUILTIN` serial is ignored and the record is skipped;
18. empty serial record is skipped;
19. module description is updated from live inventory;
20. module type creation uses the device manufacturer when live manufacturer is
    missing;
21. nested hardware is flattened into device-level module bays;
22. multiple chassis records produce a per-device error;
23. parser failure for one device does not stop all devices;
24. second run after successful sync reports in-sync;
25. branch argument is passed through to NetBox access;
26. message argument is passed to pynetbox write operations;
27. CLI command calls `sync_device_inventory`;
28. `sync_device_inventory` is the only device inventory synchronization task
    exposed;
29. module type glob condition maps a live module name to a NetBox module type;
30. module type regex condition maps a live module name to a NetBox module type;
31. module type `eval` condition maps a live module name to a NetBox module
    type;
32. module bay glob condition maps a live slot name to a NetBox module bay;
33. module bay regex condition maps a live slot name to a NetBox module bay;
34. module bay `eval` condition maps a live slot name to a NetBox module bay;
35. module type conditions use the NetBox device manufacturer scope;
36. module bay conditions use the NetBox device manufacturer and device type
    scope;
37. multiple matching targets produce an ambiguity error and skip the record;
38. unmatched values remain unchanged;
39. invalid mapping shape, regex, or `eval` syntax fails before NetBox writes;
40. a nested `inventory_map` wrapper is rejected by Pydantic validation;
41. mapped module bay names are used when `create_module_bays=True`;
42. mapped module type names are used when `create_module_types=True`;
43. errors include both raw and mapped values when they differ;
44. transformer file downloads through `self.fetch_file`;
45. transformer file must contain a callable named `transform`;
46. transformer receives device name, per-device parsed data, and worker;
47. transformer output is validated as a list of parser-shaped dictionaries;
48. transformer can rename, split, remove, or add records;
49. transformer failure skips only the affected device after preparation;
50. transformer URL, download, source execution, or missing function failure
    occurs before NetBox writes;
51. when both options are used, transformer runs before pattern replacement.

Test fixtures should mirror the interface sync tests by mocking Nornir
`parse_ttp` inventory results.

## Documentation Updates

Future implementation should update:

- `docs/workers/netbox/services_netbox_service_tasks_sync_device_inventory.md`;
- `mkdocs.yml`;
- CLI command examples for `netbox sync device-inventory`.

The documentation should clearly state that chassis serial updates the NetBox
device serial, while non-chassis inventory records, including transceivers and
optics, are reconciled as NetBox modules. The task should not create or update
legacy inventory items.

## Planned File Changes

Implementation should be limited to:

- `norfab/workers/netbox_worker/devices_tasks.py`;
- `norfab/workers/netbox_worker/netbox_models.py`;
- `norfab/workers/netbox_worker/netbox_worker.py`, if shared pynetbox message
  handling needs to be extended;
- `norfab/clients/nfcli_shell/netbox/netbox_picle_shell_sync_device.py`;
- `tests/test_netbox_service.py`;
- NetBox worker documentation under `docs/workers/netbox/`;
- `mkdocs.yml`, if documentation navigation changes.

This ADR file is the only file created during planning.

## Resolved Decisions

1. New task name is `sync_device_inventory`.
2. Live data source is Nornir `parse_ttp` with `get="inventory"`.
3. Chassis serial number updates `dcim.device.serial`.
4. Installed modules are reconciled as NetBox `dcim.modules`.
5. Existing NetBox module bays are the default mapping boundary.
6. Missing module bays can be created when `create_module_bays=True`.
7. Missing module types can be created when `create_module_types=True`.
8. `create_module_bays` defaults to `False`.
9. `create_module_types` defaults to `False`.
10. Module types created by the task use the NetBox device manufacturer when
    live inventory does not provide manufacturer.
11. Transceiver module bay names use raw parser slot names such as
    `module mau 0/1/0/0` by default, or mapped names when `inventory_map` or
    `inventory_transform` is supplied.
12. Nested hardware is flattened into device-level module bays.
13. Serial value `BUILTIN` is ignored.
14. Live module records with no usable serial are skipped.
15. Module descriptions are updated from live inventory.
16. Multiple chassis records produce a per-device error.
17. Device serial synchronization is handled by `sync_device_inventory`.
18. Callers must provide `devices` or Nornir filters.
19. `message` remains in the task interface and should be implemented for the
    pynetbox write operations used by this task.
20. The task should compare normalized live and NetBox state with
   `self.make_diff`.
21. Deletions are disabled by default.
22. Dry-run should return a complete action plan.
23. Raw live names are used by default when no user mapping is supplied.
24. Naming mismatches between live inventory and NetBox should be solved with
    user-supplied mapping input, not hardcoded NorFab platform alias tables.
25. Only two user-space normalization options are supported: pattern-based
    replacement and a custom Python parsed-data transformer.
26. Pattern replacement is scoped by NetBox manufacturer for module types and
    by NetBox manufacturer plus device type for module bays.
27. Pattern conditions support `glob`, `regex`, and trusted Python `eval`.
28. Pattern target keys are the NetBox module type model or module bay name to
    assign when a condition matches.
29. The custom transformer is loaded from an `nf://` file using
    `self.fetch_file`.
30. The transformer file must expose
    `transform(device_name, parsed_data, worker)`.
31. When both options are supplied, the transformer runs before pattern
    replacement.
32. `InventoryPatternMap` validates the pattern mapping input.
33. The value of `inventory_map` begins directly with `module_types` and
    `module_bays`; an additional nested `inventory_map` key is invalid.

## Review Questions

No open mapping design questions remain. Implementation should follow the two
options and execution order documented above.
