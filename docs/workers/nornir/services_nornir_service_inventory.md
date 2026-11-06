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


## NETCONF Connection Inventory

Configure the backend selected by the task's `plugin` argument. Use `ncclient`
for `plugin=ncclient` and `scrapli_netconf` for `plugin=scrapli`. Add these settings
to a host or an inherited group. Username and password inherit from the host.

NETCONF normally uses port `830`. Set the connection port explicitly when the
host's main port is SSH. The device-specific tabs below use the mapped ports
from the test lab. Replace them with the port your device uses.

=== "ncclient"

    Use the default backend with SSH host key checking enabled. Add the device's
    SSH key to the worker's known hosts before connecting.

    ```yaml
    connection_options:
      ncclient:
        port: 830
        extras:
          hostkey_verify: true
          allow_agent: false
    ```

=== "Scrapli"

    Select `plugin=scrapli` in the task. This example uses the Paramiko SSH
    transport and checks the device's SSH host key.

    ```yaml
    connection_options:
      scrapli_netconf:
        port: 830
        extras:
          transport: paramiko
          auth_strict_key: true
          ssh_config_file: true
    ```

=== "IOS XR"

    The XRD lab router uses port `8308`. Set ncclient's device name to `iosxr`.

    ```yaml
    connection_options:
      ncclient:
        port: 8308
        extras:
          hostkey_verify: true
          allow_agent: false
          device_params:
            name: iosxr
    ```

=== "IOS XE"

    The CSR1000v lab router uses port `8307`. Set ncclient's device name to `iosxe`.

    ```yaml
    connection_options:
      ncclient:
        port: 8307
        extras:
          hostkey_verify: true
          allow_agent: false
          device_params:
            name: iosxe
    ```

=== "Junos"

    The vMX lab router uses port `8305`. Set ncclient's device name to `junos`.

    ```yaml
    connection_options:
      ncclient:
        port: 8305
        extras:
          hostkey_verify: true
          device_params:
            name: junos
    ```

=== "Arista EOS"

    This example matches the cEOS lab's Scrapli connection settings, with SSH
    host key checking enabled. Select `plugin=scrapli` in the task. The first
    spine uses port `8300`.

    ```yaml
    connection_options:
      scrapli_netconf:
        port: 8300
        extras:
          transport: paramiko
          auth_strict_key: true
          ssh_config_file: true
          transport_options:
            netconf_force_pty: false
    ```

The test inventories disable SSH host key checking for disposable lab devices.
If needed in that lab, use `hostkey_verify: false` for ncclient or
`auth_strict_key: false` for Scrapli. Keep checking enabled for trusted device
connections.

## gNMI connection inventory

Configure gNMI tasks using `connection_options.pygnmi`. Username and password
inherit from the host. Set the port explicitly when the host's main port is SSH.
The port and encryption settings must match the device's gNMI service.

=== "With Encryption"

    Use TLS and verify the device certificate. Place the CA certificate that
    signed the device certificate at `/etc/norfab/certs/device-ca.pem` on each
    Nornir worker. Use the device's real CA certificate, not a sample certificate.

    ```yaml
    connection_options:
      pygnmi:
        port: 6030
        extras:
          insecure: false
          path_cert: /etc/norfab/certs/device-ca.pem
          gnmi_timeout: 10
    ```

=== "Without Encryption"

    Use plaintext only in a trusted test lab. The device must allow unencrypted
    gNMI connections.

    ```yaml
    connection_options:
      pygnmi:
        port: 6030
        extras:
          insecure: true
          gnmi_timeout: 10
    ```

=== "Juniper"

    This example uses a plaintext Junos lab service on port `57400`. Use the
    port configured on your router, or its mapped port when using containers.
    `no_qos_marking` prevents subscription requests from including a QoS marking,
    which some Junos versions reject.

    ```yaml
    connection_options:
      pygnmi:
        port: 57400
        extras:
          insecure: true
          no_qos_marking: true
          gnmi_timeout: 10
    ```

    For an encrypted Junos service, use `insecure: false` and `path_cert` as in
    the With Encryption tab. Keep `no_qos_marking: true`.


## RESTCONF connection inventory

Configure RESTCONF tasks using `connection_options.http`. Username and password inherit
from the host or its groups. Set the HTTP port explicitly when the host's main port is SSH.

=== "Arista EOS"

    Configure the HTTP connection in Nornir inventory:

    ```yaml
    connection_options:
      http:
        port: 6020
        extras:
          transport: https
          verify: true
          base_url: restconf/data
          timeout: 10
          headers:
            Accept: application/yang-data+json
            Content-Type: application/yang-data+json
    ```

    Enable RESTCONF over HTTPS on the device. This example generates a self-signed
    certificate for a lab. An existing certificate and SSL profile can also be used.

    ```text
    configure terminal
    security pki certificate generate self-signed restconf.crt key restconf.key generate rsa 2048 parameters common-name restconf
    management security
       ssl profile restconf
          certificate restconf.crt key restconf.key
       exit
    exit
    management api restconf
       transport https default
          ssl profile restconf
    end
    show management api restconf
    ```

    Verify that the server is running on port `6020` in the VRF containing the management
    interface. The control-plane ACL must permit TCP `6020`. Enabling RESTCONF does not automatically add an ACL rule.

=== "Cisco IOS XE"

    Configure the HTTP connection in Nornir inventory:

    ```yaml
    connection_options:
      http:
        port: 443
        extras:
          transport: https
          verify: true
          base_url: restconf/data
          timeout: 10
          headers:
            Accept: application/yang-data+json
            Content-Type: application/yang-data+json
    ```

    Enable RESTCONF over HTTPS on the device. This lab example creates a dedicated
    RSA key and self-signed certificate. An existing certificate and matching key
    can also be used. Replace the certificate name with your device hostname.

    ```text
    configure terminal
    crypto key generate rsa general-keys label RESTCONF-KEY modulus 2048
    crypto pki trustpoint RESTCONF-TP
     enrollment selfsigned
     subject-name CN=router1.example.com
     revocation-check none
     rsakeypair RESTCONF-KEY
     exit
    crypto pki enroll RESTCONF-TP
    ```

    Answer the enrollment prompts to generate the self-signed certificate, then enable
    HTTPS using that trustpoint. This example uses an existing local user account.
    If the device uses AAA, retain the appropriate authentication policy.

    ```text
    ip http authentication local
    no ip http secure-server
    ip http secure-trustpoint RESTCONF-TP
    ip http secure-server
    restconf
    end
    write memory
    show ip http server secure status
    show crypto pki certificates RESTCONF-TP
    ```

    Ensure the device clock is correct and TCP `443` is reachable. If HTTPS reports
    `private key not found`, the selected certificate needs its matching private key.
    A certificate marked Available alone does not confirm that the key is present.
    Setting `verify: false` does not fix a missing server private key.

Set `verify` to a CA bundle path when the device certificate requires a private CA.
A self-signed lab may use `verify: false`. Use a published host port when connecting
through a container host. Common HTTP settings can also be defined in a group.

`timeout` controls HTTP connect/read waiting, in seconds or as a connect/read pair.
It is separate from the CLI timeout for waiting on the NorFab job.
