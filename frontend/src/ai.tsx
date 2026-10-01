import { useEffect, useState } from "react";
import { Sparkles, Settings, Check, RefreshCw } from "lucide-react";
import { api, save, Row, stateNames } from "./api";
const priorities: Row = { low: "Låg", normal: "Normal", high: "Hög", urgent: "Akut" };

export function AISettingsPanel({ demo = false }: { demo?: boolean }) {
  const [config, setConfig] = useState<Row | null>(null);
  const [orgs, setOrgs] = useState<Row[]>([]);
  const [key, setKey] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  useEffect(() => { if(demo){setConfig({version:0,enabled:false,endpoint:"https://api.openai.com/v1",model:"",has_key:false,daily_limit:100,allow_changes:false,organizations:[]});setNotice("Förhandsvisning av inställningar. Demokontot kan inte aktivera externa anslutningar. Logga in med ett separat systemadministratörskonto för att konfigurera AI.");return;} let active=true; Promise.all([api("ai/settings/"), api("bootstrap/")]).then(([c,b]) => {if(active){setConfig(c);setOrgs(b.organizations || []);}}).catch(e=>{if(active)setNotice(e.message);}); return()=>{active=false;}; }, []);
  async function submit(e: React.FormEvent) {
    e.preventDefault(); if(!config)return; setBusy(true);setNotice("");
    try { const c=await api("ai/settings/",{method:"POST",body:JSON.stringify({...config,api_key:key,password,code})}); setConfig(c);setKey("");setPassword("");setCode("");setNotice("Sparat på servern. Öppna AI-assistenten för att testa anslutningen."); }
    catch(e:any){setNotice(e.message);}finally{setBusy(false);}
  }
  return <section className="panel ai-settings"><h2><Settings size={20}/> AI-inställningar</h2><p>OpenAI-kompatibelt API. Nyckeln lagras krypterad på servern. Aktivering tillåter att valda enheters arbetsorderunderlag skickas till den angivna leverantören när en användare ber om det.</p>
    {notice&&<p role="status" className="ai-notice">{notice}</p>}
    {config&&<form onSubmit={submit} className="ai-form"><fieldset disabled={demo||busy} className="ai-form">
      <label>API-adress<input required type="url" value={config.endpoint} onChange={e=>setConfig({...config,endpoint:e.target.value})}/></label>
      <label>Modellnamn<input required maxLength={120} value={config.model} placeholder="Modellens exakta API-namn" onChange={e=>setConfig({...config,model:e.target.value})}/></label>
      <label>API-nyckel {config.has_key?"· sparad nyckel finns":""}<input type="password" autoComplete="new-password" value={key} onChange={e=>setKey(e.target.value)} placeholder={config.has_key?"Lämna tomt för att behålla nyckeln":"Ange leverantörens API-nyckel"}/></label>
      <label>Högst antal anrop per dag, hela installationen<input required type="number" min="1" max="10000" value={config.daily_limit} onChange={e=>setConfig({...config,daily_limit:Number(e.target.value)})}/></label>
      <fieldset><legend>Tillåtna enheter · välj varje enhet uttryckligen</legend>{orgs.map(o=><label className="ai-check" key={o.id}><input type="checkbox" checked={config.organizations.includes(o.id)} onChange={e=>setConfig({...config,organizations:e.target.checked?[...config.organizations,o.id]:config.organizations.filter((id:string)=>id!==o.id)})}/>{o.name}</label>)}</fieldset>
      <label className="ai-check"><input type="checkbox" checked={config.enabled} onChange={e=>setConfig({...config,enabled:e.target.checked})}/>Aktivera AI och tillåt överföring av det beskrivna underlaget</label>
      <label className="ai-check"><input type="checkbox" checked={config.allow_changes} onChange={e=>setConfig({...config,allow_changes:e.target.checked})}/>Tillåt prioriteringsförslag som användaren kan godkänna</label>
      <p>Fråga, organisationsnamn, arbetsordrarnas rubriker, nummer, status, prioritet och förfallodatum kan skickas. Beskrivningar, interna kommentarer, personuppgifter i särskilda kontaktfält, bilagor och ekonomi ingår inte. Rubriker och egen frågetext kan ändå innehålla känsliga uppgifter. Kontrollera leverantörens villkor och lagringsregion innan aktivering.</p>
      <label>Ditt nuvarande lösenord<input required type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)}/></label>
      <label>Säkerhetskod från autentiseringsappen · krävs när MFA är aktivt<input inputMode="numeric" autoComplete="one-time-code" value={code} onChange={e=>setCode(e.target.value)}/></label>
      <button className="btn primary" disabled={busy}>{busy?"Sparar…":"Verifiera och spara AI-inställningar"}</button></fieldset>
    </form>}
  </section>;
}

