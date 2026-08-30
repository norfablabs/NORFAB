import {
  Suspense,
  lazy,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  ActionIcon,
  Alert,
  Avatar,
  Badge,
  Group,
  Loader,
  ScrollArea,
  Stack,
  Text,
  Tooltip,
} from "@mantine/core";
import {
  IconAlertCircle,
  IconHelpHexagon,
} from "@tabler/icons-react";
import { api, openTopologyStream } from "./api";
import AppFooter from "./components/AppFooter";
import ApplicationNavigation from "./components/ApplicationNavigation";
import type {
  ApplicationView,
  NavigationSection,
} from "./components/ApplicationNavigation";
import InspectorPanel from "./components/InspectorPanel";
import type { InspectorTab } from "./components/InspectorPanel";
import TopologyToolbar from "./components/TopologyToolbar";
import type { NodeSizeMode } from "./components/TopologyToolbar";
import {
  addParallelCurves,
  addTrafficLanes,
  endpointId,
  numericMetric,
  linkMatchesSearch,
  nodeMatchesSearch,
  selectableLayers,
  trafficMetric,
} from "./graphModel";
import type {
  GraphHandle,
  GraphNode,
  RenderedTopologyLink,
} from "./graphModel";
import type {
  DeviceOption,
  Health,
  NFWebFooterConfig,
  SelectedItem,
  TopologyHistoryItem,
  TopologyLink,
  TopologyLogEntry,
  TopologySnapshot,
} from "./types";

type NodeCoordinates = { x: number; y: number; z: number };
type HistoryResponseItem = TopologyHistoryItem | string;

const TopologyGraph = lazy(() => import("./TopologyGraph"));
const MonitoringView = lazy(() => import("./monitoring/MonitoringView"));

