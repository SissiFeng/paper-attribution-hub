import { useEffect, useRef, useState } from "react";

interface Props {
  value: number;
  duration?: number;       // ms, default 1400
  decimals?: number;       // decimal places, default 0
  prefix?: string;
  suffix?: string;
  delay?: number;          // ms before animation starts, default 0
}

function easeOutExpo(t: number): number {
  return t === 1 ? 1 : 1 - Math.pow(2, -10 * t);
}

export function AnimatedNumber({
  value,
  duration = 1400,
  decimals = 0,
  prefix = "",
  suffix = "",
  delay = 0,
}: Props) {
  const [display, setDisplay] = useState(0);
  const rafRef = useRef<number | null>(null);
  const startRef = useRef<number | null>(null);
  const startedRef = useRef(false);

  useEffect(() => {
    const run = () => {
      const timeout = setTimeout(() => {
        const animate = (ts: number) => {
          if (startRef.current === null) startRef.current = ts;
          const elapsed = ts - startRef.current;
          const progress = Math.min(elapsed / duration, 1);
          setDisplay(easeOutExpo(progress) * value);
          if (progress < 1) {
            rafRef.current = requestAnimationFrame(animate);
          } else {
            setDisplay(value);
          }
        };
        rafRef.current = requestAnimationFrame(animate);
        startedRef.current = true;
      }, delay);
      return timeout;
    };

    const t = run();
    return () => {
      clearTimeout(t);
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      startRef.current = null;
    };
  }, [value, duration, delay]);

  const formatted = display.toFixed(decimals);
  return (
    <span>
      {prefix}{formatted}{suffix}
    </span>
  );
}
