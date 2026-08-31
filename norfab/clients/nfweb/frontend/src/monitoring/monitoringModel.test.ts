import { describe, expect, it } from "vitest";
import type { MonitoringComponent, MonitoringDatabaseStats } from "../types";
import {
  jobStatusActivity,
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
