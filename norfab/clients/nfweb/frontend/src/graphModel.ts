import type { ForceGraphMethods } from "react-force-graph-3d";
import type { Health, TopologyLink, TopologyNode } from "./types";

export const LAYER_LABELS: Record<string, string> = {
  inventory: "NetBox",
  lldp: "LLDP",
  bgp: "BGP",
  interfaces: "Interfaces",
};

export const LAYER_COLORS: Record<string, string> = {
  inventory: "#3b82f6",
  lldp: "#f6c453",
  bgp: "#b67cff",
  interfaces: "#38d9c4",
};

export const HEALTH_COLORS: Record<Health, string> = {
  healthy: "#38d9c4",
  warning: "#f6c453",
  critical: "#ff5c7a",
  unknown: "#667085",
};

export type GraphNode = TopologyNode & {
  x?: number;
  y?: number;
  z?: number;
  vx?: number;
  vy?: number;
  vz?: number;
  fx?: number;
  fy?: number;
  fz?: number;
  displaySize?: number;
};

export type GraphData = { nodes: GraphNode[]; links: TopologyLink[] };
export type GraphHandle = ForceGraphMethods<GraphNode, TopologyLink>;

export function endpointId(value: string | TopologyNode): string {
  return typeof value === "string" ? value : value.id;
}

export function numericMetric(link: TopologyLink): number {
  const candidates = [
    "source_output_utilization",
    "target_output_utilization",
    "source_input_utilization",
    "target_input_utilization",
  ];
  return candidates.reduce((maximum, key) => {
    const rawValue = link.metrics[key];
    const value =
      typeof rawValue === "string"
        ? Number(rawValue.replaceAll(",", "").match(/-?\d+(?:\.\d+)?/)?.[0])
        : Number(rawValue);
    return Number.isFinite(value) ? Math.max(maximum, value) : maximum;
  }, 0);
}

export function trafficMetric(
  link: TopologyLink,
  side: "source" | "target",
): number {
  return ["rate_bps_in", "rate_bps_out"].reduce((total, metric) => {
    const value = Number(link.metrics[`${side}_${metric}`]);
    return Number.isFinite(value) ? total + Math.max(0, value) : total;
  }, 0);
}

export function addParallelCurves(links: TopologyLink[]): TopologyLink[] {
  const groups = new Map<string, TopologyLink[]>();
  links.forEach((link) => {
    const pair = [endpointId(link.source), endpointId(link.target)]
      .sort()
      .join("--");
    groups.set(pair, [...(groups.get(pair) ?? []), link]);
  });
  return links.map((link) => {
    const pair = [endpointId(link.source), endpointId(link.target)]
      .sort()
      .join("--");
    const peers = groups.get(pair) ?? [link];
    const index = peers.findIndex((candidate) => candidate.id === link.id);
    return {
      ...link,
      curvature: peers.length === 1 ? 0 : 0.35 + peers.length * 0.08,
      rotation: peers.length === 1 ? 0 : (Math.PI * 2 * index) / peers.length,
    };
  });
}
