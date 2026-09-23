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
| `site` | No | `None` | Site scope used to select an ASN range with that name |
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

    A dedicated NFCLI command is not currently registered for `create_asn`.

    ```bash
    # Use the Python API, REST API, MCP task interface, or design filter.
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
                "site": "BRANCH-001",
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
{% set edge_asn = "PRIVATE-ASNS" | netbox.create_asn("edge routing") %}

asns:
  - asn: {{ edge_asn }}
    description: edge routing
```

## Notes / Gotchas

- The named ASN range and its RIR must already exist. Supply `site` when range names are reused across site scopes.
- Repeated range allocations reuse an ASN with the same description inside that range.
- Without a description, repeated range calls allocate the next available ASN.
- Branch writes require the NetBox Branching plugin.

## Troubleshooting

- **ASN range not found:** verify the exact range name in NetBox.
- **No available ASNs:** expand the range or remove an unused allocation.
- **RIR not found:** create the RIR or correct the `rir` name.
- **Multiple description matches:** make descriptions unique inside the ASN range.

## Task Command Shell Reference

`create_asn` does not currently have a dedicated NFCLI command model.

## Python API Reference

::: norfab.workers.netbox_worker.bgp_asn_tasks.NetboxBgpAsnTasks.create_asn
