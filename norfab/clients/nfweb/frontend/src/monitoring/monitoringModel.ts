import type { MonitoringComponent, MonitoringSnapshot } from "../types";

export const maximumMonitoringSamples = 2161;

export type MonitoringResourceField = "memory_mbyte" | "cpu_percent";

function compareComponentNames(
  left: MonitoringComponent,
  right: MonitoringComponent,
) {
  return left.name.localeCompare(right.name, undefined, {
    numeric: true,
    sensitivity: "base",
  });
}

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

function collectedAtMillis(snapshot: Pick<MonitoringSnapshot, "collected_at">) {
  return Date.parse(snapshot.collected_at);
}

export function newerMonitoringSnapshot(
  current: MonitoringSnapshot | null,
  candidate: MonitoringSnapshot | null,
): MonitoringSnapshot | null {
  if (!current) return candidate;
  if (!candidate) return current;
  return collectedAtMillis(candidate) >= collectedAtMillis(current)
    ? candidate
    : current;
}

export function mergeMonitoringHistory(
  current: MonitoringSnapshot[],
  incoming: MonitoringSnapshot[],
  limit = maximumMonitoringSamples,
): MonitoringSnapshot[] {
  const byTimestamp = new Map(
    [...current, ...incoming].map((snapshot) => [snapshot.collected_at, snapshot]),
  );
  return [...byTimestamp.values()]
    .sort((left, right) => collectedAtMillis(left) - collectedAtMillis(right))
    .slice(-limit);
}

export function monitoringComponentAt(
  sample: MonitoringSnapshot,
  id: string,
): MonitoringComponent | undefined {
  if (sample.broker.id === id) return sample.broker;
  if (sample.client.id === id) return sample.client;
  return sample.workers.find((component) => component.id === id);
}

export function fabricComponentsInHistory(
  history: MonitoringSnapshot[],
): MonitoringComponent[] {
  const components = new Map<string, MonitoringComponent>();
  history.forEach((sample) => {
    components.set(sample.broker.id, sample.broker);
    sample.workers.forEach((worker) => components.set(worker.id, worker));
  });
  return [...components.values()].sort((left, right) => {
    if (left.role === "broker") return -1;
    if (right.role === "broker") return 1;
    return compareComponentNames(left, right);
  });
}

export function componentResourceSeries(
  history: MonitoringSnapshot[],
  id: string,
  field: MonitoringResourceField,
): Array<[string, number | null]> {
  return history.map((sample) => [
    sample.collected_at,
    monitoringComponentAt(sample, id)?.[field] ?? null,
  ]);
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
      score(right) - score(left) || compareComponentNames(left, right),
  );
}
