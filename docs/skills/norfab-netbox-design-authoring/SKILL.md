---
name: norfab-netbox-design-authoring
description: Author and review NorFab Netbox YAML/Jinja2 designs for design_deploy, including topology, IPAM, BGP, and configuration context. Use when translating network requirements into a reusable design or preparing an authorized preview or deployment.
---

# Author a NorFab Netbox design

Produce reviewable YAML and its input context. Deploy only when requested.
This models Netbox data. Applying device configuration is separate.

## Follow the core rules

The design MUST be as simple, linear, and minimal as possible while meeting all
requirements. Keep it readable from top to bottom without tracing template abstractions.

### Show the topology

- Nest interfaces and ports under devices.
- Nest addresses and peerings under interfaces.
- Define each cable once.
- Add Mermaid or ASCII diagrams when they clarify the design.
- Keep diagrams alongside design notes and consistent with the YAML.

### Keep YAML explicit and Jinja2 small

- You MUST NOT use Jinja2 macros.
- Use expanded YAML mappings.
- Use simple loops for repeated devices.
- Avoid large template data structures and indirect control flow.
- Avoid unnecessary calculations.
- Move complex lookups or logic into approved Python only when built-ins fall short.

### Use built-in allocation

- Use NorFab tasks for next-available resources.
- Use explicit records for agreed fixed values.
- Never guess allocated values.
- Never recreate allocation logic in templates.

### Make names and inputs meaningful

- Put values that vary between deployments in `context`, including device names.
- Use consistent names.
- Keep allocation descriptions stable.
- Ask for missing network decisions instead of inventing them.

### Include only required intent

- Add only necessary objects and context.
- Comment on design choices and exceptions.
- List existing prerequisites.
- Identify unresolved relationships.

## Read the documentation

