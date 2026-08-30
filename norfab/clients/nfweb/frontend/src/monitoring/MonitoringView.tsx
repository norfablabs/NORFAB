import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Loader,
  ScrollArea,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
  ThemeIcon,
  Title,
} from "@mantine/core";
import {
  IconActivityHeartbeat,
  IconAlertCircle,
  IconCpu,
  IconDatabase,
  IconRefresh,
  IconServer,
} from "@tabler/icons-react";
import type { EChartsOption } from "echarts";
import ReactECharts from "echarts-for-react";
import { api, openMonitoringStream } from "../api";
import type { MonitoringComponent, MonitoringSnapshot } from "../types";

const statusColor: Record<string, string> = {
  active: "fabric",
  alive: "fabric",
  complete: "fabric",
  degraded: "yellow",
  partial: "yellow",
  dead: "red",
  failed: "red",
  unreachable: "red",
  unknown: "gray",
};

function metric(value: number | null, suffix: string, digits = 1) {
  return value === null ? "Unknown" : `${value.toFixed(digits)}${suffix}`;
}

function uptime(seconds: number | null) {
  if (seconds === null) return "Unknown";
  const days = Math.floor(seconds / 86_400);
  const hours = Math.floor((seconds % 86_400) / 3_600);
  const minutes = Math.floor((seconds % 3_600) / 60);
  return days ? `${days}d ${hours}h` : hours ? `${hours}h ${minutes}m` : `${minutes}m`;
}

