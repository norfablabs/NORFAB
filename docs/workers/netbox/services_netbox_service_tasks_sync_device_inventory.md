---
tags:
  - netbox
---

# Netbox Sync Device Inventory Task

> task api name: `sync_device_inventory`

The `sync_device_inventory` task reconciles live hardware inventory collected
from the Nornir service with NetBox device and module data.

Live inventory is collected with Nornir `parse_ttp` using `get="inventory"`.
The chassis inventory record updates `dcim.device.serial`. Non-chassis
inventory records, including optics and transceivers, are managed as NetBox
`dcim.modules` installed in device-level `dcim.module_bays`.

## Parsed Inventory Records

The Nornir inventory parser and optional inventory transformer must return one
list of records per device. Every record has exactly these fields:

```yaml
- description: "ASR9K Route Switch Processor with 440G/slot Fabric and 6GB"
  slot: "module 0/RSP0/CPU0"
  module: "A9K-RSP440-TR"
  serial: "M9YXCZV9QF"
```

Each field value must be a string or `null`.

### Device Serial Number

A record whose trimmed `slot` value is `chassis`, case-insensitive, is the device chassis record:

```yaml
- description: "Cisco ASR 9006 Router"
  slot: "chassis"
  module: "ASR-9006"
  serial: "JCY98XR393D"
```

For this record, the task:

1. reads `serial` as the desired NetBox `dcim.device.serial`;
2. creates a synthetic `chassis` entry in the inventory diff;
3. updates the NetBox device serial when the live and NetBox values differ;
4. does not create a module bay, module type, or installed module for it.

The chassis `module` and `description` values do not participate in the device
serial comparison. An empty or `BUILTIN` chassis serial is ignored. Multiple
chassis records with different non-empty serial numbers produce a per-device
error and that device is skipped.

## Creation and Deletion Behavior

**Module creation** — Missing module bays and module types are reported by default. Set
`create_module_bays=True` or `create_module_types=True` when the task should
extend NetBox modeling from live inventory.

**Module deletions** — Module deletions are disabled by default. Set `process_deletions=True` to
delete NetBox modules that are absent from live network inventory.

**Invalid records** — Live records with empty module identity, empty serial numbers, or `BUILTIN`
serial numbers are skipped and reported in `res["errors"]`. Skipped slots
suppress deletion so incomplete live data does not remove existing NetBox
modules.

## Filtering Modules

The task can select or exclude modules using lists of case-sensitive glob
patterns:

- `filter_by_module`: include normalized module type names matching any pattern.
- `filter_by_slot`: include normalized module bay names matching any pattern.
- `ignore_modules`: exclude normalized module type names matching any pattern.
- `ignore_slots`: exclude normalized module bay names matching any pattern.

Filters run after the optional Python transformer, inventory name mapping, and
built-in live-data normalization. A pattern therefore matches the final
`module_type` and `slot` values used for NetBox comparison, not necessarily the
raw parser values.

Patterns within one argument use OR logic. When both include filters are
provided, a module must match both dimensions. Ignore patterns take precedence:
a match in either ignore list excludes the module.

The chassis record is never filtered, so device serial synchronization remains
independent from module selection. The same comparison scope is applied to
existing NetBox modules. A live slot excluded by a filter is also excluded from
the NetBox side, preventing it from being treated as stale when
`process_deletions=True`.

Example:

```yaml
filter_by_module:
  - "A9K-*"
  - "SFP-10G-*"
filter_by_slot:
  - "module 0/*"
ignore_modules:
  - "*-BUILTIN"
ignore_slots:
  - "module 0/PS*"
```

## Inventory Name Mapping

Use `inventory_map` when live module or slot names differ from existing NetBox
module type models and module bay names. Supply either an inline mapping or an
`nf://` reference to a YAML file available through the NorFab File Service.
The mapping is applied after an optional Python transformer and before
inventory normalization and diff calculation.

```yaml
module_types:
  Cisco:
    "ASR 9000 RSP440":
      - glob: "A9K-RSP440-*"
    "10GBASE-LR SFP+":
      - regex: "^SFP-10G-LR(=)?$"
    "ASR 9000 Fan Tray":
      - eval: "value == 'ASR-9006-FAN-V2'"

module_bays:
  Cisco:
    "ASR-9006":
      "0/RSP0":
        - glob: "module 0/RSP0/*"
      "0/1":
        - regex: "^module 0/1(/CPU0)?$"
      "TenGigE0/2/CPU0/0":
        - eval: "value == 'module mau TenGigE0/2/CPU0/0'"
```

File reference example:

```yaml
inventory_map: "nf://netbox/inventory_maps/iosxr.yaml"
```

