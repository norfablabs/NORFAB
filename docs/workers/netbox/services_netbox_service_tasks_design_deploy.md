---
tags:
  - netbox
---

# NetBox Design Deploy Task

> task API name: `design_deploy`

The `design_deploy` task validates and renders optional Jinja2 YAML, then applies it as additive NetBox target state. It creates missing objects, updates supplied fields, and does not delete omitted objects. See the [NetBox Design Specification](../../development/netbox_design_specification.md) for supported collections and nesting.

## Inputs

| Parameter | Required | Default | Description |
| --- | ---: | --- | --- |
| `design` | Yes | — | YAML text, `nf://` or `git://` template URL, or parsed mapping |
| `context` | No | `{}` | Input mapping, YAML text, or file URL validated by `design_input_schema` and exposed as `context` in Jinja2 |
| `instance` | No | Worker default | NetBox instance to target |
| `dry_run` | No | `False` | Render and calculate changes without applying them |
| `branch` | No | `None` | NetBox Branching plugin branch name |

## Design header

`design_input_schema` and `jinja_functions` are optional top-level sections. Put `---` after them when the design body contains Jinja2 so the engine can read the header before rendering.

The header can be placed in a reusable file and included at the start of an `nf://` or `git://` design:

```jinja2
{% include "includes/design_schema.yaml" %}
---
```

```yaml
design_input_schema:
  type: object
  additionalProperties: false
  properties:
    devices:
      type: array
      items:
        type: string
  required: [devices]

jinja_functions:
  allocate_vrf_route_target: nf://netbox/designs/functions/allocate_vrf_route_target.py
---
devices:
{% for device_name in context.devices %}
  - name: {{ device_name }}
{% endfor %}

vrfs:
  - name: CUSTOMER-A
    rd: "{{ allocate_vrf_route_target(100, rd_suffix=3) }}"
```

Inline JSON Schema is converted to a Pydantic model. `design_input_schema` may instead be an `nf://` or `git://` Python file containing a Pydantic model named `DesignInput`.

Every `jinja_functions` file must define a callable matching its mapping key:

```python
def allocate_vrf_route_target(rd_prefix: int, rd_suffix: int = 1) -> str:
    return f"{rd_prefix}:{rd_suffix}"
```

The engine also provides these functions and filters:

| Name | Purpose |
| --- | --- |
| `expand_range` | Expand strings such as `Ethernet[1-4]` |
| `netbox.create_object` | Create or update one ordinary design object before later Jinja calls use it |
| `netbox.create_prefix` | Allocate or reuse a prefix through `create_prefix` |
| `netbox.create_ip` | Allocate or reuse an IP address through `create_ip` |
| `netbox.create_vlan` | Allocate or reuse a VLAN through `create_vlan` |
| `netbox.create_vlan_group` | Create or update a site-scoped VLAN group through `create_vlan_group` |
| `netbox.create_asn` | Allocate or reuse an ASN through `create_asn` |

Relative Jinja2 includes are supported for designs loaded through `nf://` or `git://`:

```jinja2
{% include "includes/base_devices.yaml" %}
```

## Output

The result groups object labels by action. `diff` contains desired create fields and field-level old/new update values.

```python
{
    "created": {"devices": ["edge-1"]},
    "updated": {"interfaces": ["Ethernet1"]},
    "unchanged": {"sites": ["LAB-SITE"]},
}
```

## Python example

```python
result = client.run_job(
    "netbox",
    "design_deploy",
    workers="any",
    kwargs={
        "design": "nf://netbox/designs/site.yaml",
        "context": {"devices": ["edge-1", "edge-2"]},
    },
)
```

## NFCLI example

```text
nfcli> netbox design deploy design nf://netbox/designs/site.yaml context nf://netbox/designs/site-data.yaml
```

## Notes / Gotchas

- A design containing devices supplies `undefined` region, site, manufacturer, device role, and device type objects when mandatory references are omitted.
- Allocation functions execute while Jinja2 renders. Create their parent prefix, VLAN group, ASN range, and other dependencies first with ordered Jinja calls at the top of the design.
- Dry run cannot chain an allocation that depends on an object proposed earlier in the same render.
- Jinja function and Pydantic model files execute as Python in the NetBox worker. Reference only deployment-controlled files.
- Quote rendered values containing `:`, such as route distinguishers.

## Troubleshooting

- **Input validation failed:** compare `context` with `design_input_schema`.
- **Jinja function is not callable:** ensure its Python function name matches the `jinja_functions` key.
- **Unsupported design collection:** use a collection documented in the design specification.
- **Unable to resolve a reference:** create the referenced object earlier or verify its natural key.
- **Allocation pool not found:** create the parent prefix, VLAN group, or ASN range before deployment.

## Python API Reference

::: norfab.workers.netbox_worker.design_tasks.NetboxDesignTasks.design_deploy
