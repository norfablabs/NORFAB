---
tags:
  - netbox
---

# NetBox Create ASN Task

> task API name: `create_asn`

The `create_asn` task creates or updates one NetBox ASN. It can use an explicit ASN or allocate the next available value from an existing named ASN range.

## Inputs

| Parameter | Required | Default | Description |
| --- | ---: | --- | --- |
| `asn_range` | Conditional | `None` | Existing ASN range name used for allocation |
| `sites` | No | `None` | Site names to assign the ASN to |
| `role` | No | `None` | IPAM role name |
| `asn` | Conditional | `None` | Explicit ASN from 1 through 4294967295 |
| `rir` | Conditional | `None` | Existing RIR name required for an explicit ASN without `asn_range` |
| `description` | No | `None` | ASN description and allocation deduplication value within a range |
| `tenant` | No | `None` | Tenant name |
| `tags` | No | `None` | Tag names |
| `custom_fields` | No | `None` | NetBox custom-field values |
| `instance` | No | Worker default | NetBox instance to target |
| `dry_run` | No | `False` | Return the selected ASN without writing |
| `branch` | No | `None` | NetBox Branching plugin branch name |

Provide `asn` or `asn_range`. When `asn` is supplied without a range, `rir` is required.

## Output

```python
{
    "asn": 64512,
    "description": "edge routing",
    "status": "created",
}
```

`status` is `create` or `update` during dry-run and `created` or `updated` after an applied operation.

## Examples

=== "CLI"

    ```bash
    nf# netbox create asn asn-range PRIVATE-ASNS description "edge routing" sites BRANCH-001,BRANCH-002
    nf# netbox create asn asn 65001 rir Private sites BRANCH-001
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="./inventory.yaml") as nf:
        client = nf.make_client()

        allocated = client.run_job(
            "netbox",
            "create_asn",
            workers="any",
            kwargs={
                "asn_range": "PRIVATE-ASNS",
                "sites": ["BRANCH-001", "BRANCH-002"],
                "description": "edge routing",
            },
        )

        explicit = client.run_job(
            "netbox",
            "create_asn",
            workers="any",
            kwargs={"asn": 65001, "rir": "Private"},
        )
    ```

In a NetBox design:

```yaml
asns:
  - create_asn:
      asn_range: PRIVATE-ASNS
      description: edge routing
      sites: [BRANCH-001]
      role: BRANCH-ROUTING
```

## Notes / Gotchas

- The named ASN range and its RIR must already exist. ASN ranges have no site scope; `sites` associates the ASN with sites.
- When updating an ASN, new `sites` and `tags` are added to the existing lists. Existing entries stay in place. The same applies to custom fields whose current and new values are both lists. An empty list (`[]`) makes no change to an existing list. For custom fields, `null` clears the value, and a new scalar value replaces the old one.
- For object and multiobject custom fields, supply the related objects by name or ID. For example, a custom field referencing devices can receive `["router-1", "router-2"]`. The task looks up names in the field's related NetBox object type and sends their IDs. A name must match exactly one object; missing or ambiguous names cause an error.
- In NFCLI, separate multiple site names with commas.
- Repeated range allocations reuse an ASN with the same description inside that range.
- Without a description, repeated range calls allocate the next available ASN.
- Branch writes require the NetBox Branching plugin.

## Troubleshooting

- **ASN range not found:** verify the exact range name in NetBox.
- **No available ASNs:** expand the range or remove an unused allocation.
- **RIR not found:** create the RIR or correct the `rir` name.
- **Multiple description matches:** make descriptions unique inside the ASN range.

## Task Command Shell Reference

```bash
nf# man tree netbox create asn
netbox create asn
├── asn-range
├── asn
├── rir
├── description
├── tenant
├── sites
├── role
├── tags
├── custom-fields
├── instance
├── branch
└── dry-run
```

## Python API Reference

::: norfab.workers.netbox_worker.bgp_asn_tasks.NetboxBgpAsnTasks.create_asn
