import { useState } from "react";
import {
  ActionIcon,
  Badge,
  Button,
  Chip,
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
  IconPlayerPause,
  IconPlayerPlay,
  IconPointFilled,
  IconRefresh,
  IconRotate,
  IconSearch,
  IconSnowflake,
  IconX,
} from "@tabler/icons-react";
import { LAYER_LABELS } from "../graphModel";
import type { DeviceOption, Health, TopologyHistoryItem } from "../types";
import Timeline from "./Timeline";

export type NodeSizeMode = "fixed" | "connections" | "traffic";

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
  availableLayers: string[];
  visibleLayers: string[];
  onVisibleLayers: (layers: string[]) => void;
  health: Health | "all";
  onHealth: (health: Health | "all") => void;
  hasGraph: boolean;
  visualizationPaused: boolean;
  layoutRunning: boolean;
  rotationEnabled: boolean;
  rotationSpeed: number;
  nodeDistance: number;
  nodeSizeMode: NodeSizeMode;
  onToggleVisualization: () => void;
  onToggleLayout: () => void;
  onToggleRotation: () => void;
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
  availableLayers,
  visibleLayers,
  onVisibleLayers,
  health,
  onHealth,
  hasGraph,
  visualizationPaused,
  layoutRunning,
  rotationEnabled,
  rotationSpeed,
  nodeDistance,
  nodeSizeMode,
  onToggleVisualization,
  onToggleLayout,
  onToggleRotation,
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

  return (
    <Group className="topology-controls" gap={8} wrap="nowrap">
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
        placeholder="Find infrastructure…"
        leftSection={<IconSearch size={14} />}
        rightSection={
          search ? (
            <ActionIcon
              variant="subtle"
              color="gray"
              size="sm"
              aria-label="Clear search"
              onClick={() => onSearch("")}
            >
              <IconX size={13} />
            </ActionIcon>
          ) : undefined
        }
        size="xs"
      />

      <Group
        className="toolbar-control toolbar-layer-group"
        aria-label="Network layers"
        gap={4}
        role="group"
        wrap="nowrap"
      >
        <Chip.Group multiple value={visibleLayers} onChange={onVisibleLayers}>
          {availableLayers.length ? (
            availableLayers.map((layer) => {
              const label = LAYER_LABELS[layer] ?? layer;
              return (
                <Tooltip key={layer} label={`Toggle ${label} layer`}>
                  <Chip
                    aria-label={`${label} layer`}
                    color="fabric"
                    radius="sm"
                    size="xs"
                    value={layer}
                    variant="light"
                  >
                    {label}
                  </Chip>
                </Tooltip>
              );
            })
          ) : (
            <Button disabled size="xs" variant="default">
              No layers
            </Button>
          )}
        </Chip.Group>
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
            {layoutRunning ? <IconSnowflake size={15} /> : <IconRefresh size={15} />}
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
            <IconRotate size={15} />
          </ActionIcon>
        </Tooltip>
      </Button.Group>

      <Tooltip label="Rotation speed">
        <Select
          className="toolbar-control toolbar-control--rotation-speed"
          aria-label="Rotation speed"
          size="xs"
          allowDeselect={false}
          value={String(rotationSpeed)}
          onChange={(value) => onRotationSpeed(Number(value))}
          data={[
            { value: "0.25", label: "Slow" },
            { value: "0.7", label: "Normal" },
            { value: "1.5", label: "Fast" },
          ]}
        />
      </Tooltip>

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
