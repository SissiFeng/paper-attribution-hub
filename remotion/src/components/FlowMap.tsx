import type {FlowNode, VisualStory} from "../types";
import {monoFont, palette, reveal} from "./SceneFrame";

interface NodePosition {
  x: number;
  y: number;
  node: FlowNode;
}

const layerX: Record<FlowNode["layer"], number> = {
  institution: 40,
  topic: 600,
  label: 1160,
};

export function FlowMap({story, frame}: {story: VisualStory; frame: number}) {
  const width = 1580;
  const height = 590;
  const positions = new Map<string, NodePosition>();
  const layers: FlowNode["layer"][] = ["institution", "topic", "label"];

  for (const layer of layers) {
    const nodes = story.flow.nodes.filter((node) => node.layer === layer);
    nodes.forEach((node, index) => {
      positions.set(node.id, {
        x: layerX[layer],
        y: 80 + (index * 410) / Math.max(1, nodes.length - 1),
        node,
      });
    });
  }

  const progress = reveal(frame, 38, 130);
  return (
    <div
      style={{
        marginTop: 34,
        border: `1px solid ${palette.line}`,
        borderRadius: 30,
        background: "rgba(13,26,32,.72)",
        padding: "22px 24px 16px",
      }}
    >
      <svg width="100%" viewBox={`0 0 ${width} ${height}`}>
        {layers.map((layer) => (
          <text
            key={layer}
            x={layerX[layer]}
            y={28}
            fill={palette.muted}
            fontFamily={monoFont}
            fontSize="14"
            letterSpacing="2.2"
          >
            {layer.toUpperCase()}
          </text>
        ))}
        {story.flow.links.map((link, index) => {
          const source = positions.get(link.source);
          const target = positions.get(link.target);
          if (!source || !target) return null;
          const sx = source.x + 310;
          const sy = source.y + 31;
          const tx = target.x;
          const ty = target.y + 31;
          const mid = (sx + tx) / 2;
          const linkProgress = Math.max(0, Math.min(1, progress * 1.35 - index * 0.025));
          return (
            <path
              key={`${link.source}-${link.target}`}
              d={`M ${sx} ${sy} C ${mid} ${sy}, ${mid} ${ty}, ${tx} ${ty}`}
              fill="none"
              stroke={source.node.color}
              strokeOpacity={0.14 + Math.min(0.42, link.value / 50)}
              strokeWidth={Math.max(3, Math.sqrt(link.value) * 3.2)}
              pathLength={1}
              strokeDasharray={1}
              strokeDashoffset={1 - linkProgress}
            />
          );
        })}
        {[...positions.values()].map(({x, y, node}, index) => {
          const nodeReveal = reveal(frame, 20 + index * 7, 22);
          return (
            <g key={node.id} opacity={nodeReveal} transform={`translate(${(1 - nodeReveal) * -12} 0)`}>
              <rect x={x} y={y} width="310" height="62" rx="12" fill="rgba(7,16,21,.94)" stroke={node.color} strokeOpacity=".68" />
              <rect x={x} y={y} width="7" height="62" rx="3.5" fill={node.color} />
              <text x={x + 24} y={y + 38} fill={palette.paper} fontFamily={monoFont} fontSize="16">
                {node.name.length > 29 ? `${node.name.slice(0, 27)}…` : node.name}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

