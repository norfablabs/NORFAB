# Sync VRRP Task

The `sync_vrrp` task collects live VRRP data with the Nornir `parse_ttp`
task and its `vrrp` getter, then reconciles NetBox FHRP groups, device-interface
assignments, priorities, authentication types, and virtual IP addresses.

```python
result = client.run_job(
    service="netbox",
    task="sync_vrrp",
    workers="any",
    kwargs={
        "devices": ["router-1", "router-2"],
        "name_template": "{{ device.name }}_{{ interface }}_VRRP{{ group_id }}",
        "dry_run": True,
    },
)
```

<details>
<summary>Getter output and defaults</summary>

The parser must return a list per device with these fields:

```yaml
- interface: Ethernet1
  vrf: null
  group: 10
  protocol: vrrpv2
  virtual_address: 192.0.2.1
  priority: 110
  authentication_type: plaintext
```

`virtual_address` is required. The getter supplies a priority of `100` when
none is configured.

</details>

## Group selection

Existing assignments are found by device, interface, protocol, and group ID.
New peers find candidate groups by protocol, group ID, and VIP; the rules below
resolve candidates. VIP addresses are compared without prefix lengths.
Names and authentication are editable fields, not lookup identities.

| Existing state | How the group is selected |
| --- | --- |
| Existing interface assignment | Keep its group; synchronize its fields and VIP. |
| VIP has a named VRF | Its VRF must match the live interface VRF. |
| VIP is global | The group's assigned interfaces must have the live interface VRF. |
| Same VIP in another VRF | Use a separate group and VIP. |
| Multiple matching groups or mixed interface VRFs on a global VIP group | Report an ambiguity error. |
| Global VIP with no group assignments | Cannot identify a peer group from it. |

A missing live VRF means global. Keep Netbox interface VRFs accurate when VIPs
are stored globally. Peers can be discovered across separate sync calls;
interface names do not need to match.

VRRPv2/VRRPv3 map to Netbox `vrrp2`/`vrrp3`. Authentication values `text`,
`simple`, and `cleartext` map to `plaintext`. Extra existing VIPs are retained.

## VIP creation and reuse

| Matching IP in Netbox | Action |
| --- | --- |
| Already owned by the selected group | Reuse it and normalize its role to `vrrp`. |
| Unassigned, in global or the matching VRF | Reuse it; prefer role `vip` or `vrrp`. |
| Owned by an FHRP group in another VRF | Does not block a separate VIP record. |
| Other assigned matches | Report a conflict; never take another object's IP. |
| No reusable IP and no ownership conflict | Create a VIP with role `vrrp`. |

New VIPs use the most-specific containing prefix, or `/32` (IPv4) / `/128`
(IPv6) when none exists.

| VIP creation setting | New VIP's VRF |
| --- | --- |
| `vip_use_vrf=False` (default) | Global |
| `vip_use_vrf=True` | Live interface VRF; it must already exist in Netbox. |

**Existing VIP VRFs are always preserved.** This option affects creation only,
not group selection. A missing required VRF is reported and that VIP is skipped.

=== "CLI"

    ```bash
    nf# netbox sync vrrp devices router-1 vip-use-vrf
    ```

=== "Python"

    ```python
    result = client.run_job(
        service="netbox",
        task="sync_vrrp",
        workers="any",
        kwargs={"devices": ["router-1"], "vip_use_vrf": True},
    )
    ```

## Output

Results contain per-device `created`, `updated`, `deleted`, and `in_sync`
assignment keys (`interface:protocol:group_id`). Dry-run results, `diff`, and
approval previews use the compatible per-device action structure:

| Action | Contents |
| --- | --- |
| `create` | New interface memberships. |
| `update` | Group, VIP, and priority changes with old/new field values. |
| `delete` | Stale interface memberships; reported only. |
| `in_sync` | Memberships requiring no changes. |

Shared group/VIP changes appear for every affected peer and apply once.
**Sync is additive:** existing groups, VIPs, and assignments are never deleted.
Use `dry_run=True` to preview or `with_approval=True` to review changes.
Dry runs also report VIP ownership conflicts and missing required VRFs.

## Group names

`name_template` renders the NetBox FHRP group name and updates existing names
when the rendered value changes. It accepts either an inline Jinja2 template or
an `nf://` path retrieved through the File Sharing service. The default is:

```jinja2
{{ device.name }}_{{ interface }}_VRRP{{ group_id }}
```

For device `router-1`, interface `Ethernet1`, and group 10, the default renders
`router-1_Ethernet1_VRRP10`.

### Jinja2 context

<details>
<summary>Template variables and naming rules</summary>

The task passes these variables directly to the Jinja2 environment:

| Variable | Type and content | Example |
| --- | --- | --- |
| `device` | NetBox device object with `id`, `name`, `platform`, `role`, `device_type`, and `site` | `device.site.name` |
| `interface` | Interface name string | `Ethernet1` |
| `protocol` | NetBox-normalized protocol string | `vrrp2` or `vrrp3` |
| `group_id` | Numeric VRRP group ID | `10` |
| `virtual_address` | Bare virtual-address string | `192.0.2.1` |

`device` is a pynetbox record, so templates can access nested NetBox fields:

```jinja2
{{ device.site.name }}_{{ device.role.name }}_{{ device.name }}_{{ interface | replace('/', '_') }}_VRRP{{ group_id }}
```

Related fields such as `platform` can be empty in NetBox. Use a Jinja2
conditional when a field is optional:

```jinja2
{{ device.platform.name if device.platform else 'no-platform' }}_{{ device.name }}_VRRP{{ group_id }}
```

The environment uses strict undefined-variable handling. A missing variable or
device attribute fails rendering and prevents the sync from writing changes.
The task strips surrounding whitespace from the result. The final name must
contain between 1 and 100 characters. NetBox does not require FHRP group names
to be unique.

For shared groups, the first device/interface in sorted order supplies the name.
Groups with peers outside the selected devices retain their existing names;
select all peers together to rename a shared group.

</details>

### Render an inline template

=== "CLI"

    ```bash
    nf# netbox sync vrrp devices router-1 name-template "{{ device.site.name }}_{{ device.role.name }}_VRRP{{ group_id }}" dry-run
    ```

=== "Python"

    ```python
    result = client.run_job(
        service="netbox",
        task="sync_vrrp",
        workers="any",
        kwargs={
            "devices": ["router-1"],
            "name_template": "{{ device.site.name }}_{{ device.role.name }}_VRRP{{ group_id }}",
            "dry_run": True,
        },
    )
    ```

### Load a template using `nf://`

Store only the Jinja2 expression in a file available to the File Sharing
service, for example `netbox/vrrp_group_name.j2`:

```jinja2
{{ device.name }}-{{ interface | replace('/', '-') }}-vrrp{{ group_id }}
```

Then pass its `nf://` URL to the task:

=== "CLI"

    ```bash
    nf# netbox sync vrrp devices router-1 name-template nf://netbox/vrrp_group_name.j2 dry-run
    ```

=== "Python"

    ```python
    result = client.run_job(
        service="netbox",
        task="sync_vrrp",
        workers="any",
        kwargs={
            "devices": ["router-1"],
            "name_template": "nf://netbox/vrrp_group_name.j2",
            "dry_run": True,
        },
    )
    ```

::: norfab.workers.netbox_worker.fhrp_tasks.NetboxFhrpTasks.sync_vrrp
