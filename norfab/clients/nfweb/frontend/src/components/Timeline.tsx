interface TimelineProps {
  live: boolean;
  collectedAt?: string;
  historyLength: number;
  index: number;
  onSelect: (index: number) => void;
  onLive: () => void;
}

export default function Timeline({
  live,
  collectedAt,
  historyLength,
  index,
  onSelect,
  onLive,
}: TimelineProps) {
  return (
    <footer className="timeline-panel">
      <div className="timeline-label">
        <span className="eyebrow">Three-hour history</span>
        <strong>
          {live ? "NOW" : new Date(collectedAt ?? 0).toLocaleTimeString()}
        </strong>
      </div>
      <div className="timeline-track">
        <div className="timeline-times">
          <span>-3h</span>
          <span>-2h</span>
          <span>-1h</span>
          <span>Now</span>
        </div>
        <input
          aria-label="Topology history"
          type="range"
          min={0}
          max={Math.max(0, historyLength - 1)}
          value={index}
          disabled={!historyLength}
          onChange={(event) => onSelect(Number(event.target.value))}
        />
      </div>
      <button className={`live-button ${live ? "active" : ""}`} onClick={onLive}>
        <span /> Return to live
      </button>
    </footer>
  );
}
