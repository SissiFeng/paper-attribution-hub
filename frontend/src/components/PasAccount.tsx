import { createContext, useContext, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { api, identityChanged } from '@/reading/api';
import type { Reader } from '@/reading/api';

const Context = createContext<{user: Reader | null; checking: boolean; signIn: () => void}>({user:null, checking:true, signIn:()=>{}});
export const usePasAccount = () => useContext(Context);

export function PasAccount({children}: {children: ReactNode}) {
  const [user,setUser]=useState<Reader|null>(null), [checking,setChecking]=useState(true), [show,setShow]=useState(false);
  const [pair,setPair]=useState<{command:string; slack_url:string}|null>(null), [busy,setBusy]=useState(false), [error,setError]=useState('');
  useEffect(() => {
    let active=true;
    const refresh=()=>api<Reader>('/auth/me').then(u=>{if(active)setUser(u);}).catch(()=>{if(active)setUser(null);}).finally(()=>{if(active)setChecking(false);});
    const changed=(e:StorageEvent)=>{if(e.key==='pas.identity.changed'){setUser(null);refresh();}};
    const lost=()=>setUser(null);
    refresh(); window.addEventListener('storage',changed);window.addEventListener('pas-auth-lost',lost);
    return()=>{active=false;window.removeEventListener('storage',changed);window.removeEventListener('pas-auth-lost',lost);};
  },[]);
  useEffect(()=>{
    if(!user)return;
    let active=true;
    const refresh=()=>api<Reader>('/auth/me').then(u=>{if(active)setUser(u);}).catch(()=>{if(active)setUser(null);});
    const timer=setInterval(refresh,60000);window.addEventListener('focus',refresh);
    return()=>{active=false;clearInterval(timer);window.removeEventListener('focus',refresh);};
  },[user?.id]);
  useEffect(()=>{
    if(!pair || !show)return;
    let active=true,pending=false;
    const timer=setInterval(async()=>{
      if(pending)return;pending=true;
      try{const result=await api<{user?:Reader}>('/auth/connect/complete',{});if(active && result.user){identityChanged();setUser(result.user);setPair(null);setShow(false);}}
      catch(e){if(active){setError((e as Error).message);setPair(null);}}
      finally{pending=false;}
    },2000);
    return()=>{active=false;clearInterval(timer);};
  },[pair,show]);
  async function connect(){setBusy(true);setError('');try{setPair(await api('/auth/connect',{}));}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  async function logout(){try{await api('/auth/logout',{});identityChanged();setUser(null);}catch(e){setError((e as Error).message);setShow(true);}}
  return <Context.Provider value={{user,checking,signIn:()=>{setError('');setShow(true);}}}>
    <div className="pas-account">{user ? <><span>{user.name}{user.role==='admin'?' · Admin':''}</span><button onClick={logout}>Sign out</button></> : <button onClick={()=>setShow(true)} disabled={checking}>Sign in to PAS</button>}</div>
    {children}
    {show && <div className="pas-login-backdrop"><section className="pas-login-dialog" role="dialog" aria-modal="true" aria-labelledby="pas-signin-title">
      <button className="pas-close" aria-label="Close sign in" onClick={()=>setShow(false)}>×</button>
      <h2 id="pas-signin-title">Sign in to your PAS workspace</h2><p>You will return to this page after signing in. Your account determines access to administration and private research tools.</p>
      {pair ? <><ol><li>Copy the command below.</li><li>Send it in your <strong>AC Papers private chat</strong> in Slack.</li><li>Return to this tab. PAS will finish signing you in automatically.</li></ol><code>{pair.command}</code><div className="pas-paper-actions"><button onClick={()=>navigator.clipboard.writeText(pair.command).catch(()=>setError('Select and copy the command above.'))}>Copy command</button><a href={pair.slack_url} target="_blank" rel="noreferrer">Open AC Papers in Slack ↗</a></div><p role="status">Waiting for Slack confirmation… The code expires in five minutes.</p><small>Opening Slack alone does not confirm your identity. Send the command to the bot.</small></> : <button onClick={connect} disabled={busy}>{busy?'Connecting…':'Connect with AC Papers'}</button>}
      {error && <p role="alert">{error}</p>}
    </section></div>}
  </Context.Provider>;
}

export function RequireAccount({children,admin=false}: {children:ReactNode;admin?:boolean}) {
  const {user,checking,signIn}=usePasAccount();
  if(checking)return <p role="status">Checking access…</p>;
  if(!user)return <section className="pas-paper-panel"><h1>{admin?'Administrator sign-in required':'My research'}</h1><p>{admin?'This PAS page is available to administrators. Sign in to continue here.':'Sign in to open your private notes, comparisons and projects.'}</p><button onClick={signIn}>Sign in with AC Papers</button><p><a href="/papers">Browse papers</a></p></section>;
  if(admin && user.role!=='admin')return <section className="pas-paper-panel"><h1>Administrator access required</h1><p>Your papers and personal research workspace remain available.</p><a href="/">Back to papers</a></section>;
  return <>{children}</>;
}
