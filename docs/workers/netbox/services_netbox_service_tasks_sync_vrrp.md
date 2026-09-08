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

The parser must return a list per device with these fields:

```yaml
- interface: Ethernet1
  group: 10
  protocol: vrrpv2
  virtual_address: 192.0.2.1
  priority: 110
  authentication_type: plaintext
```

## Identity and comparison

Each assignment is identified by `(device, interface, group_id)`.
This is the correct synchronization key because NetBox stores priority on the
interface-to-group assignment, not on the FHRP group. The task groups peers
which have the same protocol, group ID, virtual address, and authentication
type into one NetBox FHRP group and creates an assignment for each participating
interface. Getter values `vrrpv2` and `vrrpv3` map to NetBox protocols `vrrp2`
and `vrrp3`, respectively.

`protocol`, `virtual_address`, `priority`, and `authentication_type` are
synchronized values. Common parser authentication values such as `text`,
`simple`, and `cleartext` are normalized to NetBox's `plaintext` value.

Both live and NetBox data use a scalar `virtual_address` in the normalized
comparison structure:

```json
{
  "router-1": {
    "Ethernet1:10": {
      "interface": "Ethernet1",
      "group_id": 10,
      "protocol": "vrrp2",
      "virtual_address": "192.0.2.1",
      "name": "router-1_Ethernet1_VRRP10",
      "priority": 110,
      "authentication_type": null
    }
  }
}
```

Each VRRP group is represented by exactly one scalar virtual IP address.

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

For a group observed on multiple peers, the first device and interface in
sorted order supply the context. The task renders the name once and applies the
same name to the shared group for every peer.

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

Bare virtual addresses receive the most-specific prefix length from a
containing NetBox prefix. If no containing prefix exists, `/32` or `/128` is
used. Before creating an address, the task searches NetBox by its bare host
value and compares matches without their prefix lengths. It reuses an address
already assigned to the target FHRP group first. Otherwise, it selects only
unassigned records, preferring an address with the `vip` or `vrrp` role before
the first unassigned match. A reused address is assigned to the FHRP group and
its role is set to `vrrp`; newly created addresses also use the `vrrp` role. If
all matching records are assigned to other NetBox objects, the task reports an
error and leaves the address, FHRP group, and interface assignment unchanged.

The normalized live and NetBox states store `virtual_address` as one string
because a VRRP group has one virtual IP. The task is additive: it does not
delete FHRP groups, assignments, or virtual IP addresses that are absent from
live parsing. Use `dry_run` to inspect the plan, or `with_approval` to review it
before writes are applied.

::: norfab.workers.netbox_worker.fhrp_tasks.NetboxFhrpTasks.sync_vrrp
