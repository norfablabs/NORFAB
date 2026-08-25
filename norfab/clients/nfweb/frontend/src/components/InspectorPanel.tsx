import type {
  SelectedItem,
  TopologyLink,
  TopologyLogEntry,
} from "../types";
import {
  LAYER_LABELS,
  endpointId,
  numericMetric,
} from "../graphModel";

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

export function DetailRows({ value }: { value: Record<string, unknown> }) {
  const rows = Object.entries(value).filter(
    ([, item]) => item !== null && item !== "",
  );
  if (!rows.length)
    return <p className="detail-empty">No additional properties</p>;
  return (
    <dl className="detail-grid">
      {rows.map(([key, item]) => (
        <div key={key}>
          <dt>{key.replaceAll("_", " ")}</dt>
          <dd>
            {Array.isArray(item)
              ? item.join(", ")
              : typeof item === "object"
                ? JSON.stringify(item)
                : String(item)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

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
  return (
    <aside className={`detail-panel ${selected ? "open" : ""}`}>
      <div className="detail-header">
        <div>
          <span className="eyebrow">{selected?.kind ?? "Inspector"}</span>
          <strong>
            {selected?.kind === "node"
              ? selected.value.label
              : selected?.kind === "link"
                ? `${endpointId(selected.value.source)} ↔ ${endpointId(selected.value.target)}`
                : "Select an object"}
          </strong>
        </div>
        {selected && (
          <button onClick={onClose} aria-label="Close details">
            ×
          </button>
        )}
      </div>
      {selected && (
        <div className="inspector-tabs" role="tablist">
          {(
            [
              ["status", "Status & utilisation"],
              ["connections", `Connections (${relatedConnections.length})`],
              ["properties", "Properties"],
            ] as const
          ).map(([item, label]) => (
            <button
              type="button"
              role="tab"
              aria-selected={tab === item}
              className={tab === item ? "active" : ""}
              onClick={() => onTab(item)}
              key={item}
            >
              {label}
            </button>
          ))}
        </div>
      )}
      <div className="inspector-body">
        {!selected && (
          <div className="inspector-empty">
            <span className="radar-glyph">◎</span>
            <p>Choose a node or link to inspect its live state and provenance.</p>
          </div>
        )}
        {selected && tab === "status" && (
          <div className="detail-content">
            <div className={`health-badge ${selected.value.health}`}>
              {selected.value.health}
            </div>
            <h3>Sources</h3>
            <div className="source-tags">
              {(selected.kind === "node"
                ? selected.value.layers
                : [selected.value.layer]
              ).map((layer) => (
                <span key={layer}>{LAYER_LABELS[layer] ?? layer}</span>
              ))}
            </div>
            <h3>Status</h3>
            <DetailRows
              value={{
                connections: relatedConnections.length,
                ...statusProperties(selected.value.attributes),
              }}
            />
            {selected.kind === "link" && (
              <>
                <h3>Utilisation and counters</h3>
                <DetailRows value={selected.value.metrics} />
              </>
            )}
          </div>
        )}
        {selected && tab === "connections" && (
          <div className="connection-list">
            {relatedConnections.length === 0 ? (
              <p className="detail-empty">No related connections</p>
            ) : (
              relatedConnections.map((link) => (
                <article className="connection-card" key={link.id}>
                  <header>
                    <strong>{LAYER_LABELS[link.layer] ?? link.layer}</strong>
                    <span className={`health-badge ${link.health}`}>
                      {link.health}
                    </span>
                  </header>
                  <p>
                    {endpointId(link.source)} ↔ {endpointId(link.target)}
                  </p>
                  <DetailRows
                    value={{
                      source_interface: link.attributes.source_interface,
                      target_interface: link.attributes.target_interface,
                      utilization: numericMetric(link),
                    }}
                  />
                </article>
              ))
            )}
          </div>
        )}
        {selected && tab === "properties" && (
          <div className="detail-content">
            <h3>Properties</h3>
            <DetailRows
              value={{
                id: selected.value.id,
                ...(selected.kind === "node"
                  ? { kind: selected.value.kind, layers: selected.value.layers }
                  : { layer: selected.value.layer }),
                ...selected.value.attributes,
              }}
            />
          </div>
        )}
      </div>

      <section className="collection-log event-log" aria-live="polite">
        <div className="section-heading">
          <span className="eyebrow">Collection events</span>
          <span className="section-count">{collectionLog.length}/300</span>
        </div>
        {collectionLog.length === 0 ? (
          <p className="log-empty">No NORFAB collection events yet.</p>
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
