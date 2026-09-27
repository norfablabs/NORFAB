# ADR: NetBox design deployment

## Core rule

Render YAML into NetBox object lists, then use pynetbox to bulk create missing
objects and bulk update existing ones. The design task decides which records go
into each batch and processes object types in NetBox dependency order. Existing
worker tasks handle operations that need allocation or other special behavior.

## Input and processing

Unique-name relationships use strings, for example `manufacturer: ACME NETWORKS`,
`region: ACME REGION`, and `rir: ACME PRIVATE`. Handlers convert these to NetBox
name lookups; name-only dictionaries are rejected. Device-type references use
`{manufacturer: ACME NETWORKS, model: ACME BRANCH ROUTER}` because model alone
does not identify a device type.

Design metadata (`design_input_schema`, `jinja_functions`) and object lists are
top-level keys in one YAML document; metadata precedes templated collections.
Jinja2 may expand short loops into object lists. `devices` remains a list and
is the only collection with
special nested handling for now. The engine unwinds its nested definitions into
lists of dictionaries, adding device and interface names from the parents:

| Under a device | Collected as |
| --- | --- |
| `interfaces` dictionary | Interface records |
| Device or interface `bgp_peerings` dictionary | BGP peering records; nested interface supplies `local_interface` |
| Interface `ip_addresses` list | IP address records assigned to that interface |
| Interface `vrrp_group_assignments` list | VRRP group assignment records for that interface |
| Interface `connection` | Connection record with this interface as one endpoint |
| Interface inline `vrf` | VRF record and interface reference |
| Interface inline `untagged_vlan` or `tagged_vlans` | VLAN records and interface references |
| VRRP assignment inline `group` | VRRP group record and assignment reference |
| BGP inline `import_policies` or `export_policies` | Routing-policy records and policy-name references |

An interface has one VRF association. An identity-only dictionary remains a
reference; additional VRF fields define an inline object. Inline VLAN definitions
include `name` and `vid`; inline VRRP groups include `group_id`. Routing policies,
including BGP import/export lists, require dictionaries with `name`; bare strings
are rejected. The BGP handler passes names to the worker tasks. Identical extracted
definitions are collected only once.
Connections may also be declared in a top-level list.

1. Render the full design with Jinja2, including its context and custom filters.
2. Parse YAML, then call `flatten_design()` explicitly to move nested records
   into top-level lists and add parent references. This step does not access
   NetBox or change the supplied design. Handlers receive only flat records.
3. Validate the flattened document with Pydantic before any handler writes.
   Collections whose handlers are not implemented remain unsupported.
4. For each object type below, look up existing records by their NetBox identity.
   Send missing records to pynetbox bulk `create()` and existing records with IDs
   to bulk `update()`. Apply supplied fields without calculating a diff.
   For new objects requiring slugs, handlers default to `slugify(name)`
   (`slugify(model)` for device types). Supplied slugs and existing slugs are preserved.
5. Call existing NetBox worker tasks for next-available allocations such as
   `create_asn`, `create_vlan`, `create_prefix`, and `create_ip`.

Use task names as explicit wrappers: `create_asn`, `create_vlan`,
`create_prefix`, and `create_ip`. Each contains that task's input arguments.
Unwrapped records use direct pynetbox fields and bulk writes. Nested
`create_ip` records inherit their device and interface. Deployment controls
`instance`, `branch`, and `dry_run` apply to all task calls.
Known ASN numbers use unwrapped `asn` records and bulk pynetbox writes.
`create_asn` requires `asn_range` and no explicit ASN number; it allocates the
next available ASN in that range.
Known VLAN IDs use unwrapped `vid` records and bulk pynetbox writes.
Every VLAN requires a group; direct VLAN-to-site association is unsupported.
Set `site` on the VLAN group to scope that group to a site.
VLAN definitions and interface VLAN references accept `group: GROUP NAME`;
handlers resolve this shorthand for the NetBox API.
`create_vlan` takes a `vlan_group` without `vid` to allocate the next available ID.

