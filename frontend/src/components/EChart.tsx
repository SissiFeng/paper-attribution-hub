import ReactECharts from "echarts-for-react";
import type { CSSProperties } from "react";

interface Props {
  option: object;
  style?: CSSProperties;
  onEvents?: Record<string, (params: unknown) => void>;
}

const DARK_BG_THEME = {
  backgroundColor: "transparent",
  textStyle: { color: "#e7eaf0" },
  legend: {
    textStyle: { color: "#9aa3b2" },
  },
  tooltip: { backgroundColor: "#181b22", borderColor: "#2a2f3a", textStyle: { color: "#e7eaf0" } },
};

export function EChart({ option, style, onEvents }: Props) {
  const merged = { ...DARK_BG_THEME, ...option };
  return (
    <ReactECharts
      option={merged}
      notMerge
      lazyUpdate
      style={{ height: 520, width: "100%", ...style }}
      onEvents={onEvents}
      opts={{ renderer: "canvas" }}
    />
  );
}
