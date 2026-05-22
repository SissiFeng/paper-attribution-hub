import { useEffect, useMemo, useRef, useState } from "react";

import type { NetworkPayload } from "@/types";

interface LaidOutNode {
  id: string;
  label: string;
  is_ac_member: boolean;
  paper_count: number;
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
}

export function NetworkGraph({ payload }: Props) {
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

  return (
    <div ref={ref}>
      <svg className="network-svg" width={size.w} height={size.h}>
        {payload.edges.map((e, i) => {
          const a = placed.nodeById.get(e.source);
          const b = placed.nodeById.get(e.target);
          if (!a || !b) return null;
          return (
            <line
              key={i}
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
              stroke="rgba(154, 163, 178, 0.5)"
              strokeWidth={Math.min(1 + e.weight * 0.8, 4)}
            />
          );
        })}
        {placed.nodes.map((n) => {
          const r = 6 + Math.min(n.paper_count, 6) * 1.5;
          return (
            <g key={n.id}>
              <circle
                cx={n.x}
                cy={n.y}
                r={r}
                fill={n.is_ac_member ? "var(--accent)" : "var(--muted)"}
                stroke="#0f1115"
                strokeWidth={1.5}
              />
              <text
                x={n.x + r + 4}
                y={n.y + 4}
                fill="var(--text)"
                fontSize={11}
              >
                {n.label}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="network-legend">
        <span><span className="dot ac" /> AC member</span>
        <span><span className="dot other" /> Co-author</span>
        <span style={{ marginLeft: "auto" }}>
          {payload.nodes.length} authors · {payload.edges.length} collaborations
        </span>
      </div>
    </div>
  );
}
