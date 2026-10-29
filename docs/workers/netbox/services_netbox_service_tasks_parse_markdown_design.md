---
tags:
  - netbox
---

# Markdown designs

## Overview

A Markdown design combines network design notes, structured input data and
Netbox object definitions in one readable document. The same file can explain a
network to reviewers and supply the data used to create or update its Netbox model.

This is useful for branch designs, repeatable site builds and service definitions
that need both operational context and precise object records. Store designs in
version control to review the rationale and data changes together.

Key features:

- Keep headings, diagrams and explanations alongside deployable YAML/Jinja blocks.
- Define inputs as YAML, JSON, CSV, plain text or visible Markdown tables.
- Split collections across document sections. Repeated collection names are combined.
- Validate inputs with a schema and reuse the design with different task context.
- Use file-backed Jinja functions and custom deployment functions.
- Define shared Netbox configuration context and device-local context explicitly.
- Convert without deployment, preview rendered YAML, or deploy the document directly.

The complete example below models a branch with two routers, a site, VLANs and
interfaces. It includes a schema, every supported context format, shared and
device-local configuration context, and the supporting Python functions.

There are two different kinds of context:

- Design `context` supplies values to Jinja and custom functions. Define it with
  tagged data blocks or marked Markdown tables.
- Netbox `config_context` and `local_context_data` store configuration data in
  Netbox. They only change when the design explicitly defines those collections.

## Output

`parse_markdown_design` returns `result.design` as YAML/Jinja source and
`result.context` as a dictionary. It does not render templates or deploy objects.
You can also pass a `.md` or `.markdown` file URL directly to `design_deploy`.

## Complete example

The example uses these files under the directory published by a FileSharing worker:

```text
netbox/
  designs/north_quay.md
  functions/site_description.py
  functions/ensure_operations_tenant.py
  functions/device_context.py
```

The design defines its own manufacturer, device type, device role, tenant and
site. It needs a configured Netbox worker and permission to create these objects.
The hardware names are fictional. Device configuration delivery is a separate step.

### Markdown design file

`netbox/designs/north_quay.md` contains the following document. The outer
four-backtick fence is only used to display the example on this page.

````markdown
# North Quay branch

Two branch routers share site-wide DNS and telemetry settings. Each router has
an Ethernet uplink. VLANs are recorded in the site-scoped group for later use.

## Site and shared settings

```yaml context.site
North Quay
```

```yaml context.settings
owner: Network Operations
dns_servers:
  - 192.0.2.53
  - 192.0.2.54
telemetry_enabled: true
```

```json context.labels
{"environment": "lab", "change": "CHG-1042"}
```

```text context.banner
Authorised access only.
```

## Uplink schedule

```csv context.uplinks
device,interface,description
nq-rtr-1,Ethernet1,"Primary uplink, cabinet A"
nq-rtr-2,Ethernet1,"Backup uplink, cabinet B"
```

## VLAN schedule

<!-- context.vlans -->

| name | vid |
| --- | --- |
| USERS | 100 |
| MANAGEMENT | 200 |

## Ownership and hardware

```yaml design
tenants:
  - name: Example Branches
  - custom_function: ensure_operations_tenant
    name: "{{ context.site }} Operations"
manufacturers:
  - name: Example Networks
device_types:
  - manufacturer: Example Networks
    model: Example Branch Router
device_roles:
  - name: branch-router
sites:
  - name: {{ context.site | tojson }}
    tenant: Example Branches
    description: {{ context.site | site_description | tojson }}
```

## Router 1

```yaml design
devices:
  - name: nq-rtr-1
    site: {{ context.site | tojson }}
    tenant: Example Branches
    role: branch-router
    device_type:
      manufacturer: Example Networks
      model: Example Branch Router
    status: planned
```

## Router 2

```yaml design
devices:
  - name: nq-rtr-2
    site: {{ context.site | tojson }}
    tenant: Example Branches
    role: branch-router
    device_type:
      manufacturer: Example Networks
      model: Example Branch Router
    status: planned
```

## Interfaces and VLANs

```yaml design
interfaces:
{% for uplink in context.uplinks %}
  - device: {{ uplink.device | tojson }}
    name: {{ uplink.interface | tojson }}
    type: 1000base-t
    description: {{ uplink.description | tojson }}
{% endfor %}
vlan_groups:
  - name: "{{ context.site }} VLANS"
    site: {{ context.site | tojson }}
vlans:
{% for vlan in context.vlans %}
  - name: {{ vlan.name | tojson }}
    vid: {{ vlan.vid | int }}
    group: "{{ context.site }} VLANS"
{% endfor %}
```

