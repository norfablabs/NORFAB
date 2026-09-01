import { describe, expect, it } from "vitest";
import type { MonitoringComponent, MonitoringDatabaseStats, MonitoringSnapshot } from "../types";
import {
  componentResourceSeries,
  fabricComponentsInHistory,
  jobStatusActivity,
  mergeMonitoringHistory,
  newerMonitoringSnapshot,
  rankWorkersByUtilization,
} from "./monitoringModel";

function worker(
  name: string,
  cpuPercent: number | null,
  memoryMbyte: number | null,
): MonitoringComponent {
  return {
    id: `worker:${name}`,
    name,
    role: "worker",
    status: "alive",
    service: "nornir",
    cpu_percent: cpuPercent,
    memory_mbyte: memoryMbyte,
    uptime_seconds: null,
    holdtime_seconds: null,
    keepalives_sent: null,
    keepalives_received: null,
    messages_sent: null,
    messages_received: null,
    reconnects: null,
    queue_depth: null,
    worker_count: null,
    service_count: null,
  };
}

describe("rankWorkersByUtilization", () => {
  it("sorts descending by CPU plus memory relative to the largest worker", () => {
    const workers = [
      worker("balanced", 45, 500),
      worker("memory-heavy", 5, 1000),
      worker("cpu-heavy", 80, 100),
    ];

    expect(rankWorkersByUtilization(workers).map(({ name }) => name)).toEqual([
      "memory-heavy",
      "balanced",
      "cpu-heavy",
    ]);
    expect(workers.map(({ name }) => name)).toEqual([
      "balanced",
      "memory-heavy",
      "cpu-heavy",
    ]);
  });

  it("treats unknown resource values as zero", () => {
    expect(
      rankWorkersByUtilization([
        worker("unknown", null, null),
        worker("known", 1, 1),
      ]).map(({ name }) => name),
    ).toEqual(["known", "unknown"]);
  });

  it("uses natural worker-name ordering to break equal-score ties", () => {
    expect(
      rankWorkersByUtilization([
        worker("worker-10", 1, 1),
        worker("worker-2", 1, 1),
      ]).map(({ name }) => name),
    ).toEqual(["worker-2", "worker-10"]);
  });
});

function database(jobsByStatus: Record<string, number>): MonitoringDatabaseStats {
  return {
    total_jobs: Object.values(jobsByStatus).reduce((total, value) => total + value, 0),
    jobs_last_24h: 0,
    total_events: 0,
    avg_completion_seconds: null,
    oldest_job_ts: null,
    newest_job_ts: null,
    jobs_by_status: jobsByStatus,
    jobs_by_service: {},
    events_by_severity: {},
  };
}

function snapshot(
  collectedAt: string,
  workers: MonitoringComponent[] = [],
): MonitoringSnapshot {
  return {
    collected_at: collectedAt,
    duration_ms: 1,
    status: "complete",
    broker: { ...worker("broker", 1, 10), id: "broker", role: "broker" },
    client: { ...worker("nfweb", 1, 10), id: "client:nfweb", role: "client" },
    workers,
    database: database({}),
    errors: [],
  };
}

describe("monitoring history", () => {
  it("deduplicates and orders out-of-order HTTP and WebSocket samples", () => {
    const newest = snapshot("2026-08-31T10:00:10Z");
    const oldest = snapshot("2026-08-31T10:00:00Z");
    const middle = snapshot("2026-08-31T10:00:05Z");

    expect(
      mergeMonitoringHistory([newest], [middle, oldest, middle]).map(
        ({ collected_at }) => collected_at,
      ),
    ).toEqual([
      "2026-08-31T10:00:00Z",
      "2026-08-31T10:00:05Z",
      "2026-08-31T10:00:10Z",
    ]);
    expect(newerMonitoringSnapshot(newest, middle)).toBe(newest);
    expect(newerMonitoringSnapshot(middle, newest)).toBe(newest);
  });

  it("retains disconnected workers in fabric history and emits gaps", () => {
    const retired = worker("retired", 20, 200);
    const current = worker("current", 30, 300);
    const history = [
      snapshot("2026-08-31T10:00:00Z", [retired]),
      snapshot("2026-08-31T10:00:05Z", [current]),
    ];

    expect(fabricComponentsInHistory(history).map(({ name }) => name)).toEqual([
      "broker",
      "current",
      "retired",
    ]);
    expect(componentResourceSeries(history, retired.id, "memory_mbyte")).toEqual([
      ["2026-08-31T10:00:00Z", 200],
      ["2026-08-31T10:00:05Z", null],
    ]);
  });
});

describe("jobStatusActivity", () => {
  it("returns positive status-count changes for each sample interval", () => {
    const activity = jobStatusActivity([
      {
        collected_at: "2026-08-31T10:00:00Z",
        database: database({ STARTED: 4, COMPLETED: 10, FAILED: 1 }),
      },
      {
        collected_at: "2026-08-31T10:00:05Z",
        database: database({ STARTED: 6, COMPLETED: 13, FAILED: 2 }),
      },
      {
        collected_at: "2026-08-31T10:00:10Z",
        database: database({ STARTED: 3, COMPLETED: 17, FAILED: 2, STALE: 1 }),
      },
    ]);

    expect(activity).toEqual([
      {
        collected_at: "2026-08-31T10:00:05Z",
        counts: { FAILED: 1, STARTED: 2, COMPLETED: 3, STALE: 0 },
      },
      {
        collected_at: "2026-08-31T10:00:10Z",
        counts: { FAILED: 0, STARTED: 0, COMPLETED: 4, STALE: 1 },
      },
    ]);
  });
});
