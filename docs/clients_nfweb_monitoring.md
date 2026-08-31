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
- compact broker and local-client CPU and resident-memory summaries;
- aligned worker CPU and resident-memory comparisons, ranked on every sample by
  CPU plus memory relative to the largest worker;
- separate CPU and memory trends for the selected worker;
- broker worker and service totals;
- worker keepalive transmit/receive totals and current hold time;
- NFWeb client outbound-queue state;
- local client job-database totals, last-24-hour volume, event count, average
  completion time, and stacked job-status activity over time;
- a full-width database summary for the selected worker, including recent job,
  status, and task counts returned by that worker's existing `job_list` task.

The browser receives new samples over a WebSocket. The Refresh button requests an
immediate sample. A dashboard selector can request refreshes every 5, 10, 30, or
60 seconds; periodic server collection remains shared by all browser tabs. Worker
comparison charts show ten workers at a time and share one vertical scroll/zoom
position when more workers are available.

The job activity chart compares each retained database snapshot with the previous
sample and stacks positive increases for `FAILED`, `STARTED`, `COMPLETED`, and
`STALE`. The client database stores current aggregate counts rather than a status
transition journal, so decreases are not presented as invented transitions.

## Data Sources

Monitoring reuses normal NORFAB interfaces:

| Component data | Existing interface |
| --- | --- |
| Broker state and process resources | `mmi.service.broker` / `show_broker` |
| Worker registration and keepalives | `mmi.service.broker` / `show_workers` |
| Worker process resources and uptime | `get_watchdog_stats` on all workers |
| Local client counters and process resources | The NFWeb process and its native `NFPClient` |
| Job and event statistics | The native client's existing job database |
| Selected-worker job statistics | Existing `job_list` task on that worker |

The monitoring request traffic itself is included in the local client's job and
message accounting. The dashboard reads aggregate database statistics; it does
not capture or retain message payloads or create a separate monitoring database.
Selecting a worker makes one targeted `job_list` request and summarizes at most
the latest 1,000 returned records. The card labels a full window as truncated;
it does not present the bounded result as an all-time worker total.

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
