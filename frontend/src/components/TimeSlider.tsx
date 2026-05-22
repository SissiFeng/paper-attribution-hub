import { useEffect, useRef, useState } from "react";

interface Props {
  minYear: number;
  maxYear: number;
  yearFrom: number;
  yearTo: number;
  onChange: (yearFrom: number, yearTo: number) => void;
  playStepMs?: number;
}

/** Dual-handle year slider with optional play button that cycles
 *  yearTo through [yearFrom..maxYear] on a timer. */
export function TimeSlider({
  minYear,
  maxYear,
  yearFrom,
  yearTo,
  onChange,
  playStepMs = 900,
}: Props) {
  const [playing, setPlaying] = useState(false);
  const trackRef = useRef<HTMLDivElement | null>(null);
  const dragRef = useRef<"from" | "to" | null>(null);

  // Play loop: increment yearTo each tick until it hits maxYear, then loop back to yearFrom.
  useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => {
      const next = yearTo >= maxYear ? yearFrom : yearTo + 1;
      onChange(yearFrom, next);
    }, playStepMs);
    return () => clearInterval(id);
  }, [playing, yearTo, yearFrom, maxYear, onChange, playStepMs]);

  const total = Math.max(1, maxYear - minYear);
  const pctFrom = ((yearFrom - minYear) / total) * 100;
  const pctTo = ((yearTo - minYear) / total) * 100;

  const yearFromX = (clientX: number): number => {
    const el = trackRef.current;
    if (!el) return yearFrom;
    const r = el.getBoundingClientRect();
    const pct = Math.max(0, Math.min(1, (clientX - r.left) / r.width));
    return Math.round(minYear + pct * total);
  };

  const handlePointerDown = (handle: "from" | "to") => (
    e: React.PointerEvent
  ) => {
    e.preventDefault();
    dragRef.current = handle;
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    if (!dragRef.current) return;
    const y = yearFromX(e.clientX);
    if (dragRef.current === "from") {
      onChange(Math.min(y, yearTo), yearTo);
    } else {
      onChange(yearFrom, Math.max(y, yearFrom));
    }
  };

  const handlePointerUp = (e: React.PointerEvent) => {
    dragRef.current = null;
    try {
      (e.target as HTMLElement).releasePointerCapture(e.pointerId);
    } catch {
      /* ignore */
    }
  };

  const years: number[] = [];
  for (let y = minYear; y <= maxYear; y++) years.push(y);

  return (
    <div className="v7-timeslider">
      <button
        className={`play-btn ${playing ? "playing" : ""}`}
        onClick={() => setPlaying((p) => !p)}
        aria-label={playing ? "Pause" : "Play"}
      >
        {playing ? "⏸" : "▶"}
      </button>
      <div className="year-label">
        {yearFrom} – {yearTo}
      </div>
      <div
        className="track-wrap"
        ref={trackRef}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
      >
        <div className="track" />
        <div
          className="track-fill"
          style={{ left: `${pctFrom}%`, width: `${pctTo - pctFrom}%` }}
        />
        {years.map((y) => {
          const left = ((y - minYear) / total) * 100;
          return (
            <div
              key={y}
              className="year-tick"
              style={{ left: `${left}%`, top: "50%" }}
            >
              {y}
            </div>
          );
        })}
        <div
          className="handle"
          style={{ left: `${pctFrom}%`, top: "50%", marginTop: -9 }}
          onPointerDown={handlePointerDown("from")}
        />
        <div
          className="handle"
          style={{
            left: `${pctTo}%`,
            top: "50%",
            marginTop: -9,
            borderColor: "var(--art-hot-pink)",
          }}
          onPointerDown={handlePointerDown("to")}
        />
      </div>
    </div>
  );
}
