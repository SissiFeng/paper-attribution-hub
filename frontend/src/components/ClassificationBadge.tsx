import type { RelevanceLabel } from "@/types";

export function ClassificationBadge({ label }: { label: RelevanceLabel | string }) {
  return <span className={`badge ${label}`}>{label.replace("_", " ")}</span>;
}

export function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  return (
    <span>
      <span className="confidence-bar">
        <span style={{ width: `${pct}%` }} />
      </span>
      {pct}%
    </span>
  );
}
