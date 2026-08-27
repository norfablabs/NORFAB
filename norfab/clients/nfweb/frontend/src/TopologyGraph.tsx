import { useEffect } from "react";
import type { MutableRefObject } from "react";
import ForceGraph3D from "react-force-graph-3d";
import {
  CanvasTexture,
  LinearFilter,
  Sprite,
  SpriteMaterial,
  SRGBColorSpace,
  Vector2,
} from "three";
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js";
import type { SelectedItem } from "./types";
import {
  HEALTH_COLORS,
  LAYER_COLORS,
  LAYER_LABELS,
  endpointId,
  numericMetric,
} from "./graphModel";
import type {
  GraphData,
  GraphHandle,
  GraphNode,
  RenderedTopologyLink,
} from "./graphModel";

function escapeHtml(value: unknown): string {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function nodeLabelSprite(node: GraphNode): Sprite {
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d");
  const label = node.label || node.id;
  const fontSize = 28;
  const horizontalPadding = 14;
  const verticalPadding = 8;

  if (!context) return new Sprite();
  context.font = `600 ${fontSize}px system-ui, sans-serif`;
  canvas.width = Math.ceil(
    context.measureText(label).width + horizontalPadding * 2,
  );
  canvas.height = fontSize + verticalPadding * 2;
  context.font = `600 ${fontSize}px system-ui, sans-serif`;
  context.textAlign = "center";
  context.textBaseline = "middle";
  context.fillStyle = "rgba(7, 11, 18, 0.82)";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.strokeStyle = HEALTH_COLORS[node.health];
  context.lineWidth = 2;
  context.strokeRect(1, 1, canvas.width - 2, canvas.height - 2);
  context.fillStyle = "#e7eef8";
  context.fillText(label, canvas.width / 2, canvas.height / 2);

  const texture = new CanvasTexture(canvas);
  texture.colorSpace = SRGBColorSpace;
  texture.minFilter = LinearFilter;
  const sprite = new Sprite(
    new SpriteMaterial({ map: texture, transparent: true, depthWrite: false }),
  );
  const scale = 0.07;
  const nodeRadius = 4 * Math.cbrt(Math.max(node.displaySize ?? 1, 1));
  sprite.scale.set(canvas.width * scale, canvas.height * scale, 1);
  sprite.position.y = nodeRadius + (canvas.height * scale) / 2 + 2;
  return sprite;
}

interface TopologyGraphProps {
  graphRef: MutableRefObject<GraphHandle | undefined>;
  width: number;
  height: number;
  graphData: GraphData;
  rememberNodePositions: () => void;
  selectGraphItem: (item: SelectedItem) => void;
  onEngineStop: () => void;
  bloomEnabled: boolean;
}

export default function TopologyGraph({
  graphRef,
  width,
  height,
  graphData,
  rememberNodePositions,
  selectGraphItem,
  onEngineStop,
  bloomEnabled,
}: TopologyGraphProps) {
  useEffect(() => {
    const composer = graphRef.current?.postProcessingComposer();
    if (!composer) return;
    const bloomPass = new UnrealBloomPass(
      new Vector2(width, height),
      1.15,
      0.65,
      0.08,
    );
    bloomPass.enabled = bloomEnabled;
    composer.addPass(bloomPass);
    return () => {
      composer.removePass(bloomPass);
      bloomPass.dispose();
    };
  }, [bloomEnabled, graphRef, height, width]);

  return (
    <ForceGraph3D<GraphNode, RenderedTopologyLink>
      ref={graphRef}
      width={width}
      height={height}
      graphData={graphData}
      backgroundColor="#000003"
      showNavInfo={false}
      controlType="orbit"
      cooldownTicks={160}
      nodeLabel={(node) => {
        const item = node as GraphNode;
        return `<b>${escapeHtml(item.label)}</b><br>${escapeHtml(item.health)} / ${escapeHtml(item.kind)}`;
      }}
      nodeColor={(node) => {
        const item = node as GraphNode;
        return item.searchMatch ? "#ffffff" : HEALTH_COLORS[item.health];
      }}
      nodeOpacity={0.92}
      nodeResolution={12}
      nodeRelSize={2.2}
      nodeVal={(node) => {
        const item = node as GraphNode;
        return (item.displaySize ?? 5) * (item.searchMatch ? 1.8 : 1);
      }}
      nodeThreeObject={(node) => nodeLabelSprite(node as GraphNode)}
      nodeThreeObjectExtend
      linkLabel={(link) => {
        const item = link as RenderedTopologyLink;
        const count = `${item.memberCount} ${item.memberCount === 1 ? "link" : "links"}`;
        return `<b>${escapeHtml(LAYER_LABELS[item.layer] ?? item.layer)}</b><br>${escapeHtml(endpointId(item.source))} ↔ ${escapeHtml(endpointId(item.target))}<br>${escapeHtml(count)} / ${escapeHtml(item.health)}`;
      }}
      linkColor={(link) => {
        const item = link as RenderedTopologyLink;
        return item.searchMatch
          ? "#ffffff"
          : LAYER_COLORS[item.layer] ?? HEALTH_COLORS.unknown;
      }}
      linkOpacity={0.72}
      linkWidth={(link) =>
        0.7 +
        Math.min(numericMetric(link as RenderedTopologyLink), 100) / 22 +
        ((link as RenderedTopologyLink).searchMatch ? 2.2 : 0)
      }
      linkCurvature="curvature"
      linkCurveRotation="rotation"
      onNodeClick={(node) =>
        selectGraphItem({ kind: "node", value: node as GraphNode })
      }
      onLinkClick={(link) =>
        selectGraphItem({ kind: "link", value: link as RenderedTopologyLink })
      }
      onNodeDragEnd={rememberNodePositions}
      onBackgroundClick={() => selectGraphItem(null)}
      onEngineStop={onEngineStop}
    />
  );
}