export function AIPage() {
  const [info,setInfo]=useState<Row|null>(null);
  const [org,setOrg]=useState("");
  const [bundle,setBundle]=useState<Row|null>(null);
  const [question,setQuestion]=useState("");
  const [result,setResult]=useState<Row|null>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [consent,setConsent]=useState(false);
  const [saved,setSaved]=useState<string[]>([]);
  const [requestKey,setRequestKey]=useState(()=>crypto.randomUUID());
  const [refresh,setRefresh]=useState(0);
  useEffect(()=>{let active=true;api("ai/context/").then(r=>{if(active)setInfo(r);}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[]);
  useEffect(()=>{let active=true;setBundle(null);setResult(null);setConsent(false);setSaved([]);setError("");setRequestKey(crypto.randomUUID());if(org)api("ai/context/?org="+encodeURIComponent(org)).then(r=>{if(active)setBundle(r);}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[org,refresh]);
  async function ask(e:React.FormEvent){e.preventDefault();if(!bundle||!consent)return;setBusy(true);setError("");setResult(null);setSaved([]);
    try{setResult(await api("ai/chat/",{method:"POST",headers:{"Idempotency-Key":requestKey},body:JSON.stringify({org,question,context_digest:bundle.digest})}));}
    catch(e:any){setError(e.message+" Inget svar innebär inte säkert att leverantören saknar debitering. Samma fråga med samma anropsnyckel skickas inte dubbelt.");}finally{setBusy(false);}
  }
  async function approve(p:Row){setBusy(true);setError("");try{await save("ai/apply/",{token:p.token});setSaved(s=>[...s,p.token]);}catch(e:any){setError(e.message);}finally{setBusy(false);}}
  return <div className="ai-page"><div className="page-heading"><div><div className="eyebrow">ANALYS & ARBETSSTÖD</div><h1><Sparkles size={30}/> AI-assistent</h1><p>Förstå läget, få förslag och granska ändringar innan de sparas.</p></div></div>
    {error&&<p role="alert" className="ai-notice">{error}</p>}
    {!info?<p role="status">Läser AI-inställningar…</p>:!info.enabled?<section className="panel"><h2>Anslut organisationens AI</h2><p>AI är avstängd. En systemadministratör anger API-adress, modell och nyckel under Administration → AI-inställningar. Inga uppgifter skickas innan funktionen är aktiverad.</p><a href="#/admin" className="btn">Öppna Administration</a></section>:<>
    <div className="ai-grid"><section className="panel"><h2>1. Välj underlag</h2><label>Organisationsenhet<select disabled={busy} value={org} onChange={e=>setOrg(e.target.value)}><option value="">Välj enhet</option>{info?.organizations.map((o:Row)=><option key={o.id} value={o.id}>{o.name}</option>)}</select></label>{info?.enabled&&info.organizations.length===0&&<p>Du har ingen enhet med tillåten AI-åtkomst.</p>}
      {bundle&&<><p><strong>{bundle.context.included}</strong> av {bundle.context.total} arbetsorder. Exakt vald enhet; underenheter ingår inte.</p><p>Modell: {bundle.model}<br/>Mottagare: {bundle.endpoint}</p><details><summary>Granska uppgifterna som skickas</summary><p>{bundle.context.note}</p><div className="ai-source-list">{bundle.context.rows.map((r:Row)=><p key={r.id}>#{r.number} {r.title} · {stateNames[r.status]} · {priorities[r.priority]} · {r.due_date||"Datum saknas"}</p>)}</div><p>Statusantal: {bundle.context.status_counts.map((r:Row)=>`${stateNames[r.status]} ${r.count}`).join(", ")}</p></details><button className="btn" disabled={busy} onClick={()=>setRefresh(n=>n+1)}><RefreshCw size={16}/>Läs in aktuellt underlag</button></>}
    </section><section className="panel"><h2>2. Fråga assistenten</h2><form className="ai-form" onSubmit={ask}><label>Din fråga<textarea required disabled={busy} rows={5} maxLength={4000} value={question} onChange={e=>{setQuestion(e.target.value);setRequestKey(crypto.randomUUID());setResult(null);}} placeholder="Sammanfatta arbetsläget och föreslå vilka ärenden vi bör prioritera."/></label><p>Första versionen kan analysera arbetsorder och föreslå ändrad prioritet. Varje fråga är fristående. AI-svar kan innehålla fel; kontrollera underlaget.</p><label className="ai-check"><input type="checkbox" disabled={busy} checked={consent} onChange={e=>setConsent(e.target.checked)}/>Skicka min fråga och det granskade underlaget till vald AI-leverantör</label><button className="btn primary" disabled={busy||!bundle||!consent||!question.trim()}><Sparkles size={16}/>{busy?"Arbetar…":"Analysera med AI"}</button></form></section></div>
    {result&&<section className="panel ai-answer"><h2>Assistentens svar</h2><p className="ai-answer-text">{result.answer}</p><p className="muted">{result.model} · {new Date(result.generated_at).toLocaleString("sv-SE")} · Underlag: {result.sources.included} av {result.sources.total} arbetsorder</p>{result.proposals.map((p:Row)=><article className="ai-proposal" key={p.token}><h3>#{p.number} {p.title}</h3><p>{p.reason}</p><p>Prioritet: <strong>{priorities[p.before]} → {priorities[p.after]}</strong></p>{saved.includes(p.token)?<p role="status"><Check size={16}/> Sparat och loggat</p>:<button className="btn primary" disabled={busy} onClick={()=>approve(p)}>Godkänn och spara denna ändring</button>}</article>)}<details><summary>Källposter i underlaget</summary>{result.sources.rows.map((r:Row)=><p key={r.id}>#{r.number} {r.title} · version {r.version}</p>)}</details></section>}
    </>}
  </div>;
}
