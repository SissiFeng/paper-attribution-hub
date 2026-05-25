import { useRef, type ReactNode, type CSSProperties } from "react";

interface Props {
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
  maxTilt?: number;   // degrees, default 10
  scale?: number;     // hover scale, default 1.03
  glare?: boolean;    // glossy sheen, default true
}

export function TiltCard({
  children,
  className,
  style,
  maxTilt = 10,
  scale = 1.03,
  glare = true,
}: Props) {
  const cardRef = useRef<HTMLDivElement>(null);
  const glareRef = useRef<HTMLDivElement>(null);

  function onMove(e: React.MouseEvent<HTMLDivElement>) {
    const el = cardRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    const dx = (e.clientX - cx) / (rect.width / 2);
    const dy = (e.clientY - cy) / (rect.height / 2);
    const rotX = -dy * maxTilt;
    const rotY = dx * maxTilt;

    el.style.transform = `perspective(600px) rotateX(${rotX}deg) rotateY(${rotY}deg) scale(${scale})`;
    el.style.transition = "transform 0.08s ease-out";

    if (glare && glareRef.current) {
      // Glare angle: 0deg = top-left, 180deg = bottom-right
      const angle = Math.atan2(dy, dx) * (180 / Math.PI) + 90;
      const dist = Math.sqrt(dx * dx + dy * dy);
      glareRef.current.style.opacity = String(dist * 0.25);
      glareRef.current.style.transform = `rotate(${angle}deg)`;
    }
  }

  function onLeave() {
    const el = cardRef.current;
    if (!el) return;
    el.style.transform = `perspective(600px) rotateX(0deg) rotateY(0deg) scale(1)`;
    el.style.transition = "transform 0.35s ease-out";
    if (glare && glareRef.current) {
      glareRef.current.style.opacity = "0";
    }
  }

  return (
    <div
      ref={cardRef}
      className={className}
      style={{ ...style, transformStyle: "preserve-3d", willChange: "transform" }}
      onMouseMove={onMove}
      onMouseLeave={onLeave}
    >
      {children}
      {glare && (
        <div
          ref={glareRef}
          style={{
            position: "absolute",
            inset: 0,
            borderRadius: "inherit",
            background:
              "linear-gradient(135deg, rgba(255,255,255,0.30) 0%, transparent 60%)",
            opacity: 0,
            pointerEvents: "none",
            transition: "opacity 0.08s",
          }}
        />
      )}
    </div>
  );
}
