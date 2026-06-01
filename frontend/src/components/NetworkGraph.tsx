import { useEffect, useMemo, useRef, useState } from "react";

import type { NetworkPayload } from "@/types";

interface LaidOutNode {
  id: string;
  label: string;
  is_ac_member: boolean;
  paper_count: number;
  ppr_score: number;
  c_norm: number;
  cross_sdl_diversity: number;
  bridge_score: number;
  x: number;
  y: number;
  vx: number;
  vy: number;
}

/**
 * Tiny force-directed layout. We don't pull in d3 just to render ~20 nodes —
 * a few iterations of repulsion + spring tension is plenty.
 */
function layout(payload: NetworkPayload, width: number, height: number, iters = 240) {
  const nodes: LaidOutNode[] = payload.nodes.map((n, i) => ({
    id: n.id,
    label: n.label,
    is_ac_member: n.is_ac_member,
    paper_count: n.paper_count,
    ppr_score: n.ppr_score ?? 0,
    c_norm: n.c_norm ?? 1,
    cross_sdl_diversity: n.cross_sdl_diversity ?? 0,
    bridge_score: n.bridge_score ?? 0,
    x: width / 2 + Math.cos((i / payload.nodes.length) * Math.PI * 2) * 180,
    y: height / 2 + Math.sin((i / payload.nodes.length) * Math.PI * 2) * 180,
    vx: 0,
    vy: 0,
  }));
  const nodeById = new Map(nodes.map((n) => [n.id, n]));
  const k = 0.04;
  const repulsion = 6000;
  const ideal = 100;

  for (let step = 0; step < iters; step++) {
    for (const a of nodes) {
      a.vx *= 0.85;
      a.vy *= 0.85;
    }
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i];
        const b = nodes[j];
        const dx = a.x - b.x;
        const dy = a.y - b.y;
        const dist2 = dx * dx + dy * dy + 0.01;
        const force = repulsion / dist2;
        const dist = Math.sqrt(dist2);
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        a.vx += fx;
        a.vy += fy;
        b.vx -= fx;
        b.vy -= fy;
      }
    }
    for (const e of payload.edges) {
      const a = nodeById.get(e.source);
      const b = nodeById.get(e.target);
      if (!a || !b) continue;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const dist = Math.sqrt(dx * dx + dy * dy + 0.01);
      const f = (dist - ideal) * k * Math.log2(1 + e.weight);
      const fx = (dx / dist) * f;
      const fy = (dy / dist) * f;
      a.vx += fx;
      a.vy += fy;
      b.vx -= fx;
      b.vy -= fy;
    }
    for (const n of nodes) {
      n.x += n.vx;
      n.y += n.vy;
      n.x = Math.max(40, Math.min(width - 40, n.x));
      n.y = Math.max(40, Math.min(height - 40, n.y));
    }
  }
  return { nodes, nodeById };
}

interface Props {
  payload: NetworkPayload;
  selectedId?: string | null;
  onSelect?: (id: string | null) => void;
}

