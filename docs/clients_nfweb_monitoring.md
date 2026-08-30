---
tags:
  - clients
  - web
  - monitoring
---

# Runtime Monitoring Dashboard

NFWeb Runtime Monitoring is a read-only dashboard for the current NORFAB fabric.
It shows the broker, every worker known to the broker, and the local NFWeb client
without deploying another service or telemetry system.

## What It Shows

The dashboard provides:

- current broker, worker, and local-client health;
- CPU and resident-memory gauges for the selected component;
- CPU and memory trends over the retained window;
- worker memory comparison;
- broker worker and service totals;
- worker keepalive transmit/receive totals and current hold time;
- NFWeb client message and aggregate worker keepalive counter trends;
- NFWeb client reconnect and outbound-queue counters;
- worker service, uptime, CPU, memory, and keepalive details.

The browser receives new samples over a WebSocket. The Refresh button requests an
immediate sample; periodic collection remains shared by all browser tabs.

## Data Sources

Monitoring reuses normal NORFAB interfaces:

| Component data | Existing interface |
| --- | --- |
| Broker state and process resources | `mmi.service.broker` / `show_broker` |
| Worker registration and keepalives | `mmi.service.broker` / `show_workers` |
| Worker process resources and uptime | `get_watchdog_stats` on all workers |
| Local client counters and process resources | The NFWeb process and its native `NFPClient` |

The monitoring request traffic itself is included in the local client's message
counters. The dashboard presents counters and sampled status; it does not capture
or retain message payloads.

## In-memory History

Samples are held in a bounded Python deque for up to 180 minutes. They are not
written to SQLite, logs, or another database. Restarting NFWeb clears all
monitoring history, which is intentional.

The history length also has a sample-count bound derived from the collection
interval. The browser uses the server's retained samples to draw trends and then
appends live WebSocket samples.

## Configuration

Configure monitoring under `client.nfweb.monitoring`:

```yaml
client:
  nfweb:
    monitoring:
      collection_interval: 5
      retention_minutes: 180
      request_timeout: 10
```

| Field | Default | Meaning |
| --- | ---: | --- |
| `collection_interval` | `5` | Seconds between samples; minimum 5 seconds |
| `retention_minutes` | `180` | In-memory history window; maximum 180 minutes |
| `request_timeout` | `10` | Seconds allowed for each NORFAB status request |

Unknown settings are rejected.

## Failure Behavior

If a worker does not return watchdog data, it remains visible with the registration
state provided by the broker and unknown resource values. A sample is marked
`partial` when some calls fail and `failed` when broker state is unavailable.
Unknown values are shown as unknown rather than inferred.

Monitoring is polling-based and read-only, has no persistence, and shares NFWeb's
existing security boundary. Restrict NFWeb to a trusted administrative network as
described in the [NFWeb overview](clients_nfweb_overview.md#security-boundary).