export default function MonitoringView() {
  const [history, setHistory] = useState<MonitoringSnapshot[]>([]);
  const [latest, setLatest] = useState<MonitoringSnapshot | null>(null);
  const [selectedId, setSelectedId] = useState("broker");
  const [connection, setConnection] = useState<
    "connecting" | "connected" | "disconnected"
  >("connecting");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const acceptSnapshot = useCallback((snapshot: MonitoringSnapshot) => {
    setLatest(snapshot);
    setHistory((current) => [
      ...current.filter((item) => item.collected_at !== snapshot.collected_at),
      snapshot,
    ].slice(-2161));
  }, []);

  useEffect(() => {
    let cancelled = false;
    api
      .monitoringHistory()
      .then((samples) => {
        if (cancelled) return;
        setHistory(samples);
        setLatest(samples.at(-1) ?? null);
      })
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setLoading(false));
    const closeStream = openMonitoringStream(acceptSnapshot, setConnection);
    return () => {
      cancelled = true;
      closeStream();
    };
  }, [acceptSnapshot]);

  const components = useMemo(
    () => latest ? [latest.broker, latest.client, ...latest.workers] : [],
    [latest],
  );
  const selected =
    components.find((component) => component.id === selectedId) ??
    latest?.broker ??
    null;
  const aliveWorkers = latest?.workers.filter((worker) => worker.status === "alive").length ?? 0;

  const gaugeOptions = useMemo(() => {
    const cpu = selected?.cpu_percent ?? null;
    const memory = selected?.memory_mbyte ?? null;
    const makeGauge = (
      value: number | null,
      name: string,
      maximum: number,
      suffix: string,
      color: string,
    ): EChartsOption => ({
      backgroundColor: "transparent",
      aria: { enabled: true },
      series: [{
        type: "gauge",
        min: 0,
        max: maximum,
        startAngle: 210,
        endAngle: -30,
        progress: { show: true, width: 12, itemStyle: { color } },
        axisLine: { lineStyle: { width: 12, color: [[1, "#25313f"]] } },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: { show: false },
        pointer: { show: false },
        title: { color: "#8b98a9", fontSize: 12, offsetCenter: [0, "68%"] },
        detail: {
          color: "#e6edf3",
          fontSize: 25,
          fontWeight: 700,
          offsetCenter: [0, "12%"],
          formatter: value === null ? "Unknown" : `{value}${suffix}`,
        },
        data: [{ value: value ?? 0, name }],
      }],
    });
    return [
      makeGauge(cpu, "CPU", Math.max(100, Math.ceil((cpu ?? 0) / 100) * 100), "%", "#4bbbad"),
      makeGauge(memory, "Resident memory", Math.max(512, Math.ceil((memory ?? 0) / 256) * 256), " MiB", "#6ea8fe"),
    ];
  }, [selected]);

  const trendOption = useMemo<EChartsOption>(() => {
    const points = history.map((sample) => {
      const all = [sample.broker, sample.client, ...sample.workers];
      return all.find((component) => component.id === selected?.id);
    });
    return {
      backgroundColor: "transparent",
      aria: { enabled: true },
      animationDuration: 250,
      color: ["#4bbbad", "#6ea8fe"],
      tooltip: { trigger: "axis", backgroundColor: "#151e29", borderColor: "#334155", textStyle: { color: "#e6edf3" } },
      legend: { top: 0, textStyle: { color: "#9aa8b8" } },
      grid: { left: 46, right: 52, top: 42, bottom: 48 },
      xAxis: { type: "time", axisLabel: { color: "#7f8da0" }, axisLine: { lineStyle: { color: "#334155" } } },
      yAxis: [
        { type: "value", name: "CPU %", min: 0, axisLabel: { color: "#7f8da0" }, splitLine: { lineStyle: { color: "#202b38" } } },
        { type: "value", name: "MiB", min: 0, axisLabel: { color: "#7f8da0" }, splitLine: { show: false } },
      ],
      dataZoom: [{ type: "inside" }, { type: "slider", height: 16, bottom: 6, borderColor: "#334155", fillerColor: "rgba(75,187,173,.18)" }],
      series: [
        { name: "CPU", type: "line", smooth: true, showSymbol: false, connectNulls: false, data: history.map((sample, index) => [sample.collected_at, points[index]?.cpu_percent ?? null]) },
        { name: "Memory", type: "line", yAxisIndex: 1, smooth: true, showSymbol: false, connectNulls: false, areaStyle: { opacity: 0.08 }, data: history.map((sample, index) => [sample.collected_at, points[index]?.memory_mbyte ?? null]) },
      ],
    };
  }, [history, selected]);

  const workerMemoryOption = useMemo<EChartsOption>(() => ({
    backgroundColor: "transparent",
    aria: { enabled: true },
    animationDuration: 250,
    grid: { left: 112, right: 26, top: 12, bottom: 28 },
    xAxis: { type: "value", name: "MiB", axisLabel: { color: "#7f8da0" }, splitLine: { lineStyle: { color: "#202b38" } } },
    yAxis: { type: "category", data: latest?.workers.map((worker) => worker.name) ?? [], axisLabel: { color: "#9aa8b8", width: 96, overflow: "truncate" } },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, backgroundColor: "#151e29", borderColor: "#334155", textStyle: { color: "#e6edf3" } },
    series: [{ type: "bar", data: latest?.workers.map((worker) => worker.memory_mbyte) ?? [], itemStyle: { color: "#4bbbad", borderRadius: [0, 4, 4, 0] }, barMaxWidth: 18 }],
  }), [latest]);

  const messageOption = useMemo<EChartsOption>(() => ({
    backgroundColor: "transparent",
    aria: { enabled: true },
    animationDuration: 250,
    color: ["#4bbbad", "#6ea8fe", "#f5a65b", "#d07cf2"],
    tooltip: { trigger: "axis", backgroundColor: "#151e29", borderColor: "#334155", textStyle: { color: "#e6edf3" } },
    legend: { top: 0, textStyle: { color: "#9aa8b8" } },
    grid: { left: 54, right: 26, top: 42, bottom: 48 },
    xAxis: { type: "time", axisLabel: { color: "#7f8da0" }, axisLine: { lineStyle: { color: "#334155" } } },
    yAxis: { type: "value", min: 0, axisLabel: { color: "#7f8da0" }, splitLine: { lineStyle: { color: "#202b38" } } },
    dataZoom: [{ type: "inside" }, { type: "slider", height: 16, bottom: 6, borderColor: "#334155", fillerColor: "rgba(75,187,173,.18)" }],
    series: [
      { name: "Client TX", type: "line", smooth: true, showSymbol: false, data: history.map((sample) => [sample.collected_at, sample.client.messages_sent]) },
      { name: "Client RX", type: "line", smooth: true, showSymbol: false, data: history.map((sample) => [sample.collected_at, sample.client.messages_received]) },
      { name: "Keepalive TX", type: "line", smooth: true, showSymbol: false, data: history.map((sample) => [sample.collected_at, sample.workers.some((worker) => worker.keepalives_sent !== null) ? sample.workers.reduce((total, worker) => total + (worker.keepalives_sent ?? 0), 0) : null]) },
      { name: "Keepalive RX", type: "line", smooth: true, showSymbol: false, data: history.map((sample) => [sample.collected_at, sample.workers.some((worker) => worker.keepalives_received !== null) ? sample.workers.reduce((total, worker) => total + (worker.keepalives_received ?? 0), 0) : null]) },
    ],
  }), [history]);

  const refresh = async () => {
    setRefreshing(true);
    setError(null);
    try {
      acceptSnapshot(await api.refreshMonitoring());
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setRefreshing(false);
    }
  };

  if (loading && !latest) {
    return <Stack className="monitoring-loading" align="center"><Loader size="sm" /><Text size="sm">Collecting fabric status</Text></Stack>;
  }

  return (
    <ScrollArea className="monitoring-dashboard" type="auto">
      <Stack gap="md" p="lg">
        <Group justify="space-between" align="flex-end">
          <div>
            <Text c="fabric" fw={700} size="xs" tt="uppercase">Fabric observability</Text>
            <Title order={2}>Runtime monitoring</Title>
            <Text c="dimmed" size="sm">Live broker, NFWeb client, worker resources, and keepalive state.</Text>
          </div>
          <Group gap="sm">
            <Badge color={connection === "connected" ? "fabric" : connection === "connecting" ? "yellow" : "red"} variant="light">{connection}</Badge>
            <Button leftSection={<IconRefresh size={16} />} loading={refreshing} onClick={refresh} variant="light">Refresh</Button>
          </Group>
        </Group>

        {error && <Alert color="red" icon={<IconAlertCircle size={18} />} title="Monitoring warning" withCloseButton onClose={() => setError(null)}>{error}</Alert>}
        {latest?.errors.length ? <Alert color="yellow" icon={<IconAlertCircle size={18} />} title="Partial sample">{latest.errors.join("; ")}</Alert> : null}

        <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="md">
          {[
            { label: "Broker", value: latest?.broker.status ?? "unknown", detail: `${latest?.broker.worker_count ?? 0} workers / ${latest?.broker.service_count ?? 0} services`, icon: IconServer },
            { label: "Workers online", value: `${aliveWorkers} / ${latest?.workers.length ?? 0}`, detail: "Broker keepalive state", icon: IconActivityHeartbeat },
            { label: "NFWeb client", value: latest?.client.status ?? "unknown", detail: `${latest?.client.messages_sent ?? 0} TX / ${latest?.client.messages_received ?? 0} RX`, icon: IconDatabase },
            { label: "Collection", value: latest?.status ?? "waiting", detail: latest ? `${latest.duration_ms} ms · ${new Date(latest.collected_at).toLocaleTimeString()}` : "Waiting for data", icon: IconCpu },
          ].map((item) => (
            <Card className="monitoring-summary-card" key={item.label} padding="lg" radius="md" withBorder>
              <Group justify="space-between" align="flex-start">
                <div><Text c="dimmed" size="xs" tt="uppercase" fw={700}>{item.label}</Text><Text fw={800} size="xl" mt={4}>{item.value}</Text></div>
                <ThemeIcon color={statusColor[item.value] ?? "fabric"} size="lg" variant="light"><item.icon size={19} /></ThemeIcon>
              </Group>
              <Text c="dimmed" size="xs" mt="md">{item.detail}</Text>
            </Card>
          ))}
        </SimpleGrid>

        <Group justify="space-between">
          <div><Text fw={700}>Component detail</Text><Text c="dimmed" size="xs">Select a process to inspect its latest reading and three-hour in-memory trend.</Text></div>
          <Select aria-label="Select monitored component" data={components.map((component) => ({ value: component.id, label: `${component.name} · ${component.role}` }))} value={selected?.id ?? null} onChange={(value) => value && setSelectedId(value)} searchable w={280} />
        </Group>

        <SimpleGrid cols={{ base: 1, md: 2, xl: 4 }} spacing="md">
          <Card className="monitoring-chart-card" padding="md" radius="md" withBorder><ReactECharts option={gaugeOptions[0]} style={{ height: 210 }} notMerge lazyUpdate /></Card>
          <Card className="monitoring-chart-card" padding="md" radius="md" withBorder><ReactECharts option={gaugeOptions[1]} style={{ height: 210 }} notMerge lazyUpdate /></Card>
          <Card className="monitoring-chart-card monitoring-chart-card--wide" padding="md" radius="md" withBorder>
            <Group justify="space-between"><div><Text fw={700}>Resource trend</Text><Text c="dimmed" size="xs">{selected?.name ?? "No component selected"}</Text></div><Badge color={statusColor[selected?.status ?? "unknown"]} variant="light">{selected?.status ?? "unknown"}</Badge></Group>
            <ReactECharts option={trendOption} style={{ height: 250 }} notMerge lazyUpdate />
          </Card>
        </SimpleGrid>

        <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="md">
          <Card className="monitoring-chart-card" padding="lg" radius="md" withBorder>
            <Text fw={700}>Worker memory</Text><Text c="dimmed" size="xs">Latest resident memory by worker</Text>
            <ReactECharts option={workerMemoryOption} style={{ height: Math.max(220, (latest?.workers.length ?? 0) * 34) }} notMerge lazyUpdate />
          </Card>
          <Card className="monitoring-chart-card" padding="lg" radius="md" withBorder>
            <Group justify="space-between"><div><Text fw={700}>{selected?.name ?? "Component"}</Text><Text c="dimmed" size="xs">Latest process counters</Text></div><Badge color={statusColor[selected?.status ?? "unknown"]}>{selected?.status ?? "unknown"}</Badge></Group>
            <SimpleGrid cols={2} mt="lg">
              {[
                ["CPU", metric(selected?.cpu_percent ?? null, "%")],
                ["Memory", metric(selected?.memory_mbyte ?? null, " MiB")],
                ["Uptime", uptime(selected?.uptime_seconds ?? null)],
                ["Holdtime", metric(selected?.holdtime_seconds ?? null, " s")],
                ["Keepalives", selected?.keepalives_sent === null || selected?.keepalives_sent === undefined ? "Unknown" : `${selected.keepalives_sent} TX / ${selected.keepalives_received ?? 0} RX`],
                ["Messages", selected?.messages_sent === null || selected?.messages_sent === undefined ? "Unknown" : `${selected.messages_sent} TX / ${selected.messages_received ?? 0} RX`],
                ["Reconnects", selected?.reconnects === null || selected?.reconnects === undefined ? "Unknown" : String(selected.reconnects)],
                ["Queue depth", selected?.queue_depth === null || selected?.queue_depth === undefined ? "Unknown" : String(selected.queue_depth)],
              ].map(([label, value]) => <div className="monitoring-metric" key={label}><Text c="dimmed" size="xs">{label}</Text><Text fw={700}>{value}</Text></div>)}
            </SimpleGrid>
          </Card>
        </SimpleGrid>

        <Card className="monitoring-chart-card" padding="lg" radius="md" withBorder>
          <Text fw={700}>Message counters</Text>
          <Text c="dimmed" size="xs">NFWeb client traffic and aggregate worker keepalives across the retained window</Text>
          <ReactECharts option={messageOption} style={{ height: 280 }} notMerge lazyUpdate />
        </Card>

        <Card className="monitoring-table-card" padding={0} radius="md" withBorder>
          <Group justify="space-between" p="lg"><div><Text fw={700}>Workers</Text><Text c="dimmed" size="xs">Broker liveness and watchdog resource statistics</Text></div><Badge variant="light">{latest?.workers.length ?? 0}</Badge></Group>
          <ScrollArea type="auto">
            <Table highlightOnHover verticalSpacing="sm" horizontalSpacing="lg">
              <Table.Thead><Table.Tr><Table.Th>Worker</Table.Th><Table.Th>Service</Table.Th><Table.Th>Status</Table.Th><Table.Th>CPU</Table.Th><Table.Th>Memory</Table.Th><Table.Th>Uptime</Table.Th><Table.Th>Holdtime</Table.Th><Table.Th>Keepalives</Table.Th></Table.Tr></Table.Thead>
              <Table.Tbody>{latest?.workers.map((worker: MonitoringComponent) => <Table.Tr key={worker.id} onClick={() => setSelectedId(worker.id)} className="monitoring-worker-row"><Table.Td><Text fw={650} size="sm">{worker.name}</Text></Table.Td><Table.Td>{worker.service ?? "Unknown"}</Table.Td><Table.Td><Badge color={statusColor[worker.status]} size="sm" variant="light">{worker.status}</Badge></Table.Td><Table.Td>{metric(worker.cpu_percent, "%")}</Table.Td><Table.Td>{metric(worker.memory_mbyte, " MiB")}</Table.Td><Table.Td>{uptime(worker.uptime_seconds)}</Table.Td><Table.Td>{metric(worker.holdtime_seconds, " s")}</Table.Td><Table.Td>{worker.keepalives_sent === null ? "Unknown" : `${worker.keepalives_sent} / ${worker.keepalives_received}`}</Table.Td></Table.Tr>)}</Table.Tbody>
            </Table>
          </ScrollArea>
        </Card>
      </Stack>
    </ScrollArea>
  );
}