The downloaded YAML is parsed with `yaml.safe_load` and validated with the
same Pydantic model used for inline mappings. Invalid YAML, invalid mapping
conditions, and missing files fail the task before any NetBox writes.

### Mapping Scope

- `module_types` is selected using the exact, case-sensitive NetBox device
  manufacturer `name`.
- A module type target key is the desired NetBox module type `model`.
- Module type conditions test the live record's `module` value.
- `module_bays` is selected using the exact NetBox manufacturer name followed
  by the exact NetBox device type `model`.
- A module bay target key is the desired NetBox module bay `name`.
- Module bay conditions test the live record's `slot` value.
- Chassis records are not mapped.

Each condition contains exactly one matcher:

- `glob` uses case-sensitive glob matching.
- `regex` performs a full regular-expression match.
- `eval` evaluates trusted Python configuration with the live string available
  as `value`.

Conditions under one target use OR logic. If one target matches, its key
replaces the live value. If nothing matches, the original value is retained.
If multiple targets match, the record is skipped and the ambiguity is added to
`res["errors"]`.

!!! warning
    `eval` is trusted executable configuration, not a security sandbox. Only
    accept inventory mappings from trusted sources.

## Python Inventory Transformer

Use `inventory_transform` for normalization that cannot be expressed with
pattern mappings. Its value is an `nf://` reference to a Python file available
through the NorFab File Service:

```yaml
inventory_transform: "nf://netbox/inventory_transformers/iosxr.py"
```

The file must export a function named `transform` with this contract:

```python

def transform(
    device_name: str,
    parsed_data: list,
    worker: object,
    device_platform: str | None = None,
    device_manufacturer: str | None = None,
    device_type: str | None = None,
) -> list[dict]:
    """Normalize parsed inventory records for one device."""
    transformed_data = []

    for record in parsed_data:
        slot = record["slot"]

        if slot.startswith("module mau "):
            record["slot"] = slot.removeprefix("module mau ")

        if (
            device_manufacturer == "Cisco"
            and device_type == "ASR-9006"
            and record["module"] == "A9K-RSP440-TR"
        ):
            record["module"] = "ASR 9000 RSP440"

        transformed_data.append(record)

    return transformed_data
```

The arguments are:

- `device_name`: current NetBox and Nornir device name.
- `parsed_data`: parsed records for that device, list of dictionaries with `slot`, `serial`, `description`, `module` keys.
- `worker`: active NetBox worker object, including its configuration and
  all worker helper methods.
- `device_platform`: NetBox device platform `name`, or `None` when no platform
  is assigned.
- `device_manufacturer`: NetBox device type manufacturer `name`.
- `device_type`: NetBox device type `model`.

The return value must be a list of dictionaries. Every dictionary must contain
exactly `description`, `slot`, `module`, and `serial`, with each value set to a
string or `None`. Returning an empty list means there is no usable inventory
for that device. Invalid output or an exception skips that device and records
the validation or execution error in result's `errors`.

The transformer is loaded once per task and called once per device. It runs
before `inventory_map`, so pattern conditions test the transformed `module`
and `slot` values. The device metadata arguments are read from NetBox before
the transformer runs, so they describe the current NetBox device, not the live
inventory record.

!!! warning
    Transformer files are executed as trusted Python code. Store them only in
    controlled File Service locations.

## Result Structure

**Dry-run mode** (`dry_run=True`) returns the raw diff without writing to
NetBox:

```json
{
    "<device>": {
        "create": ["module 0/RSP0/CPU0", "module mau 0/1/0/0"],
        "update": {
            "chassis": {
                "serial": {"old_value": "OLD123", "new_value": "JCY98XR393D"}
            }
        },
        "delete": ["module stale"],
        "in_sync": []
    }
}
```

**With Review** — Pass `with_review=True` to use interactive NFCLI workflow. Sync task displays its preview, and waits for approval before applying changes. Declining at that point will return dry-run result.

!!! note
    
    When both `dry-run` and `with_review` are `True`, `dry-run` logic ignored.

**Live-run mode** (`dry_run=False`, default) applies changes and returns a per-device action summary:

```json
{
    "<device>": {
        "created": [
            "Cisco A9K-RSP440-TR",
            "Cisco SFP-10G-LR",
            "module 0/RSP0/CPU0",
            "module mau 0/1/0/0"
        ],
        "updated": ["chassis"],
        "deleted": [],
        "in_sync": []
    }
}
```

The `created` list includes created module bays, module types, and installed
modules. In live-run mode `res["diff"]` is also populated with the raw diff.
Missing module bays, missing module types, failed writes, and ignored live
records are reported in `res["errors"]`.

## Branching Support

