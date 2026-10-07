// Adapted from Lieflat Charts basics-gallery.html: F2, F3 and F5.
// PolyForm Noncommercial 1.0.0; see public/licenses/lieflat-charts.txt.
import { useEffect, useRef, useState, type ReactNode } from "react";
import { tickUnit, type ChartPoint } from "./data";
import "./editorial.css";

function ChartCard({ title, subtitle, source, points, children, valueLabel = "Papers" }: {
  title: string; subtitle: string; source: string; points: ChartPoint[]; children: ReactNode; valueLabel?: string;
}) {
  const ref = useRef<HTMLElement>(null);
  const [visible, setVisible] = useState(false);
  const [replay, setReplay] = useState(0);
  useEffect(() => {
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        setVisible(true);
        observer.disconnect();
      }
    }, { threshold: 0.15 });
    if (ref.current) observer.observe(ref.current);
    return () => observer.disconnect();
  }, []);
  return <article ref={ref} className="lf-card">
    <div className="lf-heading"><h2>{title}</h2>
      <button type="button" onClick={() => setReplay((n) => n + 1)} aria-label={`Replay ${title}`}>Replay</button>
    </div>
    <p className="lf-sub">{subtitle}</p>
    <div key={replay} className={visible ? "lf-revealed" : "lf-waiting"}>{children}</div>
    <p className="lf-source">{source}</p>
    <details><summary>View exact values</summary>
      <table><caption>{title}</caption><thead><tr><th scope="col">Year / topic</th><th scope="col">{valueLabel}</th></tr></thead>
        <tbody>{points.map((p) => <tr key={p.label}><th scope="row">{p.label}</th><td>{p.value.toLocaleString()}</td></tr>)}</tbody>
      </table>
    </details>
  </article>;
}

export function AnnualChart({ points }: { points: ChartPoint[] }) {
  const peak = points.reduce<ChartPoint | null>((best, p) => !best || p.value > best.value ? p : best, null);
  return <TimeSeriesChart points={points}
    title={peak ? `${peak.label} has the most papers in this selection` : "Publication years"}
    source="filtered analytics / timeline · labels" />;
}

