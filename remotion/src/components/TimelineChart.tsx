import {interpolate} from "remotion";

import type {VisualStory} from "../types";
import {monoFont, palette, reveal} from "./SceneFrame";

interface Props {
  story: VisualStory;
  frame: number;
}

export function TimelineChart({story, frame}: Props) {
  const {years, series} = story.timeline;
  const width = 1190;
  const height = 520;
  const left = 76;
  const right = 34;
  const top = 40;
  const bottom = 66;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const maxValue = Math.max(1, ...series.flatMap((item) => item.values));
  const progress = reveal(frame, 34, 150);

  const x = (index: number) => left + (plotWidth * index) / Math.max(1, years.length - 1);
  const y = (value: number) => top + plotHeight - (plotHeight * value) / maxValue;

  return (
    <div style={{display: "grid", gridTemplateColumns: "1fr 300px", gap: 50, marginTop: 36}}>
      <div
        style={{
          border: `1px solid ${palette.line}`,
          borderRadius: 28,
          padding: "22px 20px 8px",
          background: "rgba(13,26,32,.72)",
          boxShadow: "0 30px 80px rgba(0,0,0,.28)",
        }}
      >
        <svg width="100%" viewBox={`0 0 ${width} ${height}`}>
          {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
            const value = Math.round(maxValue * ratio);
            const gridY = y(value);
            return (
              <g key={ratio}>
                <line x1={left} x2={width - right} y1={gridY} y2={gridY} stroke={palette.line} />
                <text x={left - 18} y={gridY + 5} textAnchor="end" fill={palette.muted} fontFamily={monoFont} fontSize="13">
                  {value}
                </text>
              </g>
            );
          })}
          {years.map((year, index) => (
            <text
              key={year}
              x={x(index)}
              y={height - 25}
              textAnchor="middle"
              fill={palette.muted}
              fontFamily={monoFont}
              fontSize="14"
            >
              {year}
            </text>
          ))}
          {series.map((item, seriesIndex) => {
            const path = item.values
              .map((value, index) => `${index === 0 ? "M" : "L"} ${x(index)} ${y(value)}`)
              .join(" ");
            const seriesProgress = interpolate(progress, [seriesIndex * 0.12, 0.72 + seriesIndex * 0.12], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            });
            return (
              <g key={item.name}>
                <path
                  d={path}
                  fill="none"
                  stroke={item.color}
                  strokeWidth="5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  pathLength={1}
                  strokeDasharray={1}
                  strokeDashoffset={1 - seriesProgress}
                />
                {item.values.map((value, index) => {
                  const pointProgress = interpolate(
                    seriesProgress,
                    [index / years.length, Math.min(1, index / years.length + 0.12)],
                    [0, 1],
                    {extrapolateLeft: "clamp", extrapolateRight: "clamp"},
                  );
                  return (
                    <circle
                      key={`${item.name}-${years[index]}`}
                      cx={x(index)}
                      cy={y(value)}
                      r={7 * pointProgress}
                      fill={palette.ink}
                      stroke={item.color}
                      strokeWidth="4"
                    />
                  );
                })}
              </g>
            );
          })}
        </svg>
      </div>
      <div style={{display: "flex", flexDirection: "column", justifyContent: "center", gap: 22}}>
        {series.map((item, index) => {
          const opacity = reveal(frame, 80 + index * 18, 22);
          const lastValue = item.values[item.values.length - 1] ?? 0;
          return (
            <div
              key={item.name}
              style={{
                opacity,
                transform: `translateY(${(1 - opacity) * 18}px)`,
                borderLeft: `3px solid ${item.color}`,
                padding: "4px 0 4px 20px",
              }}
            >
              <div style={{fontFamily: monoFont, color: item.color, fontSize: 14, letterSpacing: ".08em", textTransform: "uppercase"}}>
                {item.name}
              </div>
              <div style={{fontFamily: monoFont, color: palette.paper, fontSize: 42, fontWeight: 500, marginTop: 6}}>
                {lastValue}
              </div>
              <div style={{fontFamily: monoFont, color: palette.muted, fontSize: 14}}>illustrative papers in {years.at(-1)}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

