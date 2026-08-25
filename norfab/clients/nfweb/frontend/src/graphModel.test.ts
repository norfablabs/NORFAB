import { describe, expect, it } from "vitest";
import type { TopologyLink, TopologyNode } from "./types";
import {
  addParallelCurves,
  endpointId,
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
      link("inventory:1", "spine-1", "spine-2"),
      { ...link("lldp:1", "spine-2", "spine-1"), layer: "lldp" },
    ]);

    expect(links).toHaveLength(2);
    expect(links.every((item) => item.curvature && item.curvature > 0)).toBe(
      true,
    );
    expect(links[0].rotation).not.toBe(links[1].rotation);
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