export function TimeSeriesChart({ points: input, title, source, valueLabel = "Papers", variant = "line", flaggedYear }: {
  points: ChartPoint[]; title: string; source: string; valueLabel?: string;
  variant?: "line" | "hairline-area"; flaggedYear?: string;
}) {
  const points = [...input].sort((a, b) => Number(a.label) - Number(b.label));
  const max = Math.max(1, ...points.map((p) => p.value));
  const first = Number(points[0]?.label ?? 0);
  const last = Number(points.at(-1)?.label ?? first);
  const x = (p: ChartPoint) => first === last ? 260 : 48 + (Number(p.label) - first) / (last - first) * 424;
  const y = (p: ChartPoint) => 238 - p.value / max * 178;
  const peak = points.reduce<ChartPoint | null>((best, p) => !best || p.value > best.value ? p : best, null);
  const path = points.map((p, i) => `${i && p.label !== flaggedYear && Number(p.label) === Number(points[i - 1].label) + 1 ? "L" : "M"}${x(p)},${y(p)}`).join(" ");
  const labels = new Set([0, Math.floor((points.length - 1) / 2), points.length - 1]);
  const flagged = points.find((p) => p.label === flaggedYear);
  const prior = flagged ? points[points.indexOf(flagged) - 1] : undefined;
  return <ChartCard title={title} valueLabel={valueLabel}
    subtitle={`${variant === "line" ? "One dot" : "One vertical hairline"} = one publication year · height = ${valueLabel.toLowerCase()} · pink = peak${peak === flagged ? " (hollow when flagged)" : ""} · gaps remain disconnected`}
    source={`${variant === "line" ? "F2 · Hairline Line" : "F3 · Hairline Area"} · ${source}`} points={points}>
    {flagged && <p className="lf-sub">{flagged.label} is below 60% of the previous year's count. Dashed / hollow marks a coverage check, not confirmed missing data. All values remain included.</p>}
    {points.length ? <svg viewBox="0 0 520 290" role="img" aria-label={`${title}; ${valueLabel.toLowerCase()} by publication year; exact values below`}>
      {[0, 0.5, 1].map((fraction) => <g key={fraction}>
        <line x1="48" x2="472" y1={238 - fraction * 178} y2={238 - fraction * 178} className="lf-grid" />
        <text x="38" y={242 - fraction * 178} textAnchor="end">{Number((fraction * max).toFixed(1))}</text>
      </g>)}
      {variant === "hairline-area" && points.map((p, i) => <line key={`stem-${p.label}`}
        x1={x(p)} x2={x(p)} y1="238" y2={y(p)} stroke={p === peak ? "var(--lf-ink)" : "var(--lf-data)"}
        strokeWidth={p === peak ? 1.1 : .55} className="lf-row" style={{ animationDelay: `${Math.min(i, 40) * .014}s` }} />)}
      {flagged && prior && Number(flagged.label) === Number(prior.label) + 1 && <path
        d={`M${x(prior)},${y(prior)} L${x(flagged)},${y(flagged)}`} fill="none" stroke="currentColor" strokeWidth="1" strokeDasharray="4 4" />}
      <path d={path} className="lf-draw" pathLength="1" fill="none" stroke="currentColor" strokeWidth="1" />
      {points.map((p, i) => <g key={p.label}>
        <line x1={x(p)} x2={x(p)} y1="238" y2="231" className="lf-grid" />
        <circle cx={x(p)} cy={y(p)} r={p === peak ? 4.2 : 2.1} fill={p === flagged ? "var(--lf-bg)" : p === peak ? "var(--lf-hero)" : "var(--lf-data)"} stroke="var(--lf-ink)" strokeWidth={p === flagged || p === peak ? 1.2 : 0} className="lf-dot" style={{ animationDelay: `${0.2 + Math.min(i, 30) * 0.03}s` }}><title>{`${p.label}: ${p.value} ${valueLabel.toLowerCase()}`}</title></circle>
        {p === peak && <text x={x(p)} y={y(p) - 13} textAnchor="middle" className="lf-value">{p.value.toLocaleString()}</text>}
        {labels.has(i) && <text x={x(p)} y="260" textAnchor="middle">{p.label}</text>}
      </g>)}
    </svg> : <p className="lf-empty">No dated values match this selection.</p>}
  </ChartCard>;
}

export function TopicsChart({ points }: { points: ChartPoint[] }) {
  const unit = tickUnit(points);
  const max = Math.max(1, ...points.map((p) => p.value));
  const step = 380 / Math.max(1, max / unit);
  return <ChartCard title="The most represented research themes"
    subtitle={`Up to 8 topics · one full tick = ${unit} paper${unit === 1 ? "" : "s"} · shorter final tick = remainder`}
    source="F5 · Tick Rows · filtered analytics / timeline · topics" points={points}>
    {points.length ? <svg viewBox={`0 0 520 ${points.length * 58 + 20}`} role="img" aria-label="Top topics by paper count; topics overlap; exact values below">
      {points.map((p, i) => {
        const baseline = 39 + i * 58;
        const count = Math.ceil(p.value / unit);
        return <g key={p.label} className="lf-row" style={{ animationDelay: `${i * 0.08}s` }}>
          <text x="24" y={baseline - 21}><title>{p.label}</title>{p.label.length > 56 ? `${p.label.slice(0, 53)}…` : p.label}</text>
          <line x1="24" x2="404" y1={baseline} y2={baseline} className="lf-grid" />
          {Array.from({ length: count }, (_, k) => {
            const fraction = Math.min(1, (p.value - k * unit) / unit);
            const position = 24 + k * step + step / 2;
            return <g key={k}>
              <line x1={position} x2={position} y1={baseline} y2={baseline - 13 * fraction} stroke="currentColor" strokeWidth="1" />
              {k % 5 === 4 && <circle cx={position} cy={baseline + 4} r="0.8" className="lf-guide-dot" />}
            </g>;
          })}
          <text x="490" y={baseline - 1} textAnchor="end" className="lf-value">{p.value.toLocaleString()}</text>
        </g>;
      })}
    </svg> : <p className="lf-empty">No topic assignments match this selection.</p>}
  </ChartCard>;
}
