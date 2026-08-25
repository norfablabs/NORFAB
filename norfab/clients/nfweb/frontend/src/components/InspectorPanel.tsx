import {
  ActionIcon,
  Badge,
  Group,
  ScrollArea,
  Stack,
  Tabs,
  Text,
  ThemeIcon,
} from "@mantine/core";
import {
  IconActivityHeartbeat,
  IconListDetails,
  IconPlugConnected,
  IconRadar,
  IconX,
} from "@tabler/icons-react";
import { LAYER_LABELS, endpointId, numericMetric } from "../graphModel";
import SearchableSortableTable from "./SearchableSortableTable";
import type { InspectorTableRow } from "./SearchableSortableTable";
import type {
  Health,
  SelectedItem,
  TopologyLink,
  TopologyLogEntry,
} from "../types";

export type InspectorTab = "status" | "connections" | "properties";

function eventTime(value?: string | null): string {
  if (!value) return "--:--:--.---";
  const match = value.match(/\d{2}:\d{2}:\d{2}(?:\.\d{3})?/);
  if (match) return match[0];
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleTimeString([], {
        hour12: false,
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        fractionalSecondDigits: 3,
      });
}

function eventResource(resource: TopologyLogEntry["resource"]): string {
  if (!resource) return "";
  return Array.isArray(resource) ? resource.join(",") : resource;
}

function healthColor(health: Health): string {
  if (health === "healthy") return "teal";
  if (health === "warning") return "yellow";
  if (health === "critical") return "red";
  return "gray";
}

function statusProperties(value: Record<string, unknown>) {
  const terms = [
    "status",
    "state",
    "health",
    "speed",
    "rate",
    "utilization",
    "error",
    "packet",
    "transition",
  ];
  return Object.fromEntries(
    Object.entries(value).filter(([key]) =>
      terms.some((term) => key.toLowerCase().includes(term)),
    ),
  );
}

export function formatDetailValue(value: unknown): string {
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "object" && value !== null) return JSON.stringify(value);
  return String(value);
}

export function detailTableRows(
  value: Record<string, unknown>,
  prefix: string,
): InspectorTableRow[] {
  return Object.entries(value)
    .filter(([, item]) => item !== null && item !== "")
    .map(([key, item]) => {
      const label = key.replaceAll("_", " ");
      return {
        id: `${prefix}-${key}`,
        values: { field: label, value: formatDetailValue(item) },
      };
    });
}

const DETAIL_COLUMNS = [
  { key: "field", label: "Field" },
  { key: "value", label: "Value" },
];

const CONNECTION_COLUMNS = [
  { key: "connection", label: "Connection" },
  { key: "layer", label: "Layer" },
  { key: "state", label: "State / metric" },
];

interface InspectorPanelProps {
  selected: SelectedItem;
  tab: InspectorTab;
  relatedConnections: TopologyLink[];
  collectionLog: TopologyLogEntry[];
  onTab: (tab: InspectorTab) => void;
  onClose: () => void;
}

