import { describe, expect, it } from "vitest";
import type { TopologyLink, TopologyNode } from "./types";
import {
  addParallelCurves,
  endpointId,
  linkMatchesSearch,
  nodeMatchesSearch,
  numericMetric,
  selectableLayers,
} from "./graphModel";

function link(
  id: string,
  source: string | TopologyNode,
  target: string | TopologyNode,
  metrics: Record<string, unknown> = {},
): TopologyLink {
  return {
    id,
    source,
    target,
    layer: "lldp",
    health: "healthy",
    metrics,
    attributes: {},
  };
}

describe("topology graph helpers", () => {
  it("only exposes graph-producing layers as selectable controls", () => {
    expect(selectableLayers(["inventory", "lldp", "bgp", "interfaces"])).toEqual(
      ["inventory", "lldp", "bgp"],
    );
  });

  it("reads endpoints after ForceGraph replaces IDs with node objects", () => {
    const node: TopologyNode = {
      id: "spine-1",
      label: "Spine 1",
      kind: "device",
      health: "healthy",
      layers: ["lldp"],
      attributes: {},
    };

    expect(endpointId("spine-1")).toBe("spine-1");
    expect(endpointId(node)).toBe("spine-1");
  });

  it("groups reverse and multi-layer links into stable parallel curves", () => {
    const links = addParallelCurves([
      { ...link("inventory:1", "spine-1", "spine-2"), layer: "inventory" },
      { ...link("lldp:1", "spine-2", "spine-1"), layer: "lldp" },
    ]);

    expect(links).toHaveLength(2);
    expect(links.every((item) => item.curvature && item.curvature > 0)).toBe(
      true,
    );
    expect(links[0].rotation).not.toBe(links[1].rotation);
  });

  it("matches topology elements across labels, layers, and attributes", () => {
    const node: TopologyNode = {
      id: "leaf-1",
      label: "Brisbane leaf",
      kind: "device",
      health: "healthy",
      layers: ["lldp"],
      attributes: { site: "BNE" },
    };
    const peering = {
      ...link("bgp:1", "leaf-1", "spine-1"),
      layer: "bgp",
      attributes: { peer_asn: 65100 },
    };

    expect(nodeMatchesSearch(node, "brisbane")).toBe(true);
    expect(nodeMatchesSearch(node, "bne")).toBe(true);
    expect(linkMatchesSearch(peering, "leaf-1")).toBe(false);
    expect(linkMatchesSearch(peering, "peerings")).toBe(true);
    expect(linkMatchesSearch(peering, "BGP")).toBe(true);
    expect(linkMatchesSearch(peering, "65100")).toBe(true);
  });

  it("bundles same-layer links by node pair without combining layers", () => {
    const links = addParallelCurves([
      {
        ...link("lldp:1", "spine-1", "spine-2", {
          source_output_utilization: 22,
        }),
        attributes: {
          source_interface: "Ethernet1",
          target_interface: "Ethernet2",
        },
      },
      {
        ...link("lldp:2", "spine-2", "spine-1", {
          source_output_utilization: 67,
        }),
        health: "warning",
        attributes: {
          source_interface: "Ethernet4",
          target_interface: "Ethernet3",
        },
      },
      { ...link("inventory:1", "spine-1", "spine-2"), layer: "inventory" },
      { ...link("bgp:1", "spine-1", "spine-2"), layer: "bgp" },
    ]);

    expect(links).toHaveLength(3);
    const lldp = links.find((item) => item.layer === "lldp");
    expect(lldp).toMatchObject({
      source: "spine-1",
      target: "spine-2",
      health: "warning",
      memberCount: 2,
      attributes: {
        combined_links: 2,
        interface_pairs: ["Ethernet1 ↔ Ethernet2", "Ethernet3 ↔ Ethernet4"],
      },
    });
    expect(numericMetric(lldp!)).toBe(67);
    expect(links.map((item) => item.layer).sort()).toEqual([
      "bgp",
      "inventory",
      "lldp",
    ]);
  });

  it("uses the largest reported utilization without inventing missing values", () => {
    expect(
      numericMetric(
        link("lldp:1", "spine-1", "spine-2", {
          source_output_utilization: "27.5%",
          target_input_utilization: 31,
        }),
      ),
    ).toBe(31);
    expect(numericMetric(link("lldp:2", "spine-1", "spine-2"))).toBe(0);
  });
});
