# Nornir Worker Inventory

Content of `inventory.yaml` need to be updated to include Nornir worker details:

``` yaml title="inventory.yaml"
broker: 
  endpoint: "tcp://127.0.0.1:5555" 
  shared_key: "5z1:yW}]n?UXhGmz+5CeHN1>:S9k!eCh6JyIhJqO"

workers:
  nornir-worker-1: 
    - nornir/nornir-worker-1.yaml

topology: 
  workers: 
    - nornir-worker-1
```

To obtain broker `shared_key` run this command on broker:

```
cd <path/to/broker/inventory.yaml>
nfcli --show-broker-shared-key
```

Sample Nornir worker inventory definition

!!! example

    === "Netbox >= 4.3.0"

        This inventory `filters` section contains GraphQL query examples 
        compatible with Netbox 4.3.0 and above.

        ``` yaml title="nornir/nornir-worker-1.yaml"
        service: nornir
        watchdog_interval: 30
        connections_idle_timeout: null
        failed_hosts_recovery_timeout: 60
        reset_failed_hosts_before_task: false

        # these parameters mapped to Nornir inventory
        # https://nornir.readthedocs.io/en/latest/tutorial/inventory.html
        runner:
          plugin: RetryRunner
          options: 
            num_workers: 100
            num_connectors: 10
            connect_retry: 1
            connect_backoff: 1000
            connect_splay: 100
            task_retry: 1
            task_backoff: 1000
            task_splay: 100
            reconnect_on_fail: True
            task_timeout: 600
        hosts: {}
        groups: {}
        defaults: {}
        logging: {}
        user_defined: {}

        # Netbox Service Nornir Inventory integration
        netbox:
          instance: prod
          interfaces:
            ip_addresses: True
            inventory_items: True
          connections: True
          nbdata: True
          circuits: True
          primary_ip: "ipv4"
          devices:
            - fceos4
            - fceos5
            - fceos8
            - ceos1
          filters: 
            - name: '{i_contains: "fceos3"}'
            - '{platform: {name: {exact: "cisco_xr"}}}'
        ```

**watchdog_interval**

Watchdog run interval in seconds, default is 30

**connections_idle_timeout**

Watchdog connection idle timeout, default is ``None`` - no timeout, connection always kept alive, if set to 0, connections disconnected right after task completed, if positive number, connection disconnected after not being used for over ``connections_idle_timeout``

**failed_hosts_recovery_timeout**

Time in seconds before the watchdog recovers hosts marked as failed by Nornir.
The default is `60`. This setting is used only when
`reset_failed_hosts_before_task` is `false`.

While a host is errdisabled, later Nornir tasks skip it by default. Set
`on_failed=True` in the Python API, or use `on-failed` in NFCLI, to include
errdisabled hosts in one specific task execution. This does not clear their
failed-host state.

Use the `errdisabled_hosts_list` task or `show nornir errdisabled-hosts` to
inspect recovery timing. Use the `errdisabled_hosts_clear` task or
`nornir clear errdisabled-hosts` to recover all hosts immediately. See
[Errdisabled Hosts Tasks](services_nornir_service_tasks_errdisabled_hosts.md)
for the complete workflow.

**reset_failed_hosts_before_task**

Reset Nornir's failed-host state before each task. The default is `false`,
which enables errdisabled-host tracking and recovery. Set this to `true` only
to retain the earlier behavior where every task starts with all matched hosts
enabled.

!!! warning "Mutually exclusive recovery modes"

    When `reset_failed_hosts_before_task: true`, persistent errdisabled-host
    behavior is disabled. `failed_hosts_recovery_timeout` does not control host
    eligibility because failed hosts are reset before the next task. The
    `on_failed`/`on-failed` override and watchdog recovery timer are therefore
    unnecessary in this mode.

    When `reset_failed_hosts_before_task: false`, failed hosts remain
    errdisabled until the watchdog timeout expires, they are cleared on demand,
    or a particular run includes them with `on_failed=True`.

Nornir task results include hosts executed during the current job in
`resources`, and hosts that failed during that job in `resources_failed`.

## Netbox Inventory Integration

NorFab Nornir Worker supports tight integration with Netbox to fetch devices data such as device interfaces, ip addresses, circuits, configuration context. Netbox 3.7.x and 4.x.x supported. 

Sample Nornir Worker inventory parameters to fetch devices data from Netbox

``` yaml
netbox:
  instance: prod
  interfaces:
    ip_addresses: True
    inventory_items: True
  connections: True
  nbdata: True
  circuits: True
  primary_ip: "ipv4"
  devices:
    - fceos4
    - fceos5
    - fceos8
    - ceos1
  filters: 
    - q: fceos3
    - manufacturer: cisco
      platform: cisco_xr
```

**filters**

List of Netbox REST API filters to pull devices data.

**devices**

List of exact device names to retrieve from Netbox, names used as hosts' names in Nornir inventory.

**instance**

Specifies the name of the NetBox instance to be used. This parameter is useful for environments with multiple NetBox instances, allowing to target a specific instance to fetch devices data.

**interfaces**

Indicates whether to include interface data in the results.

Extras:

- **ip_addresses**: When set to `True`, includes IP address information associated with the interfaces in Netbox. 
- **inventory_items**: When set to `True`, includes inventory items associated with the interfaces in Netbox. 

**connections**

Specifies whether to include connection data in the inventory.

**nbdata**

Specifies whether to merge NetBox devices data into Nornir hosts' `data`. This is useful when need to make Netbox device `config_context` available in Nornir hosts' `data` together with other device information such as Netbox `site`, `tags`, `role` etc.

**circuits**

Indicates whether to fetch circuits data from Netbox and map it to hosts data.

**primary_ip**

Specifies what Netbox device IP address to use for Nornir host's `hostname` parameter, supported values are `ipv4`, `ip4`, `ipv6` or `ip6`, uses Netbox device name instead if no primary IP address mapped to the device in Netbox.
