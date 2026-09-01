import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ActionIcon, Badge, Button, Card, Group, Loader, Select, SimpleGrid, Stack, Text, ThemeIcon } from "@mantine/core";
import { IconActivityHeartbeat, IconAlertCircle, IconBriefcase, IconCpu, IconDatabase, IconRefresh, IconServer, IconX } from "@tabler/icons-react";
import type { EChartsOption } from "echarts";
import ReactECharts from "echarts-for-react";
import { api, openMonitoringStream } from "../api";
import type { MonitoringSnapshot, MonitoringWorkerDatabaseStats } from "../types";
import {
  componentResourceSeries,
  fabricComponentsInHistory,
  jobStatusActivity,
  mergeMonitoringHistory,
  newerMonitoringSnapshot,
  rankWorkersByUtilization,
  trackedJobStatuses,
} from "./monitoringModel";

const statusColor: Record<string, string> = { active: "fabric", alive: "fabric", complete: "fabric", degraded: "yellow", partial: "yellow", dead: "red", failed: "red", unreachable: "red", unknown: "gray" };
const jobStatusColors: Record<string, string> = { COMPLETED: "#4bbbad", FAILED: "#f06565", STALE: "#f5a65b", STARTED: "#6ea8fe", DISPATCHED: "#8b7cf6", SUBMITTING: "#d07cf2", NEW: "#7f8da0" };
const fabricSeriesColors = ["#f5a65b", "#4bbbad", "#6ea8fe", "#d07cf2", "#8b7cf6", "#f06565", "#76c893", "#f4d35e", "#4cc9f0", "#b8c0ff", "#ff8fab", "#90be6d", "#c77dff"];
const refreshIntervals = [5, 10, 30, 60].map((seconds) => ({ value: String(seconds), label: `${seconds} seconds` }));

function metric(value: number | null | undefined, suffix: string, digits = 1) {
  return value === null || value === undefined ? "Unknown" : `${value.toFixed(digits)}${suffix}`;
}

function compactNumber(value: number) {
  return new Intl.NumberFormat(undefined, { notation: "compact" }).format(value);
}

