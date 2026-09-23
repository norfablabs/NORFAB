# NetBox Design Specification

## Status

This document defines the NetBox design format implemented by `design_deploy`. Global collections remain the general form. The implemented nested forms are listed below; other relationships continue to use their global collections until added explicitly.

## Goals

The format must:

- describe additive NetBox target state in one YAML schema;
- follow NetBox object and field names where practical;
- support both global objects and concise nested relationships;
- accept fully static YAML without Jinja2;
- optionally use Jinja2 for loops, conditions, calculations, and allocations;
- use existing NetBox fields and relationships to make allocations idempotent;
- call dedicated NetBox worker tasks where they exist;
- create missing objects and update supplied fields without deleting omitted objects.

The design engine must not introduce a second allocation language, allocation keys, reference syntax, or a flattened intermediate YAML format.

## Input processing

`design` accepts either a parsed mapping or YAML text loaded inline, through `nf://`, or through `git://`. `context` contains user input exposed through the Jinja2 `context` variable.

1. The engine reads the optional top-level `design_input_schema` and `jinja_functions` sections.
2. It validates `context` before rendering.
3. Text is optionally rendered with Jinja2 and then parsed as YAML.
4. The metadata sections are removed from the rendered document.
5. The engine walks the target state and calls the appropriate NetBox tasks.

A rendered template and an equivalent static document have identical meaning.

## Design input contract

An inline JSON Schema documents and validates the context expected by a design. When the body contains Jinja2, separate the metadata header from the target-state document with `---` so the header can be read before rendering:

```yaml
design_input_schema:
  type: object
  additionalProperties: false
  properties:
    devices:
      type: array
      items:
        type: string
      minItems: 1
  required:
    - devices
---
devices:
{% for device_name in context.devices %}
  - name: {{ device_name }}
{% endfor %}
```

The engine generates a Pydantic `DesignInput` model from the JSON Schema and validates `context` before passing it to Jinja2. For example, `context: {site: BRANCH-001}` is referenced as `{{ context.site }}`.

For contracts that need Pydantic validators or Python types, reference an `nf://` or `git://` Python file instead:

```yaml
design_input_schema: nf://netbox/designs/models/device_design_input.py
---
devices:
{% for device_name in context.devices %}
  - name: {{ device_name }}
{% endfor %}
```

The referenced file must define a Pydantic model named `DesignInput`:

```python
from pydantic import BaseModel, ConfigDict


class DesignInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    devices: list[str]
```

Both metadata sections are optional. A static design can omit them and supply NetBox collections directly.

The metadata header may be shared through a relative Jinja2 include when the design is loaded through `nf://` or `git://`:

```jinja2
{% include "includes/branch_office_design_schema.yaml" %}
---
# Target-state collections follow.
```

The engine resolves this header include before validating `context`, then renders the complete design.

## Global collections

Top-level collections define shared or standalone NetBox objects. Examples include:

```yaml
sites:
  - name: LAB-SITE
    status: active

roles:
  - name: Access
    slug: access

prefixes:
  - prefix: 10.1.0.0/24
    site: LAB-SITE
    role: Access

vlans:
  - name: Users
    group: LAB VLAN POOL
    vid: 100

ip_addresses:
  - address: 192.0.2.10/32
    description: Shared service address

route_targets:
  - name: "65000:100"

bgp_sessions:
  - name: edge-1-upstream
    device: edge-1
    local_address: 192.0.2.1
    local_as: 65001
    remote_address: 192.0.2.2
    remote_as: 64496
```

Global collections remain valid even when the same object type is also accepted in a nested location.

## Nested relationships

Nesting removes repeated parent identifiers where ownership or association is clear. Object fields otherwise retain their NetBox names.

The initial nested relationships are:

| Parent | Nested field | Inferred relationship |
| --- | --- | --- |
| Device | `interfaces` | Interface `device` |
| Device | `bgp` or `bgp_sessions` | BGP device and local context |
| Interface | `ip_addresses` | IP assigned object |
| Interface | `mac_addresses` | MAC assigned object |
| Interface | `untagged_vlan` | Interface access VLAN |
| Interface | `tagged_vlans` | Interface tagged VLANs |
| Prefix | `ip_addresses` | Parent prefix without interface assignment |
| VRF | `import_targets` | Imported route targets |
| VRF | `export_targets` | Exported route targets |

Nested objects use the same natural identity as global objects. Declare an object either globally or in its nested location. The current executor concatenates both forms and does not merge duplicate declarations before preparing create and update batches.

