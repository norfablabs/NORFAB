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
  lldp: "#f97316",
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
  searchMatch?: boolean;
};

export function selectableLayers(layers: string[]): string[] {
  return layers.filter((layer) => layer !== "interfaces");
}

export type RenderedTopologyLink = TopologyLink & {
  curvature: number;
  rotation: number;
  memberCount: number;
  memberLinks: TopologyLink[];
  searchMatch?: boolean;
};

export type GraphData = { nodes: GraphNode[]; links: RenderedTopologyLink[] };
export type GraphHandle = ForceGraphMethods<GraphNode, RenderedTopologyLink>;

export function endpointId(value: string | TopologyNode): string {
  return typeof value === "string" ? value : value.id;
}

export function numericMetric(
  link: TopologyLink | RenderedTopologyLink,
): number {
  if ("memberLinks" in link && link.memberLinks.length > 1) {
    return link.memberLinks.reduce(
      (maximum, member) => Math.max(maximum, numericMetric(member)),
      0,
    );
  }
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

function includesSearch(value: unknown, query: string): boolean {
  return String(value ?? "").toLowerCase().includes(query);
}

export function nodeMatchesSearch(node: TopologyNode, query: string): boolean {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return false;
  return includesSearch(
    `${node.id} ${node.label} ${node.kind} ${node.health} ${node.layers.join(" ")} ${JSON.stringify(node.attributes)}`,
    normalized,
  );
}

export function linkMatchesSearch(link: TopologyLink, query: string): boolean {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return false;
  return includesSearch(
    `${link.id} ${link.layer} ${LAYER_LABELS[link.layer] ?? ""} ${link.layer === "bgp" ? "peerings" : "links"} ${link.health} ${JSON.stringify(link.attributes)} ${JSON.stringify(link.metrics)}`,
    normalized,
  );
}

const HEALTH_PRIORITY: Record<Health, number> = {
  unknown: 0,
  healthy: 1,
  warning: 2,
  critical: 3,
};

function linkPair(link: TopologyLink): [string, string] {
  return [endpointId(link.source), endpointId(link.target)].sort() as [
    string,
    string,
  ];
}

function bundleAttributes(
  links: TopologyLink[],
  source: string,
): Record<string, unknown> {
  const interfacePairs = links.map((link) => {
    const linkSource = endpointId(link.source);
    const sourceInterface = link.attributes.source_interface ?? "-";
    const targetInterface = link.attributes.target_interface ?? "-";
    return linkSource === source
      ? `${sourceInterface} ↔ ${targetInterface}`
      : `${targetInterface} ↔ ${sourceInterface}`;
  });
  return {
    combined_links: links.length,
    link_ids: links.map((link) => link.id),
    interface_pairs: interfacePairs,
  };
}

function bundleLinksByLayer(
  links: TopologyLink[],
): Array<Omit<RenderedTopologyLink, "curvature" | "rotation">> {
  const groups = new Map<string, TopologyLink[]>();
  links.forEach((link) => {
    const pair = linkPair(link);
    const key = JSON.stringify([link.layer, ...pair]);
    groups.set(key, [...(groups.get(key) ?? []), link]);
  });

  return [...groups.values()].map((members) => {
    const [source, target] = linkPair(members[0]);
    const health = members.reduce(
      (worst, member) =>
        HEALTH_PRIORITY[member.health] > HEALTH_PRIORITY[worst]
          ? member.health
          : worst,
      members[0].health,
    );
    if (members.length === 1) {
      return {
        ...members[0],
        memberCount: 1,
        memberLinks: members,
      };
    }
    return {
      id: `bundle:${members[0].layer}:${encodeURIComponent(source)}:${encodeURIComponent(target)}`,
      source,
      target,
      layer: members[0].layer,
      health,
      metrics: {},
      attributes: bundleAttributes(members, source),
      memberCount: members.length,
      memberLinks: members,
    };
  });
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

export function addParallelCurves(links: TopologyLink[]): RenderedTopologyLink[] {
  const bundledLinks = bundleLinksByLayer(links);
  const groups = new Map<string, typeof bundledLinks>();
  bundledLinks.forEach((link) => {
    const pair = JSON.stringify(linkPair(link));
    groups.set(pair, [...(groups.get(pair) ?? []), link]);
  });
  return bundledLinks.map((link) => {
    const pair = JSON.stringify(linkPair(link));
    const peers = groups.get(pair) ?? [link];
    const index = peers.findIndex((candidate) => candidate.id === link.id);
    return {
      ...link,
      curvature: peers.length === 1 ? 0 : 0.35 + peers.length * 0.08,
      rotation: peers.length === 1 ? 0 : (Math.PI * 2 * index) / peers.length,
    };
  });
}
