import { NavLink } from "react-router-dom";
import styles from "./Sidebar.module.css";

// ── Route groups ────────────────────────────────────────────────────────────

const RESEARCH_NAV = [
  { to: "/",           label: "Papers",       end: true },
  { to: "/queue",      label: "Review Queue"            },
  { to: "/discovery",  label: "Discovery"               },
  { to: "/retrieval",  label: "Graph RAG"               },
];

const ANALYTICS_NAV = [
  { to: "/insights",  label: "Insights"   },
  { to: "/growth",    label: "Net Growth" },
  { to: "/timeline",  label: "Timeline"   },
  { to: "/sankey",    label: "Sankey"     },
  { to: "/impact",    label: "Impact"     },
  { to: "/drift",     label: "Drift"      },
];

const NETWORK_NAV = [
  { to: "/multi-graph",  label: "Multi-Graph" },
  { to: "/network",      label: "Co-Author"   },
  { to: "/geographic",   label: "Geographic"  },
];

const TEAM_NAV = [
  { to: "/people", label: "People Grid" },
];

const OPS_NAV = [
  { to: "/lint",          label: "Lint Report"   },
  { to: "/duplicates",    label: "Duplicates"    },
  { to: "/evidence-gaps", label: "Evidence Gaps" },
  { to: "/pipeline",      label: "Pipeline"      },
  { to: "/report",        label: "Report"        },
  { to: "/eval",          label: "Eval"          },
];

// ── Icons ───────────────────────────────────────────────────────────────────

const ICONS: Record<string, JSX.Element> = {
  Papers: (
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
      <rect x="2" y="1" width="10" height="13" rx="1.5" />
      <line x1="5" y1="5" x2="9" y2="5" />
      <line x1="5" y1="8" x2="10" y2="8" />
      <line x1="5" y1="11" x2="8" y2="11" />
    </svg>
  ),
  "Review Queue": (
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
      <rect x="1.5" y="1.5" width="13" height="13" rx="2" />
      <polyline points="4,8 6.5,10.5 12,5" />
    </svg>
  ),
  Discovery: (
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
      <circle cx="6.5" cy="6.5" r="4" />
      <line x1="10" y1="10" x2="14" y2="14" />
    </svg>
  ),
  Insights: (
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
      <polyline points="1,12 5,7 8,9 11,4 15,8" />
    </svg>
  ),
  "Net Growth": (
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
      <polyline points="1,13 4,9 7,10 10,5 15,2" />
      <polyline points="11,2 15,2 15,6" />
    </svg>
  ),
  Timeline: (
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
      <line x1="1" y1="8" x2="15" y2="8" />
      <circle cx="4" cy="8" r="1.5" fill="currentColor" stroke="none" />
      <circle cx="8" cy="5" r="1.5" fill="currentColor" stroke="none" />
      <circle cx="12" cy="8" r="1.5" fill="currentColor" stroke="none" />
    </svg>
  ),
  Sankey: (
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
      <path d="M1 3 C6 3 6 7 11 7 C14 7 15 7 15 7" />
      <path d="M1 6 C5 6 5 11 10 11 C13 11 15 11 15 11" />
      <line x1="1" y1="3" x2="1" y2="6" />
      <line x1="15" y1="7" x2="15" y2="11" />
    </svg>
  ),
  Impact: (
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
      <polyline points="1,13 5,8 8,10 15,3" />
      <polyline points="11,3 15,3 15,7" />
    </svg>
  ),
  Drift: (
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
      <circle cx="8" cy="8" r="6" />
      <path d="M5 8 Q8 4 11 8 Q8 12 5 8" />
    </svg>
  ),
  "Multi-Graph": (
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
      <circle cx="4" cy="4" r="2" />
      <circle cx="12" cy="4" r="2" />
      <circle cx="4" cy="12" r="2" />
      <circle cx="12" cy="12" r="2" />
      <line x1="6" y1="4" x2="10" y2="4" />
      <line x1="4" y1="6" x2="4" y2="10" />
      <line x1="6" y1="12" x2="10" y2="12" />
      <line x1="12" y1="6" x2="12" y2="10" />
      <line x1="6" y1="6" x2="10" y2="10" />
    </svg>
  ),
  "Co-Author": (
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
      <circle cx="5" cy="5" r="2.5" />
      <circle cx="11" cy="5" r="2.5" />
      <circle cx="8" cy="12" r="2.5" />
      <line x1="7" y1="5" x2="7.5" y2="5" />
      <line x1="6.5" y1="7" x2="7" y2="10" />
      <line x1="9.5" y1="7" x2="9" y2="10" />
    </svg>
  ),
  Geographic: (
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
      <circle cx="8" cy="8" r="6" />
      <path d="M2 8 Q5 6 8 8 Q11 10 14 8" />
      <line x1="8" y1="2" x2="8" y2="14" />
    </svg>
  ),
  "People Grid": (
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
      <rect x="1" y="1" width="5" height="5" rx="1" />
      <rect x="10" y="1" width="5" height="5" rx="1" />
      <rect x="1" y="10" width="5" height="5" rx="1" />
      <rect x="10" y="10" width="5" height="5" rx="1" />
    </svg>
  ),
  "Evidence Gaps": (
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
      <circle cx="8" cy="8" r="6" />
      <line x1="8" y1="5" x2="8" y2="9" />
      <circle cx="8" cy="11" r="0.6" fill="currentColor" stroke="none" />
    </svg>
  ),
  "Lint Report": (
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
      <rect x="2" y="1.5" width="12" height="13" rx="1.5" />
      <polyline points="4.5,5 6,6.5 9,3.5" />
      <line x1="4.5" y1="10" x2="11.5" y2="10" />
      <line x1="4.5" y1="12.5" x2="9.5" y2="12.5" />
    </svg>
  ),
  Duplicates: (
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
      <rect x="2" y="2" width="8" height="8" rx="1.5" />
      <rect x="6" y="6" width="8" height="8" rx="1.5" />
      <line x1="4" y1="5" x2="8" y2="5" />
      <line x1="8" y1="10" x2="12" y2="10" />
    </svg>
  ),
  Pipeline: (
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
      <rect x="1" y="4" width="3.5" height="3" rx="1" />
      <rect x="6.25" y="4" width="3.5" height="3" rx="1" />
      <rect x="11.5" y="4" width="3.5" height="3" rx="1" />
      <line x1="4.5" y1="5.5" x2="6.25" y2="5.5" />
      <line x1="9.75" y1="5.5" x2="11.5" y2="5.5" />
    </svg>
  ),
  Report: (
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
      <rect x="2" y="1" width="12" height="14" rx="1.5" />
      <line x1="5" y1="5" x2="11" y2="5" />
      <line x1="5" y1="8" x2="11" y2="8" />
      <line x1="5" y1="11" x2="8" y2="11" />
    </svg>
  ),
  Eval: (
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
      <rect x="1" y="7" width="2.5" height="7" rx="0.5" />
      <rect x="6" y="4" width="2.5" height="10" rx="0.5" />
      <rect x="11" y="1" width="2.5" height="13" rx="0.5" />
    </svg>
  ),
};