`devices[].bgp.local_as` supplies a default to sessions under `bgp.sessions`; it is not written as a device field because NetBox has no direct device-to-ASN field. A session may override it. `devices[].bgp_sessions` is an equivalent direct list without shared BGP defaults.

## Static design example

```yaml
sites:
  - name: LAB-SITE
    status: active

roles:
  - name: Access
    slug: access

prefixes:
  - prefix: 10.1.0.0/24
    status: active
    site: LAB-SITE
    role: Access

vlans:
  - name: Users
    group: LAB VLAN POOL
    vid: 100

route_targets:
  - name: "65000:100"

vrfs:
  - name: CUSTOMER-A
    import_targets:
      - name: "65000:100"
    export_targets:
      - name: "65000:100"

devices:
  - name: edge-1
    site: LAB-SITE
    bgp:
      local_as: 65001
    interfaces:
      - name: Ethernet1
        type: 1000base-t
        mode: tagged
        untagged_vlan:
          group: LAB VLAN POOL
          vid: 100
        tagged_vlans:
          - group: LAB VLAN POOL
            vid: 200
        mac_addresses:
          - mac_address: 02:00:00:00:00:01
        ip_addresses:
          - address: 10.1.0.1/24
            status: active
```

An IP address that does not belong to an interface can be global or nested under its prefix:

```yaml
prefixes:
  - prefix: 198.51.100.0/24
    role: Services
    ip_addresses:
      - address: 198.51.100.10/24
        description: Service VIP
```

## Jinja2

Jinja2 is optional helper syntax. It may reduce repetition or calculate concrete values, but it does not change the YAML schema.

Templates loaded through `nf://` or `git://` support relative includes:

```jinja2
{% include "includes/base_devices.yaml" %}
```

Custom callables belong to the design. Each `jinja_functions` key must match a callable in the referenced Python file. The callable is available as a direct Jinja function and as a filter:

```yaml
jinja_functions:
  allocate_vrf_route_target: nf://netbox/designs/functions/allocate_vrf_route_target.py
---
vrfs:
  - name: CUSTOMER-A
    rd: "{{ allocate_vrf_route_target(100, rd_suffix=3) }}"
```

```yaml
devices:
{% for number in range(1, 3) %}
  - name: edge-{{ number }}
    interfaces:
      - name: Ethernet1
        type: 1000base-t
{% endfor %}
```

The engine exposes NetBox allocation helpers as callable functions and as filters for chaining. Both forms call the same implementation.

`netbox.create_object(collection, **fields)` applies one ordinary design object immediately and returns its natural identifier. Put ordered calls at the top of a template when later allocation calls require hierarchy objects or pools created by the same design.

```jinja2
{{ netbox.create_prefix(
     parent="10.0.0.0/8",
     prefixlen=24,
     description="LAB access"
   ) }}
```

Equivalent filter form:

```jinja2
{{ "10.0.0.0/8" | netbox.create_prefix(
     "LAB access",
     prefixlen=24
   ) }}
```

## Allocations

Allocation helpers create or find a NetBox object while Jinja2 renders and return a concrete value suitable for YAML. They use dedicated worker tasks such as `create_prefix`, `create_ip`, `create_vlan`, and `create_asn`.

An allocation must search for its previous result before taking the next available value. Identification uses ordinary NetBox fields and relationships:

- IP address: device and interface assignment, or description within a prefix;
- prefix: parent and description, optionally scoped by VRF or other supplied fields;
- VLAN: group and name;
- ASN: description or its existing BGP relationship;
- MAC address: its address and assigned interface; deterministic Jinja functions may calculate the address;
- VRRP group: protocol and group ID, or name where supported;
- route target: value, description, or VRF association;
- BGP community: value, name, description, or BGP association.

If supplied fields match multiple objects, the allocation must fail. A repeated call must return the existing value instead of consuming another one.

### Inline allocations

Place a single-use allocation where its concrete result is consumed:

```yaml
devices:
  - name: edge-1
    bgp:
      local_as: >-
        {{ netbox.create_asn(
             asn_range="PRIVATE ASN POOL",
             description="edge-1 local ASN"
           ) }}
    interfaces:
      - name: Ethernet1
        type: 1000base-t
        mode: access
        untagged_vlan:
          group: LAB VLAN POOL
          vid: >-
            {{ netbox.create_vlan(
                 vlan_group="LAB VLAN POOL",
                 name="Users"
               ) }}
        ip_addresses:
          - address: >-
              {{ netbox.create_ip(
                   prefix="LAB access",
                   description="edge-1 Ethernet1",
                   create_peer_ip=false
                 ) }}
```