```yaml
ip_addresses:
  - address: 192.0.2.1/24
  - create_ip:
      prefix: 192.0.2.0/24
      description: Branch gateway
```

Process supported top-level keys and extracted nested objects in this order:

```text
tenants
regions
manufacturers
platforms
device_types
device_roles
sites
rack_roles
racks
roles
rirs
asn_ranges
asns
vlan_groups
vlans
route_targets
vrfs
prefixes
devices
interfaces
connections
ip_addresses
bgp_communities
routing_policies
bgp_peerings
vrrp_groups
vrrp_group_assignments
```

Each type needs a handler in `design_tasks.py` that collects its records, determines
their identity, and selects the pynetbox batch or existing allocation task.
Device nesting is a deliberate convenience handled during collection; it does
not change the creation order or the bulk create/update approach.

## Object-to-task mapping

Custom creators are registered by name and file URL in `custom_functions`.
Calls run after the collection's built-in writes and allocations, in listed order:

```yaml
custom_functions:
  branch_asn: nf://netbox/functions/branch_asn.py
asns:
  - custom_function: branch_asn
    asn_range: BRANCH
```

The file exports the registered function name. Sibling arguments are passed
unchanged, plus `netbox` (the deployment's pynetbox instance) and `dry_run`.
References and call signatures are checked before writes. Functions must honor
`dry_run`, return serializable data, and raise on failure. Returned data appears
under the collection's `custom` results; exceptions stop deployment.

| Design objects | Creation/update path |
| --- | --- |
| `tenants`, `regions`, `manufacturers`, `platforms`, `device_types`, `device_roles`, `sites`, `roles`, `rirs` | Implemented per-collection handlers using pynetbox bulk create/update. |
| `rack_roles`, `racks`, `asn_ranges`, `vrfs` | Implemented per-collection handlers using pynetbox bulk create/update. |
| `route_targets` | Bulk create/update by name before VRFs. VRF `import_route_targets` and `export_route_targets` accept dictionaries with `name` only, extracted and deduplicated into the top-level collection. Additional fields define the target's properties. The VRF handler resolves IDs for NetBox `import_targets` and `export_targets`. |
| `asns` | Pynetbox bulk create/update; `create_asn` wrapper calls `bgp_asn_tasks.py`. |
| `vlan_groups` | `process_vlan_groups` using pynetbox bulk create/update with direct API fields. |
| `vlans` | Pynetbox bulk create/update; `create_vlan` wrapper calls `vlan_tasks.py`, including next-available VLAN ID allocation. |
| `prefixes` | Pynetbox bulk create/update for explicit prefixes; `create_prefix` in `prefix_tasks.py` for allocation. |
| `devices` | Pynetbox bulk create/update after nested records are extracted; no dedicated `create_device` task exists. |
| `interfaces` | Pynetbox bulk create/update; `create_device_interfaces` in `interfaces_tasks.py` only creates missing interfaces and is not the update path. |
| `ip_addresses` | Pynetbox bulk create/update for explicit addresses; `create_ip` in `ip_tasks.py` for allocation. |
| `bgp_communities` | Dictionaries with `value`; pynetbox bulk create/update by community value. Bare strings are rejected. |
| `routing_policies` | Pynetbox bulk create/update by name, before sessions; includes extracted inline policies. |
| `bgp_peerings` | `create_bgp_peering` for missing sessions and `update_bgp_peering` for existing names, using bulk input. |
| `vrrp_groups`, `vrrp_group_assignments` | Pynetbox bulk create/update; `sync_vrrp` in `fhrp_tasks.py` synchronizes live state and is not a design-creation task. |
| `connections` | Pynetbox bulk create/update after interfaces exist. One interface per side; existing cables are matched by endpoints. Ports cabled elsewhere are rejected without disconnecting them. |

Device types are defined as a top-level list and created after their manufacturers
and accept `default_platform: PLATFORM NAME`, converted to a NetBox name reference.
They follow platforms and precede devices. Top-level connections and nested
interface `connection` entries use the same handler.
