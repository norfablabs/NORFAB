---
tags:
  - netbox
  - tutorials
---

# Author a Netbox design with an agent

Use this guide as an agent instruction when translating a network requirement into a NorFab YAML design. Produce a reviewable design first. Deploy only when the user requests deployment.

## Read before authoring

- [Design deployment reference](../workers/netbox/services_netbox_service_tasks_design_deploy.md): supported objects, reference formats, nesting, allocation tasks, and function contracts.
- [Complete ACME branch design](https://github.com/norfablabs/NORFAB/blob/master/tests/nf_tests_inventory/netbox/designs/acme_branch_network_design_v1.yaml): a worked reference for device, interface, IP, VLAN, BGP, console, power, and context definitions. Adapt the relevant parts rather than copying its addresses or names into another network.
- When working in the repository, check `design_tasks.py` and `netbox_models.py` for the installed implementation. Do not assume newer documentation matches an older worker.

## Gather the minimum requirements

Confirm the target Netbox instance and branch, site and tenant, device names and types, topology, addressing pools, VLAN groups, ASNs, and required configuration context. Separate objects the design owns from existing objects it only references.

Always prefer deploying to a branch when Netbox branching is available. Confirm the branch with the user and supply it through the task's `branch` argument. If branching is unavailable, tell the user that enabling the Netbox Branching plugin is worth considering so design changes can be reviewed separately from main data. Make clear that deployment without a branch changes main data directly.

Ask about missing decisions that affect identity, allocation, or connectivity. Do not invent production addresses, VLAN IDs, ASNs, credentials, or device models. Record any agreed assumptions with the draft.

## Build the design

1. Use one YAML document. Put optional `design_input_schema` and `jinja_functions` metadata at the beginning as valid YAML, before object definitions or Jinja directives. Do not add `jinja_functions` unless a custom filter is actually required. Define reusable inputs through `context`; keep validation proportionate and honor requests to omit it.
2. Use lists of dictionaries for top-level objects. Use only supported top-level keys. YAML order does not control deployment order, the engine does.
3. Group interfaces and ports under their devices. Keep IP allocations, connections, and BGP peerings under the relevant interface when supported. Use dictionaries keyed by interface or peering name and lists for `ip_addresses`. Nesting supplies device and interface references automatically.
4. Use direct names only where the reference documents name shorthand. For example, `site: BRANCH-1` and `vrf: CUSTOMER` are valid, while device types require `{manufacturer: ACME, model: ROUTER}`. Every VLAN needs a group.
5. Define prerequisites or explicitly list them as required existing objects. Parent, LAG, and bridge interfaces must exist or be defined in the design. Avoid chains requiring more than two interface creation passes. Define each cable once.
6. You **MUST prefer built-in next-available allocation tasks or explicit YAML object definitions** over custom Jinja2 filters, macros, Python helpers, or address calculations. Use `create_ip`, `create_prefix`, `create_vlan`, and `create_asn` when values should be allocated; use explicit records when the user supplies fixed values. Pass the task's documented arguments unchanged and give allocations stable names or descriptions for reuse.
7. Reserve Jinja2 primarily for `for` loops, `if` conditions, `context` access, and string templating. Keep object definitions in the YAML sections where they belong. Use dedicated loops for similar device groups, such as spines and leaves, and retain meaningful differences with conditions.
8. Add `config_context` or `local_context_data` only when requested or needed by an identified consumer. Do not invent configuration-intent keys merely to make a Netbox model look complete: stored context does not configure devices. If needed, shared data belongs in `config_context` and device-specific data in `local_context_data`.

### Keep YAML readable and Jinja2 small

Define devices, interfaces, links, VLANs, and pools directly under supported YAML
keys. Do not move the design into large `{% set %}` lists, dictionaries, or tuple
tables and reconstruct it through template logic. Short literal loop inputs are
appropriate when their meaning is obvious, for example
`{% for spine, local_as in [(1, 65001), (2, 65002)] %}`. This keeps agreed ASNs
explicit while sharing the device definition. Avoid calculating identifiers
when a short literal list is clearer.

Use expanded YAML mappings and lists. Compact pairs such as `- [100, 200]` are
appropriate for VLAN ranges; deeply nested flow mappings are harder to review.
Add short YAML or Jinja2 comments explaining pool selection, peer allocation,
redundancy, and exceptions. Avoid comments that merely restate field names.

Do not split IP strings, calculate octet offsets, or introduce an address macro
to reproduce next-available allocation. Do not guess allocated values from the
order of records or assume an empty parent will always yield particular
addresses. Downstream objects must reference the actual allocation through a
supported lookup. Fixed addresses must come from an agreed addressing plan.

### Allocate pools first, then interface addresses

- Define the parent prefix from `context`, then use `create_prefix` to allocate
  pools within it. Give pools a site, functional role, and stable description.
  Define the corresponding IPAM roles in the design or list them as prerequisites.
- Select pools in `create_ip.prefix` using site and role where practical. Use
  distinct roles or additional filters when different pools serve different
  purposes; redundant leaves may share a pool while a standalone leaf needs its
  own. Do not rely on description strings alone when site and role express the
  intended selection clearly.
- In the current worker, `create_ip.prefix.role` is a **role name** resolved to
  `role_id`; `site` is also resolved by name. This is task-specific handling:
  direct Netbox REST filters may require slugs or IDs. Check the installed
  implementation and do not assume `role__name` is a supported REST filter.
- Put `create_ip` under the interface's `ip_addresses`. Use `mask_len: 31` for
  an IPv4 point-to-point child subnet or `mask_len: 32` for a loopback host
  allocation. Do not define every `/31` at the top level when the interface
  allocator can create it from a shared pool.
- For a connected point-to-point link, define its cable once and use
  `create_peer_ip: true` on one endpoint. The task assigns both endpoint IPs;
  omit the duplicate allocation on the peer. Connections are created before IP
  allocation. IPv4 `/32` and IPv6 `/128` allocations automatically skip peers,
  so they do not need `create_peer_ip: false`.
- BGP peerings nested under interfaces inherit `local_interface`. For supported
  point-to-point masks, the task can resolve the local IP and derive the peer IP
  after allocation. Do not embed guessed addresses. `create_reverse` controls
  BGP sessions, whereas `create_peer_ip` controls IP allocation; they are separate.
- `create_asn` reuses an ASN by description within its named range. It is not a
  Jinja2 function or a general reference expression: BGP `local_as` and
  `remote_as` currently require numbers. Use agreed numeric ASNs consistently
  unless a documented mechanism resolves the allocated ASN at deployment time.

For example, under an existing device's `interfaces`, this loopback definition
uses a previously defined site-scoped pool with the IPAM role `LOOPBACKS`:

```yaml
Loopback0:
  type: virtual
  ip_addresses:
    - create_ip:
        prefix:
          site: "{{ context.site }}"
          role: LOOPBACKS
        mask_len: 32
        description: "{{ context.site }} spine-1 Loopback0"
        is_primary: true
```

### Handle unsupported relationships explicitly

Check the task reference and implementation before adding allocation arguments.
`create_prefix` supports VLAN association through `vlan` (VID) together with
`vlan_group` (group name), never VID and site alone. However, `create_ip` cannot
assign an allocated VIP to an FHRP group. A group's `vip`
accepts an explicit CIDR address, not an allocation call. See the
[design specification TODOs](../development/adr_netbox_design_specification.md#todo).

Do not silently drop a required relationship or claim an incomplete model is
functional. Explain the specific gap and agree whether to use explicit values,
defer the relationship, or extend the worker. Label deferred work in the design
and delivery notes. An unassigned allocated VIP does not complete a VRRP gateway.

Custom code is a last resort. Before creating or adding a custom Jinja2 filter,
macro, Python helper, or deployment-time function, you **MUST ask the user to
confirm that they want custom code and receive explicit approval**. This applies
even when the helper is small or would make the template shorter. A request to
create a design does not itself authorize custom code. Do not ask again if the
user has already explicitly authorized that specific custom implementation.

The approval request **MUST** explain:

1. The exact required behavior or relationship that cannot be expressed.
2. Which built-in allocation tasks, supported nesting, reference formats, and
   explicit YAML alternatives were checked, and why each applicable option is
   insufficient. Cite the relevant task documentation or implementation; do not
   infer a missing feature merely from an unfamiliar interface.
3. What the proposed function would do, when it would run, what it would read or
   write, and which files or dependencies it would add.
4. The available alternatives without custom code and their tradeoffs, including
   any requirement that would remain unmet.

End with a direct question, such as: “Do you want me to create this custom
function to handle this gap?” Wait for an affirmative answer before creating
the custom implementation or adding its invocation to the design. Silence is
not approval. Continue any independent work using supported built-in features
while the decision is pending. If approval is declined, stay within the agreed
alternative and clearly document any deferred requirement.

Jinja2 runs before deployment and cannot read objects that the same design has
yet to create. Never allocate or write Netbox objects from Jinja2. Approved
custom writes belong in deployment-time functions that honor `dry_run`.

## Minimal allocation pattern

This draft creates its parent pool before allocating an address. Replace the example pool only with an approved pool. Repeated calls use the stable description to find the allocation.

```yaml
design_input_schema:
  type: object
  properties:
    parent_prefix:
      type: string
  required:
    - parent_prefix
  additionalProperties: false

prefixes:
  - prefix: "{{ context.parent_prefix }}"
    description: EXAMPLE branch allocation pool

ip_addresses:
  - create_ip:
      prefix: "{{ context.parent_prefix }}"
      description: EXAMPLE branch service address
```

Example context: `{"parent_prefix": "192.0.2.0/24"}`. Interface assignment and more allocation patterns are in the [task reference](../workers/netbox/services_netbox_service_tasks_design_deploy.md#built-in-next-available-allocation-functions).

## Deploy through NorFab MCP

If NorFab MCP is available, discover the exposed Netbox `design_deploy` tool and use it when the user authorizes execution. Supply the worker-accessible design path as `design`, template inputs as `context`, and the agreed `instance` and `branch`. Use `dry_run: true` for a preview. Inspect the returned worker results for `failed` and `errors` before reporting success. Tool availability alone does not authorize deployment. See the [MCP invocation example](../workers/netbox/services_netbox_service_tasks_design_deploy.md#examples).

Example task arguments for a preview, assuming branching is available:

```json
{
  "design": "nf://netbox/designs/branch.yaml",
  "context": {"site": "BRANCH-1"},
  "branch": "branch-review",
  "dry_run": true
}
```

Adapt the arguments to the discovered tool's schema and the design's input schema. For an authorized deployment, call the same tool with `dry_run: false`. If MCP is unavailable, provide the CLI or Python invocation instead of claiming the design was deployed.

## Review and verify

- Check object identities, reference formats, plugin requirements, and allocation pools against the target environment. Existing matching objects will be updated, even if another design originally created them.
- Check both BGP endpoints and ASNs. New peerings default to reverse-session creation. Use `create_reverse: false` when defining each direction yourself.
- Check that allocation filters select the intended pools and that consumers do not assume particular next-available values. Keep peer IP allocation on one endpoint per cable.
- Review custom Python files as executable worker code. Respect `dry_run` and do not embed credentials.
- If authorized to execute, start with a dry run. It does not create prerequisites, so unresolved planned objects are not proof that the actual deployment will fail. A dry run is not a security boundary for custom functions.
- `create_ip` dry runs ignore `mask_len` and do not create child subnets; do not treat their candidate addresses as the final `/31` or `/32` allocation plan.
- For an approved real deployment, inspect `failed`, `errors`, and per-object results, then verify the resulting objects and relationships in Netbox. Repeat deployment should reuse identities, but may still send updates. Do not claim a dry run proves successful deployment.
- On failure, report what completed before the failure. There is no automatic rollback. Never delete pre-existing objects to make a test pass.

## Deliver to the user

Provide the YAML, any referenced Python files, required `context`, existing-object prerequisites, and the intended instance/branch. Include the deployment command or API call from the [reference examples](../workers/netbox/services_netbox_service_tasks_design_deploy.md#examples), adjusted to the user's environment. State exactly what was validated or deployed and what remains unverified.
