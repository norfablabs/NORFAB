import { useState } from "react";
import {
  ActionIcon,
  Badge,
  Button,
  Group,
  Menu,
  ScrollArea,
  SegmentedControl,
  Select,
  Slider,
  Text,
  TextInput,
  Tooltip,
} from "@mantine/core";
import {
  IconChevronDown,
  IconCheck,
  IconLoader2,
  IconPlayerPause,
  IconPlayerPlay,
  IconPointFilled,
  IconRefresh,
  IconSearch,
  IconSparkles,
  IconSnowflake,
  IconTopologyStar3,
  IconX,
} from "@tabler/icons-react";
import { LAYER_COLORS } from "../graphModel";
import type { DeviceOption, Health, TopologyHistoryItem } from "../types";
import Timeline from "./Timeline";

export type NodeSizeMode = "fixed" | "connections" | "traffic";

const LINK_SELECTOR_GROUPS = [
  {
    label: "L1",
    layers: [
      { value: "inventory", label: "NetBox" },
      { value: "lldp", label: "LLDP" },
    ],
  },
  {
    label: "BGP",
    layers: [{ value: "bgp", label: "Peerings" }],
  },
] as const;

interface TopologyToolbarProps {
  deviceOptions: DeviceOption[];
  selectedDevices: string[];
  draftDevices: string[];
  discoveringDevices: boolean;
  applyingDevices: boolean;
  onDraftDevices: (devices: string[]) => void;
  onApplyDevices: () => void | Promise<void>;
  search: string;
  onSearch: (value: string) => void;
  activeSearch: string;
  onApplySearch: (value: string) => void;
  availableLayers: string[];
  visibleLayers: string[];
  onVisibleLayers: (layers: string[]) => void;
  health: Health | "all";
  onHealth: (health: Health | "all") => void;
  hasGraph: boolean;
  visualizationPaused: boolean;
  layoutRunning: boolean;
  rotationEnabled: boolean;
  bloomEnabled: boolean;
  rotationSpeed: number;
  nodeDistance: number;
  nodeSizeMode: NodeSizeMode;
  onToggleVisualization: () => void;
  onToggleLayout: () => void;
  onToggleRotation: () => void;
  onToggleBloom: () => void;
  onRotationSpeed: (speed: number) => void;
  onNodeDistance: (distance: number) => void;
  onNodeSizeMode: (mode: NodeSizeMode) => void;
  refreshing: boolean;
  canRefresh: boolean;
  onRefresh: () => void;
  streamLabel: string;
  streamColor: string;
  live: boolean;
  collectedAt?: string;
  history: TopologyHistoryItem[];
  snapshotId?: string;
  onSelectHistory: (snapshotId: string) => void;
  onLive: () => void;
}

