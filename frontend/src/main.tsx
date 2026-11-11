import {useEffect,useState} from 'react';
import {createRoot} from 'react-dom/client';
import './style.css';
import LegacyApp from './LegacyApp';
import Portal from './Portal';
function Boot(){
 const [mode,setMode]=useState(''),[error,setError]=useState('');
 useEffect(()=>{fetch('/api/health').then(r=>{if(!r.ok)throw new Error('The local server is not ready.');return r.json();}).then(d=>setMode(d.mode)).catch(e=>setError(e.message));},[]);
 if(error)return <div className="boot-message">{error} Start Run-ORBIT.cmd and reload this page.</div>;
 if(!mode)return <div className="boot-message">Opening ORBIT…</div>;
 return mode==='local-workspace'?<Portal/>:<LegacyApp/>;
}
createRoot(document.getElementById('root')!).render(<Boot/>);
