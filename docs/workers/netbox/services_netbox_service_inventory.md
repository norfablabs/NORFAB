# Netbox Worker Inventory

Content of `inventory.yaml` need to be updated to include Netbox worker details:

``` yaml title="inventory.yaml"
broker: 
  endpoint: "tcp://127.0.0.1:5555" 
  shared_key: "5z1:yW}]n?UXhGmz+5CeHN1>:S9k!eCh6JyIhJqO"

workers:
  fastapi-worker-1: 
    - netbox/netbox-worker-1.yaml

topology: 
  workers: 
    - netbox-worker-1
```

To obtain broker `shared_key` run this command on broker:

```
cd <path/to/broker/inventory.yaml>
nfcli --show-broker-shared-key
```

Sample Netbox Worker Inventory:

``` yaml title="netbox/netbox-worker-1.yaml"
service: netbox
cache_use: True # or False, refresh, force
cache_ttl: 31557600
netbox_connect_timeout: 10
netbox_read_timeout: 300
netbox_retries: 3
netbox_retry_backoff: 0.5
branch_create_timeout: 120
grapqhl_max_workers: 4
instances:
  prod:
    default: True
    url: "http://192.168.4.130:8000/"
    token: "0123456789abcdef0123456789abcdef01234567"
    ssl_verify: False
  dev:
    url: "http://192.168.4.131:8000/"
    token: "0123456789abcdef0123456789abcdef01234567"
    ssl_verify: False
  preprod:
    url: "http://192.168.4.132:8000/"
    token: "0123456789abcdef0123456789abcdef01234567"
    ssl_verify: False
```

## Netbox Worker Inventory Parameters

| Parameter | Default | Description |
| --- | --- | --- |
| `service` | `netbox` | Worker service type. Must be set to `netbox` for Netbox workers. |
| `cache_use` | `True` | Controls whether Netbox query results are cached. Supports `True`, `False`, `refresh`, and `force`. |
| `cache_ttl` | `31557600` | Cache entry TTL in seconds. Default is one year. |
| `netbox_connect_timeout` | `10` | Netbox API connection timeout in seconds. |
| `netbox_read_timeout` | `300` | Netbox API read timeout in seconds. |
| `netbox_retries` | `3` | Number of retries for Netbox API requests made through `requests` sessions and `pynetbox` sessions. |
| `netbox_retry_backoff` | `0.5` | Retry backoff factor for Netbox API requests. |
| `branch_create_timeout` | `120` | Maximum wait time in seconds for a Netbox branching plugin branch to become ready. |
| `grapqhl_max_workers` | `4` | Maximum number of parallel workers used by paginated Netbox GraphQL queries. |
| `instances` | required | Mapping of Netbox instance names to connection parameters. At least one instance is required. |

## Netbox Instance Parameters

| Parameter | Default | Description |
| --- | --- | --- |
| `default` | `False` | Marks this instance as the default Netbox instance. If no instance has `default: True`, the last configured instance is used. |
| `url` | required | Base URL for the Netbox instance. Trailing slashes are removed automatically. |
| `token` | required | Netbox API token used for REST, GraphQL, and `pynetbox` requests. |
| `ssl_verify` | `True` | Controls TLS certificate verification. Set to `False` for lab systems with self-signed certificates. |
