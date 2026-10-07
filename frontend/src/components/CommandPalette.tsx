import { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useLocation, useNavigate } from 'react-router-dom';
import { findNavigation, navigationActive } from './navigation';
import type { NavigationItem } from './navigation';
import styles from './CommandPalette.module.css';

function Match({text,query}:{text:string;query:string}) {
  const words=query.trim().split(/\s+/).filter(Boolean);
  if(!words.length)return <>{text}</>;
  const expression=new RegExp('('+words.map(w=>w.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('|')+')','gi');
  return <>{text.split(expression).map((part,i)=>i%2?<mark key={i}>{part}</mark>:part)}</>;
}

export function CommandPalette({items,admin,onClose}:{items:NavigationItem[];admin:boolean;onClose:()=>void}) {
  const [query,setQuery]=useState(''),[selected,setSelected]=useState(0);
  const dialog=useRef<HTMLDialogElement>(null),input=useRef<HTMLInputElement>(null);
  const navigate=useNavigate(),location=useLocation();
  const results=useMemo(()=>findNavigation(items,query),[items,query]);
  const index=Math.min(selected,Math.max(0,results.length-1));
  useEffect(()=>{
    const element=dialog.current!,previous=document.activeElement;
    const overflow=document.body.style.overflow;
    element.showModal();document.body.style.overflow='hidden';input.current?.focus();
    return()=>{element.close();document.body.style.overflow=overflow;if(previous instanceof HTMLElement && previous.isConnected)previous.focus();};
  },[]);
  useEffect(()=>{dialog.current?.querySelector('[aria-selected="true"]')?.scrollIntoView({block:'nearest'});},[index,query]);
  function choose(item:NavigationItem) {
    onClose();navigate(item.to);
    requestAnimationFrame(()=>document.getElementById('pas-main')?.focus({preventScroll:true}));
  }
  return createPortal(<dialog ref={dialog} className={styles.dialog} aria-labelledby="pas-command-title" onCancel={e=>{e.preventDefault();onClose();}}
    onClick={e=>{const rect=e.currentTarget.getBoundingClientRect();if(e.target===e.currentTarget && (e.clientX<rect.left||e.clientX>rect.right||e.clientY<rect.top||e.clientY>rect.bottom))onClose();}}>
    <header className={styles.header}><div><p>PAS / NAVIGATION</p><h2 id="pas-command-title">Find a page</h2></div><button onClick={onClose} aria-label="Close page search">Esc</button></header>
    <div className={styles.search}><svg aria-hidden="true" width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="8.5" cy="8.5" r="5.5"/><path d="m13 13 4 4"/></svg>
      <input ref={input} aria-label="Search PAS pages" role="combobox" aria-autocomplete="list" aria-expanded="true" aria-controls="pas-command-results" aria-activedescendant={results.length?'pas-command-option-'+index:undefined}
        placeholder="Search pages, tools, or 项目…" value={query} maxLength={120} onChange={e=>{setQuery(e.target.value);setSelected(0);}}
        onKeyDown={e=>{if(e.nativeEvent.isComposing)return;if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();if(results.length)setSelected((index+(e.key==='ArrowDown'?1:-1)+results.length)%results.length);}else if(e.key==='Enter'){e.preventDefault();if(results[index])choose(results[index]);}}}/>
    </div>
    <p className={styles.scope}>Search page names and descriptions. Your notes and conversations stay private.</p>
    <ul id="pas-command-results" className={styles.results} role="listbox" aria-label="PAS pages">
      {results.map((item,i)=>{const current=navigationActive(item,location.pathname,location.search,admin),locked=item.access==='admin'&&!admin;
        return <li key={item.to} id={'pas-command-option-'+i} role="option" aria-selected={i===index} className={styles.option}
          onPointerMove={()=>setSelected(i)} onMouseDown={e=>e.preventDefault()} onClick={()=>choose(item)}>
          <span className={styles.resultBody}><span className={styles.group}>{item.group}</span><strong><Match text={item.label} query={query}/></strong><span className={styles.description}><Match text={item.description} query={query}/></span></span>
          <span className={styles.meta}>{current&&<span className={styles.current}>Current page</span>}{locked?<span className={styles.lock}>Admin access</span>:item.access==='member'?<span>Personal workspace</span>:null}<span className={styles.enter} aria-hidden="true">↵</span></span>
        </li>;
      })}
    </ul>
    {!results.length&&<div className={styles.empty} role="status"><strong>No pages match “{query}”</strong><p>Try “papers”, “institution”, or “项目”.</p></div>}
    <footer className={styles.footer}><span aria-live="polite">{results.length} {results.length===1?'page':'pages'}</span><span>↑ ↓ Select <span>↵ Open</span> Esc Close</span></footer>
  </dialog>,document.body);
}