export default function TopologyToolbar({
  deviceOptions,
  selectedDevices,
  draftDevices,
  discoveringDevices,
  applyingDevices,
  onDraftDevices,
  onApplyDevices,
  search,
  onSearch,
  activeSearch,
  onApplySearch,
  availableLayers,
  visibleLayers,
  onVisibleLayers,
  health,
  onHealth,
  hasGraph,
  visualizationPaused,
  layoutRunning,
  rotationEnabled,
  bloomEnabled,
  rotationSpeed,
  nodeDistance,
  nodeSizeMode,
  onToggleVisualization,
  onToggleLayout,
  onToggleRotation,
  onToggleBloom,
  onRotationSpeed,
  onNodeDistance,
  onNodeSizeMode,
  refreshing,
  canRefresh,
  onRefresh,
  streamLabel,
  streamColor,
  live,
  collectedAt,
  history,
  snapshotId,
  onSelectHistory,
  onLive,
}: TopologyToolbarProps) {
  const [deviceMenuOpened, setDeviceMenuOpened] = useState(false);
  const [deviceFilter, setDeviceFilter] = useState("");
  const normalizedDeviceFilter = deviceFilter.trim().toLowerCase();
  const filteredDeviceOptions = normalizedDeviceFilter
    ? deviceOptions.filter((device) =>
        `${device.name} ${device.sources.join(" ")}`
          .toLowerCase()
          .includes(normalizedDeviceFilter),
      )
    : deviceOptions;

  const applyDeviceSelection = async () => {
    await onApplyDevices();
    setDeviceMenuOpened(false);
    setDeviceFilter("");
  };
  const normalizedSearch = search.trim();
  const searchIsApplied =
    Boolean(activeSearch) &&
    normalizedSearch.toLowerCase() === activeSearch.toLowerCase();
  const toggleSearch = () => {
    onApplySearch(searchIsApplied ? "" : normalizedSearch);
  };

  const changeVisibleLinkGroup = (
    groupLayers: readonly string[],
    selectedGroupLayers: string[],
  ) => {
    const group = new Set(groupLayers);
    const nextLayers = new Set(
      visibleLayers.filter((layer) => !group.has(layer)),
    );
    selectedGroupLayers.forEach((layer) => nextLayers.add(layer));
    onVisibleLayers(
      availableLayers.filter((layer) => nextLayers.has(layer)),
    );
  };

  return (
    <Group className="topology-controls" gap={8} wrap="nowrap">
      <Tooltip label="Refresh topology">
        <ActionIcon
          className="toolbar-control"
          aria-label="Refresh topology"
          variant="subtle"
          loading={refreshing}
          disabled={!canRefresh}
          onClick={onRefresh}
          size="sm"
        >
          <IconRefresh size={15} />
        </ActionIcon>
      </Tooltip>

      <Menu
        opened={deviceMenuOpened}
        onChange={setDeviceMenuOpened}
        closeOnItemClick={false}
        position="bottom-start"
        shadow="md"
        width={320}
      >
        <Menu.Target>
          <Button
            className="toolbar-control toolbar-control--devices"
            aria-label="Select topology devices"
            aria-expanded={deviceMenuOpened}
            loading={discoveringDevices}
            size="xs"
            variant="default"
            rightSection={<IconChevronDown size={14} />}
          >
            {discoveringDevices
              ? "Discovering devices"
              : selectedDevices.length
                ? `${selectedDevices.length} selected`
                : "Select devices"}
          </Button>
        </Menu.Target>
        <Menu.Dropdown>
          <Menu.Label>{deviceOptions.length} discovered</Menu.Label>
          <TextInput
            aria-label="Filter topology devices"
            leftSection={<IconSearch size={14} />}
            mb={6}
            placeholder="Filter devices..."
            rightSection={
              deviceFilter ? (
                <ActionIcon
                  aria-label="Clear device filter"
                  color="gray"
                  onClick={() => setDeviceFilter("")}
                  size="sm"
                  variant="subtle"
                >
                  <IconX size={13} />
                </ActionIcon>
              ) : undefined
            }
            size="xs"
            value={deviceFilter}
            onChange={(event) => setDeviceFilter(event.currentTarget.value)}
          />
          <Menu.Item
            color="gray"
            disabled={draftDevices.length === 0}
            leftSection={<IconX size={14} />}
            onClick={() => onDraftDevices([])}
          >
            Clear selection
          </Menu.Item>
          <Menu.Divider />
          <ScrollArea.Autosize mah={260} type="auto">
            {deviceOptions.length ? (
              filteredDeviceOptions.length ? (
                <Menu.CheckboxGroup value={draftDevices} onChange={onDraftDevices}>
                  {filteredDeviceOptions.map((device) => (
                    <Menu.CheckboxItem
                      aria-label={`Select ${device.name}`}
                      key={device.name}
                      value={device.name}
                      rightSection={
                        <Text c="dimmed" size="xs">
                          {device.sources.join(" + ") || "inventory"}
                        </Text>
                      }
                    >
                      {device.name}
                    </Menu.CheckboxItem>
                  ))}
                </Menu.CheckboxGroup>
              ) : (
                <Text c="dimmed" p="sm" size="xs">
                  No devices match this filter.
                </Text>
              )
            ) : (
              <Text c="dimmed" p="sm" size="xs">
                No devices reported by NetBox or Nornir.
              </Text>
            )}
          </ScrollArea.Autosize>
          <Menu.Divider />
          <Menu.Item
            aria-label="Apply device scope"
            color="teal"
            disabled={applyingDevices}
            leftSection={<IconCheck size={14} />}
            onClick={applyDeviceSelection}
          >
            {applyingDevices
              ? "Collecting…"
              : draftDevices.length
                ? `Collect ${draftDevices.length} ${draftDevices.length === 1 ? "device" : "devices"}`
                : "Clear topology"}
          </Menu.Item>
        </Menu.Dropdown>
      </Menu>

      <TextInput
        className="toolbar-control toolbar-control--search"
        aria-label="Find infrastructure"
        value={search}
        onChange={(event) => onSearch(event.currentTarget.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter") onApplySearch(normalizedSearch);
        }}
        placeholder="Find infrastructure…"
        leftSectionPointerEvents="all"
        leftSection={
          <Tooltip label={searchIsApplied ? "Disable search highlight" : "Apply search highlight"}>
            <ActionIcon
              aria-label={searchIsApplied ? "Disable topology search" : "Apply topology search"}
              color={searchIsApplied ? "fabric" : "gray"}
              disabled={!searchIsApplied && !normalizedSearch}
              onClick={toggleSearch}
              size="sm"
              variant={searchIsApplied ? "light" : "subtle"}
            >
              <IconSearch size={14} />
            </ActionIcon>
          </Tooltip>
        }
        rightSection={
          search || activeSearch ? (
            <ActionIcon
              variant="subtle"
              color="gray"
              size="sm"
              aria-label="Clear search"
              onClick={() => {
                onSearch("");
                onApplySearch("");
              }}
            >
              <IconX size={13} />
            </ActionIcon>
          ) : undefined
        }
        size="xs"
      />

      <Group
        className="toolbar-control toolbar-layer-group"
        aria-label="Link selectors"
        gap={4}
        role="group"
        wrap="nowrap"
      >
        {availableLayers.length ? (
          LINK_SELECTOR_GROUPS.map((selector) => {
            const layers = selector.layers.filter((layer) =>
              availableLayers.includes(layer.value),
            );
            if (!layers.length) return null;
            const layerValues = layers.map((layer) => layer.value);
            const selectedValues = layerValues.filter((layer) =>
              visibleLayers.includes(layer),
            );
            return (
              <Menu
                closeOnItemClick={false}
                key={selector.label}
                position="bottom-start"
                shadow="md"
                width={176}
              >
                <Menu.Target>
                  <Button
                    className="toolbar-control toolbar-link-selector"
                    aria-label={`Select ${selector.label} links`}
                    data-active={selectedValues.length > 0 || undefined}
                    leftSection={
                      <span
                        aria-hidden="true"
                        className="layer-color-key"
                      >
                        {layers.map((layer) => (
                          <span
                            className="layer-color-key__segment"
                            data-layer={layer.value}
                            key={layer.value}
                            style={{ backgroundColor: LAYER_COLORS[layer.value] }}
                          />
                        ))}
                      </span>
                    }
                    rightSection={<IconChevronDown size={14} />}
                    size="xs"
                    variant="default"
                  >
                    {selector.label}
                  </Button>
                </Menu.Target>
                <Menu.Dropdown>
                  <Menu.Label>{selector.label} links</Menu.Label>
                  <Menu.CheckboxGroup
                    value={selectedValues}
                    onChange={(values) =>
                      changeVisibleLinkGroup(layerValues, values)
                    }
                  >
                    {layers.map((layer) => (
                      <Menu.CheckboxItem
                        aria-label={
                          layer.value === "bgp"
                            ? "BGP peerings"
                            : `${layer.label} links`
                        }
                        key={layer.value}
                        value={layer.value}
                      >
                        <span className="layer-menu-label">
                          <span
                            aria-hidden="true"
                            className="layer-menu-label__line"
                            data-layer={layer.value}
                            style={{ backgroundColor: LAYER_COLORS[layer.value] }}
                          />
                          {layer.label}
                        </span>
                      </Menu.CheckboxItem>
                    ))}
                  </Menu.CheckboxGroup>
                </Menu.Dropdown>
              </Menu>
            );
          })
        ) : (
          <Button disabled size="xs" variant="default">
            No links
          </Button>
        )}
      </Group>

      <Select
        className="toolbar-control toolbar-control--health"
        aria-label="Health filter"
        value={health}
        onChange={(value) => value && onHealth(value as Health | "all")}
        allowDeselect={false}
        data={[
          { value: "all", label: "All states" },
          { value: "healthy", label: "Healthy" },
          { value: "warning", label: "Warning" },
          { value: "critical", label: "Critical" },
          { value: "unknown", label: "Unknown" },
        ]}
        size="xs"
      />

      <Button.Group className="toolbar-control" aria-label="3D graph controls">
        <Tooltip label={visualizationPaused ? "Resume rendering" : "Pause rendering"}>
          <ActionIcon
            variant={visualizationPaused ? "default" : "light"}
            aria-label={visualizationPaused ? "Resume rendering" : "Pause rendering"}
            disabled={!hasGraph}
            onClick={onToggleVisualization}
            size="xs"
          >
            {visualizationPaused ? <IconPlayerPlay size={15} /> : <IconPlayerPause size={15} />}
          </ActionIcon>
        </Tooltip>
        <Tooltip label={layoutRunning ? "Freeze layout" : "Recalculate layout"}>
          <ActionIcon
            variant={layoutRunning ? "light" : "default"}
            aria-label={layoutRunning ? "Freeze layout" : "Recalculate layout"}
            disabled={!hasGraph}
            onClick={onToggleLayout}
            size="xs"
          >
            {layoutRunning ? (
              <IconSnowflake size={15} />
            ) : (
              <IconTopologyStar3 size={15} />
            )}
          </ActionIcon>
        </Tooltip>
        <Tooltip label={bloomEnabled ? "Disable bloom" : "Enable bloom"}>
          <ActionIcon
            variant={bloomEnabled ? "light" : "default"}
            aria-label={bloomEnabled ? "Disable bloom" : "Enable bloom"}
            disabled={!hasGraph}
            onClick={onToggleBloom}
            size="xs"
          >
            <IconSparkles size={15} />
          </ActionIcon>
        </Tooltip>
        <Tooltip label={rotationEnabled ? "Disable rotation" : "Enable rotation"}>
          <ActionIcon
            variant={rotationEnabled ? "light" : "default"}
            aria-label={rotationEnabled ? "Disable rotation" : "Enable rotation"}
            disabled={!hasGraph}
            onClick={onToggleRotation}
            size="xs"
          >
            <IconLoader2
              className={rotationEnabled ? "toolbar-spinner toolbar-spinner--active" : "toolbar-spinner"}
              size={15}
            />
          </ActionIcon>
        </Tooltip>
        <Menu position="bottom-start" shadow="md" width={128}>
          <Menu.Target>
            <ActionIcon
              aria-label={`Select rotation speed, current ${rotationSpeed}x`}
              className="rotation-speed-trigger"
              disabled={!hasGraph}
              size="xs"
              title={`Rotation speed: ${rotationSpeed}×`}
              variant="default"
            >
              <IconChevronDown size={12} />
            </ActionIcon>
          </Menu.Target>
          <Menu.Dropdown>
            <Menu.Label>Rotation speed</Menu.Label>
            <Menu.RadioGroup
              value={String(rotationSpeed)}
              onChange={(value) => onRotationSpeed(Number(value))}
            >
              {[0.5, 1, 2, 3].map((speed) => (
                <Menu.RadioItem key={speed} value={String(speed)}>
                  {speed}×
                </Menu.RadioItem>
              ))}
            </Menu.RadioGroup>
          </Menu.Dropdown>
        </Menu>
      </Button.Group>

      <Tooltip label={`Layout distance: ${nodeDistance}`}>
        <Group className="toolbar-control toolbar-distance" gap={6} wrap="nowrap">
          <Text c="dimmed" size="xs">
            {nodeDistance}
          </Text>
          <Slider
            className="toolbar-distance-slider"
            min={40}
            max={180}
            step={5}
            value={nodeDistance}
            onChange={onNodeDistance}
            size="xs"
            thumbLabel="Layout distance"
          />
        </Group>
      </Tooltip>

      <Tooltip label="Size topology nodes by fixed size, connection count, or traffic">
        <SegmentedControl
          className="toolbar-control toolbar-control--node-size"
          aria-label="Node size mode"
          size="xs"
          value={nodeSizeMode}
          onChange={(value) => onNodeSizeMode(value as NodeSizeMode)}
          data={[
            { value: "fixed", label: "Fixed" },
            { value: "connections", label: "Links" },
            { value: "traffic", label: "Traffic" },
          ]}
        />
      </Tooltip>

      <Tooltip label={`Topology stream: ${streamLabel}`}>
        <Badge
          className="toolbar-control"
          variant="light"
          color={streamColor}
          leftSection={<IconPointFilled size={10} />}
        >
          {streamLabel}
        </Badge>
      </Tooltip>

      <Timeline
        live={live}
        collectedAt={collectedAt}
        history={history}
        snapshotId={snapshotId}
        onSelect={onSelectHistory}
        onLive={onLive}
      />
    </Group>
  );
}
