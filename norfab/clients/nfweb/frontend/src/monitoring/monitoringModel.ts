import type { MonitoringComponent, MonitoringSnapshot } from "../types";

export const trackedJobStatuses = [
  "FAILED",
  "STARTED",
  "COMPLETED",
  "STALE",
] as const;

export type TrackedJobStatus = (typeof trackedJobStatuses)[number];

export interface JobStatusActivityPoint {
  collected_at: string;
  counts: Record<TrackedJobStatus, number>;
}

export function jobStatusActivity(
  history: Array<Pick<MonitoringSnapshot, "collected_at" | "database">>,
): JobStatusActivityPoint[] {
  return history.slice(1).map((sample, index) => {
    const previous = history[index];
    return {
      collected_at: sample.collected_at,
      counts: Object.fromEntries(
        trackedJobStatuses.map((status) => [
          status,
          Math.max(
            0,
            (sample.database.jobs_by_status[status] ?? 0) -
              (previous.database.jobs_by_status[status] ?? 0),
          ),
        ]),
      ) as Record<TrackedJobStatus, number>,
    };
  });
}

export function rankWorkersByUtilization(
  workers: MonitoringComponent[],
): MonitoringComponent[] {
  const maximumMemory = Math.max(
    0,
    ...workers.map((worker) => worker.memory_mbyte ?? 0),
  );
  const score = (worker: MonitoringComponent) =>
    (worker.cpu_percent ?? 0) +
    (maximumMemory ? ((worker.memory_mbyte ?? 0) / maximumMemory) * 100 : 0);

  return [...workers].sort(
    (left, right) =>
      score(right) - score(left) || left.name.localeCompare(right.name),
  );
}
