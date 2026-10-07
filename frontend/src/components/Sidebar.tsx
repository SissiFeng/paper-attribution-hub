import { Link, useLocation } from "react-router-dom";
import { useEffect, useMemo, useRef, useState } from "react";
import { API_BASE } from "@/lib/runtime";
import styles from "./Sidebar.module.css";
import { usePasAccount } from './PasAccount';
import { CommandPalette } from './CommandPalette';
import { navigationItems, navigationActive, navigationShortcut } from './navigation';

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
  "Graph RAG": (
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
      <circle cx="8" cy="4" r="2" />
      <circle cx="3" cy="12" r="2" />
      <circle cx="13" cy="12" r="2" />
      <line x1="8" y1="6" x2="5" y2="10" />
      <line x1="8" y1="6" x2="11" y2="10" />
      <line x1="5" y1="12" x2="11" y2="12" />
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
  "Institution Compare": (
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
      <rect x="1.5" y="3" width="5" height="10" rx="1" />
      <rect x="9.5" y="6" width="5" height="7" rx="1" />
      <line x1="4" y1="1" x2="4" y2="3" />
      <line x1="12" y1="4" x2="12" y2="6" />
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
  "Knowledge Transfer": (
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
      <circle cx="3.5" cy="8" r="2.5" />
      <circle cx="12.5" cy="8" r="2.5" />
      <path d="M6 6.5 Q8 5 10 6.5" />
      <path d="M10 9.5 Q8 11 6 9.5" />
    </svg>
  ),
  "Transfer Studio": (
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
      <rect x="1.5" y="2" width="6" height="6" rx="1" />
      <rect x="8.5" y="8" width="6" height="6" rx="1" />
      <path d="M7.5 5 H11 V8" />
      <polyline points="9.5,6.5 11,8 12.5,6.5" />
    </svg>
  ),
  "Knowledge Base": (
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
      <path d="M8 3 C6.5 1.8 4 1.8 2 2.5 V12.5 C4 11.8 6.5 11.8 8 13" />
      <path d="M8 3 C9.5 1.8 12 1.8 14 2.5 V12.5 C12 11.8 9.5 11.8 8 13" />
      <line x1="8" y1="3" x2="8" y2="13" />
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

function NavItemLink({ to, label, active, restricted=false, onClick }: { to: string; label: string; active: boolean; restricted?: boolean; onClick?: () => void }) {
  const researchIcons: Record<string, JSX.Element> = {'Paper attribution':ICONS.Papers, 'My research':ICONS['Knowledge Base'], 'Manage access':ICONS['People Grid']};
  return (
    <Link
      to={to}
      aria-current={active ? "page" : undefined}
      data-nav-current={active || undefined}
      title={label + (restricted ? ' — Administrator access' : '')}
      aria-label={label + (restricted ? ' — Administrator access' : '')}
      onClick={onClick}
      className={`${styles.navItem}${active ? ` ${styles.active}` : ""}`}
    >
      <span className={styles.navIcon}>{ICONS[label] || researchIcons[label]}</span>
      <span data-nav-label>{label}</span>
      {restricted && <span className={styles.accessLock} aria-hidden="true"><svg width="10" height="12" viewBox="0 0 12 14" fill="none" stroke="currentColor"><rect x="1.5" y="6" width="9" height="6.5" rx="1"/><path d="M3.5 6V4a2.5 2.5 0 0 1 5 0v2"/></svg></span>}
    </Link>
  );
}

// ── Component ────────────────────────────────────────────────────────────────

export function Sidebar() {
  const {user}=usePasAccount();
  const admin=user?.role==='admin';
  const [expanded,setExpanded]=useState(false);
  const close=()=>setExpanded(false);
  const [commandOpen,setCommandOpen]=useState(false),[shortcut,setShortcut]=useState('Ctrl K');
  const location=useLocation(),items=useMemo(()=>navigationItems(admin),[admin]);
  const nav=useRef<HTMLElement>(null),highlight=useRef<HTMLSpanElement>(null),positioned=useRef(false);
  useEffect(()=>{
    setShortcut(/Mac|iPhone|iPad/.test(navigator.platform)?'⌘ K':'Ctrl K');
    const key=(event:KeyboardEvent)=>{
      if(!navigationShortcut(event))return;
      if(!commandOpen&&document.querySelector('dialog[open], [aria-modal="true"]'))return;
      event.preventDefault();setCommandOpen(open=>!open);setExpanded(false);
    };
    const message=(event:MessageEvent)=>{
      const frame=document.querySelector<HTMLIFrameElement>('iframe[title="PAS private research workspace"]');
      if(event.origin===window.location.origin&&frame&&event.source===frame.contentWindow&&event.data?.type==='pas:navigation:open'&&!document.querySelector('dialog[open], [aria-modal="true"]')){
        setCommandOpen(true);setExpanded(false);
      }
    };
    window.addEventListener('keydown',key);window.addEventListener('message',message);
    return()=>{window.removeEventListener('keydown',key);window.removeEventListener('message',message);};
  },[commandOpen]);
  useEffect(()=>{
    const container=nav.current!,block=highlight.current!;
    const active=container.querySelector<HTMLElement>('[data-nav-current="true"]');
    if(!active){block.style.opacity='0';container.removeAttribute('data-highlight-ready');positioned.current=false;return;}
    let alive=true,lastTarget='';
    const place=(animate=false)=>{
      if(!alive)return;
      const root=container.getBoundingClientRect(),target=active.getBoundingClientRect(),label=active.querySelector('[data-nav-label]')!.getBoundingClientRect();
      const width=root.width<100?target.width:Math.min(target.width,label.right-target.left+12),height=target.height;
      const x=target.left-root.left,y=target.top-root.top;
      const signature=[x,y,width,height].join(':');
      if(signature===lastTarget)return;
      lastTarget=signature;
      const before=block.getBoundingClientRect();block.getAnimations().forEach(a=>a.cancel());
      Object.assign(block.style,{width:width+'px',height:height+'px',transform:`translate(${x}px, ${y}px)`,opacity:'1'});
      if(animate&&positioned.current&&!window.matchMedia('(prefers-reduced-motion: reduce)').matches){
        block.animate([{transform:`translate(${before.left-root.left}px, ${before.top-root.top}px) scale(${before.width/width}, ${before.height/height})`},{transform:`translate(${x}px, ${y}px) scale(1)`}],{duration:280,easing:'cubic-bezier(.2,.9,.25,1.08)'});
      }
      container.dataset.highlightReady='true';positioned.current=true;
    };
    place(true);
    const observer=new ResizeObserver(()=>place());observer.observe(container);observer.observe(active);
    document.fonts.ready.then(()=>place());
    return()=>{alive=false;observer.disconnect();};
  },[location.pathname,location.search,admin,expanded]);

  return (
    <aside className={`${styles.sidebar}${expanded ? ` ${styles.expanded}` : ''}`}>
      <button className={styles.menuToggle} aria-expanded={expanded} aria-controls="pas-navigation" onClick={()=>setExpanded(!expanded)}>{expanded?'Close menu':'Menu'}</button>
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
          <div className={styles.logoSub}>Research & Evidence</div>
        </div>
      </div>

      <button className={styles.commandTrigger} onClick={()=>{close();setCommandOpen(true);}} aria-label="Find a PAS page" aria-keyshortcuts="Meta+K Control+K" title="Find a PAS page (⌘ / Ctrl K)">
        <svg aria-hidden="true" width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="6.5" cy="6.5" r="4.5"/><path d="m10 10 4 4"/></svg>
        <span>Find a page</span><kbd>{shortcut}</kbd>
      </button>
      <nav ref={nav} className={styles.nav} id="pas-navigation" aria-label="PAS navigation">
        <span ref={highlight} className={styles.highlight} aria-hidden="true"/>
        {['Research','Analytics','Network','Team','Operations'].map(group=><div key={group} className={styles.navGroup}>
          <div className={styles.sectionLabel}>{group}</div>
          {items.filter(item=>item.group===group).map(item=><NavItemLink key={item.to} to={item.to} label={item.label}
            active={navigationActive(item,location.pathname,location.search,admin)} restricted={item.access==='admin'&&!admin} onClick={close}/>)}
        </div>)}
      </nav>
      {commandOpen&&<CommandPalette items={items} admin={admin} onClose={()=>setCommandOpen(false)}/>}

      {/* Footer utilities */}
      {admin && <div className={styles.footer}>
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
      </div>}
    </aside>
  );
}
