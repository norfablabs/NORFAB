# Sync BGP Communities

The `bgp_community_sync` task collects community definitions from live devices
with the TTP Templates `bgp_communities` getter. It stores `rt` communities as
NetBox IPAM route targets. When the NetBox BGP plugin is installed, it stores
all other community types as BGP plugin communities. Without the plugin, the
task synchronizes route targets only.

Objects are identified by community value. When several devices use different
community-set names for the same value, the task stores the sorted, unique names
as a comma-separated string in an optional custom field. The task creates and
updates objects but never deletes them.

The optional custom field can be assigned to `ipam.routetarget`,
`netbox_bgp.community`, or both. If the configured field does not exist, object
synchronization continues without community-name updates.

## Live data

The getter returns one record per concrete community value:

```yaml
- value: 65000:100
  type: standard
  name: CUSTOMER_EXPORT
- value: 65000:200
  type: rt
  name: TENANT_BLUE
```

For example, if another device calls `65000:100` `BLUE_EXPORT`, the resulting
custom-field value is:

```text
BLUE_EXPORT, CUSTOMER_EXPORT
```

## Output

Dry-run results contain separate `route_targets` and `communities` scopes:

```json
{
  "route_targets": {
    "create": ["65000:200"],
    "update": {},
    "delete": [],
    "in_sync": []
  },
  "communities": {
    "create": ["65000:100"],
    "update": {},
    "delete": [],
    "in_sync": []
  }
}
```

Write runs return `created`, `updated`, `deleted`, and `in_sync`. The prepared
plan remains available in the top-level `diff` field. `delete` and `deleted`
are always empty.

## Examples

=== "CLI"

    ```bash
    nf# netbox sync bgp-communities devices fn-ceos-lf-1 dry-run
    ```

    ```bash
    nf# netbox sync bgp-communities FC leaf community-name-field community_aliases
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="./inventory.yaml") as nf:
        client = nf.make_client()
        result = client.run_job(
            "netbox",
            "bgp_community_sync",
            workers="any",
            kwargs={
                "devices": ["edge-1", "edge-2"],
                "dry_run": True,
                "community_name_field": "community_name",
            },
        )
        print(result)
    ```

## Notes

- The NetBox BGP plugin must accept each non-route-target value returned by the
  getter. NetBox API validation errors are returned when a value is unsupported.
- If the BGP plugin is not installed, the result contains only the
  `route_targets` scope and all non-`rt` getter records are skipped.
- The selected devices define the complete live alias set written to the custom
  field. Use the full intended device scope when synchronizing shared values.
- NetBox-only objects are retained because a scoped live query cannot prove
  that a globally shared community is stale.

## Troubleshooting

If a device has no result, confirm that its platform is supported by the
`bgp_communities` getter and that the Nornir worker can run the getter command.
For custom-field errors, confirm the field is long text and assigned to the
target NetBox object type.

## Task command shell reference

```bash
nf# man tree netbox.sync.bgp-communities
```

## Python API reference

::: norfab.workers.netbox_worker.bgp_community_tasks.NetboxBgpCommunityTasks.bgp_community_sync
