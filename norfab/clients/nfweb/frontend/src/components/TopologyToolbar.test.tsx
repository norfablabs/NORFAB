import { MantineProvider } from "@mantine/core";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import TopologyToolbar from "./TopologyToolbar";

describe("TopologyToolbar", () => {
  it("renders accessible framework controls for the topology actions", () => {
    const markup = renderToStaticMarkup(
      <MantineProvider>
        <TopologyToolbar
          deviceOptions={[{ name: "spine-1", sources: ["nornir"] }]}
          selectedDevices={["spine-1"]}
          draftDevices={["spine-1"]}
          discoveringDevices={false}
          applyingDevices={false}
          onDraftDevices={() => undefined}
          onApplyDevices={() => undefined}
          search=""
          onSearch={() => undefined}
          activeSearch=""
          onApplySearch={() => undefined}
          topologySources={["netbox", "nornir", "live-lldp", "circuits"]}
          onTopologySources={() => undefined}
          protocols={["bgp"]}
          onProtocols={() => undefined}
          statsMode="off"
          onStatsMode={() => undefined}
          health="all"
          onHealth={() => undefined}
          hasGraph
          visualizationPaused={false}
          layoutRunning={false}
          rotationEnabled
          bloomEnabled
          rotationSpeed={1}
          nodeDistance={85}
          nodeSizeMode="fixed"
          onToggleVisualization={() => undefined}
          onToggleLayout={() => undefined}
          onToggleRotation={() => undefined}
          onToggleBloom={() => undefined}
          onRotationSpeed={() => undefined}
          onNodeDistance={() => undefined}
          onNodeSizeMode={() => undefined}
          refreshing={false}
          canRefresh
          onRefresh={() => undefined}
          streamLabel="Live"
          streamColor="fabric"
          live
          history={[
            {
              snapshot_id: "snapshot-1",
              collected_at: "2026-08-25T10:15:30.000Z",
            },
          ]}
          snapshotId="snapshot-1"
          onSelectHistory={() => undefined}
          onLive={() => undefined}
        />
      </MantineProvider>,
    );

    expect(markup).toContain('aria-label="Select topology devices"');
    expect(markup.indexOf('aria-label="Refresh topology"')).toBeLessThan(
      markup.indexOf('aria-label="Select topology devices"'),
    );
    expect(markup).toContain("1 selected");
    expect(markup).toContain('aria-label="Find infrastructure"');
    expect(markup).toContain('aria-label="Apply topology search"');
    expect(markup).toContain("Link selectors");
    expect(markup).toContain('aria-label="Select topology links"');
    expect(markup).toContain('aria-label="Select protocols"');
    expect(markup).toContain('aria-label="Select topology statistics"');
    expect(markup.indexOf('aria-label="Select topology links"')).toBeLessThan(
      markup.indexOf('aria-label="Select protocols"'),
    );
    expect(markup.indexOf('aria-label="Select protocols"')).toBeLessThan(
      markup.indexOf('aria-label="Select topology statistics"'),
    );
    expect(markup).not.toContain('aria-label="NetBox layer"');
    expect(markup).toContain("Health filter");
    expect(markup).toContain("Pause rendering");
    expect(markup).toContain("Recalculate layout");
    expect(markup).toContain("tabler-icon-topology-star-3");
    expect(markup).toContain("Disable rotation");
    expect(markup).toContain("toolbar-spinner--active");
    expect(markup).toContain("Disable bloom");
    expect(markup).toContain(
      'aria-label="Select rotation speed, current 1x"',
    );
    expect(markup.indexOf('aria-label="Disable bloom"')).toBeLessThan(
      markup.indexOf('aria-label="Disable rotation"'),
    );
    expect(markup.indexOf('aria-label="Disable rotation"')).toBeLessThan(
      markup.indexOf('aria-label="Select rotation speed, current 1x"'),
    );
    expect(markup).toContain("Layout distance");
    expect(markup).toContain("Node size mode");
    expect(markup).toContain("Topology history controls");
    expect(markup).toContain("Topology snapshot");
    expect(markup).not.toContain("tabler-icon-history");
    expect(markup.indexOf('aria-label="Return to live topology"')).toBeLessThan(
      markup.indexOf('aria-label="Topology stream: Live"'),
    );
    expect(markup).not.toContain('aria-haspopup="dialog"');
    expect(markup).toContain('aria-haspopup="menu"');
  });
});