This task is branch aware and can push updates to a NetBox branch when the
NetBox Branching plugin is installed. Use the `branch` argument to target a
branch.

## Examples

=== "NFCLI"

    Preview chassis serial and module changes for one device:

    ```
    nf#netbox sync device-inventory devices iosxr1 dry-run
    ```

    Sync a device using only existing NetBox module bays and module types:

    ```
    nf#netbox sync device-inventory devices iosxr1
    ```

    Create missing module bays from live slot names, but require module types
    to already exist:

    ```
    nf#netbox sync device-inventory devices iosxr1 create-module-bays
    ```

    Create missing module bays and module types, then install modules:

    ```
    nf#netbox sync device-inventory devices iosxr1 create-module-bays create-module-types
    ```

    Sync multiple devices:

    ```
    nf#netbox sync device-inventory devices iosxr1 iosxr2 create-module-bays create-module-types
    ```

    Delete stale NetBox modules that are absent from live inventory:

    ```
    nf#netbox sync device-inventory devices iosxr1 create-module-bays create-module-types process-deletions
    ```

    Sync into a NetBox branch:

    ```
    nf#netbox sync device-inventory devices iosxr1 branch inventory-sync-branch create-module-bays create-module-types
    ```

    Add a NetBox changelog message to write operations:

    ```
    nf#netbox sync device-inventory devices iosxr1 message "sync inventory from live device" create-module-bays create-module-types
    ```

    Use Nornir host filters instead of explicit device names:

    ```
    nf#netbox sync device-inventory FC iosxr create-module-bays create-module-types
    ```

    Target a specific NetBox worker and keep detailed output:

    ```
    nf#netbox sync device-inventory workers netbox-worker-1 devices iosxr1 verbose-result
    ```

    Normalize parsed inventory with a Python transformer:

    ```
    nf#netbox sync device-inventory devices iosxr1 inventory-transform nf://netbox/inventory_transformers/iosxr.py dry-run
    ```

    Load inventory mappings from a YAML file:

    ```
    nf#netbox sync device-inventory devices iosxr1 inventory-map nf://netbox/inventory_maps/iosxr.yaml dry-run
    ```

    Sync only RSP and line-card modules in slots below `module 0`:

    ```
    nf#netbox sync device-inventory devices iosxr1 filter-by-module "A9K-RSP*" "A9K-MOD*" filter-by-slot "module 0/*" dry-run
    ```

    Ignore optics and power-module slots:

    ```
    nf#netbox sync device-inventory devices iosxr1 ignore-modules "SFP-*" ignore-slots "power-module *" dry-run
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    nf = NorFab(inventory="./inventory.yaml")
    nf.start()
    client = nf.make_client()

    # dry run - preview raw create/update/delete/in_sync diff
    result = client.run_job(
        "netbox",
        "sync_device_inventory",
        workers="any",
        kwargs={
            "devices": ["iosxr1"],
            "dry_run": True,
        },
    )

    # sync using existing NetBox module bays and module types only
    result = client.run_job(
        "netbox",
        "sync_device_inventory",
        workers="any",
        kwargs={
            "devices": ["iosxr1"],
        },
    )

    # create missing module bays from live inventory slot names
    result = client.run_job(
        "netbox",
        "sync_device_inventory",
        workers="any",
        kwargs={
            "devices": ["iosxr1"],
            "create_module_bays": True,
        },
    )

    # create missing module bays and module types, then install modules
    result = client.run_job(
        "netbox",
        "sync_device_inventory",
        workers="any",
        kwargs={
            "devices": ["iosxr1"],
            "create_module_bays": True,
            "create_module_types": True,
        },
    )

    # sync multiple devices
    result = client.run_job(
        "netbox",
        "sync_device_inventory",
        workers="any",
        kwargs={
            "devices": ["iosxr1", "iosxr2"],
            "create_module_bays": True,
            "create_module_types": True,
        },
    )

    # delete stale NetBox modules absent from live inventory
    result = client.run_job(
        "netbox",
        "sync_device_inventory",
        workers="any",
        kwargs={
            "devices": ["iosxr1"],
            "create_module_bays": True,
            "create_module_types": True,
            "process_deletions": True,
        },
    )

    # sync into a NetBox branch and attach a changelog message
    result = client.run_job(
        "netbox",
        "sync_device_inventory",
        workers="any",
        kwargs={
            "devices": ["iosxr1"],
            "branch": "inventory-sync-branch",
            "message": "sync inventory from live device",
            "create_module_bays": True,
            "create_module_types": True,
        },
    )

    # use Nornir host filters instead of explicit device names
    result = client.run_job(
        "netbox",
        "sync_device_inventory",
        workers="any",
        kwargs={
            "FC": "iosxr",
            "create_module_bays": True,
            "create_module_types": True,
        },
    )

    # filter and ignore normalized module type and slot names
    result = client.run_job(
        "netbox",
        "sync_device_inventory",
        workers="any",
        kwargs={
            "devices": ["iosxr1"],
            "filter_by_module": ["A9K-RSP*", "A9K-MOD*"],
            "filter_by_slot": ["module 0/*"],
            "ignore_modules": ["*-BUILTIN"],
            "ignore_slots": ["module 0/PS*"],
            "dry_run": True,
        },
    )

    # map live module and slot names to existing NetBox names
    inventory_map = {
        "module_types": {
            "Cisco": {
                "ASR 9000 RSP440": [
                    {"glob": "A9K-RSP440-*"},
                ],
                "10GBASE-LR SFP+": [
                    {"regex": r"^SFP-10G-LR(=)?$"},
                ],
            },
        },
        "module_bays": {
            "Cisco": {
                "ASR-9006": {
                    "0/RSP0": [
                        {"glob": "module 0/RSP0/*"},
                    ],
                    "TenGigE0/2/CPU0/0": [
                        {
                            "eval": (
                                "value == "
                                "'module mau TenGigE0/2/CPU0/0'"
                            )
                        },
                    ],
                },
            },
        },
    }
    result = client.run_job(
        "netbox",
        "sync_device_inventory",
        workers="any",
        kwargs={
            "devices": ["iosxr1"],
            "inventory_map": inventory_map,
            "dry_run": True,
        },
    )

    # load the same mapping structure from the NorFab File Service
    result = client.run_job(
        "netbox",
        "sync_device_inventory",
        workers="any",
        kwargs={
            "devices": ["iosxr1"],
            "inventory_map": "nf://netbox/inventory_maps/iosxr.yaml",
            "dry_run": True,
        },
    )

    # run a transformer, then apply mappings to its returned records
    result = client.run_job(
        "netbox",
        "sync_device_inventory",
        workers="any",
        kwargs={
            "devices": ["iosxr1"],
            "inventory_transform": (
                "nf://netbox/inventory_transformers/iosxr.py"
            ),
            "inventory_map": inventory_map,
            "dry_run": True,
        },
    )

    nf.destroy()
    ```

