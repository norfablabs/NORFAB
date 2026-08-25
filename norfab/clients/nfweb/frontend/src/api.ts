import type {
  DeviceInventory,
  DeviceSelection,
  NFWebBrowserConfig,
  TopologyHistoryItem,
  TopologyLogEntry,
  TopologySnapshot,
} from "./types";

async function request<T>(
  path: string,
  method = "GET",
  body?: unknown,
  marker?: string,
): Promise<T> {
  const response = await fetch(path, {
    method,
    headers: {
      Accept: "application/json",
      ...(body !== undefined && { "Content-Type": "application/json" }),
      ...(marker && { "X-NFWeb-Request": marker }),
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
      "topology-selection",
    ),
  refresh: () =>
    request<TopologySnapshot>(
      "/api/v1/topology/refresh",
      "POST",
      undefined,
      "topology-refresh",
    ),
};

export function openTopologyStream(
  onSnapshot: (snapshot: TopologySnapshot) => void,
  onState: (state: "connecting" | "connected" | "disconnected") => void,
): () => void {
  let socket: WebSocket | null = null;
  let stopped = false;
  let retry = 500;
  let reconnectTimer: number | undefined;

  const connect = () => {
    if (stopped) return;
    onState("connecting");
    socket = new WebSocket(
      `ws://${window.location.host}/api/v1/topology/stream`,
    );
    socket.onopen = () => {
      retry = 500;
      onState("connected");
    };
    socket.onmessage = (event) => {
      const message = JSON.parse(event.data) as {
        type: string;
        data?: TopologySnapshot;
      };
      if (message.type === "snapshot" && message.data) onSnapshot(message.data);
    };
    socket.onclose = () => {
      onState("disconnected");
      if (!stopped) {
        reconnectTimer = window.setTimeout(connect, retry);
        retry = Math.min(retry * 2, 10_000);
      }
    };
  };

  connect();
  return () => {
    stopped = true;
    if (reconnectTimer) window.clearTimeout(reconnectTimer);
    socket?.close();
  };
}
