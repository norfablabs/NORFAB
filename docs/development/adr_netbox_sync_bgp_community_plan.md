# ADR - NetBox `sync_bgp_community` Task Plan

## Status

Accepted on 31 August 2026.

## Goal

Add a small standalone NetBox task named `sync_bgp_community`. It collects live
BGP communities with the TTP Templates `bgp_communities` getter, groups records
by community value, and reconciles:

- `rt` values with NetBox IPAM route targets;
- every non-`rt` value with NetBox BGP plugin communities.

Different community-set names observed for the same value are stored in the
`community_name` custom field as a comma-separated string.

## Design

1. Add `bgp_community_tasks.py` with a `NetboxBgpCommunityTasks` mixin and a
   decorated `sync_bgp_community` task.
2. Reuse the common NetBox and Nornir arguments: `instance`, `branch`,
   `devices`, host filters, `timeout`, `dry_run`, and `with_approval`.
3. Run Nornir `parse_ttp` once with `get="bgp_communities"` and the selected
   devices.
4. Normalize live data into two dictionaries keyed by `value`. Deduplicate and
   sort each value's getter `name` entries before joining them with `", "`.
5. Check for the NetBox BGP plugin, then fetch IPAM route targets and, when the
   plugin is installed, BGP plugin communities. Without the plugin, skip all
   non-`rt` records and synchronize route targets only.
6. Compare live and NetBox state through the existing `self.make_diff()` helper,
   which uses DeepDiff. Return separate `route_targets` and `communities`
   actions.
7. On write runs, bulk-create missing objects and append missing live names to
   the `community_name` custom field. Existing custom-field values are
   preserved. Do not rename route targets or modify other fields.
8. Report malformed records without making writes for them.

The first implementation will not delete NetBox objects. A missing live record
does not prove that a globally shared community is stale.

## Models and Interfaces

- Add `SyncBgpCommunityInput` and `SyncBgpCommunityResult` to
  `netbox_models.py`.
- Register the mixin in `netbox_worker.py`.
- Add the NFCLI command `netbox sync bgp-communities` using the same thin shell
  pattern as `sync_vrfs`.
- Do not add the task to `sync_all` or `check_sync` in this change.

## Documentation and Tests

- Add a task page with inputs, output, CLI and Python examples, then register it
  in `mkdocs.yml`.
- Update `docs/norfab_features.md`, its Last updated date, and the 0.22.0
  changelog entry.
- Add a focused `tests/services/netbox/test_sync_bgp_community.py` suite covering
  dry-run, create, alias aggregation across devices, update, idempotency,
  branch forwarding, malformed results, and no deletions.
- Add minimal FakeNOS command output to two existing simulated devices so the
  same value is returned under different community-set names.
- Add one pytest marker and run the focused tests, Ruff, and relevant docs
  checks.

## Planned Files

- `norfab/workers/netbox_worker/bgp_community_tasks.py`
- `norfab/workers/netbox_worker/netbox_models.py`
- `norfab/workers/netbox_worker/netbox_worker.py`
- `norfab/clients/nfcli_shell/netbox/netbox_picle_shell_sync_bgp_community.py`
- `norfab/clients/nfcli_shell/netbox/netbox_picle_shell.py`
- `tests/services/netbox/test_sync_bgp_community.py`
- two existing FakeNOS device YAML files
- `pyproject.toml`, `mkdocs.yml`, the task documentation, feature catalogue, and
  changelog

## Decisions

1. Store the getter's live community-set `name` values, not device names.
2. Store `rt` in IPAM and all other getter types in the BGP plugin.
3. Never delete objects.
4. Use optional argument `community_name_field`, defaulting to
   `community_name`. If the configured field does not exist, continue without
   synchronizing community names.
5. When an object already exists, split the current custom-field value by
   comma, strip spaces, append missing live names, and skip updates when all
   live names are already present.
