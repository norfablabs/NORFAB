import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { MantineProvider } from "@mantine/core";
import InspectorPanel, {
  detailTableRows,
  formatDetailValue,
  type InspectorTab,
} from "./InspectorPanel";
import type { SelectedItem, TopologyLink } from "../types";

const selected: SelectedItem = {
  kind: "node",
  value: {
    id: "leaf-01",
    label: "leaf-01",
    kind: "device",
    health: "healthy",
    layers: ["lldp"],
    attributes: { site: "lab", status: "active" },
  },
};

const connection: TopologyLink = {
  id: "leaf-01--spine-01",
  source: "leaf-01",
  target: "spine-01",
  layer: "lldp",
  health: "healthy",
  metrics: { source_input_utilization: 12 },
  attributes: {
    source_interface: "Ethernet1",
    target_interface: "Ethernet2",
  },
};

describe("inspector table rows", () => {
  it("formats list values as readable comma-separated text", () => {
    expect(formatDetailValue(["bgp", "lldp"])).toBe("bgp, lldp");
  });

  it("omits empty property values", () => {
    const rows = detailTableRows(
      { site: "dc1", description: "", address: null },
      "properties",
    );

    expect(rows).toEqual([
      {
        id: "properties-site",
        values: { field: "site", value: "dc1" },
      },
    ]);
  });

  it.each<[InspectorTab, string]>([
    ["status", "Status details"],
    ["connections", "Related connections"],
    ["properties", "Source properties"],
  ])("renders the %s tab as a searchable table", (tab, tableLabel) => {
    const markup = renderToStaticMarkup(
      <MantineProvider>
        <InspectorPanel
          selected={selected}
          tab={tab}
          relatedConnections={[connection]}
          collectionLog={[]}
          onTab={() => undefined}
          onClose={() => undefined}
        />
      </MantineProvider>,
    );

    expect(markup).toContain(`aria-label="${tableLabel}"`);
    expect(markup).toContain('placeholder="Search by any field"');
  });
});
