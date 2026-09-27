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

1. Use one YAML document. Put `design_input_schema` and `jinja_functions` at the beginning as valid YAML, before object definitions or Jinja directives. Define reusable user inputs through `context` and validate them with the input schema.
2. Use lists of dictionaries for top-level objects. Use only supported top-level keys. YAML order does not control deployment order, the engine does.
3. Group interfaces, ports, peerings, and local context under their devices. Use the documented nested shapes, including dictionaries keyed by interface or peering name and lists for `ip_addresses`.
4. Use direct names only where the reference documents name shorthand. For example, `site: BRANCH-1` and `vrf: CUSTOMER` are valid, while device types require `{manufacturer: ACME, model: ROUTER}`. Every VLAN needs a group.
5. Define prerequisites or explicitly list them as required existing objects. Parent, LAG, and bridge interfaces must exist or be defined in the design. Avoid chains requiring more than two interface creation passes. Define each cable once.
6. For known values, use explicit records. For next-available values, use `create_ip`, `create_prefix`, `create_vlan`, or `create_asn` with the corresponding task's arguments. Give allocations stable names or descriptions so repeat deployment can find them. IPv4 /32 and IPv6 /128 allocations automatically skip peer allocation.
7. Use Jinja loops to reduce repetition. Jinja functions calculate values before deployment and must not depend on objects the design will create. Use deployment-time custom functions only when their extra logic is needed.
8. Put shared context in `config_context`. Put per-device calculations in `local_context_data` so they run last against the modeled device. Ordinary custom functions perform their own writes. Device-local context functions receive a pynetbox `device` and return a dictionary for the handler to save.

## Minimal allocation pattern

This draft creates its parent pool before allocating an address. Replace the example pool only with an approved pool. Repeated calls use the stable description to find the allocation.

```yaml
design_input_schema:
  type: object
  properties:
    parent_prefix: {type: string}
  required: [parent_prefix]
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
- Review custom Python files as executable worker code. Respect `dry_run` and do not embed credentials.
- If authorized to execute, start with a dry run. It does not create prerequisites, so unresolved planned objects are not proof that the actual deployment will fail. A dry run is not a security boundary for custom functions.
- For an approved real deployment, inspect `failed`, `errors`, and per-object results, then verify the resulting objects and relationships in Netbox. Repeat deployment should reuse identities, but may still send updates. Do not claim a dry run proves successful deployment.
- On failure, report what completed before the failure. There is no automatic rollback. Never delete pre-existing objects to make a test pass.

## Deliver to the user

Provide the YAML, any referenced Python files, required `context`, existing-object prerequisites, and the intended instance/branch. Include the deployment command or API call from the [reference examples](../workers/netbox/services_netbox_service_tasks_design_deploy.md#examples), adjusted to the user's environment. State exactly what was validated or deployed and what remains unverified.