export default function MonitoringView() {
  const [history, setHistory] = useState<MonitoringSnapshot[]>([]);
  const [latest, setLatest] = useState<MonitoringSnapshot | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [connection, setConnection] = useState<"connecting" | "connected" | "disconnected">("connecting");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshInterval, setRefreshInterval] = useState(5);
  const [error, setError] = useState<string | null>(null);
  const [workerDatabase, setWorkerDatabase] = useState<MonitoringWorkerDatabaseStats | null>(null);
  const [workerDatabaseError, setWorkerDatabaseError] = useState<string | null>(null);
  const [workerDatabaseLoading, setWorkerDatabaseLoading] = useState(false);
  const [workerWindowStart, setWorkerWindowStart] = useState(0);
  const [fabricZoom, setFabricZoom] = useState({ start: 0, end: 100 });
  const refreshInFlight = useRef(false);

  const acceptSnapshot = useCallback((snapshot: MonitoringSnapshot) => {
    setLatest((current) => newerMonitoringSnapshot(current, snapshot));
    setHistory((current) => mergeMonitoringHistory(current, [snapshot]));
    setError(null);
  }, []);

  useEffect(() => {
    let cancelled = false;
    api.monitoringHistory().then((samples) => {
      if (cancelled) return;
      setHistory((current) => mergeMonitoringHistory(current, samples));
      setLatest((current) => newerMonitoringSnapshot(current, samples.at(-1) ?? null));
    }).catch((reason: Error) => {
      if (!cancelled) setError(reason.message);
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });
    const closeStream = openMonitoringStream(acceptSnapshot, setConnection);
    return () => { cancelled = true; closeStream(); };
  }, [acceptSnapshot]);

  const selected = latest?.workers.find((worker) => worker.id === selectedId) ?? latest?.workers[0] ?? null;
  const aliveWorkers = latest?.workers.filter((worker) => worker.status === "alive").length ?? 0;
  const rankedWorkers = useMemo(
    () => rankWorkersByUtilization(latest?.workers ?? []),
    [latest],
  );
  const workerScrollEnabled = rankedWorkers.length > 10;
  const workerWindowEnd = Math.min(
    workerWindowStart + 9,
    Math.max(rankedWorkers.length - 1, 0),
  );
  const currentFabricComponents = useMemo(
    () => latest ? [latest.broker, ...latest.workers] : [],
    [latest],
  );
  const historicalFabricComponents = useMemo(
    () => fabricComponentsInHistory(history),
    [history],
  );
  const fabricMemoryTotal = currentFabricComponents.reduce((total, component) => total + (component.memory_mbyte ?? 0), 0);
  const fabricCpuTotal = currentFabricComponents.reduce((total, component) => total + (component.cpu_percent ?? 0), 0);

  useEffect(() => {
    setWorkerWindowStart(0);
  }, [latest?.collected_at]);

  useEffect(() => {
    let cancelled = false;
    if (!selected?.name) {
      setWorkerDatabase(null);
      setWorkerDatabaseError(null);
      return;
    }
    setWorkerDatabase(null);
    setWorkerDatabaseError(null);
    setWorkerDatabaseLoading(true);
    api.workerDatabaseStats(selected.name)
      .then((statistics) => {
        if (!cancelled) setWorkerDatabase(statistics);
      })
      .catch((reason: Error) => {
        if (!cancelled) setWorkerDatabaseError(reason.message);
      })
      .finally(() => {
        if (!cancelled) setWorkerDatabaseLoading(false);
      });
    return () => { cancelled = true; };
  }, [selected?.name]);

  const comparisonOption = useCallback((field: "memory_mbyte" | "cpu_percent", unit: string, color: string): EChartsOption => ({
    backgroundColor: "transparent",
    aria: { enabled: true },
    animationDuration: 250,
    grid: { left: 126, right: workerScrollEnabled ? 36 : 22, top: 8, bottom: 24 },
    xAxis: { type: "value", name: unit, min: 0, axisLabel: { color: "#7f8da0", fontSize: 10 }, splitLine: { lineStyle: { color: "#202b38" } } },
    yAxis: { type: "category", inverse: true, data: rankedWorkers.map((worker) => worker.name), axisLabel: { color: "#9aa8b8", fontSize: 10, width: 112, overflow: "truncate", interval: 0, hideOverlap: false }, axisTick: { show: false } },
    dataZoom: workerScrollEnabled ? [
      { type: "inside", yAxisIndex: 0, startValue: workerWindowStart, endValue: workerWindowEnd, zoomLock: true, filterMode: "none" },
      { type: "slider", yAxisIndex: 0, startValue: workerWindowStart, endValue: workerWindowEnd, right: 3, width: 10, showDetail: false, showDataShadow: false, brushSelect: false, zoomLock: true, borderColor: "#334155", fillerColor: "rgba(75,187,173,.2)" },
    ] : [],
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, backgroundColor: "#151e29", borderColor: "#334155", textStyle: { color: "#e6edf3" } },
    series: [{ type: "bar", data: rankedWorkers.map((worker) => worker[field]), itemStyle: { color, borderRadius: [0, 3, 3, 0] }, barMaxWidth: 13 }],
  }), [rankedWorkers, workerScrollEnabled, workerWindowEnd, workerWindowStart]);

  const handleWorkerDataZoom = useCallback((event: { batch?: Array<{ start?: number; startValue?: number }>; start?: number; startValue?: number }) => {
    const zoom = event.batch?.[0] ?? event;
    const maximumStart = Math.max(rankedWorkers.length - 10, 0);
    const requestedStart = Number.isFinite(zoom.startValue)
      ? Number(zoom.startValue)
      : Math.round(((zoom.start ?? 0) / 100) * Math.max(rankedWorkers.length - 1, 0));
    setWorkerWindowStart(
      Math.max(0, Math.min(Math.round(requestedStart), maximumStart)),
    );
  }, [rankedWorkers.length]);

  const workerChartEvents = useMemo(
    () => ({ datazoom: handleWorkerDataZoom }),
    [handleWorkerDataZoom],
  );

  const workerMemoryOption = useMemo(() => comparisonOption("memory_mbyte", "MiB", "#4bbbad"), [comparisonOption]);
  const workerCpuOption = useMemo(() => comparisonOption("cpu_percent", "%", "#6ea8fe"), [comparisonOption]);

  const fabricConsumptionOption = useCallback((field: "memory_mbyte" | "cpu_percent", unit: string): EChartsOption => ({
    backgroundColor: "transparent",
    aria: { enabled: true },
    animationDuration: 250,
    color: fabricSeriesColors,
    legend: { type: "scroll", top: 0, left: 4, right: 4, itemWidth: 10, itemHeight: 7, textStyle: { color: "#9aa8b8", fontSize: 9 }, pageTextStyle: { color: "#9aa8b8" } },
    grid: { left: 48, right: 18, top: 30, bottom: 30 },
    xAxis: { type: "time", splitNumber: 4, axisLabel: { color: "#7f8da0", fontSize: 9, hideOverlap: true }, axisLine: { lineStyle: { color: "#334155" } } },
    yAxis: { type: "value", name: unit, min: 0, axisLabel: { color: "#7f8da0", fontSize: 9 }, splitLine: { lineStyle: { color: "#202b38" } } },
    dataZoom: [{ type: "inside", xAxisIndex: 0, start: fabricZoom.start, end: fabricZoom.end }],
    tooltip: { trigger: "axis", order: "valueDesc", backgroundColor: "#151e29", borderColor: "#334155", textStyle: { color: "#e6edf3" } },
    series: historicalFabricComponents.map((component, index) => ({
      name: component.role === "broker" ? "Broker" : component.name,
      type: "line",
      stack: `fabric-${field}`,
      smooth: true,
      showSymbol: false,
      connectNulls: false,
      lineStyle: { width: 1.4, color: fabricSeriesColors[index % fabricSeriesColors.length] },
      areaStyle: { opacity: 0.16, color: fabricSeriesColors[index % fabricSeriesColors.length] },
      emphasis: { focus: "series" },
      data: componentResourceSeries(history, component.id, field),
    })),
  }), [fabricZoom.end, fabricZoom.start, historicalFabricComponents, history]);

  const handleFabricDataZoom = useCallback((event: { batch?: Array<{ start?: number; end?: number }>; start?: number; end?: number }) => {
    const zoom = event.batch?.[0] ?? event;
    setFabricZoom((current) => ({
      start: Math.max(0, Math.min(zoom.start ?? current.start, 100)),
      end: Math.max(0, Math.min(zoom.end ?? current.end, 100)),
    }));
  }, []);

  const fabricChartEvents = useMemo(
    () => ({ datazoom: handleFabricDataZoom }),
    [handleFabricDataZoom],
  );

  const fabricMemoryOption = useMemo(() => fabricConsumptionOption("memory_mbyte", "MiB"), [fabricConsumptionOption]);
  const fabricCpuOption = useMemo(() => fabricConsumptionOption("cpu_percent", "%"), [fabricConsumptionOption]);

  const selectedTrendOption = useCallback((field: "memory_mbyte" | "cpu_percent", unit: string, color: string): EChartsOption => ({
    backgroundColor: "transparent",
    aria: { enabled: true },
    animationDuration: 250,
    tooltip: { trigger: "axis", backgroundColor: "#151e29", borderColor: "#334155", textStyle: { color: "#e6edf3" } },
    grid: { left: 42, right: 18, top: 12, bottom: 34 },
    xAxis: { type: "time", axisLabel: { color: "#7f8da0", fontSize: 10 }, axisLine: { lineStyle: { color: "#334155" } } },
    yAxis: { type: "value", name: unit, min: 0, axisLabel: { color: "#7f8da0", fontSize: 10 }, splitLine: { lineStyle: { color: "#202b38" } } },
    dataZoom: [{ type: "inside" }],
    series: [{ type: "line", smooth: true, showSymbol: false, connectNulls: false, lineStyle: { color, width: 2 }, areaStyle: { color, opacity: 0.08 }, data: componentResourceSeries(history, selected?.id ?? "", field) }],
  }), [history, selected?.id]);

  const selectedMemoryOption = useMemo(() => selectedTrendOption("memory_mbyte", "MiB", "#4bbbad"), [selectedTrendOption]);
  const selectedCpuOption = useMemo(() => selectedTrendOption("cpu_percent", "%", "#6ea8fe"), [selectedTrendOption]);

  const jobsOption = useMemo<EChartsOption>(() => {
    const activity = jobStatusActivity(history);
    return {
      backgroundColor: "transparent",
      aria: { enabled: true },
      animationDuration: 250,
      color: trackedJobStatuses.map((status) => jobStatusColors[status]),
      legend: { top: 0, itemWidth: 9, itemHeight: 9, textStyle: { color: "#9aa8b8", fontSize: 9 } },
      grid: { left: 42, right: 12, top: 30, bottom: 34 },
      xAxis: { type: "time", splitNumber: 3, axisLabel: { color: "#9aa8b8", fontSize: 9, hideOverlap: true }, axisLine: { lineStyle: { color: "#334155" } } },
      yAxis: { type: "value", min: 0, minInterval: 1, axisLabel: { color: "#7f8da0", fontSize: 10 }, splitLine: { lineStyle: { color: "#202b38" } } },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, backgroundColor: "#151e29", borderColor: "#334155", textStyle: { color: "#e6edf3" } },
      dataZoom: [{ type: "inside", xAxisIndex: 0 }],
      series: trackedJobStatuses.map((status) => ({
        name: status,
        type: "bar",
        stack: "status-changes",
        barMaxWidth: 20,
        itemStyle: { color: jobStatusColors[status] },
        data: activity.map((point) => [point.collected_at, point.counts[status]]),
      })),
    };
  }, [history]);

  const refresh = useCallback(async () => {
    if (refreshInFlight.current) return;
    refreshInFlight.current = true;
    setRefreshing(true);
    setError(null);
    try { acceptSnapshot(await api.refreshMonitoring()); }
    catch (reason) { setError((reason as Error).message); }
    finally {
      refreshInFlight.current = false;
      setRefreshing(false);
    }
  }, [acceptSnapshot]);

  const readLatestSnapshot = useCallback(async () => {
    if (refreshInFlight.current) return;
    refreshInFlight.current = true;
    try {
      acceptSnapshot(await api.monitoringSnapshot());
      setError(null);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      refreshInFlight.current = false;
    }
  }, [acceptSnapshot]);

  useEffect(() => {
    const timer = window.setInterval(() => void readLatestSnapshot(), refreshInterval * 1000);
    return () => window.clearInterval(timer);
  }, [readLatestSnapshot, refreshInterval]);

  if (loading && !latest) return <Stack className="monitoring-loading" align="center"><Loader size="sm" /><Text size="sm">Collecting fabric status</Text></Stack>;

  const chartHeight = Math.max(138, Math.min(218, rankedWorkers.length * 18 + 38));
  const database = latest?.database;
  const warningMessage = error ?? (latest?.errors.length ? latest.errors.join("; ") : null);
  const warningSeverity = error ? "error" : "warning";

  return (
    <div className="monitoring-dashboard">
      <Stack className="monitoring-dashboard-content" gap="xs">
        <Group className="monitoring-dashboard-toolbar" justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap"><Text c="fabric" fw={700} size="xs" tt="uppercase">Fabric observability</Text><Text c="dimmed" size="xs">{latest ? `${latest.duration_ms} ms · ${new Date(latest.collected_at).toLocaleTimeString()}` : "Waiting for data"}</Text></Group>
          <div className="monitoring-toolbar-message" data-severity={warningSeverity} role="status" aria-live="polite">
            {warningMessage ? <><IconAlertCircle size={13} /><Text size="xs" title={warningMessage}>{warningMessage}</Text>{error ? <ActionIcon aria-label="Dismiss monitoring warning" color="red" onClick={() => setError(null)} size="xs" variant="subtle"><IconX size={11} /></ActionIcon> : null}</> : null}
          </div>
          <Group gap="xs" wrap="nowrap"><Select aria-label="Monitoring refresh interval" data={refreshIntervals} value={String(refreshInterval)} onChange={(value) => value && setRefreshInterval(Number(value))} allowDeselect={false} size="xs" w={116} /><Badge color={connection === "connected" ? "fabric" : connection === "connecting" ? "yellow" : "red"} variant="light">{connection}</Badge><Button leftSection={<IconRefresh size={14} />} loading={refreshing} onClick={() => void refresh()} size="compact-sm" variant="light">Refresh</Button></Group>
        </Group>

        <div className="monitoring-summary-grid">
          <Card className="monitoring-summary-card" padding="sm" radius="md" withBorder><Group justify="space-between" wrap="nowrap"><Group gap="xs" wrap="nowrap"><ThemeIcon color="fabric" size="md" variant="light"><IconServer size={16} /></ThemeIcon><div><Text c="dimmed" size="xs" fw={700}>BROKER</Text><Badge color={statusColor[latest?.broker.status ?? "unknown"]} size="xs" variant="light">{latest?.broker.status ?? "unknown"}</Badge></div></Group><div className="monitoring-inline-metrics"><span>CPU <b>{metric(latest?.broker.cpu_percent, "%")}</b></span><span>MEM <b>{metric(latest?.broker.memory_mbyte, " MiB")}</b></span><span>WORKERS <b>{latest?.broker.worker_count ?? 0}</b></span></div></Group></Card>
          <Card className="monitoring-summary-card" padding="sm" radius="md" withBorder><Group justify="space-between" wrap="nowrap"><Group gap="xs" wrap="nowrap"><ThemeIcon color="fabric" size="md" variant="light"><IconCpu size={16} /></ThemeIcon><div><Text c="dimmed" size="xs" fw={700}>NFWEB CLIENT</Text><Badge color={statusColor[latest?.client.status ?? "unknown"]} size="xs" variant="light">{latest?.client.status ?? "unknown"}</Badge></div></Group><div className="monitoring-inline-metrics"><span>CPU <b>{metric(latest?.client.cpu_percent, "%")}</b></span><span>MEM <b>{metric(latest?.client.memory_mbyte, " MiB")}</b></span><span>QUEUE <b>{latest?.client.queue_depth ?? 0}</b></span></div></Group></Card>
          <Card className="monitoring-summary-card" padding="sm" radius="md" withBorder><Group justify="space-between" wrap="nowrap"><Group gap="xs" wrap="nowrap"><ThemeIcon color="fabric" size="md" variant="light"><IconActivityHeartbeat size={16} /></ThemeIcon><div><Text c="dimmed" size="xs" fw={700}>WORKERS ONLINE</Text><Text fw={800} size="lg">{aliveWorkers} / {latest?.workers.length ?? 0}</Text></div></Group><Text c="dimmed" size="xs">{latest?.broker.service_count ?? 0} services</Text></Group></Card>
          <Card className="monitoring-summary-card" padding="sm" radius="md" withBorder><Group justify="space-between" wrap="nowrap"><Group gap="xs" wrap="nowrap"><ThemeIcon color="fabric" size="md" variant="light"><IconDatabase size={16} /></ThemeIcon><div><Text c="dimmed" size="xs" fw={700}>CLIENT JOB DB</Text><Text fw={800} size="lg">{compactNumber(database?.total_jobs ?? 0)} jobs</Text></div></Group><div className="monitoring-compact-stat"><b>{compactNumber(database?.jobs_last_24h ?? 0)}</b><span>24h</span></div><div className="monitoring-compact-stat"><b>{compactNumber(database?.total_events ?? 0)}</b><span>events</span></div></Group></Card>
        </div>

        <SimpleGrid className="monitoring-comparison-grid" cols={{ base: 1, md: 2 }} spacing="xs">
          <Card className="monitoring-chart-card" padding="xs" radius="md" withBorder><Group justify="space-between" px={4}><div><Text fw={700} size="sm">Worker memory</Text><Text c="dimmed" size="xs">Ranked by CPU + relative memory · top 10 shown</Text></div><IconDatabase color="#4bbbad" size={17} /></Group><ReactECharts option={workerMemoryOption} style={{ height: chartHeight }} onEvents={workerChartEvents} notMerge /></Card>
          <Card className="monitoring-chart-card" padding="xs" radius="md" withBorder><Group justify="space-between" px={4}><div><Text fw={700} size="sm">Worker CPU</Text><Text c="dimmed" size="xs">Ranked by CPU + relative memory · top 10 shown</Text></div><IconCpu color="#6ea8fe" size={17} /></Group><ReactECharts option={workerCpuOption} style={{ height: chartHeight }} onEvents={workerChartEvents} notMerge /></Card>
        </SimpleGrid>

        <SimpleGrid className="monitoring-fabric-grid" cols={{ base: 1, md: 2 }} spacing="xs">
          <Card className="monitoring-chart-card monitoring-fabric-chart-card" padding="xs" radius="md" withBorder><Group justify="space-between" px={4}><div><Text fw={700} size="sm">Total fabric memory</Text><Text c="dimmed" size="xs">Broker + all workers · stacked by process</Text></div><Text c="fabric" fw={800} size="sm">{metric(fabricMemoryTotal, " MiB")}</Text></Group><ReactECharts option={fabricMemoryOption} style={{ height: 134 }} onEvents={fabricChartEvents} notMerge /></Card>
          <Card className="monitoring-chart-card monitoring-fabric-chart-card" padding="xs" radius="md" withBorder><Group justify="space-between" px={4}><div><Text fw={700} size="sm">Total fabric CPU</Text><Text c="dimmed" size="xs">Broker + all workers · stacked by process</Text></div><Text c="blue" fw={800} size="sm">{metric(fabricCpuTotal, "%")}</Text></Group><ReactECharts option={fabricCpuOption} style={{ height: 134 }} onEvents={fabricChartEvents} notMerge /></Card>
        </SimpleGrid>

        <Card className="monitoring-detail-card" padding="xs" radius="md" withBorder>
          <Group className="monitoring-detail-toolbar" justify="space-between" wrap="nowrap" px={4}>
            <Group gap="sm" wrap="nowrap"><Select aria-label="Select monitored worker" data={latest?.workers.map((worker) => ({ value: worker.id, label: worker.name })) ?? []} value={selected?.id ?? null} onChange={(value) => value && setSelectedId(value)} placeholder="Select worker" searchable size="xs" w={230} /><Badge color={statusColor[selected?.status ?? "unknown"]} size="sm" variant="light">{selected?.status ?? "unknown"}</Badge><Text c="dimmed" size="xs">{selected?.service ?? "No service"}</Text></Group>
            <Group gap="md" wrap="nowrap"><Text c="dimmed" size="xs">CPU <b>{metric(selected?.cpu_percent, "%")}</b></Text><Text c="dimmed" size="xs">Memory <b>{metric(selected?.memory_mbyte, " MiB")}</b></Text><Text c="dimmed" size="xs">Worker jobs <b>{workerDatabaseLoading ? "…" : compactNumber(workerDatabase?.returned_jobs ?? 0)}</b></Text></Group>
          </Group>
          <SimpleGrid className="monitoring-detail-grid" cols={{ base: 1, md: 3 }} spacing="xs">
            <div className="monitoring-mini-chart"><Group className="monitoring-mini-chart-header" gap={5}><IconDatabase color="#4bbbad" size={14} /><Text fw={700} size="xs">Memory trend</Text></Group><ReactECharts option={selectedMemoryOption} style={{ height: 154 }} notMerge lazyUpdate /></div>
            <div className="monitoring-mini-chart"><Group className="monitoring-mini-chart-header" gap={5}><IconCpu color="#6ea8fe" size={14} /><Text fw={700} size="xs">CPU trend</Text></Group><ReactECharts option={selectedCpuOption} style={{ height: 154 }} notMerge lazyUpdate /></div>
            <div className="monitoring-mini-chart"><Group className="monitoring-mini-chart-header" justify="space-between"><Group gap={5}><IconBriefcase color="#d07cf2" size={14} /><div><Text fw={700} size="xs">Job status activity</Text><Text c="dimmed" size="xs">Positive changes per interval</Text></div></Group><Text c="dimmed" size="xs">Avg {metric(database?.avg_completion_seconds, " s")}</Text></Group><ReactECharts option={jobsOption} style={{ height: 154 }} notMerge lazyUpdate /></div>
          </SimpleGrid>
        </Card>

        <Card className="monitoring-worker-db-card" padding="xs" radius="md" withBorder>
          <Group className="monitoring-worker-db-layout" justify="space-between" wrap="nowrap">
            <Group gap="xs" wrap="nowrap">
              <ThemeIcon color="fabric" size="md" variant="light"><IconDatabase size={16} /></ThemeIcon>
              <div className="monitoring-worker-db-title"><Text fw={700} size="xs">{selected?.name ?? "Worker"} job database</Text><Text c="dimmed" size="xs">Recent records from the existing worker job_list task</Text></div>
            </Group>
            {workerDatabaseLoading ? <Loader size="xs" /> : workerDatabaseError ? <Text c="red" size="xs">{workerDatabaseError}</Text> : (
              <Group className="monitoring-worker-db-stats" gap="lg" wrap="nowrap">
                <div className="monitoring-worker-db-metric"><b>{compactNumber(workerDatabase?.returned_jobs ?? 0)}</b><span>{workerDatabase?.potentially_truncated ? `latest ${workerDatabase.window_limit}` : "jobs returned"}</span></div>
                {Object.entries(workerDatabase?.jobs_by_status ?? {}).sort(([left], [right]) => left.localeCompare(right)).map(([status, count]) => <div className="monitoring-worker-db-metric" key={status}><b className={`monitoring-job-status monitoring-job-status-${status.toLowerCase()}`}>{compactNumber(count)}</b><span>{status}</span></div>)}
                <div className="monitoring-worker-db-metric monitoring-worker-db-tasks"><b>{Object.keys(workerDatabase?.jobs_by_task ?? {}).length}</b><span>{Object.entries(workerDatabase?.jobs_by_task ?? {}).slice(0, 3).map(([task, count]) => `${task} ${count}`).join(" · ") || "tasks"}</span></div>
                <div className="monitoring-worker-db-metric"><b>{workerDatabase?.newest_job_ts ? new Date(workerDatabase.newest_job_ts).toLocaleTimeString() : "—"}</b><span>latest job</span></div>
              </Group>
            )}
          </Group>
        </Card>
      </Stack>
    </div>
  );
}