function supportsWebGL(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
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

function historyItem(snapshot: TopologySnapshot): TopologyHistoryItem {
  return {
    snapshot_id: snapshot.snapshot_id,
    collected_at: snapshot.collected_at,
  };
}

function normalizeHistory(items: HistoryResponseItem[]): TopologyHistoryItem[] {
  return items.map((item) =>
    typeof item === "string"
      ? { snapshot_id: item, collected_at: item }
      : item,
  );
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
  const [history, setHistory] = useState<TopologyHistoryItem[]>([]);
  const [footerConfig, setFooterConfig] = useState<NFWebFooterConfig>({
    message: "",
    fastapi_url: null,
    docs_url: null,
    github_url: null,
  });
  const [collectionLog, setCollectionLog] = useState<TopologyLogEntry[]>([]);
  const [visibleLayers, setVisibleLayers] = useState<Set<string>>(new Set());
  const [openNavigation, setOpenNavigation] =
    useState<NavigationSection | null>("dashboards");
  const [activeView, setActiveView] = useState<ApplicationView>(
    window.location.hash === "#monitoring" ? "monitoring" : "topology",
  );
  const [search, setSearch] = useState("");
  const [activeSearch, setActiveSearch] = useState("");
  const [health, setHealth] = useState<Health | "all">("all");
  const [selected, setSelected] = useState<SelectedItem>(null);
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("status");
  const [layoutRunning, setLayoutRunning] = useState(true);
  const [visualizationPaused, setVisualizationPaused] = useState(false);
  const [rotationEnabled, setRotationEnabled] = useState(false);
  const [bloomEnabled, setBloomEnabled] = useState(true);
  const [trafficEnabled, setTrafficEnabled] = useState(false);
  const [rotationSpeed, setRotationSpeed] = useState(1);
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
  const [draftDevices, setDraftDevices] = useState<string[]>([]);
  const [discoveringDevices, setDiscoveringDevices] = useState(true);
  const [applyingDevices, setApplyingDevices] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [webglSupported] = useState(supportsWebGL);

  useEffect(() => {
    liveRef.current = live;
  }, [live]);

  useEffect(() => {
    const selectView = () =>
      setActiveView(
        window.location.hash === "#monitoring" ? "monitoring" : "topology",
      );
    window.addEventListener("hashchange", selectView);
    return () => window.removeEventListener("hashchange", selectView);
  }, []);

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
  }, [activeView]);

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
      const nextAvailableLayers = selectableLayers(next.layers);
      setAvailableLayers(nextAvailableLayers);
      if (!layersInitialized.current) {
        layersInitialized.current = true;
        setVisibleLayers(new Set(nextAvailableLayers));
      }
      appendCollectionLog(snapshotLogs(next));
      setHistory((current) => {
        return [
          ...current.filter((item) => item.snapshot_id !== next.snapshot_id),
          historyItem(next),
        ];
      });
      if (liveRef.current) setSnapshot(next);
    },
    [appendCollectionLog, rememberNodePositions],
  );

  useEffect(() => {
    let cancelled = false;
    api
      .config()
      .then((config) => {
        if (!cancelled) setFooterConfig(config.footer);
      })
      .catch((reason: Error) => setError(reason.message));
    api
      .history()
      .then((nextHistory) => {
        if (cancelled) return;
        setHistory(normalizeHistory(nextHistory));
      })
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setLoading(false));
    api
      .devices()
      .then((inventory) => {
        if (cancelled) return;
        setDeviceOptions(inventory.devices);
        setSelectedDevices(inventory.selected);
        setDraftDevices(inventory.selected);
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
      return { nodes: [] as GraphNode[], links: [] as RenderedTopologyLink[] };
    const query = activeSearch.trim().toLowerCase();
    const allowedNodeIds = new Set(
      snapshot.nodes
        .filter((node) => health === "all" || node.health === health)
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
    const matchingLinks = new Set(
      query
        ? links.filter((link) => linkMatchesSearch(link, query)).map((link) => link.id)
        : [],
    );
    const matchingNodeIds = new Set(
      query
        ? snapshot.nodes
            .filter((node) => nodeMatchesSearch(node, query))
            .map((node) => node.id)
        : [],
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
          searchMatch: matchingNodeIds.has(node.id),
        };
      });
    const renderedLinks = addParallelCurves(links).map((link) => ({
      ...link,
      searchMatch:
        Boolean(query) &&
        link.memberLinks.some((member) => matchingLinks.has(member.id)),
    }));
    return {
      nodes,
      links: trafficEnabled ? addTrafficLanes(renderedLinks) : renderedLinks,
    };
  }, [
    snapshot,
    visibleLayers,
    activeSearch,
    health,
    layoutRunning,
    nodeSizeMode,
    trafficEnabled,
  ]);

  useEffect(() => {
    renderedGraphData.current = graphData;
  }, [graphData]);

  useEffect(() => {
    const linkForce = graphRef.current?.d3Force("link") as
      | {
          strength: (
            accessor: (link: RenderedTopologyLink) => number,
          ) => unknown;
        }
      | undefined;
    if (!linkForce) return;
    const degrees = new Map<string, number>();
    graphData.links.forEach((link) => {
      if (link.visualOnly) return;
      [endpointId(link.source), endpointId(link.target)].forEach((nodeId) =>
        degrees.set(nodeId, (degrees.get(nodeId) ?? 0) + 1),
      );
    });
    linkForce.strength((link) => {
      if (link.visualOnly) return 0;
      return (
        1 /
        Math.max(
          1,
          Math.min(
            degrees.get(endpointId(link.source)) ?? 1,
            degrees.get(endpointId(link.target)) ?? 1,
          ),
        )
      );
    });
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
      graphRef.current?.zoomToFit(700, 160);
      hasFramedGraph.current = true;
    }, 900);
    return () => window.clearTimeout(timer);
  }, [graphData.nodes.length]);

  const selectHistory = async (snapshotId: string) => {
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

  const applyDeviceSelection = async () => {
    if (applyingDevices) return;
    setApplyingDevices(true);
    setError(null);
    setLive(true);
    liveRef.current = true;
    setSelected(null);
    try {
      const result = await api.selectDevices(draftDevices);
      setSelectedDevices(result.selected);
      setHistory([]);
      setCollectionLog([]);
      layersInitialized.current = false;
      setAvailableLayers([]);
      setVisibleLayers(new Set());
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
        const normalizedScopeHistory = normalizeHistory(scopeHistory);
        setHistory((current) => [
          ...normalizedScopeHistory,
          ...current.filter(
            (item) =>
              !normalizedScopeHistory.some(
                (scopeItem) => scopeItem.snapshot_id === item.snapshot_id,
              ),
          ),
        ]);
        appendCollectionLog(scopeLogs);
      }
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setApplyingDevices(false);
    }
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

  const streamLabel = !live
    ? "Historical"
    : connection === "connected"
      ? "Live"
      : connection === "connecting"
        ? "Connecting"
        : "Offline";
  const streamColor = !live
    ? "gray"
    : connection === "connected"
      ? "fabric"
      : connection === "connecting"
        ? "yellow"
        : "red";

  return (
    <main
      className={`app-shell${activeView === "monitoring" ? " monitoring-shell" : ""}`}
      id={activeView}
    >
      <header className="topbar">
        <Group className="brand" gap="sm" wrap="nowrap">
          <Avatar color="fabric" radius="sm">
            N
          </Avatar>
          <div>
            <Text fw={800} size="sm">
              NORFAB
            </Text>
            <Text c="dimmed" size="xs">
              Network operations
            </Text>
          </div>
        </Group>
        {activeView === "topology" ? (
          <ScrollArea
            className="topbar-title toolbar-scroll"
            offsetScrollbars="present"
            scrollbarSize={5}
            scrollbars="x"
            type="auto"
            viewportProps={{
              "aria-label": "Topology toolbar",
              role: "region",
            }}
          >
            <TopologyToolbar
            deviceOptions={deviceOptions}
            selectedDevices={selectedDevices}
            draftDevices={draftDevices}
            discoveringDevices={discoveringDevices}
            applyingDevices={applyingDevices}
            onDraftDevices={setDraftDevices}
            onApplyDevices={applyDeviceSelection}
            search={search}
            onSearch={setSearch}
            activeSearch={activeSearch}
            onApplySearch={setActiveSearch}
            availableLayers={availableLayers}
            visibleLayers={[...visibleLayers]}
            onVisibleLayers={(layers) => setVisibleLayers(new Set(layers))}
            health={health}
            onHealth={setHealth}
            hasGraph={graphData.nodes.length > 0}
            visualizationPaused={visualizationPaused}
            layoutRunning={layoutRunning}
            rotationEnabled={rotationEnabled}
            bloomEnabled={bloomEnabled}
            trafficEnabled={trafficEnabled}
            rotationSpeed={rotationSpeed}
            nodeDistance={nodeDistance}
            nodeSizeMode={nodeSizeMode}
            onToggleVisualization={toggleVisualization}
            onToggleLayout={() =>
              layoutRunning ? pauseLayout() : startLayout()
            }
            onToggleRotation={toggleRotation}
            onToggleBloom={() => setBloomEnabled((enabled) => !enabled)}
            onToggleTraffic={() => setTrafficEnabled((enabled) => !enabled)}
            onRotationSpeed={setRotationSpeed}
            onNodeDistance={changeNodeDistance}
            onNodeSizeMode={setNodeSizeMode}
            refreshing={refreshing}
            canRefresh={selectedDevices.length > 0}
            onRefresh={refreshTopology}
            streamLabel={streamLabel}
            streamColor={streamColor}
            live={live}
            history={history}
            snapshotId={snapshot?.snapshot_id}
            onSelectHistory={selectHistory}
            onLive={returnToLive}
            />
          </ScrollArea>
        ) : (
          <Group className="monitoring-topbar-title" gap="sm">
            <Text fw={700} size="sm">
              Monitoring
            </Text>
            <Text c="dimmed" size="xs">
              Live fabric runtime health
            </Text>
          </Group>
        )}
      </header>

      <ApplicationNavigation
        open={openNavigation}
        active={activeView}
        onToggle={setOpenNavigation}
      />

      {activeView === "monitoring" ? (
        <Suspense
          fallback={
            <Stack className="monitoring-loading" align="center" gap="xs">
              <Loader size="sm" />
              <Text size="sm">Loading monitoring dashboard</Text>
            </Stack>
          }
        >
          <MonitoringView />
        </Suspense>
      ) : (
        <>
          <section
            className="graph-stage"
            aria-label="3D network topology"
            ref={graphStageRef}
          >
        <Group className="graph-summary" gap={6} wrap="nowrap">
          <Badge
            color={
              snapshot?.status === "complete"
                ? "fabric"
                : snapshot?.status === "failed"
                  ? "red"
                  : snapshot?.status === "partial"
                    ? "yellow"
                    : "gray"
            }
            variant="light"
            size="sm"
          >
            {snapshot?.status ?? "waiting"}
          </Badge>
          <Text c="dimmed" size="xs">
            {graphData.nodes.length}{" "}
            {graphData.nodes.length === 1 ? "node" : "nodes"} /{" "}
            {graphData.links.filter((link) => !link.visualOnly).length}{" "}
            {graphData.links.filter((link) => !link.visualOnly).length === 1
              ? "link"
              : "links"}
          </Text>
        </Group>
        {loading && webglSupported && (
          <Stack className="stage-message" align="center" gap="xs">
            <Loader size="sm" />
            <Text size="sm">Connecting to the fabric</Text>
          </Stack>
        )}
        {!loading && webglSupported && !snapshot && (
          <Stack className="stage-message" align="center" gap="xs">
            <Text fw={600} size="lg">
              {selectedDevices.length
                ? "Waiting for topology data"
                : "Select devices to build the topology"}
            </Text>
            <Text c="dimmed" size="sm">
              {selectedDevices.length
                ? "The local collector will publish a frame when workers respond."
                : "Discovery does not start collection until a scope is applied."}
            </Text>
          </Stack>
        )}
        {!loading && webglSupported && snapshot && snapshot.nodes.length === 0 && (
          <Stack className="stage-message" align="center" gap="xs">
            <Text fw={600} size="lg">
              Collection returned no topology nodes
            </Text>
            <Text c="dimmed" size="sm">
              Review Collection events for the NetBox query result and worker
              messages.
            </Text>
          </Stack>
        )}
        {!loading &&
          webglSupported &&
          snapshot &&
          snapshot.nodes.length > 0 &&
            graphData.nodes.length === 0 && (
            <Stack className="stage-message" align="center" gap="xs">
              <Text fw={600} size="lg">
                No nodes match the active controls
              </Text>
              <Text c="dimmed" size="sm">
                Clear the search or reset the layer and health filters.
              </Text>
            </Stack>
          )}
        {!loading && !webglSupported && (
          <Stack className="stage-message" align="center" gap="xs">
            <Text fw={600} size="lg">
              3D rendering is unavailable
            </Text>
            <Text c="dimmed" size="sm">
              Enable WebGL or open NFWeb in a browser with 3D acceleration.
            </Text>
          </Stack>
        )}
        {error && (
          <Alert
            className="error-banner"
            color="red"
            title="Client warning"
            icon={<IconAlertCircle size={18} />}
            withCloseButton
            onClose={() => setError(null)}
          >
            {error}
          </Alert>
        )}
        {webglSupported && (
          <Suspense
            fallback={
              <Stack className="stage-message" align="center" gap="xs">
                <Loader size="sm" />
                <Text size="sm">Loading 3D renderer</Text>
              </Stack>
            }
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
                  graphRef.current?.zoomToFit(700, 160);
                  hasFramedGraph.current = true;
                }
              }}
              bloomEnabled={bloomEnabled}
            />
          </Suspense>
        )}
        <Tooltip label="Drag to orbit, scroll to zoom, select a node or link for details">
          <ActionIcon
            className="graph-help"
            aria-label="Show topology interaction help"
            color="gray"
            variant="default"
          >
            <IconHelpHexagon size={16} />
          </ActionIcon>
        </Tooltip>
          </section>

          <InspectorPanel
            selected={selected}
            tab={inspectorTab}
            relatedConnections={relatedConnections}
            collectionLog={collectionLog}
            onTab={setInspectorTab}
            onClose={() => setSelected(null)}
          />
        </>
      )}

      <AppFooter config={footerConfig} />
    </main>
  );
}
