import { escapeHtml } from "@/lib/html";

export function coauthorHeatmapTooltip(
  rowLabel: unknown,
  columnLabel: unknown,
  value: unknown,
  sameInstitution: boolean,
): string {
  const row = escapeHtml(rowLabel);
  const count = escapeHtml(value);
  if (sameInstitution) return `<b>${row}</b><br/>${count} papers`;
  return `<b>${row}</b><br/>↔ ${escapeHtml(columnLabel)}<br/><b>${count}</b> joint papers`;
}

export function transferFlowTooltip(
  citingLab: unknown,
  citedLab: unknown,
  value: unknown,
): string {
  return `${escapeHtml(citingLab)} cites ${escapeHtml(citedLab)}: <b>${escapeHtml(value)}</b>`;
}

export function institutionTopicHeatmapTooltip(
  institution: unknown,
  topic: unknown,
  value: unknown,
): string {
  return `<div style="font-family:'JetBrains Mono',monospace;font-size:12px;padding:2px">
          <b>${escapeHtml(institution)}</b><br/>
          ${escapeHtml(topic)}: <b>${escapeHtml(value)}</b> papers
        </div>`;
}
