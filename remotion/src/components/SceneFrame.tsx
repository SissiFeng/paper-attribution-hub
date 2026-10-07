import type {CSSProperties, ReactNode} from "react";
import {AbsoluteFill, interpolate, useCurrentFrame} from "remotion";

import type {VisualStory} from "../types";

export const palette = {
  ink: "#071015",
  panel: "#0d1a20",
  paper: "#eee9df",
  muted: "#9aabae",
  line: "rgba(214, 229, 226, 0.16)",
  gold: "#f0c76a",
  teal: "#65c8bf",
  rose: "#d99aad",
  blue: "#6594b1",
};

export const displayFont = '"Newsreader Variable", Georgia, serif';
export const monoFont = '"IBM Plex Mono", ui-monospace, monospace';

export function reveal(frame: number, start: number, duration = 24): number {
  return interpolate(frame, [start, start + duration], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
}

interface SceneProps {
  start: number;
  duration: number;
  children: ReactNode;
  style?: CSSProperties;
}

export function Scene({start, duration, children, style}: SceneProps) {
  const frame = useCurrentFrame();
  const opacity = interpolate(
    frame,
    [start, start + 18, start + duration - 20, start + duration],
    [0, 1, 1, 0],
    {extrapolateLeft: "clamp", extrapolateRight: "clamp"},
  );

  return (
    <AbsoluteFill
      style={{
        opacity,
        padding: "112px 116px 104px",
        ...style,
      }}
    >
      {children}
    </AbsoluteFill>
  );
}

export function Background() {
  const frame = useCurrentFrame();
  const drift = interpolate(frame, [0, 1350], [-20, 40]);
  return (
    <AbsoluteFill style={{backgroundColor: palette.ink, overflow: "hidden"}}>
      <div
        style={{
          position: "absolute",
          width: 920,
          height: 920,
          left: -260 + drift,
          top: -420,
          borderRadius: "50%",
          background: "radial-gradient(circle, rgba(101,200,191,0.13), rgba(7,16,21,0) 68%)",
        }}
      />
      <div
        style={{
          position: "absolute",
          width: 780,
          height: 780,
          right: -270 - drift * 0.5,
          bottom: -390,
          borderRadius: "50%",
          background: "radial-gradient(circle, rgba(240,199,106,0.11), rgba(7,16,21,0) 70%)",
        }}
      />
      <svg width="100%" height="100%" style={{opacity: 0.24}}>
        <defs>
          <pattern id="pas-grid" width="64" height="64" patternUnits="userSpaceOnUse">
            <path d="M 64 0 L 0 0 0 64" fill="none" stroke="rgba(214,229,226,.12)" strokeWidth="1" />
            <circle cx="0" cy="0" r="1.4" fill="rgba(240,199,106,.45)" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#pas-grid)" />
      </svg>
      <AbsoluteFill
        style={{
          opacity: 0.18,
          backgroundImage:
            "repeating-linear-gradient(115deg, transparent 0, transparent 5px, rgba(255,255,255,.02) 6px)",
        }}
      />
    </AbsoluteFill>
  );
}

export function Kicker({children, color = palette.gold}: {children: ReactNode; color?: string}) {
  return (
    <div
      style={{
        color,
        fontFamily: monoFont,
        fontSize: 18,
        fontWeight: 500,
        letterSpacing: "0.16em",
        textTransform: "uppercase",
      }}
    >
      {children}
    </div>
  );
}

export function StoryFooter({story}: {story: VisualStory}) {
  const frame = useCurrentFrame();
  return (
    <div
      style={{
        position: "absolute",
        left: 116,
        right: 116,
        bottom: 38,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        borderTop: `1px solid ${palette.line}`,
        paddingTop: 18,
        color: palette.muted,
        fontFamily: monoFont,
        fontSize: 14,
        letterSpacing: "0.06em",
      }}
    >
      <div style={{display: "flex", alignItems: "center", gap: 14}}>
        <span
          style={{
            display: "inline-block",
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: story.data_status === "verified_snapshot" ? palette.teal : palette.rose,
          }}
        />
        {story.data_status.replaceAll("_", " ").toUpperCase()}
        <span style={{color: "rgba(238,233,223,.35)"}}>·</span>
        SCOPE {story.audit.filter_fingerprint.slice(0, 12)}
      </div>
      <div>VISUAL_STORY.V1 · FRAME {String(frame).padStart(4, "0")}</div>
    </div>
  );
}

