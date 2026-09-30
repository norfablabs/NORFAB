---
tags:
  - netbox
---

# Deploy a Netbox design

`design_deploy` renders a YAML design with Jinja2, validates the rendered document, then creates or updates Netbox objects in dependency order. It never deletes objects omitted from the design. Existing objects receive the supplied fields on every run. The task does not calculate a diff before sending updates.

## Design overview

For an agent-oriented authoring workflow, see [Author a Netbox design with an agent](../../tutorials/norfab_netbox_design_authoring.md).

A design is one YAML document with object collections such as `sites` and `devices`. It can also contain three optional control sections:

| Section | Purpose |
| --- | --- |
| `design_input_schema` | Validate values supplied through `context` before rendering. |
| `jinja_functions` | Load Python functions for use while Jinja2 renders the YAML. |
| `custom_functions` | Load Python functions called later, during collection deployment. |
| Remaining top-level keys | Define lists of Netbox objects dictionaries to create or update, such as `sites`, `devices`, and `ip_addresses`. See [supported Netbox objects and deployment order](#netbox-objects-and-deployment-order). |

For YAML text or a file URL, put `design_input_schema` and `jinja_functions` before the first object collection. The loader reads only that initial metadata block to validate context and register Jinja2 functions **before** rendering the full document. `custom_functions` is loaded after rendering and does not have this placement requirement.

!!! warning "Keep pre-render metadata at the start"

    The loader parses only the initial YAML lines containing `design_input_schema`, `jinja_functions`, `custom_functions`, comments, and indented lines. It stops at the first other top-level line. This portion of document must be valid YAML on its own: keep Jinja2 expressions and top-level template directives out of it, and put `design_input_schema` and `jinja_functions` before any object collection. Use **one YAML document**. Do not insert `---` between metadata and collections. A schema or Jinja2 function declared after a collection will not be available before rendering.

## Design input schema

`design_input_schema` validates the supplied `context` before Jinja2 renders the design. Use inline JSON Schema or an `nf://` / `git://` Python file defining a Pydantic `DesignInput` model. The validated context is available as `context` in the template.

=== "Inline schema"

    ```yaml
    design_input_schema:
      type: object
      properties:
        site: {type: string, minLength: 1}
      required: [site]
      additionalProperties: false

    sites:
      - name: "{{ context.site }}"
    ```

=== "Pydantic Model-based design"

    ```yaml
    design_input_schema: nf://netbox/designs/site_input.py

    sites:
      - name: "{{ context.site }}"
        status: active
    ```

    The referenced `nf://netbox/designs/site_input.py` contains:

    ```python
    from pydantic import BaseModel, ConfigDict

    class DesignInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        site: str
    ```

## Jinja2 rendering

When `design` is YAML text or a file URL, Jinja2 renders it before YAML parsing, flattening, validation, or deployment. It receives `context` and a `netbox` pynetbox instance. File-based designs also support relative includes. `jinja_functions` loads named Python callables from `nf://` or `git://` files as both filters and template globals. When `design` is supplied as a Python dictionary, the task uses its values directly: Jinja2 expressions such as `{{ context.site }}` inside that dictionary are not evaluated.

!!! warning "Jinja2 runs before deployment"

    Jinja2 filters and global functions run while the design is rendered, before any object in that design is created. They may query objects already in Netbox, but must not depend on objects the same design plans to create: those objects do not exist yet. Use deployment-time `custom_functions` when a function needs objects created by an earlier collection.

=== "Jinja2 Loop"

    ```yaml
    devices:
    {% for name in context.devices %}
      - name: "{{ name }}"
        site: "{{ context.site }}"
        role: ROUTER
        device_type: {manufacturer: ACME, model: ROUTER}
    {% endfor %}
    ```

=== "Custom filter"

    ```yaml
    jinja_functions:
      site_label: nf://netbox/designs/site_label.py

    sites:
      - name: "{{ context.site }}"
        description: "{{ context.site | site_label('ACME') }}"
    ```

    The referenced `nf://netbox/designs/site_label.py` contains:

    ```python
    def site_label(site: str, prefix: str) -> str:
        return f"{prefix} site: {site}"
    ```

    In `context.site | site_label('ACME')`, Jinja2 passes `context.site` as `site` and `'ACME'` as `prefix`. The function does not receive `context` or `netbox` unless the template passes them explicitly.

=== "Global function"

    ```yaml
    jinja_functions:
      site_label: nf://netbox/designs/site_label.py

    sites:
      - name: "{{ context.site }}"
        description: "{{ site_label(context.site, 'ACME') }}"
    ```

    The referenced `nf://netbox/designs/site_label.py` contains:

    ```python
    def site_label(site: str, prefix: str) -> str:
        return f"{prefix} site: {site}"
    ```

    In `site_label(context.site, 'ACME')`, the template passes `site` and `prefix` explicitly. Pass `netbox` explicitly too if the function needs to query it.

Jinja2 reads may query `netbox`, but object writes belong in collection handlers or deployment-time custom functions: rendering runs before design prerequisites are created.

## Netbox objects and deployment order

Each design section contains a list of object records. The rows show the order in which Netbox objects are processed. Deployment stops at the first failure. For records with specified values, **Match fields** identify an existing object to update instead of creating another. Allocation tasks and custom functions use their own lookup rules.

| Order | Design top-level key | Netbox object | Match fields | Description and current limitations |
| ---: | --- | --- | --- | --- |
| 1 | `tenants` | `netbox.tenancy.tenants` | `name` | — |
| 2 | `regions` | `netbox.dcim.regions` | `name` | Parent can be a name. |
| 3 | `manufacturers` | `netbox.dcim.manufacturers` | `name` | — |
| 4 | `platforms` | `netbox.dcim.platforms` | `name` | Manufacturer can be a name. |
| 5 | `device_types` | `netbox.dcim.device_types` | `manufacturer`, `model` | Default platform can be a name. |
| 6 | `device_roles` | `netbox.dcim.device_roles` | `name` | — |
| 7 | `sites` | `netbox.dcim.sites` | `name` | Region and tenant can be names. |
| 8 | `rack_roles` | `netbox.dcim.rack_roles` | `name` | — |
| 9 | `racks` | `netbox.dcim.racks` | `site`, `name` | Site, role, and tenant can be names. |
| 10 | `roles` | `netbox.ipam.roles` | `name` | — |
| 11 | `rirs` | `netbox.ipam.rirs` | `name` | — |
| 12 | `asn_ranges` | `netbox.ipam.asn_ranges` | `name` | Ranges are not site-scoped. |
| 13 | `asns` | `netbox.ipam.asns` | `asn` | Explicit numbers are matched globally. `create_asn` allocates from a named range. Supports `sites` and `role`. |
| 14 | `vlan_groups` | `netbox.ipam.vlan_groups` | `name` | Scope by rack, location, site, site group, region, cluster, or cluster group. |
| 15 | `vlans` | `netbox.ipam.vlans` | `group`, `vid` | VLANs with a specified ID require both fields. Existing VLANs gain new tags and custom-field list items. `create_vlan` allocates a VID. Direct VLAN `site` is unsupported. |
| 16 | `route_targets` | `netbox.ipam.route_targets` | `name` | VRF and L2VPN references can inline target dictionaries. |
| 17 | `vrfs` | `netbox.ipam.vrfs` | `name`, `rd` | Import/export route targets must be dictionaries. Existing target lists gain missing targets. |
| 18 | `l2vpns` | `netbox.vpn.l2vpns` | `name` | Import/export route targets must be dictionaries. Existing target lists gain missing targets. Nested terminations are flattened. |
| 19 | `prefixes` | `netbox.ipam.prefixes` | `prefix`, `vrf` | Explicit prefixes can select location, site, site group, or region scope, and refer to a VLAN by `{group, vid}`. Existing prefixes gain new tags and custom-field list items. `create_prefix` supports site scope and VLAN association through `vlan` (VID) plus `vlan_group` (name). |
| 20 | `devices` | `netbox.dcim.devices` | `site` and `name`, plus `tenant` when supplied | Nested components are flattened before writes. |
| 21 | `interfaces` | `netbox.dcim.interfaces` | `device`, `name` | Independent interfaces are written before those with `parent`, `lag`, or `bridge`. |
| 22 | `l2vpn_terminations` | `netbox.vpn.l2vpn_terminations` | Attached interface or VLAN | Attachments require `l2vpn` and either `device` with `interface`, or VLAN `group` with `vid`. An attachment already used by another L2VPN is rejected. |
| 23 | `power_ports` | `netbox.dcim.power_ports` | `device`, `name` | Nested connection is flattened. |
| 24 | `console_ports` | `netbox.dcim.console_ports` | `device`, `name` | Nested connection is flattened. |
| 25 | `power_outlets` | `netbox.dcim.power_outlets` | `device`, `name` | Nested connection is flattened. |
| 26 | `console_server_ports` | `netbox.dcim.console_server_ports` | `device`, `name` | Nested connection is flattened. |
| 27 | `connections` | `netbox.dcim.cables` | Existing cable on both terminations | Creates interface, console, and power cables. Each end currently has one termination. An already-cabled port cannot be moved. |
| 28 | `vrrp_groups` | `netbox.ipam.fhrp_groups` | `protocol`, `group_id` | Inline `vip` becomes an explicit IP address; use top-level `create_ip.vrrp_group` for allocation. |
| 29 | `ip_addresses` | `netbox.ipam.ip_addresses` | `address`, `vrf` | Addresses with specified values are bulk-written. `create_ip` allocates the next available address and can assign it to an interface or named VRRP group. |
| 30 | `vrrp_group_assignments` | `netbox.ipam.fhrp_group_assignments` | `group`, `interface` | Associates an existing group and interface with priority. |
| 31 | `primary_ip` | `netbox.dcim.devices` | Device: `site` and `name`, plus `tenant` when supplied | Sets an existing `primary_ip4` or `primary_ip6`. It does not create the address. |
| 32 | `bgp_communities` | `netbox.plugins.bgp.community` | `value`, plus `description` when supplied | A different description creates another community. Without description, the value must identify one object. |
| 33 | `routing_policies` | `netbox.plugins.bgp.routing_policy` | `name` | Peering references can inline policy dictionaries. |
| 34 | `bgp_peerings` | `netbox.plugins.bgp.session` | Supplied or generated `name` | Uses `create_bgp_peering` to create missing sessions. Existing sessions are left unchanged. New sessions default to `create_reverse: true`. Supports import/export policy dictionaries. |
| 35 | `config_context` | `netbox.extras.config_contexts` | `name` | `data` is a dictionary and `sites` scopes it. |
| 36 | `local_context_data` | `netbox.dcim.devices` | Device: `site` and `name`, plus `tenant` when supplied | Replaces each device's local context dictionary last. |

Ordinary records use Netbox API field names. Handlers bulk-create missing objects and bulk-update existing ones. Common name references, such as `device.site`, `device.role`, and `vlan.group`, are resolved by their handlers. Fields without a documented name shorthand must use a payload accepted by the target Netbox API. Unknown top-level collections are rejected.

When updating an existing record, design handlers add requested tags and custom-field list values without removing existing members. They also add VRF and L2VPN route targets, interface tagged VLANs, and config-context scope lists. Only config-context `sites` accepts site names; other scope lists use NetBox IDs. Scalar custom fields replace their old values. VLAN-group `vid_ranges`, local context data, and config-context `data` retain replacement behavior. Named object and multiobject custom-field values are resolved to NetBox IDs before writes.



## Built-In Task Wrappers

Task wrappers call standalone NorFab NetBox service tasks during the relevant deployment stage. The wrapper contains that task's arguments, without renaming them. The allocation wrappers are useful when a design knows the pool and the object's purpose, but not its final ASN, VLAN ID, subnet, or IP address. Several branches can use the same design and receive different available values from their own pools.

| Task wrapper | How it works |
| --- | --- |
| [create_asn](services_netbox_service_tasks_create_asn.md) | Selects an available ASN from an existing named range. |
| [create_vlan](services_netbox_service_tasks_create_vlan.md) | Selects an available VID from an existing VLAN group's allowed ranges. |
| [create_prefix](services_netbox_service_tasks_create_prefix.md) | Allocates a child prefix of the requested length inside an existing parent prefix; supports VLAN association by VID and group name. |
| [create_ip](services_netbox_service_tasks_create_ip.md) | Allocates an address from an existing prefix and can assign it to a device interface or named VRRP group. |
| [create_bgp_peering](services_netbox_service_tasks_create_bgp_peering.md) | Creates a BGP session under `bgp_peerings`; can derive the local address from an interface and create a reverse session. |

Both forms belong under `ip_addresses`. Specify each address when its value is known:

```yaml
ip_addresses:
  - address: 192.0.2.10/24
    description: ACME gateway 1
  - address: 192.0.2.11/24
    description: ACME gateway 2
  - address: 192.0.2.12/24
    description: ACME gateway 3
  - address: 192.0.2.13/24
    description: ACME gateway 4
  - address: 192.0.2.14/24
    description: ACME gateway 5
```

When the values are not known, ask the standalone `create_ip` task to select five available addresses from an existing prefix. Each request has a distinct description so it can find its address on a repeat run:

```yaml
ip_addresses:
  - create_ip:
      prefix: 192.0.2.0/24
      description: ACME gateway 1
  - create_ip:
      prefix: 192.0.2.0/24
      description: ACME gateway 2
  - create_ip:
      prefix: 192.0.2.0/24
      description: ACME gateway 3
  - create_ip:
      prefix: 192.0.2.0/24
      description: ACME gateway 4
  - create_ip:
      prefix: 192.0.2.0/24
      description: ACME gateway 5
```

For each object type, specified values are created or updated before next-available requests run. Allocation tasks look for an existing match on repeat deployment. Give each request a stable name or description and enough scope to identify it, otherwise a repeat run can allocate another value.

Entries under `bgp_peerings` call `create_bgp_peering` after the design's devices, interfaces, IP addresses, and ASNs have been deployed. Use a stable supplied or generated session name so repeat deployments find the existing session. Existing sessions are not updated by the design:

```yaml
bgp_peerings:
  - name: ACME BRANCH PEER
    device: acme-branch-rtr-1
    local_interface: Ethernet1
    local_as: 4200650001
    remote_as: 4200650000
    create_reverse: false
```

### Allocation examples

=== "Combined example"

    The design creates an RIR, ASN range, VLAN group, and parent prefix. It then allocates an ASN, VLAN ID, child prefix, and IP address from those objects, in deployment order.

    ```yaml
    rirs:
      - name: ACME PRIVATE
        is_private: true

    asn_ranges:
      - name: ACME BRANCH ASNS
        rir: ACME PRIVATE
        start: 4200650001
        end: 4200650099

    asns:
      - create_asn:
          asn_range: ACME BRANCH ASNS
          description: ACME branch ASN

    vlan_groups:
      - name: ACME BRANCH VLANS
        vid_ranges: [[100, 199]]

    vlans:
      - create_vlan:
          vlan_group: ACME BRANCH VLANS
          name: ACME USERS

    prefixes:
      - prefix: 198.19.224.0/20
        description: ACME allocation pool
      - create_prefix:
          parent: 198.19.224.0/20
          prefixlen: 24
          description: ACME user subnet

    ip_addresses:
      - create_ip:
          prefix: {description: ACME user subnet}
          description: ACME user gateway
    ```

=== "ASN"

    Prerequisites: A text custom field named `deployment_owner` enabled for ASN objects (`ipam.asn`) in Netbox.

    The design creates an ASN range under the RIR, then `create_asn` selects an available number from that range and sets its custom fields. Its description lets the task find the same ASN on a repeat run.

    ```yaml
    rirs:
      - name: ACME PRIVATE
        is_private: true

    asn_ranges:
      - name: ACME BRANCH ASNS
        rir: ACME PRIVATE
        start: 4200650001
        end: 4200650099

    asns:
      - create_asn:
          asn_range: ACME BRANCH ASNS
          description: ACME branch ASN
          custom_fields:
            deployment_owner: ACME
    ```

=== "VLAN"

    The design creates a VLAN group allowing IDs 100–199, then `create_vlan` selects the next available ID for `ACME USERS`. Its name and group identify it on a repeat run.

    ```yaml
    vlan_groups:
      - name: ACME BRANCH VLANS
        vid_ranges: [[100, 199]]

    vlans:
      - create_vlan:
          vlan_group: ACME BRANCH VLANS
          name: ACME USERS
          description: User access VLAN
    ```

=== "Prefix"

    The design creates the `/20` parent prefix, then `create_prefix` allocates an available `/24` within it. Its description helps the task find that child on a repeat run.

    ```yaml
    prefixes:
      - prefix: 198.19.224.0/20
        description: ACME allocation pool
      - create_prefix:
          parent: 198.19.224.0/20
          prefixlen: 24
          description: ACME user subnet
    ```

=== "IP address"

    The design creates a `/24` prefix, then `create_ip` selects an available address from the prefix identified by its description.

    ```yaml
    prefixes:
      - prefix: 198.19.225.0/24
        description: ACME user subnet

    ip_addresses:
      - create_ip:
          prefix: {description: ACME user subnet}
          description: ACME user gateway
    ```

### Create ASN Next Available Allocation

The standalone [create_asn task](services_netbox_service_tasks_create_asn.md) takes an `asn_range` name and selects an available ASN. Supply a stable `description` so repeat deployments can find the ASN already allocated within that range. The allocated ASN can use `sites: [SITE-1, SITE-2]` and `role: ROLE NAME`. `sites` assigns the ASN to sites, it does not select the range by site. ASN ranges are not site-scoped.

### Create VLAN Next Available Allocation

The standalone [create_vlan task](services_netbox_service_tasks_create_vlan.md) takes `vlan_group` and `name`, then selects an available VID from the group's ranges. It reuses a VLAN with the same name in that group on repeat deployment.

!!! warning "VLANs require a group"

    Every VLAN in a design must belong to a VLAN group. Direct VLAN-to-site association is unsupported. Scope the group instead.

A VLAN group accepts one of `rack`, `location`, `site`, `site_group`, `region`, `cluster`, or `cluster_group` as a scope name. The referenced object must exist. For a rack or location, `site` may also be supplied to distinguish equal names at different sites.

```yaml
vlan_groups:
  - name: BRANCH FLOOR VLANS
    location: Floor 2
    site: BRANCH-1
    vid_ranges: [[100, 199]]
```

### Create Prefix Next Available Allocation

The standalone [create_prefix task](services_netbox_service_tasks_create_prefix.md) takes a `parent` prefix or parent filter dictionary and a `prefixlen`, then allocates an available child prefix. A stable `description`, optionally with `site`, `role`, or `vrf`, helps it find the same child on repeat deployment. `create_prefix.parent` can select the parent through a dictionary of filters. The task accepts `site` for the allocated child's scope and the pair `vlan` (VID) and `vlan_group` (group name) to associate an existing VLAN. Site cannot replace the group for VLAN identification. It has no `location`, `site_group`, or `region` argument for the child.

Both `vlan` and `vlan_group` must be supplied together. The VLAN must exist when allocation runs; VLANs defined in the same design are created before prefixes. A missing group or VLAN stops allocation. On repeat deployment, the association is updated if needed; omitting both arguments preserves it.

```yaml
vlan_groups:
  - name: BRANCH VLANS
    vid_ranges:
      - [100, 199]
vlans:
  - name: USERS
    vid: 100
    group: BRANCH VLANS
prefixes:
  - prefix: 198.19.224.0/20
  - create_prefix:
      parent: 198.19.224.0/20
      prefixlen: 24
      description: Branch user subnet
      vlan: 100
      vlan_group: BRANCH VLANS
```

### Create IP Next Available Allocation

IPv4 /32 and IPv6 /128 allocations work with the default `create_peer_ip` setting. The task automatically skips peer creation and peer-subnet reuse for these host prefixes. There is no need to set `create_peer_ip: false` explicitly.

The standalone [create_ip task](services_netbox_service_tasks_create_ip.md) takes a `prefix` string or filter dictionary and allocates an available IP. It can assign that IP to a `device` and `interface`. If nested under an interface's `ip_addresses`, the design supplies those two arguments during flattening.

To allocate a VIP, supply `vrrp_group` with a unique existing VRRPv2 or VRRPv3 group name. Groups defined in the same design are deployed before IP allocations. The task reuses an address assigned to that group within the selected prefix, optionally matching `description`, and defaults the IP role to `vrrp`. Missing, ambiguous, or non-VRRP group names fail before allocation.

Put this wrapper in the **top-level `ip_addresses` collection**. Do not nest it under an interface: `vrrp_group` cannot accompany `device`, `interface`, or `is_primary: true`. Group allocation disables peer IP allocation automatically. See the [allocated VIP example](#nested-vrrp-group-records) below.

A dry run does not create the VLANs, groups, or prefixes proposed by the design. Allocation lookups therefore require those prerequisites to exist already. The `create_ip` dry-run limitation still applies: `mask_len` is ignored and no child subnet is created.

## Custom fields

Put a `custom_fields` dictionary on an object record. Its keys are Netbox custom-field names, not labels. Definitions must already exist and be enabled for that object type. The design passes values through to Netbox, which validates their types and choices. Updates PATCH supplied values without clearing omitted custom fields. Use `null` to clear a nullable scalar field.

When updating an ASN, a design adds new sites and tags without removing existing
ones. When updating a VLAN or prefix, it adds new tags. For these objects, if both the
existing and supplied values of a custom field are lists, the design adds only
new items. Supplying `[]` leaves an existing list unchanged. For custom fields,
`null` clears the value, and a new scalar value replaces the old one.

FHRP group assignments and ConfigContext objects do not support custom fields. Device-local context is ordinary JSON data, not a custom-field definition. The design does not create custom-field definitions.

=== "Device and interface"

    Prerequisites: the referenced device prerequisites and custom-field definitions enabled for devices and interfaces respectively.

    ```yaml
    devices:
      - name: branch-router-1
        site: BRANCH-1
        role: ROUTER
        device_type: {manufacturer: ACME, model: ROUTER}
        custom_fields:
          deployment_owner: ACME
        interfaces:
          Loopback0:
            type: virtual
            custom_fields:
              service_name: routing
    ```

=== "Next-available allocation"

    Prerequisites: `deployment_owner` enabled for prefixes and IP addresses. Arguments belong inside the allocation wrapper.

    ```yaml
    prefixes:
      - prefix: 192.0.2.0/24
        custom_fields: {deployment_owner: ACME}
      - create_prefix:
          parent: 192.0.2.0/24
          prefixlen: 28
          description: ACME services
          custom_fields: {deployment_owner: ACME}
    ip_addresses:
      - create_ip:
          prefix: {description: ACME services}
          description: ACME service IP
          custom_fields: {deployment_owner: ACME}
    ```

=== "Clear a value"

    Prerequisites: the prefix and a nullable `deployment_owner` custom field.

    ```yaml
    prefixes:
      - prefix: 192.0.2.0/24
        custom_fields: {deployment_owner: null}
    ```

## Custom functions

Custom functions let a design run Python during deployment for use cases such as custom next-available allocation, Netbox lookups, or object creation that needs additional logic.

The following contract applies to `custom_function` on an object record. [Device-local context functions](#device-local-context) have a different contract.

When `branch` is supplied to `design_deploy`, the provided `netbox` client is already configured for that branch. Queries and writes through this client use the deployment branch. Custom functions do not need to initialize branching themselves.

| Argument | Type | Supplied by | Meaning |
| --- | --- | --- | --- |
| `netbox` | `pynetbox.core.api.Api` | Deployment | Pynetbox client bound to the deployment's Netbox instance and branch. Use it for queries and writes. |
| `dry_run` | `bool` | Deployment | Whether this is a preview. The function must avoid writes when `True`. Deployment does not intercept its API calls. |
| Other record fields | As defined in YAML | Design record | Every field except `custom_function` is passed unchanged as a keyword argument. For example, `profile: foo` becomes `profile="foo"`. |

`custom_function` selects the registered function and is not passed as an argument. Do not supply `netbox` or `dry_run` in the record, because deployment supplies them. No device object or design `context` is passed automatically.

| Function outcome | Deployment behavior |
| --- | --- |
| Returns a value | Appends `{"function": NAME, "result": VALUE}` under the object's `custom` results list, such as `vlans.custom`. Return JSON-serializable data. The value is not passed to the object handler or written to Netbox automatically. |
| Returns nothing | Records `null` as the function result. |
| Raises an exception | Reports the failure and stops deployment. Earlier writes are not rolled back. |

=== "Route target allocation"

    This example allocates a route target. Register the Python file under `custom_functions`, then use `custom_function: allocate_route_target` in a `route_targets` record. The function runs during the route-target deployment stage, after route-target records without `custom_function` have been processed. The record's other fields become keyword arguments, and deployment also supplies `netbox` and `dry_run`.

    ```yaml
    custom_functions:
      allocate_route_target: nf://netbox/designs/allocate_route_target.py

    tenants:
      - name: ACME

    route_targets:
      - custom_function: allocate_route_target
        tenant: ACME
        description: ACME branch route target
    ```

    The referenced `nf://netbox/designs/allocate_route_target.py` contains:

    ```python
    def allocate_route_target(netbox, dry_run, tenant, description):
        # Replace this fixed value with a real allocation rule when needed.
        name = "65000:100"
        existing = netbox.ipam.route_targets.get(name=name)
        if not dry_run:
            if existing:
                existing.update({"tenant": {"name": tenant}, "description": description})
            else:
                netbox.ipam.route_targets.create(
                    {"name": name, "tenant": {"name": tenant}, "description": description}
                )
        return {"name": name}
    ```

    The `tenant` and `description` fields become function arguments. Deployment supplies `netbox` and `dry_run`, so do not put them in the record. This dummy allocator always returns `65000:100`. It also creates or updates that route target unless `dry_run` is true. Returning a value alone would only add it to the deployment result, not create an object. The return value appears under `route_targets.custom`. Custom functions must handle their own lookups and writes, including dry-run behavior. Only load trusted Python files.

=== "Calculated VLAN name"

    This function calculates a VLAN name from the additional `profile` argument, then creates or updates the VLAN. The VLAN group must already exist when the `vlans` stage runs.

    ```yaml
    custom_functions:
      create_profile_vlan: nf://netbox/designs/create_profile_vlan.py

    vlan_groups:
      - name: BRANCH VLANS

    vlans:
      - custom_function: create_profile_vlan
        group: BRANCH VLANS
        vid: 120
        profile: foo
    ```

    The referenced `nf://netbox/designs/create_profile_vlan.py` contains:

    ```python
    def create_profile_vlan(netbox, dry_run, group, vid, profile):
        name = f"{profile.upper()}-{vid}"
        vlan_group = netbox.ipam.vlan_groups.get(name=group)
        if vlan_group is None:
            raise ValueError(f"VLAN group not found: {group}")
        existing = netbox.ipam.vlans.get(group_id=vlan_group.id, vid=vid)
        if not dry_run:
            if existing:
                existing.update({"name": name})
            else:
                netbox.ipam.vlans.create(
                    {"group": vlan_group.id, "vid": vid, "name": name}
                )
        return {"group": group, "vid": vid, "name": name}
    ```

    `group`, `vid`, and `profile` are passed unchanged from the design record. The calculated name is `FOO-120`. Because this is a custom-function record, the function performs its own lookup and write. Its return value appears under `vlans.custom`.

=== "Jinja2 loop and community allocation"

    Jinja2 expands `context.devices` into one record per device. It does not allocate anything. During the later `bgp_communities` stage, each record calls the custom function with its `device` name. The function reuses a community identified by its description or takes the next free value in the example range.

    ```yaml
    custom_functions:
      allocate_device_community: nf://netbox/designs/allocate_device_community.py

    bgp_communities:
    {% for device in context.devices %}
      - custom_function: allocate_device_community
        device: "{{ device }}"
        asn: 65100
    {% endfor %}
    ```

    Supply a context such as `{"devices": ["branch-rtr-1", "branch-rtr-2"]}`. The referenced `nf://netbox/designs/allocate_device_community.py` contains:

    ```python
    def allocate_device_community(netbox, dry_run, device, asn):
        description = f"Community for {device}"
        communities = list(netbox.plugins.bgp.community.all())
        existing = next(
            (item for item in communities
             if item.description == description
             and item.value in {f"{asn}:{number}" for number in range(100, 200)}),
            None,
        )
        used = {item.value for item in communities}
        value = existing.value if existing else next(
            (f"{asn}:{number}" for number in range(100, 200)
             if f"{asn}:{number}" not in used),
            None,
        )
        if value is None:
            raise ValueError(f"No free BGP community in {asn}:100-199")
        if not dry_run and existing is None:
            netbox.plugins.bgp.community.create(
                {"value": value, "description": description}
            )
        return {"device": device, "value": value}
    ```

    The record passes `asn=65100` to the function, so allocated values start at `65100:100`. Each created community is identified on repeat deployment by `Community for <device>`. The returned dictionary appears under `bgp_communities.custom`. A dry run makes no reservations, so multiple records may propose the same free value.

    This simplified allocator is intended for sequential deployments. It does not reserve values against concurrent allocations. The built-in handler for explicit community records matches `value` and, when supplied, `description`. A different description creates a separate community. If description is omitted, more than one matching value is an error.

## Nested Device Records

Nesting keeps a device and its related objects together, making the design more natural to read and shorter to write. Interfaces, IP addresses, and peerings inherit their device or interface names instead of repeating them in separate top-level records.

Device records may contain `interfaces`, `bgp_peerings`, `power_ports`, `console_ports`, `power_outlets`, `console_server_ports`, and `local_context_data`. An interface may contain `ip_addresses`, `bgp_peerings`, `connection`, `vrf`, `untagged_vlan`, `tagged_vlans`, and `vrrp`. The task flattens these before validation or writes. It adds device and interface names to extracted records and merges them with records already at the top level. Inline VRFs, VLANs, VRRP groups, route targets, and routing policies are also collected into their earlier collections. Interface VRF identity dictionaries and VLAN group/VID dictionaries remain references. Nested route-target and routing-policy dictionaries are always collected as definitions, even with only a name.

=== "All nested fields"

    Prerequisites: Named sites, roles, device types, VLAN group, referenced VLANs/VRF, remote endpoints, peering IPs/ASNs, and the BGP plugin.

    This shows every device-nested collection and every interface-nested field. Referenced sites, roles, device types, VLANs, and remote endpoints must exist or be defined earlier in the design. Use the focused tabs for complete examples of the less obvious fields.

    ```yaml
    devices:
      - name: branch-agg-1
        site: BRANCH-1
        role: AGGREGATION
        device_type: {manufacturer: ACME, model: AGG SWITCH}
        interfaces:
          Port-Channel1: {type: lag}
          Ethernet1:
            type: 10gbase-x-sfpp
            lag: {name: Port-Channel1}
            connection: {device: branch-router-1, interface: Ethernet1}
            tagged_vlans: [{group: BRANCH VLANS, vid: 100}]
          Vlan100:
            type: virtual
            vrf: BRANCH VRF
            untagged_vlan: {group: BRANCH VLANS, vid: 100}
            ip_addresses: [{address: 192.0.2.21/24}]
            vrrp: {group_id: 10, vip: 192.0.2.1/24, priority: 200}
            bgp_peerings:
              - name: branch-agg-1-to-branch-router-1
                remote_address: 192.0.2.11
                local_as: 65100
                remote_as: 65200
                create_reverse: false
        bgp_peerings:
          - name: branch-agg-1-loopback-peer
            local_address: 192.0.2.101
            remote_address: 192.0.2.102
            local_as: 65100
            remote_as: 65200
            create_reverse: false
        power_ports:
          PSU1: {type: iec-60320-c14}
        console_ports:
          Console: {type: rj-45}
        power_outlets:
          Outlet-1: {type: iec-60320-c13}
        console_server_ports:
          Line-1: {type: rj-45}
        local_context_data: {profile: aggregation}
    ```

    Equivalent using top-level keys:

    ```yaml
    devices:
    - name: branch-agg-1
      site: BRANCH-1
      role: AGGREGATION
      device_type:
        manufacturer: ACME
        model: AGG SWITCH
    interfaces:
    - type: lag
      name: Port-Channel1
      device: branch-agg-1
    - type: 10gbase-x-sfpp
      lag:
        name: Port-Channel1
      tagged_vlans:
      - group: BRANCH VLANS
        vid: 100
      name: Ethernet1
      device: branch-agg-1
    - type: virtual
      vrf: BRANCH VRF
      untagged_vlan:
        group: BRANCH VLANS
        vid: 100
      name: Vlan100
      device: branch-agg-1
    power_ports:
    - type: iec-60320-c14
      name: PSU1
      device: branch-agg-1
    console_ports:
    - type: rj-45
      name: Console
      device: branch-agg-1
    power_outlets:
    - type: iec-60320-c13
      name: Outlet-1
      device: branch-agg-1
    console_server_ports:
    - type: rj-45
      name: Line-1
      device: branch-agg-1
    connections:
    - a_terminations:
      - device: branch-agg-1
        interface: Ethernet1
      b_terminations:
      - device: branch-router-1
        interface: Ethernet1
    vrrp_groups:
    - group_id: 10
      protocol: vrrp2
      name: VRRP 10
    ip_addresses:
    - address: 192.0.2.21/24
      device: branch-agg-1
      interface: Vlan100
    - address: 192.0.2.1/24
      fhrp_group:
        protocol: vrrp2
        group_id: 10
    vrrp_group_assignments:
    - group_id: 10
      protocol: vrrp2
      device: branch-agg-1
      interface: Vlan100
      priority: 200
    bgp_peerings:
    - local_address: 192.0.2.101
      remote_address: 192.0.2.102
      local_as: 65100
      remote_as: 65200
      create_reverse: false
      name: branch-agg-1-loopback-peer
      device: branch-agg-1
    - remote_address: 192.0.2.11
      local_as: 65100
      remote_as: 65200
      create_reverse: false
      name: branch-agg-1-to-branch-router-1
      device: branch-agg-1
      local_interface: Vlan100
    local_context_data:
    - device: branch-agg-1
      site: BRANCH-1
      local_context_data:
        profile: aggregation
    ```

    The peering under `Vlan100` receives `local_interface: Vlan100`. The peering directly under the device does not. Interface creation uses two passes: independent interfaces first, then interfaces referencing `parent`, `lag`, or `bridge`.

=== "Interfaces"

    Prerequisites: Named site, role, manufacturer, and device type.

    `interfaces` is a dictionary keyed by interface name. The device name is added to every extracted interface. Independent interfaces are created before subinterfaces and LAG members.

    ```yaml
    devices:
      - name: branch-agg-1
        site: BRANCH-1
        role: AGGREGATION
        device_type: {manufacturer: ACME, model: AGG SWITCH}
        interfaces:
          Port-Channel1: {type: lag}
          Ethernet1: {type: 10gbase-x-sfpp, lag: {name: Port-Channel1}}
          Ethernet2.100: {type: virtual, parent: {name: Ethernet2}}
          Ethernet2: {type: 10gbase-x-sfpp}
    ```

    Equivalent using top-level keys:

    ```yaml
    devices:
    - name: branch-agg-1
      site: BRANCH-1
      role: AGGREGATION
      device_type:
        manufacturer: ACME
        model: AGG SWITCH
    interfaces:
    - type: lag
      name: Port-Channel1
      device: branch-agg-1
    - type: 10gbase-x-sfpp
      lag:
        name: Port-Channel1
      name: Ethernet1
      device: branch-agg-1
    - type: virtual
      parent:
        name: Ethernet2
      name: Ethernet2.100
      device: branch-agg-1
    - type: 10gbase-x-sfpp
      name: Ethernet2
      device: branch-agg-1
    ```

=== "Device BGP peerings"

    Prerequisites: Named site, role, device type, both IP addresses, both ASNs, and the BGP plugin.

    Device-level `bgp_peerings` is a list. Flattening adds `device`; `name` is optional and is generated by `create_bgp_peering` when omitted. Supply addresses explicitly when no local interface is given.

    ```yaml
    devices:
      - name: branch-agg-1
        site: BRANCH-1
        role: AGGREGATION
        device_type: {manufacturer: ACME, model: AGG SWITCH}
        bgp_peerings:
          - name: branch-agg-1-to-router-1
            local_address: 192.0.2.101
            remote_address: 192.0.2.102
            local_as: 65100
            remote_as: 65200
            create_reverse: false
    ```

    Equivalent using top-level keys:

    ```yaml
    devices:
    - name: branch-agg-1
      site: BRANCH-1
      role: AGGREGATION
      device_type:
        manufacturer: ACME
        model: AGG SWITCH
    bgp_peerings:
    - local_address: 192.0.2.101
      remote_address: 192.0.2.102
      local_as: 65100
      remote_as: 65200
      create_reverse: false
      name: branch-agg-1-to-router-1
      device: branch-agg-1
    ```

=== "VRRP"

    Prerequisites: Named site, role, manufacturer, and device type.

    A compact interface `vrrp` record creates an FHRP group, its VIP IP address, and an assignment to the interface. The protocol defaults to `vrrp2`. The same group can be assigned to a second device with a different priority.

    ```yaml
    devices:
      - name: branch-agg-1
        site: BRANCH-1
        role: AGGREGATION
        device_type: {manufacturer: ACME, model: AGG SWITCH}
        interfaces:
          Vlan100:
            type: virtual
            vrrp:
              group_id: 10
              name: BRANCH GATEWAY
              vip: 192.0.2.1/24
              priority: 200
      - name: branch-agg-2
        site: BRANCH-1
        role: AGGREGATION
        device_type: {manufacturer: ACME, model: AGG SWITCH}
        interfaces:
          Vlan100:
            type: virtual
            vrrp:
              group_id: 10
              name: BRANCH GATEWAY
              vip: 192.0.2.1/24
              priority: 100
    ```

    Equivalent using top-level keys:

    ```yaml
    devices:
    - name: branch-agg-1
      site: BRANCH-1
      role: AGGREGATION
      device_type:
        manufacturer: ACME
        model: AGG SWITCH
    - name: branch-agg-2
      site: BRANCH-1
      role: AGGREGATION
      device_type:
        manufacturer: ACME
        model: AGG SWITCH
    interfaces:
    - type: virtual
      name: Vlan100
      device: branch-agg-1
    - type: virtual
      name: Vlan100
      device: branch-agg-2
    vrrp_groups:
    - group_id: 10
      name: BRANCH GATEWAY
      protocol: vrrp2
    ip_addresses:
    - address: 192.0.2.1/24
      fhrp_group:
        protocol: vrrp2
        group_id: 10
    vrrp_group_assignments:
    - group_id: 10
      protocol: vrrp2
      device: branch-agg-1
      interface: Vlan100
      priority: 200
    - group_id: 10
      protocol: vrrp2
      device: branch-agg-2
      interface: Vlan100
      priority: 100
    ```

    Top-level `vrrp_groups` can instead provide a `vip` and an `assignments` list.

=== "IP addresses"

    Prerequisites: Named site, role, device type, and allocation prefix.

    An interface can contain explicit addresses and `create_ip` next-available allocations. Flattening adds the device and interface names to each address. `primary_ip` runs after address creation and selects an existing address.

    ```yaml
    devices:
      - name: branch-agg-1
        site: BRANCH-1
        role: AGGREGATION
        device_type: {manufacturer: ACME, model: AGG SWITCH}
        interfaces:
          Loopback0:
            type: virtual
            ip_addresses:
              - address: 192.0.2.21/32
              - create_ip:
                  prefix: 198.51.100.0/24
                  description: branch-agg-1 service IP
    primary_ip:
      - device: branch-agg-1
        site: BRANCH-1
        address: 192.0.2.21/32
    ```

    Equivalent using top-level keys:

    ```yaml
    devices:
    - name: branch-agg-1
      site: BRANCH-1
      role: AGGREGATION
      device_type:
        manufacturer: ACME
        model: AGG SWITCH
    interfaces:
    - type: virtual
      name: Loopback0
      device: branch-agg-1
    ip_addresses:
    - address: 192.0.2.21/32
      device: branch-agg-1
      interface: Loopback0
    - create_ip:
        prefix: 198.51.100.0/24
        description: branch-agg-1 service IP
        device: branch-agg-1
        interface: Loopback0
    primary_ip:
    - device: branch-agg-1
      site: BRANCH-1
      address: 192.0.2.21/32
    ```

    The `create_ip` prefix must already exist or be created earlier in the design. `primary_ip.field` defaults to `primary_ip4`. Set it to `primary_ip6` for IPv6.

=== "Interface connection"

    Prerequisites: Named site, role, device type, and remote device/interface.

    `connection` under an interface specifies the remote device and interface. The local endpoint comes from its parent device and interface. Both interfaces must exist by the connections stage.

    ```yaml
    devices:
      - name: branch-agg-1
        site: BRANCH-1
        role: AGGREGATION
        device_type: {manufacturer: ACME, model: AGG SWITCH}
        interfaces:
          Ethernet1:
            type: 10gbase-x-sfpp
            connection: {device: branch-router-1, interface: Ethernet1}
    ```

    Equivalent using top-level keys:

    ```yaml
    devices:
    - name: branch-agg-1
      site: BRANCH-1
      role: AGGREGATION
      device_type:
        manufacturer: ACME
        model: AGG SWITCH
    interfaces:
    - type: 10gbase-x-sfpp
      name: Ethernet1
      device: branch-agg-1
    connections:
    - a_terminations:
      - device: branch-agg-1
        interface: Ethernet1
      b_terminations:
      - device: branch-router-1
        interface: Ethernet1
    ```

=== "Interface VRF"

    Prerequisites: Named site, role, manufacturer, and device type.

    A string names an existing VRF. A dictionary with fields beyond its identity is also collected as a VRF definition and deployed before interfaces.

    ```yaml
    devices:
      - name: branch-agg-1
        site: BRANCH-1
        role: AGGREGATION
        device_type: {manufacturer: ACME, model: AGG SWITCH}
        interfaces:
          Vlan100:
            type: virtual
            vrf: {name: BRANCH VRF, rd: "65100:100", description: Branch routing}
    ```

    Equivalent using top-level keys:

    ```yaml
    vrfs:
    - name: BRANCH VRF
      rd: 65100:100
      description: Branch routing
    devices:
    - name: branch-agg-1
      site: BRANCH-1
      role: AGGREGATION
      device_type:
        manufacturer: ACME
        model: AGG SWITCH
    interfaces:
    - type: virtual
      vrf:
        name: BRANCH VRF
        rd: 65100:100
      name: Vlan100
      device: branch-agg-1
    ```

=== "Untagged VLAN"

    Prerequisites: Named site, role, device type, and VLAN group.

    `untagged_vlan` identifies one VLAN by group and VID. If its dictionary also contains `name`, it becomes a VLAN definition deployed before interfaces.

    ```yaml
    devices:
      - name: branch-access-1
        site: BRANCH-1
        role: ACCESS
        device_type: {manufacturer: ACME, model: ACCESS SWITCH}
        interfaces:
          Ethernet1:
            type: 1000base-t
            untagged_vlan: {group: BRANCH VLANS, vid: 100, name: USERS}
    ```

    Equivalent using top-level keys:

    ```yaml
    vlans:
    - group: BRANCH VLANS
      vid: 100
      name: USERS
    devices:
    - name: branch-access-1
      site: BRANCH-1
      role: ACCESS
      device_type:
        manufacturer: ACME
        model: ACCESS SWITCH
    interfaces:
    - type: 1000base-t
      untagged_vlan:
        group: BRANCH VLANS
        vid: 100
      name: Ethernet1
      device: branch-access-1
    ```

=== "Tagged VLANs"

    Prerequisites: Named site, role, device type, VLAN group, and VLAN 200.

    `tagged_vlans` is a list. Entries with `name` and `vid` define VLANs. Entries with just `group` and `vid` refer to VLANs already defined elsewhere.

    ```yaml
    devices:
      - name: branch-access-1
        site: BRANCH-1
        role: ACCESS
        device_type: {manufacturer: ACME, model: ACCESS SWITCH}
        interfaces:
          Ethernet48:
            type: 10gbase-x-sfpp
            mode: tagged
            tagged_vlans:
              - {group: BRANCH VLANS, vid: 100, name: USERS}
              - {group: BRANCH VLANS, vid: 200}
    ```

    Equivalent using top-level keys:

    ```yaml
    vlans:
    - group: BRANCH VLANS
      vid: 100
      name: USERS
    devices:
    - name: branch-access-1
      site: BRANCH-1
      role: ACCESS
      device_type:
        manufacturer: ACME
        model: ACCESS SWITCH
    interfaces:
    - type: 10gbase-x-sfpp
      mode: tagged
      tagged_vlans:
      - group: BRANCH VLANS
        vid: 100
      - group: BRANCH VLANS
        vid: 200
      name: Ethernet48
      device: branch-access-1
    ```

=== "Interface BGP peering"

    Prerequisites: Named site, role, device type, remote IP, both ASNs, and the BGP plugin.

    Nesting a peering under an interface supplies `device` and `local_interface` to `create_bgp_peering`. The task resolves the local address from IPAM on that interface. Define the interface IP before the peering stage.

    ```yaml
    devices:
      - name: branch-agg-1
        site: BRANCH-1
        role: AGGREGATION
        device_type: {manufacturer: ACME, model: AGG SWITCH}
        interfaces:
          Loopback0:
            type: virtual
            ip_addresses: [{address: 192.0.2.101/32}]
            bgp_peerings:
              - name: branch-agg-1-to-branch-router-1
                remote_address: 192.0.2.102
                local_as: 65100
                remote_as: 65200
                create_reverse: false
    ```

    Equivalent using top-level keys:

    ```yaml
    devices:
    - name: branch-agg-1
      site: BRANCH-1
      role: AGGREGATION
      device_type:
        manufacturer: ACME
        model: AGG SWITCH
    interfaces:
    - type: virtual
      name: Loopback0
      device: branch-agg-1
    ip_addresses:
    - address: 192.0.2.101/32
      device: branch-agg-1
      interface: Loopback0
    bgp_peerings:
    - remote_address: 192.0.2.102
      local_as: 65100
      remote_as: 65200
      create_reverse: false
      name: branch-agg-1-to-branch-router-1
      device: branch-agg-1
      local_interface: Loopback0
    ```

=== "Power ports"

    Prerequisites: Named site, role, device type, and remote PDU outlet.

    `power_ports` is keyed by port name. A nested `connection` specifies a remote power outlet. The PDU and outlet must exist by the connections stage.

    ```yaml
    devices:
      - name: branch-router-1
        site: BRANCH-1
        role: ROUTER
        device_type: {manufacturer: ACME, model: ROUTER}
        power_ports:
          PSU1:
            type: iec-60320-c14
            connection: {device: branch-pdu-1, power_outlet: Outlet-1}
    ```

    Equivalent using top-level keys:

    ```yaml
    devices:
    - name: branch-router-1
      site: BRANCH-1
      role: ROUTER
      device_type:
        manufacturer: ACME
        model: ROUTER
    power_ports:
    - type: iec-60320-c14
      name: PSU1
      device: branch-router-1
    connections:
    - a_terminations:
      - device: branch-router-1
        power_port: PSU1
      b_terminations:
      - device: branch-pdu-1
        power_outlet: Outlet-1
    ```

=== "Console ports"

    Prerequisites: Named site, role, device type, and remote console server port.

    `console_ports` is keyed by port name. Its `connection` can name a console server port.

    ```yaml
    devices:
      - name: branch-router-1
        site: BRANCH-1
        role: ROUTER
        device_type: {manufacturer: ACME, model: ROUTER}
        console_ports:
          Console:
            type: rj-45
            connection: {device: branch-console-1, console_server_port: Line-1}
    ```

    Equivalent using top-level keys:

    ```yaml
    devices:
    - name: branch-router-1
      site: BRANCH-1
      role: ROUTER
      device_type:
        manufacturer: ACME
        model: ROUTER
    console_ports:
    - type: rj-45
      name: Console
      device: branch-router-1
    connections:
    - a_terminations:
      - device: branch-router-1
        console_port: Console
      b_terminations:
      - device: branch-console-1
        console_server_port: Line-1
    ```

=== "Power outlets"

    Prerequisites: Named site, role, device type, and remote device power port.

    `power_outlets` is keyed by outlet name. A nested `connection` can point to a device power port.

    ```yaml
    devices:
      - name: branch-pdu-1
        site: BRANCH-1
        role: PDU
        device_type: {manufacturer: ACME, model: PDU}
        power_outlets:
          Outlet-1:
            type: iec-60320-c13
            connection: {device: branch-router-1, power_port: PSU1}
    ```

    Equivalent using top-level keys:

    ```yaml
    devices:
    - name: branch-pdu-1
      site: BRANCH-1
      role: PDU
      device_type:
        manufacturer: ACME
        model: PDU
    power_outlets:
    - type: iec-60320-c13
      name: Outlet-1
      device: branch-pdu-1
    connections:
    - a_terminations:
      - device: branch-pdu-1
        power_outlet: Outlet-1
      b_terminations:
      - device: branch-router-1
        power_port: PSU1
    ```

=== "Console server ports"

    Prerequisites: Named site, role, device type, and remote device console port.

    `console_server_ports` is keyed by port name. A nested `connection` can point to a device console port.

    ```yaml
    devices:
      - name: branch-console-1
        site: BRANCH-1
        role: CONSOLE SERVER
        device_type: {manufacturer: ACME, model: TERMINAL SERVER}
        console_server_ports:
          Line-1:
            type: rj-45
            connection: {device: branch-router-1, console_port: Console}
    ```

    Equivalent using top-level keys:

    ```yaml
    devices:
    - name: branch-console-1
      site: BRANCH-1
      role: CONSOLE SERVER
      device_type:
        manufacturer: ACME
        model: TERMINAL SERVER
    console_server_ports:
    - type: rj-45
      name: Line-1
      device: branch-console-1
    connections:
    - a_terminations:
      - device: branch-console-1
        console_server_port: Line-1
      b_terminations:
      - device: branch-router-1
        console_port: Console
    ```

    Define a cable at one end only. Existing cables are patched on repeat deployment. A port already cabled to a different endpoint causes an error. The design does not disconnect it.

=== "Local context data"

    Prerequisites: Named site, role, manufacturer, and device type.

    `local_context_data` is a device-local dictionary. It is processed last, after the other nested records have been deployed. It replaces the device's previous local context.

    ```yaml
    devices:
      - name: branch-router-1
        site: BRANCH-1
        role: ROUTER
        device_type: {manufacturer: ACME, model: ROUTER}
        local_context_data:
          routing: {profile: core}
    ```

    Equivalent using top-level keys:

    ```yaml
    devices:
    - name: branch-router-1
      site: BRANCH-1
      role: ROUTER
      device_type:
        manufacturer: ACME
        model: ROUTER
    local_context_data:
    - device: branch-router-1
      site: BRANCH-1
      local_context_data:
        routing:
          profile: core
    ```

    The [configuration context section](#configuration-context) also shows how to calculate this dictionary with a custom function.

!!! warning "Interface dependency limits"

    All parent, LAG, and bridge interfaces must be defined in the design or already exist in Netbox. A newly created dependent interface cannot itself be the parent of another new interface in the same deployment, because only two passes are performed.

Device matching uses name and site, plus tenant when the design supplies one. When tenant is omitted, name and site must identify one device. An ambiguous match fails. Interfaces and IP assignments refer to a device by name, so use unambiguous device names for designs that include those nested objects.

## Nested VRRP Group Records

`vrrp_groups` supports an `assignments` list and an optional `vip`. Each assignment supplies `device`, `interface`, and `priority`. The design extracts these into `vrrp_group_assignments`, adding `protocol` and `group_id` from the parent group. The optional `vip` becomes an IP address assigned to the group, not to an individual interface.

For a top-level group, specify both `protocol` and `group_id`. Unlike the compact interface `vrrp` form, this form does not default the protocol. Groups are created before their VIP addresses and interface assignments.

=== "VRRP assignments"

    Prerequisites: both devices and their Vlan100 interfaces. The VIP is created as an IP address assigned to the group. Assignments attach that group to each interface with a priority.

    ```yaml
    vrrp_groups:
      - protocol: vrrp2
        group_id: 10
        vip: 192.0.2.1/24
        assignments:
          - {device: branch-agg-1, interface: Vlan100, priority: 200}
          - {device: branch-agg-2, interface: Vlan100, priority: 100}
    ```

    Equivalent using top-level keys:

    ```yaml
    vrrp_groups:
    - protocol: vrrp2
      group_id: 10
    ip_addresses:
    - address: 192.0.2.1/24
      fhrp_group:
        protocol: vrrp2
        group_id: 10
    vrrp_group_assignments:
    - device: branch-agg-1
      interface: Vlan100
      priority: 200
      protocol: vrrp2
      group_id: 10
    - device: branch-agg-2
      interface: Vlan100
      priority: 100
      protocol: vrrp2
      group_id: 10
    ```

=== "Allocated VIP"

    Prerequisites: both devices and their Vlan100 interfaces. This design creates the pool and group before allocating the VIP. Interface assignments remain separate from the VIP's assignment to the group.

    ```yaml
    prefixes:
      - prefix: 192.0.2.0/24
        description: Branch management subnet
    vrrp_groups:
      - protocol: vrrp2
        group_id: 20
        name: BRANCH MANAGEMENT GATEWAY
        assignments:
          - device: branch-agg-1
            interface: Vlan100
            priority: 200
          - device: branch-agg-2
            interface: Vlan100
            priority: 100
    ip_addresses:
      - create_ip:
          prefix:
            description: Branch management subnet
          description: Branch management VIP
          vrrp_group: BRANCH MANAGEMENT GATEWAY
    ```

    The group's `vip` field accepts an explicit CIDR address, not a `create_ip` wrapper. Omit `vip` when allocating the address through `ip_addresses` as above. The stable group name, prefix selection, and description let repeated deployments reuse the same VIP.

## L2VPNs and Terminations

Define L2VPNs in `l2vpns`. Like VRFs, they accept `import_route_targets` and
`export_route_targets` as lists of dictionaries with `name`. These definitions
are extracted into `route_targets` and deployed before the L2VPN. Repeating the
same target dictionary in both lists creates it once.

`terminations` under an L2VPN uses the same record shape as the top-level
`l2vpn_terminations` collection, except that the parent supplies `l2vpn`.
Each termination attaches one device interface (`device` and `interface`) or
one VLAN (`group` and `vid`). The interface or VLAN must already exist or be
defined earlier in the design. NetBox permits only one L2VPN termination per
attached object; deployment reports a conflict rather than moving an object
from another L2VPN. Omitted terminations are not deleted.

```yaml
l2vpns:
  - name: BRANCH EVPN
    type: vxlan
    identifier: 10100
    import_route_targets:
      - name: "65100:100"
    export_route_targets:
      - name: "65100:100"
    terminations:
      - device: branch-router-1
        interface: Ethernet1
      - group: BRANCH VLANS
        vid: 100

l2vpn_terminations:
  - l2vpn: BRANCH EVPN
    device: branch-router-2
    interface: Ethernet1
```

The `l2vpn_terminations` stage runs after interfaces. A dry run can report
planned terminations even when their interfaces or VLANs are also planned and
therefore have no IDs yet.

## Nested VRF Records

VRFs accept `import_route_targets` and `export_route_targets` as lists of dictionaries. These route targets become top-level definitions and are deployed before their VRF, even when only `name` is supplied. A VRF can be defined at the top level or nested under a device interface.

=== "VRF route targets"

    Prerequisites: none for these IPAM objects. Route targets are created before the VRF and associated through its import/export fields.

    ```yaml
    vrfs:
      - name: BRANCH VRF
        rd: "65100:100"
        import_route_targets:
          - name: "65100:100"
            description: Branch routes
        export_route_targets:
          - name: "65100:100"
            description: Branch routes
    ```

    Equivalent using top-level keys:

    ```yaml
    route_targets:
    - name: 65100:100
      description: Branch routes
    vrfs:
    - name: BRANCH VRF
      rd: 65100:100
      import_route_targets:
      - name: 65100:100
      export_route_targets:
      - name: 65100:100
    ```

=== "Interface VRF and route targets"

    Prerequisites: the named site, device role, manufacturer, and device type. The nested VRF and its route targets are created before the interface.

    ```yaml
    devices:
      - name: branch-router-1
        site: BRANCH-1
        role: ROUTER
        device_type: {manufacturer: ACME, model: ROUTER}
        interfaces:
          Vlan100:
            type: virtual
            vrf:
              name: BRANCH VRF
              rd: "65100:100"
              import_route_targets:
                - name: "65100:100"
              export_route_targets:
                - name: "65100:100"
    ```

    Equivalent using top-level keys:

    ```yaml
    route_targets:
    - name: 65100:100
    vrfs:
    - name: BRANCH VRF
      rd: 65100:100
      import_route_targets:
      - name: 65100:100
      export_route_targets:
      - name: 65100:100
    devices:
    - name: branch-router-1
      site: BRANCH-1
      role: ROUTER
      device_type:
        manufacturer: ACME
        model: ROUTER
    interfaces:
    - type: virtual
      vrf:
        name: BRANCH VRF
        rd: 65100:100
      name: Vlan100
      device: branch-router-1
    ```

## Nested BGP Peering Records

BGP peerings accept `import_policies` and `export_policies` as lists of routing-policy dictionaries. The design extracts these into top-level `routing_policies`, creates or updates them before BGP sessions, and associates them with the peering. Dictionaries containing only `name` are also treated as policy definitions. Strings are not supported.

This works for top-level `bgp_peerings` and peerings nested under devices or interfaces.

=== "Peering routing policies"

    Prerequisites: the device, both IP addresses, both ASNs, and the BGP plugin. Policy dictionaries are extracted and deployed before the peering. `create_reverse: false` creates only the specified direction.

    ```yaml
    bgp_peerings:
      - name: branch-to-core
        device: branch-router-1
        local_address: 192.0.2.1
        remote_address: 192.0.2.2
        local_as: 65100
        remote_as: 65200
        create_reverse: false
        import_policies:
          - name: BRANCH IMPORT
            description: Branch inbound policy
        export_policies:
          - name: BRANCH EXPORT
            description: Branch outbound policy
    ```

    Equivalent using top-level keys:

    ```yaml
    routing_policies:
    - name: BRANCH IMPORT
      description: Branch inbound policy
    - name: BRANCH EXPORT
      description: Branch outbound policy
    bgp_peerings:
    - name: branch-to-core
      device: branch-router-1
      local_address: 192.0.2.1
      remote_address: 192.0.2.2
      local_as: 65100
      remote_as: 65200
      create_reverse: false
      import_policies:
      - name: BRANCH IMPORT
      export_policies:
      - name: BRANCH EXPORT
    ```

## Configuration context

Top-level `config_context` creates or updates reusable Netbox ConfigContext objects. Its `data` is a dictionary, and its scope determines which devices receive it. Device-specific values belong in [device local context](#device-local-context).

A `custom_function` on a `config_context` record uses the same [arguments and return handling as any ordinary custom function](#custom-functions): deployment supplies `netbox` and `dry_run`, and the record supplies additional keyword arguments. It receives no device object. Its return value is recorded under `config_context.custom`, not saved as context data automatically. The function must perform its own writes. The Jinja calculation example below instead renders `data` for the normal handler to save.

=== "Shared site context"

    `config_context` matches an existing ConfigContext by `name`, creating it if absent or updating it if present. `sites` scopes the context to named sites created earlier or already in Netbox. Without a scope, the context applies globally, so specify one when the data is site-specific.

    ```yaml
    sites:
      - name: BRANCH-1
        slug: branch-1

    config_context:
      - name: BRANCH DEFAULTS
        sites: [BRANCH-1]
        data:
          routing:
            bgp:
              hold_time: 90
          ntp:
            servers: [192.0.2.10, 192.0.2.11]
    ```

    The `data` dictionary is sent to Netbox as supplied. The handler does not merge it with the previous `data` value.

=== "Calculated site context"

    This Jinja function calculates DNS and NTP server addresses from a site services subnet. It only returns a dictionary. The normal `config_context` handler creates or updates the site-scoped ConfigContext after rendering. The subnet must be supplied in `context`, because Jinja functions run before the design creates any Netbox objects.

    ```yaml
    jinja_functions:
      site_services_context: nf://netbox/designs/site_services_context.py

    sites:
      - name: BRANCH-1
        slug: branch-1

    config_context:
      - name: BRANCH SERVICES
        sites: [BRANCH-1]
        data: {{ site_services_context(context.services_prefix) | tojson }}
    ```

    Supply a context such as `{"services_prefix": "192.0.2.0/24"}`. The referenced `nf://netbox/designs/site_services_context.py` contains:

    ```python
    from ipaddress import ip_network


    def site_services_context(services_prefix):
        subnet = ip_network(services_prefix)
        if subnet.num_addresses < 8:
            raise ValueError("Services subnet needs at least eight addresses")
        return {
            "dns": {"servers": [str(subnet[2]), str(subnet[3])]},
            "ntp": {"servers": [str(subnet[4]), str(subnet[5])]},
        }
    ```

    For `192.0.2.0/24`, the function returns DNS servers `192.0.2.2` and `192.0.2.3`, plus NTP servers `192.0.2.4` and `192.0.2.5`. `tojson` renders the returned dictionary as valid YAML content. The function does not query or mutate Netbox. Calculation from objects created by the same design would require support for a deployment-time calculator inside `config_context.data`, which the handler does not currently provide.

## Device local context

`local_context_data` updates a `local_context_data` field on one device, not a reusable ConfigContext object. Both nested and top-level local context definitions run in the final deployment stage, after all other design objects have been created or updated. Custom functions can query those objects through the provided `netbox` client to calculate device context. Local context replaces the previous dictionary rather than merging with it.

!!! note "Final-stage queries and branching"

    During a normal deployment, objects from all preceding stages are available in Netbox when device-local context functions run. If `branch` was supplied to `design_deploy`, the provided `netbox` client already targets that branch. During a dry run, planned objects are not created and may be unavailable.

!!! important "Device-local context functions receive the device object"

    A function referenced **inside `local_context_data`** receives `device`, `netbox`, and `dry_run`, plus any arguments beside `custom_function`. `device` is the matched **pynetbox device object**, not its name. The function can inspect `device.id`, `device.name`, or other device fields. It must return a dictionary, which the handler writes to the device's local context.

The function receives the full device record so it can inspect fields beyond its identity. Related objects such as interfaces can be queried through `netbox`.

**Local Context Custom Function Input**

| Argument | Type | Supplied by | Meaning |
| --- | --- | --- | --- |
| `device` | `pynetbox.core.response.Record` | Deployment | Matched Netbox device object, available after earlier deployment stages. Inspect fields such as `device.id` and `device.name`. |
| `netbox` | `pynetbox.core.api.Api` | Deployment | Pynetbox client bound to the deployment's Netbox instance and branch. Use it to query the modeled device state. |
| `dry_run` | `bool` | Deployment | Whether this is a preview. The handler skips its write when `True`. The function should calculate and return data without making writes itself. |
| Other fields inside `local_context_data` | As defined in YAML | Design record | Fields beside `custom_function` are passed unchanged as keyword arguments, such as `interface` and `area` in the example below. |

`custom_function` selects the function and is not passed to it. Do not supply `device`, `netbox`, or `dry_run` inside the local-context dictionary. Outer device identity fields, such as `site` and `tenant`, select the device and are not forwarded as function arguments.

| Function outcome | Deployment behavior |
| --- | --- |
| Returns a dictionary | Writes it as the device's entire `local_context_data`, replacing the previous value. The result lists the device name under `local_context_data.updated`, not under `custom`. |
| Returns a dictionary during a dry run | Does not write it. The function runs only if the device already exists. Earlier planned objects may still be absent. |
| Returns another type, including `None` | Reports an error and stops deployment. A dictionary is required. |
| Raises an exception | Reports the failure and stops deployment. Earlier writes are not rolled back. |

=== "Device inline context"

    Prerequisites: Named site, role, manufacturer, and device type.

    Put `local_context_data` under a device for values specific to that device. The design writes it after all other object types, even though it appears inside the device record.

    ```yaml
    devices:
      - name: branch-router-1
        site: BRANCH-1
        role: ROUTER
        device_type: {manufacturer: ACME, model: ROUTER}
        local_context_data:
          routing:
            profile: core
            router_id: 192.0.2.101
    ```

    Equivalent using top-level keys:

    ```yaml
    devices:
    - name: branch-router-1
      site: BRANCH-1
      role: ROUTER
      device_type:
        manufacturer: ACME
        model: ROUTER
    local_context_data:
    - device: branch-router-1
      site: BRANCH-1
      local_context_data:
        routing:
          profile: core
          router_id: 192.0.2.101
    ```

    The dictionary is sent as-is. It replaces the device's previous local context.

=== "Calculate IS-IS NET ID"

    Prerequisites: Named site, role, manufacturer, and device type.

    Allocate a loopback IP first, then calculate the IS-IS NET ID from the address stored in Netbox. Pass the loopback interface name and IS-IS area beside `custom_function`. Local context runs last, so the function can read the address allocated earlier in the deployment.

    ```yaml
    custom_functions:
      calculate_isis_context: nf://netbox/designs/calculate_isis_context.py

    prefixes:
      - prefix: 192.0.2.0/24
        description: Branch loopback pool

    devices:
      - name: branch-router-2
        site: BRANCH-1
        role: ROUTER
        device_type: {manufacturer: ACME, model: ROUTER}
        interfaces:
          Loopback0:
            type: virtual
            ip_addresses:
              - create_ip:
                  prefix: 192.0.2.0/24
                  mask_len: 32
                  description: branch-router-2 loopback
        local_context_data:
          custom_function: calculate_isis_context
          interface: Loopback0
          area: "49.0001"
    ```

    Equivalent using top-level keys:

    ```yaml
    custom_functions:
      calculate_isis_context: nf://netbox/designs/calculate_isis_context.py
    prefixes:
    - prefix: 192.0.2.0/24
      description: Branch loopback pool
    devices:
    - name: branch-router-2
      site: BRANCH-1
      role: ROUTER
      device_type:
        manufacturer: ACME
        model: ROUTER
    interfaces:
    - type: virtual
      name: Loopback0
      device: branch-router-2
    ip_addresses:
    - create_ip:
        prefix: 192.0.2.0/24
        mask_len: 32
        description: branch-router-2 loopback
        device: branch-router-2
        interface: Loopback0
    local_context_data:
    - device: branch-router-2
      site: BRANCH-1
      local_context_data:
        custom_function: calculate_isis_context
        interface: Loopback0
        area: '49.0001'
    ```

    The referenced `nf://netbox/designs/calculate_isis_context.py` contains:

    ```python
    from ipaddress import ip_interface
    from typing import Any

    from pynetbox.core.api import Api
    from pynetbox.core.response import Record


    def calculate_isis_context(
        device: Record,
        netbox: Api,
        dry_run: bool,
        interface: str,
        area: str,
    ) -> dict[str, Any]:
        loopback = netbox.dcim.interfaces.get(
            device_id=device.id, name=interface, fields="id,name"
        )
        if loopback is None:
            raise ValueError(f"Interface not found: {device.name}:{interface}")
        addresses = list(netbox.ipam.ip_addresses.filter(
            interface_id=loopback.id, family=4, fields="id,address"
        ))
        if len(addresses) != 1:
            raise ValueError(
                f"Expected one IPv4 address on {device.name}:{interface}, "
                f"found {len(addresses)}"
            )
        address = ip_interface(addresses[0].address).ip
        digits = "".join(f"{octet:03d}" for octet in address.packed)
        system_id = ".".join(digits[index:index + 4] for index in (0, 4, 8))
        return {
            "device": device.name,
            "routing": {
                "router_id": str(address),
                "isis": {"net": f"{area}.{system_id}.00"},
            }
        }
    ```

    `create_ip` allocates a /32 from the pool and assigns it to `Loopback0`. The function reads that interface's IPv4 address and converts it into a twelve-digit system ID. For example, if the allocated address is `192.0.2.102/32`, the NET ID is `49.0001.1920.0000.2102.00`. It rejects missing or multiple IPv4 addresses rather than selecting one arbitrarily.

    Deployment supplies `device`, `netbox`, and `dry_run`. YAML supplies `interface` and `area`, not a predetermined router ID. The function only returns a dictionary. The local-context handler writes it to the device.

    During a dry run, the function is skipped if the device does not yet exist. If the device exists but its loopback or IP is only planned, the lookup fails because dry runs do not create them.

=== "Top-level device local context"

    Prerequisites: The specified device, site, and tenant.

    Use a top-level `local_context_data` list when the device is not defined under `devices` in this design. `site` and `device` identify it. Add `tenant` when needed to distinguish devices with the same name and site.

    ```yaml
    local_context_data:
      - device: branch-router-3
        site: BRANCH-1
        tenant: ACME
        local_context_data:
          routing: {profile: edge}
    ```

    A missing or ambiguous device fails outside dry-run mode. The update replaces its prior local context.

## Design Deployment Output

Results are keyed by collection. Each collection reports object identities in `created` and `updated`. No-op allocation results are omitted. Repeat deployments can report updates because existing records are sent to Netbox without a local diff.

```json
{
  "tenants": {"created": ["ACME"], "updated": []},
  "sites": {"created": ["BRANCH-1"], "updated": []}
}
```

Errors identify the collection that stopped deployment. Earlier collections are not rolled back.

## Examples

=== "CLI"

    ```bash
    nf# netbox design deploy design nf://netbox/designs/branch.yaml context '{"site":"BRANCH-1"}'
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="inventory.yaml") as nf:
        result = nf.client.run_job(
            service="netbox",
            task="design_deploy",
            workers="any",
            kwargs={
                "design": "nf://netbox/designs/branch.yaml",
                "context": {"site": "BRANCH-1"},
            },
        )
    ```

=== "FastAPI"

    Enable the Netbox service endpoints on the NorFab FastAPI worker and configure a bearer token. Send task arguments directly in the JSON body, without a `kwargs` wrapper. Replace the API address and token with your environment's values. This example deploys to branch `branch-review`, which requires Netbox branching.

    ```bash
    curl -X POST "http://localhost:8000/api/netbox/design_deploy/" \
      -H "Authorization: Bearer <TOKEN>" \
      -H "Content-Type: application/json" \
      -d '{"design":"nf://netbox/designs/branch.yaml","context":{"site":"BRANCH-1"},"branch":"branch-review","workers":"any"}'
    ```

    See [FastAPI setup and authentication](../fastapi/services_fastapi_service.md) for service configuration. Inspect the response's worker results for deployment errors.

=== "MCP"

    Connect your agent to the NorFab MCP service with the Netbox `design_deploy` tool exposed. Ask it to deploy using a chat message such as:

    ```text
    Use the NorFab Netbox design_deploy tool to instantiate the design at
    nf://netbox/designs/branch.yaml with context {"site": "BRANCH-1"}.
    Deploy to Netbox branch `branch-review`. If branching is unavailable,
    stop and ask before writing to main data. Report the deployment result
    and any errors.
    ```

    The agent should pass the file path as `design`, the dictionary as `context`, and the branch name as `branch`. The file must be accessible to the NorFab worker.

## Notes

- A dry run does not create prerequisites, so it cannot fully resolve references to objects proposed earlier in the same design.
- Explicit ASN, VLAN, and prefix records can supply object and multiobject custom-field references by related object name or ID. Names must identify exactly one existing object when that record is processed. Updates add multiobject references and other list values without removing current values; scalar and `null` values replace them. Custom-field definitions must already exist in NetBox.
- Check that named parents, device types, sites, interfaces, and allocation pools exist or are created earlier in the design order.
- Jinja filters, input models, and custom functions execute Python inside the worker. Use trusted files.
- See the [ACME design example](https://github.com/norfablabs/NORFAB/blob/main/tests/nf_tests_inventory/netbox/designs/acme_branch_network_design_v1.yaml) for a full nested design.

## Task command shell reference

```bash
nf#man tree netbox.design.deploy

R - required field, M - supports multiline input, D - dynamic key

root
└── netbox:    Netbox service
    └── design:    Deploy NetBox designs
        └── deploy:    Deploy an additive NetBox design
            ├── design (R):    NetBox design as YAML text, file URL, or parsed dictionary
            ├── context:    Template context validated by design_input_schema, default '{}'
            ├── instance:    NetBox instance name to target
            ├── dry-run:    Validate design without writing to NetBox, default 'False'
            ├── branch:    NetBox branching plugin branch name to use
            ├── timeout:    Job timeout
            ├── workers:    Filter worker to target, default 'any'
            ├── verbose-result:    Control output details, default 'False'
            └── nowait:    Do not wait for job to complete, default 'False'
nf#
```

## Python API reference

::: norfab.workers.netbox_worker.design_tasks.NetboxDesignTasks.design_deploy
