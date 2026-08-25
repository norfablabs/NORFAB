import {
  Suspense,
  lazy,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { api, openTopologyStream } from "./api";
import ApplicationNavigation from "./components/ApplicationNavigation";
import type { NavigationSection } from "./components/ApplicationNavigation";
import InspectorPanel from "./components/InspectorPanel";
import type { InspectorTab } from "./components/InspectorPanel";
import Timeline from "./components/Timeline";
import {
  HEALTH_COLORS,
  LAYER_COLORS,
  LAYER_LABELS,
  addParallelCurves,
  endpointId,
  numericMetric,
  trafficMetric,
} from "./graphModel";
import type { GraphHandle, GraphNode } from "./graphModel";
import type {
  DeviceOption,
  Health,
  SelectedItem,
  TopologyLink,
  TopologyLogEntry,
  TopologySnapshot,
} from "./types";

type NodeCoordinates = { x: number; y: number; z: number };
type NodeSizeMode = "fixed" | "connections" | "traffic";

const TopologyGraph = lazy(() => import("./TopologyGraph"));

function supportsWebGL(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

function relativeTime(value?: string): string {
  if (!value) return "Waiting for first sample";
  const seconds = Math.max(
    0,
    Math.round((Date.now() - Date.parse(value)) / 1000),
  );
  if (seconds < 5) return "Just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  return minutes < 60 ? `${minutes}m ago` : `${Math.floor(minutes / 60)}h ago`;
}

function snapshotLogs(snapshot: TopologySnapshot): TopologyLogEntry[] {
  return [
    ...snapshot.events.map((event, index) => ({
      ...event,
      id: `${snapshot.snapshot_id}:event:${index}`,
      snapshot_id: snapshot.snapshot_id,
      collected_at: snapshot.collected_at,
      kind: "event" as const,
    })),
    ...snapshot.errors.map((error, index) => ({
      id: `${snapshot.snapshot_id}:error:${index}`,
      snapshot_id: snapshot.snapshot_id,
      collected_at: snapshot.collected_at,
      kind: "error" as const,
      service: "topology",
      task: error.layer,
      worker: error.worker,
      severity: "ERROR",
      status: "failed",
      timestamp: snapshot.collected_at,
      resource: null,
      message: error.message,
    })),
  ];
}

export default function App() {
  const graphRef = useRef<GraphHandle | undefined>(undefined);
  const renderedGraphData = useRef<{
    nodes: GraphNode[];
    links: TopologyLink[];
  }>({ nodes: [], links: [] });
  const graphStageRef = useRef<HTMLElement | null>(null);
  const hasFramedGraph = useRef(false);
  const positions = useRef(new Map<string, NodeCoordinates>());
  const newestSnapshot = useRef<TopologySnapshot | null>(null);
  const layersInitialized = useRef(false);
  const [availableLayers, setAvailableLayers] = useState<string[]>([]);
  const [snapshot, setSnapshot] = useState<TopologySnapshot | null>(null);
  const [history, setHistory] = useState<string[]>([]);
  const [collectionLog, setCollectionLog] = useState<TopologyLogEntry[]>([]);
  const [visibleLayers, setVisibleLayers] = useState<Set<string>>(new Set());
  const [openNavigation, setOpenNavigation] =
    useState<NavigationSection | null>("dashboards");
  const [search, setSearch] = useState("");
  const [health, setHealth] = useState<Health | "all">("all");
  const [selected, setSelected] = useState<SelectedItem>(null);
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("status");
  const [layoutRunning, setLayoutRunning] = useState(true);
  const [visualizationPaused, setVisualizationPaused] = useState(false);
  const [rotationEnabled, setRotationEnabled] = useState(false);
  const [rotationSpeed, setRotationSpeed] = useState(0.7);
  const [nodeDistance, setNodeDistance] = useState(85);
  const [nodeSizeMode, setNodeSizeMode] = useState<NodeSizeMode>("fixed");
  const [live, setLive] = useState(true);
  const liveRef = useRef(true);
  const [connection, setConnection] = useState<
    "connecting" | "connected" | "disconnected"
  >("connecting");
  const [loading, setLoading] = useState(true);
  const [graphSize, setGraphSize] = useState({ width: 1, height: 1 });
  const [refreshing, setRefreshing] = useState(false);
  const [deviceOptions, setDeviceOptions] = useState<DeviceOption[]>([]);
  const [selectedDevices, setSelectedDevices] = useState<string[]>([]);
  const [draftDevices, setDraftDevices] = useState<Set<string>>(new Set());
  const [deviceMenuOpen, setDeviceMenuOpen] = useState(false);
  const [discoveringDevices, setDiscoveringDevices] = useState(true);
  const [applyingDevices, setApplyingDevices] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [webglSupported] = useState(supportsWebGL);

  useEffect(() => {
    liveRef.current = live;
  }, [live]);

  useEffect(() => {
    const graph = graphRef.current;
    graph?.d3Force("charge")?.strength(-220);
    graph?.d3Force("link")?.distance(nodeDistance);
  }, [nodeDistance, snapshot?.snapshot_id]);

  useEffect(() => {
    const controls = graphRef.current?.controls() as
      | { autoRotate?: boolean; autoRotateSpeed?: number }
      | undefined;
    if (!controls) return;
    controls.autoRotate = rotationEnabled;
    controls.autoRotateSpeed = rotationSpeed;
  }, [rotationEnabled, rotationSpeed, snapshot?.snapshot_id]);

  useEffect(() => {
    const stage = graphStageRef.current;
    if (!stage) return;
    const observer = new ResizeObserver(([entry]) => {
      setGraphSize({
        width: Math.max(1, Math.floor(entry.contentRect.width)),
        height: Math.max(1, Math.floor(entry.contentRect.height)),
      });
    });
    observer.observe(stage);
    return () => observer.disconnect();
  }, []);

  const rememberNodePositions = useCallback(() => {
    renderedGraphData.current.nodes.forEach((node) => {
      if (
        Number.isFinite(node.x) &&
        Number.isFinite(node.y) &&
        Number.isFinite(node.z)
      ) {
        positions.current.set(node.id, {
          x: node.x as number,
          y: node.y as number,
          z: node.z as number,
        });
      }
    });
  }, []);

  const appendCollectionLog = useCallback((entries: TopologyLogEntry[]) => {
    setCollectionLog((current) => {
      const merged = new Map(current.map((entry) => [entry.id, entry]));
      entries.forEach((entry) => merged.set(entry.id, entry));
      return [...merged.values()].slice(-300);
    });
  }, []);

  const acceptLiveSnapshot = useCallback(
    (next: TopologySnapshot) => {
      rememberNodePositions();
      newestSnapshot.current = next;
      setAvailableLayers(next.layers);
      if (!layersInitialized.current) {
        layersInitialized.current = true;
        setVisibleLayers(new Set(next.layers));
      }
      appendCollectionLog(snapshotLogs(next));
      setHistory((current) => {
        return [
          ...current.filter((snapshotId) => snapshotId !== next.snapshot_id),
          next.snapshot_id,
        ];
      });
      if (liveRef.current) setSnapshot(next);
    },
    [appendCollectionLog, rememberNodePositions],
  );

  useEffect(() => {
    let cancelled = false;
    api
      .history()
      .then((nextHistory) => {
        if (cancelled) return;
        setHistory(nextHistory);
      })
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setLoading(false));
    api
      .devices()
      .then((inventory) => {
        if (cancelled) return;
        setDeviceOptions(inventory.devices);
        setSelectedDevices(inventory.selected);
        setDraftDevices(new Set(inventory.selected));
        if (inventory.errors.length) {
          setError(
            inventory.errors.map((item) => item.message).join("; "),
          );
        }
      })
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setDiscoveringDevices(false));
    api
      .logs()
      .then((entries) => {
        if (!cancelled) appendCollectionLog(entries);
      })
      .catch((reason: Error) => setError(reason.message));
    const closeStream = openTopologyStream(acceptLiveSnapshot, setConnection);
    return () => {
      cancelled = true;
      closeStream();
    };
  }, [acceptLiveSnapshot, appendCollectionLog]);

  const graphData = useMemo(() => {
    if (!snapshot)
      return { nodes: [] as GraphNode[], links: [] as TopologyLink[] };
    const query = search.trim().toLowerCase();
    const allowedNodeIds = new Set(
      snapshot.nodes
        .filter((node) => health === "all" || node.health === health)
        .filter((node) => {
          if (!query) return true;
          return `${node.label} ${node.id} ${JSON.stringify(node.attributes)}`
            .toLowerCase()
            .includes(query);
        })
        .map((node) => node.id),
    );
    const links = snapshot.links.filter(
      (link) =>
        visibleLayers.has(link.layer) &&
        allowedNodeIds.has(endpointId(link.source)) &&
        allowedNodeIds.has(endpointId(link.target)) &&
        (health === "all" || link.health === health),
    );
    const linkedNodes = new Set(
      links.flatMap((link) => [
        endpointId(link.source),
        endpointId(link.target),
      ]),
    );
    const nodeStats = new Map<string, { connections: number; traffic: number }>();
    links.forEach((link) => {
      (["source", "target"] as const).forEach((side) => {
        const nodeId = endpointId(link[side]);
        const current = nodeStats.get(nodeId) ?? { connections: 0, traffic: 0 };
        current.connections += 1;
        current.traffic +=
          trafficMetric(link, side) || numericMetric(link) * 1_000_000;
        nodeStats.set(nodeId, current);
      });
    });
    const nodes = snapshot.nodes
      .filter((node) => allowedNodeIds.has(node.id))
      .filter(
        (node) =>
          linkedNodes.has(node.id) ||
          node.layers.some((layer) => visibleLayers.has(layer)),
      )
      .map((node) => {
        const coordinates = positions.current.get(node.id);
        const stats = nodeStats.get(node.id) ?? { connections: 0, traffic: 0 };
        const displaySize =
          nodeSizeMode === "connections"
            ? 3 + Math.min(stats.connections, 15) * 1.5
            : nodeSizeMode === "traffic"
              ? 3 + Math.min(18, Math.log10(stats.traffic + 1) * 2)
              : node.kind === "device"
                ? 5
                : 2.5;
        return {
          ...node,
          ...(coordinates ?? {}),
          ...(!layoutRunning && coordinates
            ? {
                fx: coordinates.x,
                fy: coordinates.y,
                fz: coordinates.z,
              }
            : {}),
          displaySize,
        };
      });
    return { nodes, links: addParallelCurves(links) };
  }, [snapshot, visibleLayers, search, health, layoutRunning, nodeSizeMode]);

  useEffect(() => {
    renderedGraphData.current = graphData;
  }, [graphData]);

  const relatedConnections = useMemo(() => {
    if (!snapshot || !selected) return [];
    if (selected.kind === "node") {
      return snapshot.links.filter(
        (link) =>
          endpointId(link.source) === selected.value.id ||
          endpointId(link.target) === selected.value.id,
      );
    }
    const selectedPair = [
      endpointId(selected.value.source),
      endpointId(selected.value.target),
    ]
      .sort()
      .join("--");
    return snapshot.links.filter(
      (link) =>
        [endpointId(link.source), endpointId(link.target)].sort().join("--") ===
        selectedPair,
    );
  }, [snapshot, selected]);

  useEffect(() => {
    if (hasFramedGraph.current || graphData.nodes.length === 0) return;
    const timer = window.setTimeout(() => {
      graphRef.current?.zoomToFit(700, 90);
      hasFramedGraph.current = true;
    }, 250);
    return () => window.clearTimeout(timer);
  }, [graphData.nodes.length]);

  const timelineIndex = snapshot
    ? Math.max(
        0,
        history.findIndex(
          (snapshotId) => snapshotId === snapshot.snapshot_id,
        ),
      )
    : Math.max(0, history.length - 1);

  const selectHistory = async (index: number) => {
    const snapshotId = history[index];
    if (!snapshotId) return;
    setLive(false);
    setSelected(null);
    try {
      setSnapshot(await api.snapshot(snapshotId));
    } catch (reason) {
      setError((reason as Error).message);
    }
  };

  const returnToLive = () => {
    setLive(true);
    setSelected(null);
    if (newestSnapshot.current) setSnapshot(newestSnapshot.current);
  };

  const refreshTopology = async () => {
    if (refreshing || selectedDevices.length === 0) return;
    setRefreshing(true);
    setError(null);
    setLive(true);
    liveRef.current = true;
    setSelected(null);
    try {
      acceptLiveSnapshot(await api.refresh());
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setRefreshing(false);
    }
  };

  const toggleDevice = (device: string) => {
    setDraftDevices((current) => {
      const next = new Set(current);
      if (next.has(device)) next.delete(device);
      else next.add(device);
      return next;
    });
  };

  const applyDeviceSelection = async () => {
    if (applyingDevices) return;
    setApplyingDevices(true);
    setError(null);
    setLive(true);
    liveRef.current = true;
    setSelected(null);
    try {
      const result = await api.selectDevices([...draftDevices]);
      setSelectedDevices(result.selected);
      setHistory([]);
      setCollectionLog([]);
      layersInitialized.current = false;
      setAvailableLayers([]);
      setVisibleLayers(new Set());
      setDeviceMenuOpen(false);
      hasFramedGraph.current = false;
      if (result.snapshot) {
        acceptLiveSnapshot(result.snapshot);
      } else {
        newestSnapshot.current = null;
        setSnapshot(null);
      }
      if (result.selected.length) {
        const [scopeHistory, scopeLogs] = await Promise.all([
          api.history(),
          api.logs(),
        ]);
        setHistory((current) => [
          ...scopeHistory,
          ...current.filter((snapshotId) => !scopeHistory.includes(snapshotId)),
        ]);
        appendCollectionLog(scopeLogs);
      }
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setApplyingDevices(false);
    }
  };

  const toggleLayer = (layer: string) => {
    setVisibleLayers((current) => {
      const next = new Set(current);
      if (next.has(layer)) next.delete(layer);
      else next.add(layer);
      return next;
    });
  };

  const startLayout = (distance = nodeDistance) => {
    const graph = graphRef.current;
    if (visualizationPaused) {
      graph?.resumeAnimation();
      setVisualizationPaused(false);
    }
    renderedGraphData.current.nodes.forEach((node) => {
      delete node.fx;
      delete node.fy;
      delete node.fz;
    });
    graph?.d3Force("link")?.distance(distance);
    setLayoutRunning(true);
    window.requestAnimationFrame(() => graph?.d3ReheatSimulation());
  };

  const toggleVisualization = () => {
    if (visualizationPaused) graphRef.current?.resumeAnimation();
    else graphRef.current?.pauseAnimation();
    setVisualizationPaused((paused) => !paused);
  };

  const toggleRotation = () => {
    if (!rotationEnabled && visualizationPaused) {
      graphRef.current?.resumeAnimation();
      setVisualizationPaused(false);
    }
    setRotationEnabled((enabled) => !enabled);
  };

  const pauseLayout = () => {
    renderedGraphData.current.nodes.forEach((node) => {
      if (
        Number.isFinite(node.x) &&
        Number.isFinite(node.y) &&
        Number.isFinite(node.z)
      ) {
        node.fx = node.x;
        node.fy = node.y;
        node.fz = node.z;
      }
    });
    rememberNodePositions();
    setLayoutRunning(false);
  };

  const changeNodeDistance = (value: number) => {
    setNodeDistance(value);
    startLayout(value);
  };

  const selectGraphItem = (item: SelectedItem) => {
    setInspectorTab("status");
    setSelected(item);
  };

  return (
    <main className="app-shell" id="topology">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">N</span>
          <div>
            <strong>NORFAB</strong>
            <span>LOCAL WEB CLIENT</span>
          </div>
        </div>
        <div className="topbar-title">
          <div className="topology-controls">
            <section className="device-control">
              <span className="eyebrow">Devices</span>
              <button
                className="device-selector"
                type="button"
                aria-haspopup="listbox"
                aria-expanded={deviceMenuOpen}
                onClick={() => setDeviceMenuOpen((open) => !open)}
              >
                <span>
                  {discoveringDevices
                    ? "Discovering..."
                    : selectedDevices.length
                      ? `${selectedDevices.length} selected`
                      : "Select devices"}
                </span>
                <span aria-hidden="true">⌄</span>
              </button>
              {deviceMenuOpen && (
                <div className="device-menu" role="listbox" aria-multiselectable>
                  <div className="device-menu-heading">
                    <strong>{deviceOptions.length} discovered</strong>
                    <button
                      type="button"
                      onClick={() => setDraftDevices(new Set())}
                    >
                      Clear
                    </button>
                  </div>
                  <div className="device-options">
                    {deviceOptions.length === 0 ? (
                      <p>No devices reported by NetBox or Nornir.</p>
                    ) : (
                      deviceOptions.map((device) => (
                        <label key={device.name}>
                          <input
                            type="checkbox"
                            checked={draftDevices.has(device.name)}
                            onChange={() => toggleDevice(device.name)}
                          />
                          <span>{device.name}</span>
                          <small>{device.sources.join(" + ")}</small>
                        </label>
                      ))
                    )}
                  </div>
                  <button
                    className="device-apply"
                    type="button"
                    disabled={applyingDevices}
                    onClick={applyDeviceSelection}
                  >
                    {applyingDevices
                      ? "Collecting..."
                      : draftDevices.size
                        ? `Collect ${draftDevices.size} devices`
                        : "Clear topology"}
                  </button>
                </div>
              )}
            </section>

            <section className="search-control">
              <label className="eyebrow" htmlFor="topology-search">
                Find infrastructure
              </label>
              <div className="search-box">
                <input
                  id="topology-search"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Device, site, role, IP..."
                />
                {search && (
                  <button onClick={() => setSearch("")} aria-label="Clear search">
                    Clear
                  </button>
                )}
              </div>
            </section>

            <section className="layer-control">
              <div className="section-heading">
                <span className="eyebrow">Network layers</span>
                <span className="section-count">
                  {visibleLayers.size}/{availableLayers.length}
                </span>
              </div>
              <div className="layer-list">
                {availableLayers.map((layer) => (
                  <button
                    key={layer}
                    className={`layer-button ${visibleLayers.has(layer) ? "active" : ""}`}
                    onClick={() => toggleLayer(layer)}
                  >
                    <span
                      className="layer-swatch"
                      style={{ background: LAYER_COLORS[layer] ?? "#8b93a7" }}
                    />
                    <span>{LAYER_LABELS[layer] ?? layer}</span>
                  </button>
                ))}
              </div>
            </section>

            <section className="health-control">
              <span className="eyebrow">Health filter</span>
              <div className="health-grid">
                {(
                  ["all", "healthy", "warning", "critical", "unknown"] as const
                ).map((item) => (
                  <button
                    key={item}
                    className={health === item ? "active" : ""}
                    onClick={() => setHealth(item)}
                  >
                    {item !== "all" && (
                      <span style={{ background: HEALTH_COLORS[item] }} />
                    )}
                    {item}
                  </button>
                ))}
              </div>
            </section>

            <section className="graph-control">
              <span className="eyebrow">3D graph</span>
              <div className="graph-control-row">
                <button
                  type="button"
                  className={visualizationPaused ? "" : "active"}
                  onClick={toggleVisualization}
                  disabled={graphData.nodes.length === 0}
                >
                  {visualizationPaused ? "Start view" : "Pause view"}
                </button>
                <button
                  type="button"
                  className={layoutRunning ? "active" : ""}
                  onClick={() =>
                    layoutRunning ? pauseLayout() : startLayout()
                  }
                  disabled={graphData.nodes.length === 0}
                >
                  {layoutRunning ? "Pause layout" : "Start layout"}
                </button>
                <button
                  type="button"
                  className={rotationEnabled ? "active" : ""}
                  onClick={toggleRotation}
                  disabled={graphData.nodes.length === 0}
                >
                  Rotation {rotationEnabled ? "on" : "off"}
                </button>
                <label>
                  <span>Rotation speed</span>
                  <select
                    value={rotationSpeed}
                    onChange={(event) =>
                      setRotationSpeed(Number(event.target.value))
                    }
                  >
                    <option value="0.25">Slow</option>
                    <option value="0.7">Normal</option>
                    <option value="1.5">Fast</option>
                  </select>
                </label>
                <label>
                  <span>Layout distance {nodeDistance}</span>
                  <input
                    type="range"
                    min="40"
                    max="180"
                    step="5"
                    value={nodeDistance}
                    onChange={(event) =>
                      changeNodeDistance(Number(event.target.value))
                    }
                  />
                </label>
                <label>
                  <span>Node size</span>
                  <select
                    value={nodeSizeMode}
                    onChange={(event) =>
                      setNodeSizeMode(event.target.value as NodeSizeMode)
                    }
                  >
                    <option value="fixed">Fixed</option>
                    <option value="connections">Connections</option>
                    <option value="traffic">Traffic</option>
                  </select>
                </label>
              </div>
            </section>

            <section className="snapshot-summary">
              <div className="section-heading">
                <span className="eyebrow">Current frame</span>
                <button
                  className="refresh-button"
                  type="button"
                  onClick={refreshTopology}
                  disabled={refreshing || selectedDevices.length === 0}
                >
                  {refreshing ? "Refreshing..." : "Refresh"}
                </button>
              </div>
              <div className={`snapshot-status ${snapshot?.status ?? "empty"}`}>
                <span>{snapshot?.status ?? "waiting"}</span>
                <small>
                  {graphData.nodes.length} nodes / {graphData.links.length} links
                </small>
              </div>
            </section>
          </div>
        </div>
        <div className="live-readout">
          <span className={`connection-dot ${connection}`} />
          <div>
            <strong>{live ? "LIVE" : "HISTORICAL"}</strong>
            <span>{relativeTime(snapshot?.collected_at)}</span>
          </div>
        </div>
      </header>

      <ApplicationNavigation
        open={openNavigation}
        onToggle={setOpenNavigation}
      />

      <section
        className="graph-stage"
        aria-label="3D network topology"
        ref={graphStageRef}
      >
        {loading && (
          <div className="stage-message">
            <span className="loader" />
            Connecting to the fabric
          </div>
        )}
        {!loading && !snapshot && (
          <div className="stage-message">
            <strong>
              {selectedDevices.length
                ? "Waiting for topology data"
                : "Select devices to build the topology"}
            </strong>
            <span>
              {selectedDevices.length
                ? "The local collector will publish a frame when workers respond."
                : "Discovery does not start collection until a scope is applied."}
            </span>
          </div>
        )}
        {!loading && snapshot && snapshot.nodes.length === 0 && (
          <div className="stage-message">
            <strong>Collection returned no topology nodes</strong>
            <span>
              Review Collection events for the NetBox query result and worker
              messages.
            </span>
          </div>
        )}
        {!loading &&
          snapshot &&
          snapshot.nodes.length > 0 &&
          graphData.nodes.length === 0 && (
            <div className="stage-message">
              <strong>No nodes match the active controls</strong>
              <span>Clear the search or reset the layer and health filters.</span>
            </div>
          )}
        {!webglSupported && (
          <div className="stage-message">
            <strong>3D rendering is unavailable</strong>
            <span>
              Enable WebGL or open NFWeb in a browser with 3D acceleration.
            </span>
          </div>
        )}
        {error && (
          <button className="error-banner" onClick={() => setError(null)}>
            <strong>Client warning</strong>
            <span>{error}</span>
            <span>×</span>
          </button>
        )}
        {webglSupported && (
          <Suspense
            fallback={<div className="stage-message">Loading 3D renderer</div>}
          >
            <TopologyGraph
              graphRef={graphRef}
              width={graphSize.width}
              height={graphSize.height}
              graphData={graphData}
              rememberNodePositions={rememberNodePositions}
              selectGraphItem={selectGraphItem}
              onEngineStop={() => {
                const data = renderedGraphData.current;
                rememberNodePositions();
                if (data.nodes.length) setLayoutRunning(false);
                if (!hasFramedGraph.current && data.nodes.length) {
                  graphRef.current?.zoomToFit(700, 90);
                  hasFramedGraph.current = true;
                }
              }}
            />
          </Suspense>
        )}
        <div className="graph-hint">
          DRAG TO ORBIT · SCROLL TO ZOOM · CLICK FOR DETAILS
        </div>
      </section>

      <InspectorPanel
        selected={selected}
        tab={inspectorTab}
        relatedConnections={relatedConnections}
        collectionLog={collectionLog}
        onTab={setInspectorTab}
        onClose={() => setSelected(null)}
      />

      <Timeline
        live={live}
        collectedAt={snapshot?.collected_at}
        historyLength={history.length}
        index={timelineIndex}
        onSelect={selectHistory}
        onLive={returnToLive}
      />
    </main>
  );
}
