import type {
  DeviceInventory,
  DeviceSelection,
  MonitoringSnapshot,
  MonitoringWorkerDatabaseStats,
  NFWebBrowserConfig,
  TopologyHistoryItem,
  TopologyLogEntry,
  TopologySnapshot,
} from "./types";

async function request<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch(path, {
    method,
    headers: {
      Accept: "application/json",
      ...(body !== undefined && { "Content-Type": "application/json" }),
    },
    ...(body !== undefined && { body: JSON.stringify(body) }),
    cache: "no-store",
  });
  if (!response.ok) {
    const detail = await response
      .json()
      .catch(() => ({ error: response.statusText }));
    throw new Error(detail.error ?? `Request failed with ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  config: () => request<NFWebBrowserConfig>("/api/v1/config"),
  monitoringSnapshot: () =>
    request<MonitoringSnapshot>("/api/v1/monitoring/snapshot"),
  monitoringHistory: () =>
    request<MonitoringSnapshot[]>("/api/v1/monitoring/history"),
  refreshMonitoring: () =>
    request<MonitoringSnapshot>("/api/v1/monitoring/refresh", "POST"),
  workerDatabaseStats: (workerName: string) =>
    request<MonitoringWorkerDatabaseStats>(
      `/api/v1/monitoring/workers/${encodeURIComponent(workerName)}/database`,
    ),
  snapshot: (id: string) =>
    request<TopologySnapshot>(
      `/api/v1/topology/snapshots/${encodeURIComponent(id)}`,
    ),
  history: () => request<TopologyHistoryItem[]>("/api/v1/topology/history"),
  logs: () => request<TopologyLogEntry[]>("/api/v1/topology/logs"),
  devices: () => request<DeviceInventory>("/api/v1/topology/devices"),
  selectDevices: (devices: string[]) =>
    request<DeviceSelection>(
      "/api/v1/topology/selection",
      "POST",
      { devices },
    ),
  refresh: () =>
    request<TopologySnapshot>(
      "/api/v1/topology/refresh",
      "POST",
    ),
};

export type StreamState = "connecting" | "connected" | "disconnected";

interface BrowserLocation {
  protocol: string;
  host: string;
}

export function webSocketUrl(
  path: string,
  location: BrowserLocation = window.location,
): string {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${location.host}${path}`;
}

function openSnapshotStream<T>(
  path: string,
  onSnapshot: (snapshot: T) => void,
  onState: (state: StreamState) => void,
): () => void {
  let socket: WebSocket | null = null;
  let stopped = false;
  let retry = 500;
  let reconnectTimer: number | undefined;

  const connect = () => {
    if (stopped) return;
    onState("connecting");
    socket = new WebSocket(webSocketUrl(path));
    socket.onopen = () => {
      if (stopped) {
        socket?.close();
        return;
      }
      retry = 500;
      onState("connected");
    };
    socket.onmessage = (event) => {
      if (stopped) return;
      if (typeof event.data !== "string") return;
      try {
        const message = JSON.parse(event.data) as {
          type: string;
          data?: T;
        };
        if (message.type === "snapshot" && message.data) onSnapshot(message.data);
      } catch {
        // Ignore malformed frames and keep the live stream connected.
      }
    };
    socket.onclose = () => {
      if (stopped) return;
      onState("disconnected");
      reconnectTimer = window.setTimeout(connect, retry);
      retry = Math.min(retry * 2, 10_000);
    };
  };

  connect();
  return () => {
    stopped = true;
    if (reconnectTimer) window.clearTimeout(reconnectTimer);
    socket?.close();
  };
}

export function openMonitoringStream(
  onSnapshot: (snapshot: MonitoringSnapshot) => void,
  onState: (state: StreamState) => void,
): () => void {
  return openSnapshotStream(
    "/api/v1/monitoring/stream",
    onSnapshot,
    onState,
  );
}

export function openTopologyStream(
  onSnapshot: (snapshot: TopologySnapshot) => void,
  onState: (state: StreamState) => void,
): () => void {
  return openSnapshotStream("/api/v1/topology/stream", onSnapshot, onState);
}
