import { NavLink } from "react-router-dom";
import styles from "./Sidebar.module.css";

const RESEARCH_NAV = [
  { to: "/",          label: "Papers",         end: true  },
  { to: "/queue",     label: "Review Queue"              },
  { to: "/insights",  label: "Insights"                  },
  { to: "/discovery", label: "Discovery"                  },
];

const OPS_NAV = [
  { to: "/evidence-gaps", label: "Evidence Gaps" },
  { to: "/pipeline",      label: "Pipeline"      },
  { to: "/report",        label: "Report"        },
  { to: "/eval",          label: "Eval"          },
];

// Minimal SVG icons (no emoji)
const ICONS: Record<string, JSX.Element> = {
  Papers: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="2" y="1" width="10" height="13" rx="1.5" />
      <line x1="5" y1="5" x2="9" y2="5" /><line x1="5" y1="8" x2="10" y2="8" /><line x1="5" y1="11" x2="8" y2="11" />
    </svg>
  ),
  "Review Queue": (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="1.5" y="1.5" width="13" height="13" rx="2" />
      <polyline points="4,8 6.5,10.5 12,5" />
    </svg>
  ),
  Insights: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <polyline points="1,12 5,7 8,9 11,4 15,8" />
    </svg>
  ),
  Discovery: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <circle cx="6.5" cy="6.5" r="4" />
      <line x1="10" y1="10" x2="14" y2="14" />
    </svg>
  ),
  "Evidence Gaps": (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <circle cx="8" cy="8" r="6" />
      <line x1="8" y1="5" x2="8" y2="8.5" /><circle cx="8" cy="11" r="0.5" fill="currentColor" />
    </svg>
  ),
  Pipeline: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="1" y="4" width="4" height="3" rx="1" />
      <rect x="6" y="4" width="4" height="3" rx="1" />
      <rect x="11" y="4" width="4" height="3" rx="1" />
      <line x1="5" y1="5.5" x2="6" y2="5.5" /><line x1="10" y1="5.5" x2="11" y2="5.5" />
      <line x1="8" y1="7" x2="8" y2="10" /><line x1="5" y1="10" x2="11" y2="10" />
    </svg>
  ),
  Report: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="2" y="1" width="12" height="14" rx="1.5" />
      <line x1="5" y1="5" x2="11" y2="5" /><line x1="5" y1="8" x2="11" y2="8" /><line x1="5" y1="11" x2="8" y2="11" />
    </svg>
  ),
  Eval: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <line x1="2" y1="13" x2="2" y2="6" /><rect x="1" y="6" width="2" height="7" />
      <line x1="7" y1="13" x2="7" y2="4" /><rect x="6" y="4" width="2" height="9" />
      <line x1="12" y1="13" x2="12" y2="8" /><rect x="11" y="8" width="2" height="5" />
    </svg>
  ),
};

function NavItemLink({
  to,
  label,
  end,
}: {
  to: string;
  label: string;
  end?: boolean;
}) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        `${styles.navItem}${isActive ? ` ${styles.active}` : ""}`
      }
    >
      <span className={styles.navIcon}>{ICONS[label]}</span>
      {label}
    </NavLink>
  );
}

export function Sidebar() {
  const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

  return (
    <aside className={styles.sidebar}>
      {/* Logo */}
      <div className={styles.logo}>
        <span className={styles.logoIcon}>
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
            <rect x="2" y="6" width="12" height="7" rx="1.5" fill="white" opacity="0.9" />
            <rect x="5" y="3" width="6" height="4" rx="1" fill="white" opacity="0.6" />
            <rect x="6.5" y="9" width="3" height="2" rx="0.5" fill="#213C51" />
          </svg>
        </span>
        <div>
          <div className={styles.logoText}>Paper Attribution</div>
          <div className={styles.logoSub}>AC Research</div>
        </div>
      </div>

      {/* Navigation */}
      <nav className={styles.nav}>
        <div className={styles.sectionLabel}>Research</div>
        {RESEARCH_NAV.map((item) => (
          <NavItemLink key={item.to} {...item} />
        ))}

        <div className={styles.sectionLabel}>Operations</div>
        {OPS_NAV.map((item) => (
          <NavItemLink key={item.to} {...item} />
        ))}
      </nav>

      {/* Footer */}
      <div className={styles.footer}>
        <a
          className={styles.footerLink}
          href={`${API_BASE}/papers/export.csv`}
          target="_blank"
          rel="noreferrer"
        >
          <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M8 3v8M5 8l3 3 3-3" /><rect x="2" y="11" width="12" height="2" rx="1" />
          </svg>
          Export CSV
        </a>
        <a
          className={styles.footerLink}
          href={`${API_BASE}/docs`}
          target="_blank"
          rel="noreferrer"
        >
          <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
            <rect x="2" y="2" width="12" height="12" rx="2" />
            <line x1="5" y1="6" x2="11" y2="6" /><line x1="5" y1="9" x2="9" y2="9" />
          </svg>
          API Docs
        </a>
      </div>
    </aside>
  );
}
