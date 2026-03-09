---
tags:
  - fakenos
---

# FakeNOS Worker Inventory

Content of `inventory.yaml` needs to be updated to include FakeNOS worker details:

``` yaml title="inventory.yaml"
broker: 
  endpoint: "tcp://127.0.0.1:5555" 
  shared_key: "5z1:yW}]n?UXhGmz+5CeHN1>:S9k!eCh6JyIhJqO"

workers:
  fakenos-worker-1: 
    - fakenos/fakenos-worker-1.yaml

topology: 
  workers: 
    - fakenos-worker-1
```

To obtain broker `shared_key` run this command on broker:

```
cd <path/to/broker/inventory.yaml>
nfcli --show-broker-shared-key
```

## FakeNOS Worker Inventory Parameters

Sample FakeNOS worker inventory file content:

``` yaml title="fakenos/fakenos-worker-1.yaml"
service: fakenos

networks:
  lab-network-1:
    inventory: fakenos/lab-network-1-inventory.yaml

nos_plugins:
  my_custom_nos: fakenos/plugins/my_custom_nos.yaml
```

### `networks`

Optional mapping of named FakeNOS networks to start automatically when the worker initialises. Each key is a unique network name; each value must provide:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `inventory` | `str` or `dict` | No | Path or URL to a FakeNOS inventory YAML file, or an inline inventory dict. If omitted, FakeNOS defaults are used. |

### `nos_plugins`

Optional mapping of custom NOS plugin names to file paths or URLs. Each plugin file must contain a valid FakeNOS NOS plugin definition in YAML format.

| Parameter | Type | Description |
|-----------|------|-------------|
| `<plugin-name>` | `str` | Path or URL to the plugin YAML file. The file is fetched and registered with FakeNOS at worker startup. |

Sample plugin definition:

``` yaml title="fakenos/plugins/my_custom_nos.yaml"
name: my_custom_nos

initial_prompt: "{base_prompt}#"

commands:
  show running-config:
    output: |
      hostname {base_prompt}
      ...
```

Above plugin can be referenced in network definition like this:

``` yaml title="fakenos/lab-network-2-inventory.yaml"
hosts:
  router-1:
    username: admin
    password: admin
    port: 10001
    nos: 
      plugin: my_custom_nos
  router-2:
    username: admin
    password: admin
    port: 10002
    platform: cisco_ios
```


## FakeNOS Network Inventory Format

The FakeNOS network inventory follows the standard [FakeNOS inventory schema](https://github.com/fakenos/fakenos). A minimal example:

``` yaml title="fakenos/lab-network-1-inventory.yaml"
hosts:
  router-1:
    username: admin
    password: admin
    port: 10001
    platform: arista_eos
  router-2:
    username: admin
    password: admin
    port: 10002
    platform: cisco_ios
```

