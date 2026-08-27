import { ActionIcon, Group, Select, Tooltip } from "@mantine/core";
import { IconBroadcast } from "@tabler/icons-react";
import type { TopologyHistoryItem } from "../types";

interface TimelineProps {
  live: boolean;
  history: TopologyHistoryItem[];
  snapshotId?: string;
  onSelect: (snapshotId: string) => void;
  onLive: () => void;
}

function formatSnapshotTimestamp(value: string): string {
  return new Date(value).toLocaleString(undefined, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export default function Timeline({
  live,
  history,
  snapshotId,
  onSelect,
  onLive,
}: TimelineProps) {
  return (
    <Group
      className="timeline-control toolbar-control"
      aria-label="Topology history controls"
      gap={6}
      role="region"
      wrap="nowrap"
    >
      <Select
        aria-label="Topology snapshot"
        className="timeline-select"
        data={history.map((item) => ({
          value: item.snapshot_id,
          label: formatSnapshotTimestamp(item.collected_at),
        }))}
        disabled={!history.length}
        placeholder="No snapshots"
        value={snapshotId ?? null}
        onChange={(value) => value && onSelect(value)}
        allowDeselect={false}
        size="xs"
      />
      <Tooltip label="Return to live topology">
        <ActionIcon
          size="sm"
          variant={live ? "filled" : "light"}
          color="fabric"
          onClick={onLive}
          aria-label="Return to live topology"
        >
          <IconBroadcast size={14} />
        </ActionIcon>
      </Tooltip>
    </Group>
  );
}