Inline `inventory_map` data is most conveniently supplied through the Python
API or workflow task `kwargs`. NFCLI supports the file-backed `inventory-map`
and `inventory-transform` references shown above.

## NORFAB Netbox Sync Device Inventory Command Shell Reference

NorFab shell supports these command options for the NetBox
`sync_device_inventory` task:

```
nf# man tree netbox.sync.device-inventory
root
└── netbox:    Netbox service
    └── sync:    Sync Netbox data
        └── device-inventory:    Sync device inventory facts e.g. serial number
            ├── timeout:    Job timeout
            ├── workers:    Filter worker to target, default 'any'
            ├── verbose-result:    Control output details, default 'False'
            ├── nowait:    Do not wait for job to complete, default 'False'
            ├── instance:    Netbox instance name to target
            ├── dry-run:    Do not commit to database
            ├── branch:    NetBox branching plugin branch name to use
            ├── devices:    List of NetBox devices to sync inventory for
            ├── process-deletions:    Delete NetBox modules present in module bays but absent from live inventory
            ├── create-module-types:    Create missing NetBox module types from live inventory model data
            ├── create-module-bays:    Create missing NetBox module bays using the live inventory slot names
            ├── inventory-map:    Pattern mappings or nf:// YAML file reference
            ├── inventory-transform:    nf:// Python transformer file containing a transform function
            ├── filter-by-module:    Glob patterns selecting normalized module type names
            ├── filter-by-slot:    Glob patterns selecting normalized module bay names
            ├── ignore-modules:    Glob patterns excluding normalized module type names
            ├── ignore-slots:    Glob patterns excluding normalized module bay names
            ├── message:    Changelog message recorded on NetBox writes
            ├── FO:    Filter hosts using Filter Object
            ├── FB:    Filter hosts by name using Glob Patterns
            ├── FH:    Filter hosts by hostname
            ├── FC:    Filter hosts containment of pattern in name
            ├── FR:    Filter hosts by name using Regular Expressions
            ├── FG:    Filter hosts by group
            ├── FP:    Filter hosts by hostname using IP Prefix
            ├── FL:    Filter hosts by names list
            ├── FM:    Filter hosts by platform
            ├── FX:    Filter hosts excluding them by name
            └── FN:    Negate the match
nf#
```

## Python API Reference

::: norfab.workers.netbox_worker.netbox_worker.NetboxWorker.sync_device_inventory