export default function InspectorPanel({
  selected,
  tab,
  relatedConnections,
  collectionLog,
  onTab,
  onClose,
}: InspectorPanelProps) {
  const title =
    selected?.kind === "node"
      ? selected.value.label
      : selected?.kind === "link"
        ? `${endpointId(selected.value.source)} ↔ ${endpointId(selected.value.target)}`
        : "Select an object";
  const sources = selected
    ? selected.kind === "node"
      ? selected.value.layers
      : [selected.value.layer]
    : [];
  const statusRows = selected
    ? detailTableRows(
        {
          health: selected.value.health,
          sources,
          connections: relatedConnections.length,
          ...statusProperties(selected.value.attributes),
          ...(selected.kind === "link"
            ? Object.fromEntries(
                Object.entries(selected.value.metrics).map(([key, value]) => [
                  `metric_${key}`,
                  value,
                ]),
              )
            : {}),
        },
        "status",
      ).map((row) =>
        row.id === "status-health"
          ? {
              ...row,
              cells: {
                value: (
                  <Badge
                    color={healthColor(selected.value.health)}
                    variant="light"
                    size="sm"
                  >
                    {selected.value.health}
                  </Badge>
                ),
              },
            }
          : row,
      )
    : [];
  const connectionRows: InspectorTableRow[] = relatedConnections.map((link) => {
    const source = endpointId(link.source);
    const target = endpointId(link.target);
    const sourceInterface = formatDetailValue(
      link.attributes.source_interface ?? "-",
    );
    const targetInterface = formatDetailValue(
      link.attributes.target_interface ?? "-",
    );
    const metric = numericMetric(link);
    return {
      id: link.id,
      values: {
        connection: `${source} ${sourceInterface} ${target} ${targetInterface}`,
        layer: LAYER_LABELS[link.layer] ?? link.layer,
        state: `${link.health} ${metric}`,
      },
      cells: {
        connection: (
          <Stack gap={1}>
            <Text fw={600} size="xs">
              {source} ↔ {target}
            </Text>
            <Text c="dimmed" size="xs">
              {sourceInterface} ↔ {targetInterface}
            </Text>
          </Stack>
        ),
        layer: (
          <Badge variant="default" size="sm">
            {LAYER_LABELS[link.layer] ?? link.layer}
          </Badge>
        ),
        state: (
          <Stack gap={1}>
            <Badge
              color={healthColor(link.health)}
              variant="light"
              size="sm"
            >
              {link.health}
            </Badge>
            <Text c="dimmed" size="xs">
              metric {metric.toLocaleString()}
            </Text>
          </Stack>
        ),
      },
    };
  });
  const propertyRows = selected
    ? detailTableRows(
        {
          id: selected.value.id,
          ...(selected.kind === "node"
            ? { kind: selected.value.kind, layers: selected.value.layers }
            : { layer: selected.value.layer }),
          ...selected.value.attributes,
        },
        "property",
      )
    : [];

  return (
    <aside className={`detail-panel ${selected ? "open" : ""}`}>
      <Group className="detail-header" justify="space-between" wrap="nowrap">
        <Stack gap={1} className="detail-title">
          <Text c="dimmed" size="xs">
            {selected ? `${selected.kind} details` : "Inspector"}
          </Text>
          <Text fw={600} size="sm" truncate>
            {title}
          </Text>
        </Stack>
        {selected && (
          <ActionIcon
            variant="subtle"
            color="gray"
            onClick={onClose}
            aria-label="Close details"
          >
            <IconX size={17} />
          </ActionIcon>
        )}
      </Group>

      {!selected ? (
        <Stack className="inspector-empty" align="center" gap="sm">
          <ThemeIcon variant="light" color="gray" size="xl" radius="sm">
            <IconRadar size={25} />
          </ThemeIcon>
          <Text c="dimmed" size="sm" ta="center">
            Choose a node or link to inspect its live state and provenance.
          </Text>
        </Stack>
      ) : (
        <Tabs
          className="inspector-content"
          value={tab}
          onChange={(value) => value && onTab(value as InspectorTab)}
        >
          <Tabs.List grow>
            <Tabs.Tab value="status" leftSection={<IconActivityHeartbeat size={14} />}>
              Status
            </Tabs.Tab>
            <Tabs.Tab value="connections" leftSection={<IconPlugConnected size={14} />}>
              Links ({relatedConnections.length})
            </Tabs.Tab>
            <Tabs.Tab value="properties" leftSection={<IconListDetails size={14} />}>
              Properties
            </Tabs.Tab>
          </Tabs.List>

          <ScrollArea className="inspector-body" type="auto">
            <Tabs.Panel value="status" p="sm">
              <SearchableSortableTable
                label="Status details"
                columns={DETAIL_COLUMNS}
                rows={statusRows}
              />
            </Tabs.Panel>

            <Tabs.Panel value="connections" p="sm">
              <SearchableSortableTable
                label="Related connections"
                columns={CONNECTION_COLUMNS}
                rows={connectionRows}
                minWidth={520}
              />
            </Tabs.Panel>

            <Tabs.Panel value="properties" p="sm">
              <SearchableSortableTable
                label="Source properties"
                columns={DETAIL_COLUMNS}
                rows={propertyRows}
              />
            </Tabs.Panel>
          </ScrollArea>
        </Tabs>
      )}

      <section className="collection-log event-log" aria-live="polite">
        <Group justify="space-between" mb="xs">
          <Text c="dimmed" fw={600} size="xs">
            Collection events
          </Text>
          <Badge variant="default" size="xs">
            {collectionLog.length}/300
          </Badge>
        </Group>
        {collectionLog.length === 0 ? (
          <Text c="dimmed" size="xs">
            No NORFAB collection events yet.
          </Text>
        ) : (
          <ol className="terminal-log">
            {collectionLog.map((entry) => (
              <li
                className={`terminal-line ${entry.severity.toLowerCase()}`}
                key={entry.id}
              >
                <time>{eventTime(entry.timestamp)}</time>
                <b>{entry.severity.toUpperCase()}</b>
                <span className="terminal-worker">{entry.worker ?? "-"}</span>
                <span className={`terminal-status ${entry.status ?? ""}`}>
                  {entry.status ?? "-"}
                </span>
                <span className="terminal-message">
                  {entry.service}.{entry.task ?? "job"}
                  {eventResource(entry.resource)
                    ? ` [${eventResource(entry.resource)}]`
                    : ""}{" "}
                  {entry.message.replaceAll(/\s+/g, " ").trim()}
                </span>
              </li>
            ))}
          </ol>
        )}
      </section>
    </aside>
  );
}