## Shared configuration context

```yaml design
config_context:
  - name: "{{ context.site }} baseline"
    is_active: true
    weight: 1000
    sites:
      - {{ context.site | tojson }}
    data:
      dns_servers: {{ context.settings.dns_servers | tojson }}
      telemetry_enabled: {{ context.settings.telemetry_enabled | tojson }}
      labels: {{ context.labels | tojson }}
      banner: {{ context.banner | tojson }}
```

## Device-local configuration context

Router 1 uses a static dictionary. Router 2 calls a function to calculate its data.
Existing device-local context is replaced by these values.

```yaml design
local_context_data:
  - device: nq-rtr-1
    site: {{ context.site | tojson }}
    tenant: Example Branches
    local_context_data:
      profile: primary
      uplink: Ethernet1
      managed: true
  - device: nq-rtr-2
    site: {{ context.site | tojson }}
    tenant: Example Branches
    local_context_data:
      custom_function: device_context
      profile: standby
```

## Input schema and functions

Metadata can appear at the end. Conversion places it before the collections.
The schema validates context when design_deploy prepares the design.

```yaml design
design_input_schema:
  type: object
  additionalProperties: false
  required: [site, settings, labels, banner, uplinks, vlans]
  properties:
    site:
      type: string
      minLength: 1
    settings:
      type: object
      required: [owner, dns_servers, telemetry_enabled]
      properties:
        owner: {type: string}
        dns_servers:
          type: array
          items: {type: string}
        telemetry_enabled: {type: boolean}
    labels:
      type: object
      required: [environment, change]
      properties:
        environment:
          type: string
          pattern: '^(lab|production)$'
        change: {type: string}
    banner:
      type: string
    uplinks:
      type: array
      items:
        type: object
        required: [device, interface, description]
        properties:
          device: {type: string}
          interface: {type: string}
          description: {type: string}
    vlans:
      type: array
      items:
        type: object
        required: [name, vid]
        properties:
          name: {type: string}
          vid:
            type: string
            pattern: '^[0-9]+$'
jinja_functions:
  site_description: nf://netbox/functions/site_description.py
custom_functions:
  ensure_operations_tenant: nf://netbox/functions/ensure_operations_tenant.py
  device_context: nf://netbox/functions/device_context.py
```
````

The two `devices:` sections become one collection, in document order. The VLAN
and interface loops consume context rows. `tojson` safely quotes strings and
preserves lists, dictionaries and booleans as YAML-compatible values.

### Supporting function files

Save this as `netbox/functions/site_description.py`. Registered Jinja functions
can be used as filters or called directly during rendering:

```python
def site_description(site):
    """Build the standard site description."""
    return f"Branch infrastructure at {site}"
```

Save this as `netbox/functions/ensure_operations_tenant.py`. A collection custom
function receives its record arguments plus `context`, `netbox` and `dry_run`.
The supplied Netbox client already uses the selected instance and branch.

```python
from norfab.utils.text import slugify


def ensure_operations_tenant(context, netbox, dry_run, name):
    """Create or update the operations tenant without writing during dry runs."""
    fields = {"description": f"Owned by {context['settings']['owner']}"}
    tenant = netbox.tenancy.tenants.get(name=name)
    if not dry_run:
        if tenant:
            tenant.update(fields)
        else:
            netbox.tenancy.tenants.create(name=name, slug=slugify(name), **fields)
    return {"name": name, "dry_run": dry_run}
```

Save this as `netbox/functions/device_context.py`. Device-local functions also
receive the matched device and must return a dictionary:

```python
def device_context(device, context, netbox, dry_run, profile):
    """Calculate device-local data without modifying Netbox."""
    return {
        "hostname": device.name,
        "profile": profile,
        "site": context["site"],
        "change": context["labels"]["change"],
    }
```

Collection functions must implement their own repeat-deployment behaviour and
honour `dry_run`. Device-local functions are skipped for new devices during a
write-free deployment preview because those device records do not exist yet.
Only load function files you trust. The worker executes Python from those files.

## Deployment and previews

Use the same Markdown file URL for each step. Explicit task context overrides
document context by top-level key. Overriding `settings` replaces its whole
mapping. Supply all required settings when doing so.

=== "CLI"

    Use the existing deployment command from the NFCLI shell:

    ```bash
    nf# netbox design deploy design nf://netbox/designs/north_quay.md dry-run-render
    nf# netbox design deploy design nf://netbox/designs/north_quay.md dry-run
    nf# netbox design deploy design nf://netbox/designs/north_quay.md
    ```

