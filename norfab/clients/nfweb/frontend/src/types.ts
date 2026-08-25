export type Health = "healthy" | "warning" | "critical" | "unknown";
export type SnapshotStatus = "complete" | "partial" | "empty" | "failed";

export interface NFWebFooterConfig {
  message: string;
  fastapi_url: string | null;
  docs_url: string | null;
  github_url: string | null;
}

export interface NFWebBrowserConfig {
  footer: NFWebFooterConfig;
}

export interface TopologyNode {
  id: string;
  label: string;
  kind: string;
  health: Health;
  layers: string[];
  attributes: Record<string, unknown>;
}

export interface TopologyLink {
  id: string;
  source: string | TopologyNode;
  target: string | TopologyNode;
  layer: string;
  health: Health;
  metrics: Record<string, unknown>;
  attributes: Record<string, unknown>;
}

export interface CollectionError {
  layer: string;
  message: string;
  worker?: string | null;
}

export interface CollectionEvent {
  service: string;
  message: string;
  severity: string;
  task?: string | null;
  worker?: string | null;
  status?: string | null;
  timestamp?: string | null;
  resource?: string | string[] | null;
}

export interface DeviceOption {
  name: string;
  sources: string[];
}

export interface DeviceInventory {
  devices: DeviceOption[];
  selected: string[];
  errors: CollectionError[];
}

export interface DeviceSelection {
  selected: string[];
  snapshot: TopologySnapshot | null;
}

export interface TopologyLogEntry extends CollectionEvent {
  id: string;
  snapshot_id: string;
  collected_at: string;
  kind: "event" | "error";
}

export interface TopologyHistoryItem {
  snapshot_id: string;
  collected_at: string;
}

export interface TopologySnapshot {
  snapshot_id: string;
  collected_at: string;
  duration_ms: number;
  status: SnapshotStatus;
  devices: string[];
  layers: string[];
  nodes: TopologyNode[];
  links: TopologyLink[];
  errors: CollectionError[];
  events: CollectionEvent[];
}

export type SelectedItem =
  | { kind: "node"; value: TopologyNode }
  | { kind: "link"; value: TopologyLink }
  | null;
