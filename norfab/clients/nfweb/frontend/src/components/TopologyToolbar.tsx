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
import { HEALTH_COLORS } from "../graphModel";
import type {
  DeviceOption,
  Health,
  StatsMode,
  TopologyHistoryItem,
} from "../types";
import Timeline from "./Timeline";

export type NodeSizeMode = "fixed" | "connections" | "traffic";

const TOPOLOGY_OPTIONS = [
  { value: "netbox", label: "NetBox" },
  { value: "nornir", label: "Nornir connections" },
  { value: "live-lldp", label: "LLDP" },
  { value: "circuits", label: "Circuits" },
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
  topologySources: string[];
  onTopologySources: (sources: string[]) => void;
  protocols: string[];
  onProtocols: (protocols: string[]) => void;
  statsMode: StatsMode;
  onStatsMode: (mode: StatsMode) => void;
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
  topologySources,
  onTopologySources,
  protocols,
  onProtocols,
  statsMode,
  onStatsMode,
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
                          {device.sources.join(" + ") || "nornir"}
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
                No devices reported by Nornir.
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
        <Menu closeOnItemClick={false} position="bottom-start" shadow="md">
          <Menu.Target>
            <Button
              aria-label="Select topology links"
              data-active={topologySources.length > 0 || undefined}
              rightSection={<IconChevronDown size={14} />}
              size="xs"
              variant="default"
            >
              Topology
            </Button>
          </Menu.Target>
          <Menu.Dropdown>
            <Menu.Label>Topology links</Menu.Label>
            <Menu.CheckboxGroup value={topologySources} onChange={onTopologySources}>
              {TOPOLOGY_OPTIONS.map((option) => (
                <Menu.CheckboxItem
                  aria-label={`${option.label} links`}
                  key={option.value}
                  value={option.value}
                >
                  {option.label}
                </Menu.CheckboxItem>
              ))}
            </Menu.CheckboxGroup>
          </Menu.Dropdown>
        </Menu>

        <Menu closeOnItemClick={false} position="bottom-start" shadow="md">
          <Menu.Target>
            <Button
              aria-label="Select protocols"
              data-active={protocols.length > 0 || undefined}
              rightSection={<IconChevronDown size={14} />}
              size="xs"
              variant="default"
            >
              Protocols
            </Button>
          </Menu.Target>
          <Menu.Dropdown>
            <Menu.Label>Protocols</Menu.Label>
            <Menu.CheckboxGroup value={protocols} onChange={onProtocols}>
              <Menu.CheckboxItem aria-label="BGP peerings" value="bgp">
                BGP
              </Menu.CheckboxItem>
            </Menu.CheckboxGroup>
          </Menu.Dropdown>
        </Menu>

        <Menu position="bottom-start" shadow="md">
          <Menu.Target>
            <Button
              aria-label="Select topology statistics"
              data-active={statsMode !== "off" || undefined}
              rightSection={<IconChevronDown size={14} />}
              size="xs"
              variant="default"
            >
              Stats
            </Button>
          </Menu.Target>
          <Menu.Dropdown>
            <Menu.Label>Statistics</Menu.Label>
            <Menu.RadioGroup
              value={statsMode}
              onChange={(value) => onStatsMode(value as StatsMode)}
            >
              {(["off", "traffic", "errors", "flaps"] as StatsMode[]).map(
                (mode) => (
                  <Menu.RadioItem key={mode} value={mode}>
                    {mode[0].toUpperCase() + mode.slice(1)}
                  </Menu.RadioItem>
                ),
              )}
            </Menu.RadioGroup>
          </Menu.Dropdown>
        </Menu>
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
        leftSection={
          <span
            aria-hidden="true"
            className="health-color-key"
            style={{
              backgroundColor:
                health === "all" ? HEALTH_COLORS.unknown : HEALTH_COLORS[health],
            }}
          />
        }
        renderOption={({ option }) => {
          const state = option.value as Health | "all";
          return (
            <span className="health-option">
              <span
                aria-hidden="true"
                className="health-color-key"
                style={{
                  backgroundColor:
                    state === "all"
                      ? HEALTH_COLORS.unknown
                      : HEALTH_COLORS[state],
                }}
              />
              {option.label}
            </span>
          );
        }}
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

      <Timeline
        live={live}
        history={history}
        snapshotId={snapshotId}
        onSelect={onSelectHistory}
        onLive={onLive}
      />

      <Tooltip label={`Topology stream: ${streamLabel}`}>
        <Badge
          aria-label={`Topology stream: ${streamLabel}`}
          className="toolbar-control"
          variant="light"
          color={streamColor}
          leftSection={<IconPointFilled size={10} />}
        >
          {streamLabel}
        </Badge>
      </Tooltip>
    </Group>
  );
}
