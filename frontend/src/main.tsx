import {useEffect,useState} from 'react';
import {createRoot} from 'react-dom/client';
import './style.css';
import LegacyApp from './LegacyApp';
import Portal from './Portal';
import {BrandLogo} from './Brand';
function Boot(){
 const [mode,setMode]=useState(''),[error,setError]=useState(''),[authenticated,setAuthenticated]=useState(false);
 useEffect(()=>{const original=window.fetch;let active=true;(async()=>{try{const r=await original('/api/health');if(!r.ok)throw new Error('The server is not ready.');const health=await r.json();if(health.mode==='hosted-workspace'){const response=await original('/api/session');const session=await response.json();if(!response.ok)throw new Error(typeof session.detail==='string'?session.detail:'Your organisation account has not been granted access.');if(session.authenticated){const token=session.csrf_token;window.fetch=(input,init)=>{const method=(init?.method||'GET').toUpperCase();const target=new URL(typeof input==='string'?input:input instanceof URL?input.href:input.url,window.location.href);if(target.origin===window.location.origin&&target.pathname.startsWith('/api/')&&!['GET','HEAD','OPTIONS'].includes(method)){const headers=new Headers(init?.headers);headers.set('X-ORBIT-CSRF',token);return original(input,{...init,headers});}return original(input,init);};setAuthenticated(true);}}if(active)setMode(health.mode);}catch(e){if(active)setError((e as Error).message);}})();return()=>{active=false;window.fetch=original;};},[]);
 if(error)return <div className="boot-message">{error}</div>;
 if(!mode)return <div className="boot-message">Opening ORBIT…</div>;
 if(mode==='hosted-workspace'&&!authenticated)return <div className="portal portal-loading"><BrandLogo/><h1>ORBIT UAT</h1><p>Sign in with your organisation account.</p><a className="primary" href="/auth/login">Sign in with Microsoft</a></div>;
 return mode==='local-workspace'||mode==='hosted-workspace'?<Portal hosted={mode==='hosted-workspace'}/>:<LegacyApp/>;
}
createRoot(document.getElementById('root')!).render(<Boot/>);