export function NetworkGraph({ payload, selectedId, onSelect }: Props) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState({ w: 800, h: 520 });

  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(() => {
      const rect = ref.current!.getBoundingClientRect();
      setSize({ w: Math.max(500, rect.width), h: 520 });
    });
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);

  const placed = useMemo(
    () => layout(payload, size.w, size.h),
    [payload, size.w, size.h]
  );

  if (payload.nodes.length === 0) {
    return <div className="empty">No co-author edges yet. Run the pipeline first.</div>;
  }

  // Adjacency set for dimming: selected node + its direct neighbors
  const adjacentIds: Set<string> = new Set();
  if (selectedId) {
    adjacentIds.add(selectedId);
    for (const e of payload.edges) {
      if (e.source === selectedId) adjacentIds.add(e.target);
      else if (e.target === selectedId) adjacentIds.add(e.source);
    }
  }
  const hasSelection = selectedId != null;

  return (
    <div ref={ref}>
      <svg
        className="network-svg"
        width={size.w}
        height={size.h}
        onClick={() => onSelect?.(null)}
        style={{ cursor: "default" }}
      >
        {payload.edges.map((e, i) => {
          const a = placed.nodeById.get(e.source);
          const b = placed.nodeById.get(e.target);
          if (!a || !b) return null;
          const isAdjEdge = !hasSelection || (adjacentIds.has(e.source) && adjacentIds.has(e.target));
          const stroke = e.is_ac_ac
            ? "rgba(52, 211, 153, 0.75)"
            : e.involves_ac
            ? "rgba(251, 191, 36, 0.65)"
            : "rgba(154, 163, 178, 0.3)";
          const strokeWidth = 1 + (e.normalized_weight ?? 0) * 3;
          return (
            <line
              key={i}
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
              stroke={stroke}
              strokeWidth={Math.min(strokeWidth, 4)}
              opacity={isAdjEdge ? 1 : 0.06}
              style={{ transition: "opacity 0.2s" }}
            />
          );
        })}
        {placed.nodes.map((n) => {
          const r = n.is_ac_member ? 15 : 5 + Math.sqrt(n.ppr_score) * 10;
          const isBridge = !n.is_ac_member && n.bridge_score > 0.15;
          const isAdj = !hasSelection || adjacentIds.has(n.id);
          const isSelected = n.id === selectedId;
          const tooltip = [
            n.label,
            `PPR score: ${(n.ppr_score * 100).toFixed(1)}%`,
            `c_norm: ${n.c_norm.toFixed(2)}${isBridge ? " ★ bridge" : ""}`,
            `Bridge score: ${n.bridge_score.toFixed(2)}`,
            `Cross-SDL diversity: ${n.cross_sdl_diversity.toFixed(2)}`,
            `Papers: ${n.paper_count}`,
          ].join("\n");
          return (
            <g
              key={n.id}
              onClick={(ev) => { ev.stopPropagation(); onSelect?.(isSelected ? null : n.id); }}
              style={{ cursor: "pointer", transition: "opacity 0.2s" }}
              opacity={isAdj ? 1 : 0.12}
            >
              <title>{tooltip}</title>
              {isSelected && (
                <circle cx={n.x} cy={n.y} r={r + 6} fill="none" stroke="white" strokeWidth={2} opacity={0.6} />
              )}
              {isBridge && !isSelected && (
                <circle
                  cx={n.x} cy={n.y} r={r + 4}
                  fill="none" stroke="rgba(251, 191, 36, 0.55)"
                  strokeWidth={2} strokeDasharray="4 3"
                />
              )}
              <circle
                cx={n.x} cy={n.y} r={r}
                fill={n.is_ac_member ? "var(--accent)" : "var(--muted)"}
                stroke="#0f1115" strokeWidth={1.5}
              />
              <text x={n.x + r + 4} y={n.y + 4} fill="var(--text)" fontSize={11}>
                {n.label}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="network-legend">
        <span><span className="dot ac" /> AC member</span>
        <span><span className="dot other" /> Co-author</span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
          <svg width={24} height={4}><line x1={0} y1={2} x2={24} y2={2} stroke="rgba(52,211,153,0.75)" strokeWidth={2.5}/></svg>
          AC–AC
        </span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
          <svg width={24} height={4}><line x1={0} y1={2} x2={24} y2={2} stroke="rgba(251,191,36,0.65)" strokeWidth={2}/></svg>
          AC–External
        </span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
          <svg width={16} height={16}>
            <circle cx={8} cy={8} r={6} fill="none" stroke="rgba(251,191,36,0.55)" strokeWidth={2} strokeDasharray="4 3"/>
          </svg>
          Bridge score &gt; 0.15
        </span>
        <span title="Node size = AC-Personalized PageRank score (structural proximity to AC core)">
          Size = PPR score
        </span>
        <span style={{ marginLeft: "auto" }}>
          {payload.nodes.length} authors · {payload.edges.length} collaborations
        </span>
      </div>
    </div>
  );
}