function NavItemLink({ to, label, end }: { to: string; label: string; end?: boolean }) {
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

// ── Component ────────────────────────────────────────────────────────────────

export function Sidebar() {
  const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

  return (
    <aside className={styles.sidebar}>
      {/* Logo / brand */}
      <div className={styles.logo}>
        <span className={styles.logoIcon}>
          <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
            <rect x="2" y="6" width="12" height="7" rx="1.5" fill="white" opacity="0.9" />
            <rect x="5" y="3" width="6" height="4" rx="1" fill="white" opacity="0.55" />
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

        <div className={styles.sectionLabel}>Analytics</div>
        {ANALYTICS_NAV.map((item) => (
          <NavItemLink key={item.to} {...item} />
        ))}

        <div className={styles.sectionLabel}>Network</div>
        {NETWORK_NAV.map((item) => (
          <NavItemLink key={item.to} {...item} />
        ))}

        <div className={styles.sectionLabel}>Team</div>
        {TEAM_NAV.map((item) => (
          <NavItemLink key={item.to} {...item} />
        ))}

        <div className={styles.sectionLabel}>Operations</div>
        {OPS_NAV.map((item) => (
          <NavItemLink key={item.to} {...item} />
        ))}
      </nav>

      {/* Footer utilities */}
      <div className={styles.footer}>
        <a
          className={styles.footerLink}
          href={`${API_BASE}/papers/export.csv`}
          target="_blank"
          rel="noreferrer"
        >
          <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
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
          <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
            <rect x="2" y="2" width="12" height="12" rx="2" />
            <line x1="5" y1="6" x2="11" y2="6" /><line x1="5" y1="9" x2="9" y2="9" />
          </svg>
          API Docs
        </a>
      </div>
    </aside>
  );
}
