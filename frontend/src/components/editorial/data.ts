import type { TimelinePayload } from "@/types";

export interface ChartPoint { label: string; value: number }

// Labels are exclusive, including UNCLASSIFIED. Topics are not exclusive.
export function annualPapers(payload: TimelinePayload): ChartPoint[] {
  if (payload.by !== "label") throw new Error("Annual totals require exclusive classification labels.");
  return [...payload.years].sort((a, b) => a - b).map((year) => ({
    label: String(year),
    value: payload.series.reduce((total, series) => total +
      series.data.reduce((sum, [y, count]) => sum + (y === year ? count : 0), 0), 0),
  }));
}

export function rankedTopics(payload: TimelinePayload): ChartPoint[] {
  return payload.series.map((series) => ({
    label: series.name,
    value: series.data.reduce((sum, [, count]) => sum + count, 0),
  })).sort((a, b) => b.value - a.value || a.label.localeCompare(b.label)).slice(0, 8);
}

export function tickUnit(points: ChartPoint[]): number {
  return Math.max(1, Math.ceil(Math.max(0, ...points.map((p) => p.value)) / 45));
}