Start with this skill. Consult the comprehensive
[design deployment documentation](https://docs.norfablabs.com/workers/netbox/services_netbox_service_tasks_design_deploy/)
or other external references only when stuck or when this skill lacks information
needed to complete the design. Read only the sections that resolve the gap.

Documentation and external links can consume substantial context. Search for
specific headings or arguments and fetch short excerpts first. Do not load entire
pages, source files, or linked examples by default, or follow links recursively.
Before loading a large reference, explain why it is needed and seek the user's
approval when feasible, unless that reading is already authorized.

- [Complete ACME design](https://github.com/norfablabs/NORFAB/blob/master/tests/nf_tests_inventory/netbox/designs/acme_branch_network_design_v1.yaml)
  for worked patterns. Adapt the relevant parts, not its names or addresses.
- [Design source](https://github.com/norfablabs/NORFAB/blob/master/norfab/workers/netbox_worker/design_tasks.py)
  when the documentation leaves behavior unclear. Trace `flatten_design`,
  validation, and the relevant handler together before drawing conclusions.
- [Input and design models](https://github.com/norfablabs/NORFAB/blob/master/norfab/workers/netbox_worker/netbox_models.py)
  when checking accepted fields and task arguments.

Use documentation and source matching the target worker version where available.
Check the connected tool's schema before execution. Flag required capabilities
that remain unverified.

## Collections and allocation arguments

Use the deployment reference for supported collections and processing order.
YAML key order does not control deployment. New devices default to planned
status. Omitted status preserves an existing device's status.

| Wrapper | Placement | Key arguments |
| --- | --- | --- |
| `create_prefix` | `prefixes` | `parent` CIDR or filters, `prefixlen`, stable `description`. Optional child `site`, `role`, `vrf`. |
| `create_ip` | `ip_addresses`, including nested interface lists | `prefix` CIDR or filters, stable `description`, optional `mask_len`. |
| `create_vlan` | `vlans` | `vlan_group`, stable `name`. Reuses by name within the group. |
| `create_asn` | `asns`, BGP `local_as`/`remote_as` | `asn_range` name, stable `description`. Ranges are not site-scoped. |
| `move_ip` | `ip_addresses`, including nested interface lists | `from_device`, `from_interface`, destination `device`/`interface`, optional `is_primary`. Nested placement supplies the destination. |

## Establish the design boundary

Gather the target Netbox instance and branch, site and tenant, device names and
types, topology, approved address pools, VLAN groups, ASNs, and any required
configuration context. Distinguish objects the design owns from existing objects
it references. Matching existing objects can update data created by another design.

Ask only for missing decisions that affect identity, allocation, or connectivity.
Do not invent production addresses, VLAN IDs, ASNs, credentials, or device models.
Record agreed assumptions and identify unresolved requirements in the draft.

Prefer a branch when the Netbox Branching plugin is available. Confirm the target
branch before execution and pass it through `branch`. If branching is unavailable,
explain that deployment changes main data directly and suggest enabling branching
for separate review. Do not silently fall back from a branch to main.

## Build readable YAML

1. Use one YAML document. Put optional `design_input_schema` and `jinja_functions`
   first as valid YAML without Jinja expressions or directives. Keep validation
   proportionate and honor requests to omit it.
2. Use supported top-level collections containing lists of dictionaries. The
   engine's dependency order determines writes, not YAML key order.
3. Nest interfaces and ports under their devices as mappings keyed by component
   name. Nest `ip_addresses` and `bgp_peerings` as lists under their interfaces.
   Use `connection` for a nested cable. Nesting supplies device/interface references.
4. Use documented name shorthands only. Prefer the unambiguous device-type form
   `{manufacturer: ACME, model: ROUTER}`. Every VLAN requires a VLAN group. Define
   prerequisites or list them as required existing objects.
5. Parent, LAG, and bridge interfaces must exist or be defined in the design.
   Avoid dependencies requiring more than two interface creation passes.
6. Use separate loops for groups such as spines and leaves. Keep object
   definitions in their YAML collections. Compact pairs are suitable for VLAN ranges.
   Quote template values safely, for example with `{{ context.site | tojson }}`.
   Inputs containing quotes must still produce valid YAML.
7. Shared context belongs in `config_context`, device-specific context in
   `local_context_data`. These dictionaries replace existing values. Stored
   context does not configure devices.

## Allocate addresses and define peerings

- Use the agreed address pools. Make each pool lookup specific enough to select one pool.
- Keep allocation names and descriptions unchanged so repeat runs reuse the same resources.
- Include resources created by allocation, such as child prefixes, in the design's ownership.
- Put interface IP allocations under that interface's `ip_addresses`.
- On a point-to-point cable, use `create_peer_ip: true` at one end to allocate both addresses.
- Use the allocated addresses in later lookups. Never guess what the allocator will choose.
- Designs create one BGP direction by default. Set `create_reverse: true` to create both.
- Check the task documentation for VLAN associations, VRRP VIPs, ASN allocation,
  and dual-stack BGP before using those features.

## Resolve gaps before adding custom code

When built-ins cannot express required behavior, choose Python by execution stage:

| Mechanism | Use and timing | Arguments and behavior |
| --- | --- | --- |
| `jinja_functions` | Filters or template globals for transformations and existing-data lookups during rendering. | Pass arguments explicitly, including `netbox` when needed. Return template values. Never write or allocate, or depend on objects this deployment has yet to create. |
| `custom_functions`, called with `custom_function` | Deployment logic after ordinary records in its collection. Can use objects already created in earlier stages and perform custom writes. | Receives `context`, `netbox`, `dry_run`, and record arguments. Honor `dry_run` and make repeat runs safe. Returns are reports, not automatic references. Device-local context functions instead return the context dictionary. |

Do not silently omit required relationships or present incomplete modeling as
functional. Explain the precise gap and agree whether to use explicit values,
defer it, or extend the worker. Label deferred requirements in delivery notes.

Before adding a custom Jinja2 filter, Python helper, or deployment function,
obtain explicit approval for that implementation unless already authorized.
Explain the missing behavior, which built-in tasks and YAML alternatives were
checked with supporting documentation or source, why they fall short, what the
code would read or write and when, added files or dependencies, and alternatives
with their tradeoffs. Wait for approval before creating or invoking the code.
Continue independent work using supported features while approval is pending.

Use trusted Python files without embedded credentials. Preview modes still
execute Python and are not a security boundary.

## Review, preview, and deploy within scope

Review identities, references, plugin requirements, allocation scope, duplicate
cables, BGP direction, and prerequisites before execution.

If execution is requested, discover the exposed NorFab Netbox `design_deploy` MCP
tool and inspect its schema. Pass `design`, `context`, `instance`, and `branch`
using that schema. A file URL must be accessible to the worker, not merely present
on the agent's machine. Do not invent a tool name or assume MCP is connected.
If unavailable, provide a Python or CLI invocation from the deployment documentation.

Use the same worker and target for preview and deployment. For Markdown designs,
follow the reference's marked-block format.

For an authorized execution workflow:

1. Use `dry_run_render: true` to inspect rendered output when useful. This returns
   before YAML parsing, flattening, object validation, and deployment.
2. Start deployment verification with `dry_run: true`. It does not create planned
   prerequisites or reserve allocations. Unresolved planned objects do not alone
   prove real deployment will fail. `create_ip` ignores `mask_len` during dry runs.
   Multiple ASN allocations can report the same available candidate.
3. Perform real writes with `dry_run: false` only when deployment is authorized.
   Do not carry `dry_run_render: true` into that call. It takes precedence.
4. Inspect every worker's `failed`, `errors`, and collection results. Verify
   objects and relationships in Netbox, or state that readback is unverified.

Deployment stops on failure without rollback. Report partial completion. Do not
blindly retry writes or delete existing objects to force success.

## Deliver the design

Deliver YAML, context, prerequisites, agreed assumptions, instance/branch, any
approved Python files, and an adjusted deployment call. State what was checked,
previewed, deployed, or verified, and what remains unresolved. Repeat runs may
send updates. Omitted objects are not deleted. Existing BGP sessions are unchanged.
Keep delivery notes short. Do not repeat the task documentation or this skill.