The nesting supplies the final relationships. For example, the engine assigns the rendered IP address to `edge-1:Ethernet1` and applies the rendered VLAN as its untagged VLAN.

### Reused allocations

Assign a reused result to a Jinja2 variable:

```yaml
{% set customer_rt = 100 | allocate_route_target(
  description="CUSTOMER-A route target"
) %}

vrfs:
  - name: CUSTOMER-A
    import_targets:
      - name: "{{ customer_rt }}"
    export_targets:
      - name: "{{ customer_rt }}"
```

Prefix allocation can similarly feed an IP allocation and a concrete prefix declaration:

```yaml
{% set access_prefix = netbox.create_prefix(
  parent="10.0.0.0/8",
  prefixlen=24,
  description="LAB access"
) %}

prefixes:
  - prefix: "{{ access_prefix }}"
    site: LAB-SITE
    role: Access
    description: LAB access

devices:
  - name: edge-1
    site: LAB-SITE
    interfaces:
      - name: Ethernet1
        ip_addresses:
          - address: >-
              {{ netbox.create_ip(
                   prefix=access_prefix,
                   description="edge-1 Ethernet1",
                   create_peer_ip=false
                 ) }}
```

The prefix declaration has a separate purpose from allocation: it reconciles fields such as site, role, status, tenant, and custom fields.

## NetBox field mappings

The YAML uses friendly natural references where the NetBox REST API requires IDs or generic assignments:

- `prefix.site` resolves the site name and writes NetBox 4 `scope_type: dcim.site` and `scope_id`;
- nested interface IP and MAC addresses write `assigned_object_type` and `assigned_object_id`;
- `untagged_vlan` and `tagged_vlans` accept VLAN identity fields such as `group` and `vid`, then write VLAN IDs;
- VRF `import_targets` and `export_targets` accept route-target names, then write route-target IDs.

NetBox 4 models MAC addresses as objects. Use `mac_addresses` under an interface rather than the removed interface `mac_address` scalar.

## Dependency and application order

Allocation pools must exist before template rendering. This includes parent prefixes, VLAN groups, and ASN ranges used by allocation helpers.

Objects referenced only when applying target state may be created by the same design. For example, a design may create a site and prefix role, allocate a prefix during rendering, and then associate that prefix with the new site and role during deployment.

The engine applies objects in dependency order, including:

1. regions, sites, roles, tenants, manufacturers, device roles, and device types;
2. prefixes, VLANs, ASNs, route targets, and VRFs;
3. racks and devices;
4. interfaces;
5. IP and MAC assignments, VLAN membership, VRRP assignments, connections, and BGP sessions.

Dedicated tasks take precedence over generic CRUD when they provide the required behavior.

## Additive behavior

The design is a source of truth for every supplied field:

- missing objects are created;
- differing supplied fields are updated;
- omitted fields are left unchanged;
- objects omitted from a later design are not deleted;
- nested child lists are additive unless a field explicitly represents complete membership.

`custom_fields` may be supplied on any object that supports them in NetBox.

Mandatory device references omitted by a design use the managed `undefined` site, region, manufacturer, role, or device type. These defaults are concrete target-state values. A site declared without a region similarly receives the `undefined` region.

## Dry run

Dry run accurately compares static designs. Allocation helpers receive `dry_run=True` and do not write their proposed object. A chained allocation that depends on that proposed object cannot complete because the intermediate object does not exist. Use dry run with static designs or templates whose allocations already exist.

Allocation task changes occur while Jinja2 renders and are not included in the design executor's `created`, `updated`, or `diff` collections. Those collections describe the rendered target-state reconciliation.

## Validation and errors

The engine must fail with a clear error when:

- a collection or nested relationship is unsupported;
- an object lacks enough fields to determine its NetBox identity;
- a reference resolves to no object after its creation phase;
- a reference or allocation lookup is ambiguous;
- an allocation pool does not exist;
- a Jinja function cannot be loaded or is not callable;
- `context` fails its declared input contract.

Errors should identify the collection, parent object where applicable, and relevant natural-key fields.

## Tested design progression

The integration suite deploys each design to NetBox and repeats deployment to verify idempotency:

| Design | Syntax | Shape | Coverage |
| --- | --- | --- | --- |
| `includes/base_devices.yaml` | Jinja2 include | Global | Included `base_design_schema.yaml`, device rendering, and managed `undefined` defaults |
| `pydantic_input_design.yaml` | Jinja2 include | Global | External Pydantic input contract |
| `device_interfaces_design.yaml` | Jinja2 | Global | Device and interface expansion |
| `static_nested_design.yaml` | Static | Global and nested | Sites, roles, prefixes, route targets, VRFs, access/tagged VLANs, interfaces, and assigned/unassigned IPs |
| `allocations_design.yaml` | Jinja2 | Global and nested | Prefix, IP, VLAN, and ASN allocation; design-owned route target and MAC functions; nested BGP and interface assignments |
| `jinja_functions_design.yaml` | Jinja2 | Global | Design-owned Jinja function loading and keyword arguments |
| `infrastructure_connections_design.yaml` | Static | Global | Regions, sites, locations, racks, interfaces, and connections |
| `network_services_design.yaml` | Static | Global | BGP sessions, L2VPNs, VRRP groups, and assignments |
| `branch_office_design.yaml` | Jinja2 | Global and nested | Included input contract; allocated prefixes, VLANs, ASNs, IPs, RDs, route targets, and MACs; BGP, cabling, and VRRP |
| `data_center_leaf_spine_design.yaml` | Jinja2 | Global and nested | Two spines, three leaves, site-scoped loopback/link/ASN allocation, routed interfaces, cabling, and underlay eBGP |

The implementation walks nested input and schedules child objects through the same collection executor used by global objects. It does not render or expose a second flattened YAML document.

## Complete branch-office example

`tests/nf_tests_inventory/netbox/designs/branch_office_design.yaml` is the canonical complete example. It uses neutral site and vendor names. The design demonstrates:

- region, site, equipment-room, rack, manufacturer, device-type, and role creation;
- two redundant routers and two access switches distributed between two racks;
- prefix, VLAN, ASN, IP, RD, route-target, and MAC allocation;
- site-scoped prefix, VLAN-group, and ASN-range selection;
- subdivision of one site prefix into links, loopbacks, management, voice, corporate, and internet pools;
- global VRF, VRRP, BGP-session, and physical-connection definitions;
- nested router and switch interfaces;
- access and tagged VLAN membership;
- interface VRF assignment and nested IP addressing;
- Jinja2 loops for repeated infrastructure without changing the resulting schema;
- an idempotent second deployment with no creates or updates.

Deploy the example through the normal task API:

```python
result = client.run_job(
    "netbox",
    "design_deploy",
    workers="any",
    kwargs={
        "design": "nf://netbox/designs/branch_office_design.yaml",
        "context": {
            "site": "BRANCH-001",
            "prefix": "10.60.0.0/16",
            "asn_range": "BRANCH-ASNS",
            "rir": "BRANCH-001-RIR",
            "rd_prefix": 65000,
            "asn_start": 4200101000,
            "asn_end": 4200101099,
        },
    },
)
```

At the top of the template, ordered `netbox.create_object` calls create the region, site, IP roles, RIR, site-scoped ASN range, and top-level prefix before allocation calls run. The existing `netbox.create_vlan_group` task then creates the site-scoped VLAN group. The top-level prefix is selected by its address and site scope; allocated child prefixes are reused by site scope and role. The design divides the supplied prefix into `/24` pools for links, loopbacks, management, voice, corporate, and internet use. It allocates two router ASNs and the required interface addresses. Device names, descriptions, BGP sessions, connections, and VRRP groups include the site name. Allocated VLAN IDs also supply the subinterface and VRRP group numbers. Repeated calls use the same object identifiers and therefore resolve to the same allocation. The included `branch_office_design_schema.yaml` validates all seven inputs and declares the route-target and MAC Jinja functions.

The four services are `MGMT`, `VOICE`, `CORP`, and `INTERNET`.

## Data-center leaf-spine example

`tests/nf_tests_inventory/netbox/designs/data_center_leaf_spine_design.yaml` models a production-style routed fabric with two spines and three leaves. It creates five switches across dedicated spine and leaf racks, allocates one loopback and ASN per switch, allocates six `/31` point-to-point prefixes and twelve endpoint addresses, cables every leaf to both spines, and creates directional underlay eBGP sessions on both endpoints.

The site, site-scoped loopback and fabric prefixes, and site-scoped ASN range must exist before rendering:

```python
result = client.run_job(
    "netbox",
    "design_deploy",
    workers="any",
    kwargs={
        "design": "nf://netbox/designs/data_center_leaf_spine_design.yaml",
        "context": {
            "site": "DC-001",
            "fabric_prefix": "10.70.0.0/16",
            "loopback_prefix": "10.71.0.0/24",
            "asn_range": "DC-FABRIC-ASNS",
        },
    },
)
```

