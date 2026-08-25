import { MantineProvider } from "@mantine/core";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import TopologyToolbar from "./TopologyToolbar";

describe("TopologyToolbar", () => {
  it("renders accessible framework controls for the topology actions", () => {
    const markup = renderToStaticMarkup(
      <MantineProvider>
        <TopologyToolbar
          deviceOptions={[{ name: "spine-1", sources: ["netbox"] }]}
          selectedDevices={["spine-1"]}
          draftDevices={["spine-1"]}
          discoveringDevices={false}
          applyingDevices={false}
          onDraftDevices={() => undefined}
          onApplyDevices={() => undefined}
          search=""
          onSearch={() => undefined}
          availableLayers={["inventory", "lldp"]}
          visibleLayers={["inventory"]}
          onVisibleLayers={() => undefined}
          health="all"
          onHealth={() => undefined}
          hasGraph
          visualizationPaused={false}
          layoutRunning
          rotationEnabled={false}
          rotationSpeed={0.7}
          nodeDistance={85}
          nodeSizeMode="fixed"
          onToggleVisualization={() => undefined}
          onToggleLayout={() => undefined}
          onToggleRotation={() => undefined}
          onRotationSpeed={() => undefined}
          onNodeDistance={() => undefined}
          onNodeSizeMode={() => undefined}
          refreshing={false}
          canRefresh
          onRefresh={() => undefined}
          streamLabel="Live"
          streamColor="fabric"
          live
          collectedAt="2026-08-25T10:15:30.000Z"
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
    expect(markup).toContain("1 selected");
    expect(markup).toContain('aria-label="Find infrastructure"');
    expect(markup).toContain("Network layers");
    expect(markup).toContain('aria-label="NetBox layer"');
    expect(markup).toContain('type="checkbox"');
    expect(markup).toContain("Health filter");
    expect(markup).toContain("Pause rendering");
    expect(markup).toContain("Freeze layout");
    expect(markup).toContain("Enable rotation");
    expect(markup).toContain("Rotation speed");
    expect(markup).toContain("Layout distance");
    expect(markup).toContain("Node size mode");
    expect(markup).toContain("Topology history controls");
    expect(markup).toContain("Topology snapshot");
    expect(markup).not.toContain('aria-haspopup="dialog"');
    expect(markup).toContain('aria-haspopup="menu"');
  });
});
