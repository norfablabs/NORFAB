# gNMI Get

Retrieve device configuration or operational data with `gnmi_get`, backed by
Nornir-Salt and pygnmi. Set, delete, and subscriptions are not exposed.

## Output

Results are keyed by host, then `get`. Each reply contains backend notification
data; values depend on the device's YANG models. `add_details=True` includes
failure metadata; `to_dict=False` returns serialized records instead.
Unmatched filters return `no_match`.

## Examples

Configure the gRPC port, credentials, and TLS in host inventory:

```yaml
connection_options:
  pygnmi:
    port: 6030
    extras:
      gnmi_timeout: 10
      path_cert: /etc/norfab/certs/device-ca.pem
```

Username and password inherit from the host. Set the port explicitly when the
host's main port is SSH. For an unencrypted test lab only, replace `path_cert`
with `insecure: true`.

=== "CLI"

    ```bash
    nf# nornir gnmi get FL ceos-spine-1 path openconfig-system:system/config/hostname datatype config
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="inventory.yaml") as nf:
        client = nf.make_client()
        result = client.run_job(
            "nornir", "gnmi_get",
            kwargs={
                "FL": ["ceos-spine-1"],
                "path": ["openconfig-system:system/config/hostname"],
                "datatype": "config",
            },
        )
        print(result)
    ```

## Notes

- Paths must be a nonempty list. Use `prefix` for a shared path prefix and
  `target` for a gNMI target name.
- Encoding defaults to backend negotiation; an explicit encoding must be
  supported by the device.
- Common host filters, retries, and structured processors such as `jmespath`
  are available. Connections are reused and tracked by the worker watchdog.
- Dependency debug logs can include backend arguments.

## Troubleshooting

Connection failures usually require checking the gRPC port, TLS settings,
credentials, and device gNMI service. RPC failures may indicate an unsupported
YANG path, datatype, or encoding. Inspect results with `add_details=True`.

## Task Command Shell Reference

```bash
nf# man tree nornir gnmi
nornir
└── gnmi
    └── get
```

## Python API Reference

::: norfab.workers.nornir_worker.gnmi_tasks.GnmiTasks.gnmi_get