=== "Python"

    ```python
    from pathlib import Path
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="inventory.yaml") as nf:
        client = nf.make_client()
        # Start with rendered YAML. Run again with dry_run=True to plan writes.
        # Remove the preview flag only when ready to create or update objects.
        response = client.run_job(
            "netbox", "design_deploy", workers="any",
            kwargs={
                "design": "nf://netbox/designs/north_quay.md",
                "dry_run_render": True,
            },
        )
        for result in response.values():
            if result["failed"]:
                raise RuntimeError(result["errors"])
            Path("north_quay.rendered.yaml").write_text(
                result["result"], encoding="utf-8"
            )
    ```

- `dry_run_render` validates inputs and runs rendering functions. It returns YAML
  before object validation or deployment. Review the saved YAML first.
- `dry_run` validates the design and returns planned writes. It can still query
  Netbox. Custom functions must honour this mode.
- Omit both flags to create or update objects. Omitted objects are not deleted.

Run these steps separately when reviewing a real change. For additional
isolation, supply a dedicated `branch` when
using a Netbox instance with the Branching plugin.

To inspect conversion without rendering or loading functions, call
`parse_markdown_design` with `kwargs={"markdown": "nf://netbox/designs/north_quay.md"}`.
Read `result.design` and `result.context` from each worker result.

## Encode context with Markdown tables

Place `<!-- context.KEY -->` on its own line before an unfenced table, as shown
for `context.vlans` above. The comment stays hidden in previews. Table headers
become dictionary keys and each row becomes one dictionary:

```yaml
vlans:
  - name: USERS
    vid: "100"
  - name: MANAGEMENT
    vid: "200"
```

CSV and Markdown cells remain strings. The example schema checks that VIDs
contain digits and the design converts them with `int`. Plain-text headers and
cells are easiest to use. Formatting such as backticks remains in the data.

## Context definitions

Each definition assigns one top-level context key. These snippets show all
supported formats using values from the complete example.

=== "YAML"

    Use YAML for typed scalars, lists and dictionaries. Numbers and booleans keep
    their types. This block defines `context.settings`:

    ````markdown
    ```yaml context.settings
    owner: Network Operations
    dns_servers:
      - 192.0.2.53
      - 192.0.2.54
    telemetry_enabled: true
    ```
    ````

=== "JSON"

    JSON also preserves types. This block defines `context.labels`:

    ````markdown
    ```json context.labels
    {"environment": "lab", "change": "CHG-1042"}
    ```
    ````

=== "CSV"

    The header row supplies dictionary keys. Each following row becomes a
    dictionary in `context.uplinks`. All cell values are strings:

    ````markdown
    ```csv context.uplinks
    device,interface,description
    nq-rtr-1,Ethernet1,"Primary uplink, cabinet A"
    nq-rtr-2,Ethernet1,"Backup uplink, cabinet B"
    ```
    ````

=== "Markdown table"

    Place the hidden comment before a normal, unfenced table. Each data row
    becomes a dictionary in `context.vlans`. VIDs remain strings:

    ```markdown
    <!-- context.vlans -->

    | name | vid |
    | --- | --- |
    | USERS | 100 |
    | MANAGEMENT | 200 |
    ```

=== "Plain text"

    The entire block becomes one string in `context.banner`, including its final
    newline. Jinja expressions inside it remain literal text:

    ````markdown
    ```text context.banner
    Authorised access only.
    ```
    ````

## Authoring rules

- Define each context key once. Nested destinations such as `context.site.name`
  are unsupported. Nested values inside a YAML or JSON block are allowed.
- YAML context must be JSON-serializable. Quote numeric mapping keys. Avoid
  binary values and sets.
- Keep table headers unique and nonempty. CSV row widths are checked. Markdown
  parsing pads missing cells and ignores extra cells, so check your table widths.
- Put each metadata key in only one design block. Inline collection values such
  as `devices: []` are unsupported. Indent collection items and multiline values.
- Keep Jinja loops and variables inside one section. Regrouping can move sections.
  Context data is never rendered as Jinja.
- Unmarked examples, tables and prose are ignored. Close fences explicitly to
  avoid accidentally including later prose in the design.
- Relative includes resolve from the Markdown file's directory when deploying
  its URL. Converted source text alone does not retain that directory.

For collection details and deployment behaviour, see
[Deploy a Netbox design](services_netbox_service_tasks_design_deploy.md).

## Python API Reference

::: norfab.workers.netbox_worker.design_tasks.NetboxDesignTasks.parse_markdown_design
