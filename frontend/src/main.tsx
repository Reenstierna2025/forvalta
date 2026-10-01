import { InspectionsPage } from "./inspections";
import { GroupDetails, ScenarioComparison, groupChoices, measureChoices } from "./report-tools";
import { PropertyWorkspace } from "./property";
import { AIPage, AISettingsPanel } from "./ai";
import { SecurityPage, AccessPanel, RecoveryCodes } from "./security";
import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Sparkles,
  LayoutDashboard,
  Building2,
  ClipboardList,
  CalendarDays,
  BarChart3,
  Settings,
  Search,
  Plus,
  ChevronDown,
  ChevronRight,
  ArrowUpRight,
  Check,
  CheckCircle2,
  Clock3,
  AlertCircle,
  X,
  Menu,
  LogOut,
  ExternalLink,
  FileText,
  Download,
  ShieldCheck,
  Layers,
  Leaf,
  KeyRound,
  Wrench,
  Paperclip,
  Send,
  Loader2,
  MoreHorizontal,
  Users,
  RefreshCw,
  FolderOpen,
  Lock,
  Copy,
  Archive,
  Wallet,
  Activity,
} from "lucide-react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";
import {
  api,
  save,
  list,
  query,
  money,
  num,
  day,
  today,
  stateNames,
  kindNames,
  Row,
  ApiError,
} from "./api";
import "./style.css";

type Field = {
  key: string;
  label: string;
  type?: string;
  required?: boolean;
  options?: [string, string][];
  min?: number;
  max?: number;
  hint?: string;
  default?: any;
};
type ModalConfig = {
  title: string;
  endpoint: string;
  fields: Field[];
  initial?: Row;
  method?: string;
  transform?: (d: Row) => Row;
  onDone?: (r: Row) => void;
};
const orgOptions = (b: Row) =>
  b.organizations?.map((o: Row) => [o.id, o.name]) || [];
const assetOptions = (b: Row, org?: string) =>
  b.assets
    ?.filter((a: Row) => !org || a.org === org)
    .map((a: Row) => [a.id, a.name]) || [];
const choices = (
  values: string[],
  labels: Row = kindNames,
): [string, string][] => values.map((v) => [v, labels[v] || v]);
const priorityNames: Row = {
  urgent: "Akut",
  high: "Hög",
  normal: "Normal",
  low: "Låg",
};
const reportNames: Row = {
  work: "Arbetsbelastning",
  overdue: "Försenade arbeten",
  rounds: "Tillsyn och skötsel",
  inspections: "Besiktningar",
  budget: "Underhållsbudget",
  maintenance: "Underhållsplan",
  assets: "Fastighetsregister",
  energy: "Energi och mätvärden",
  keys: "Nyckelutlåning",
  registry: "Planer och kontroller",
  nki: "Nöjd kundindex",
  invoices: "Fakturaunderlag",
};
const dateNow = today();
function Badge({ value }: { value: string }) {
  return (
    <span className={"badge " + value}>
      {stateNames[value] || priorityNames[value] || value}
    </span>
  );
}
function Empty({
  title = "Inga uppgifter ännu",
  text = "Lägg till den första posten för att komma igång.",
  action,
}: {
  title?: string;
  text?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="empty">
      <FolderOpen size={34} />
      <h3>{title}</h3>
      <p>{text}</p>
      {action}
    </div>
  );
}
function Loading() {
  return (
    <div className="loading">
      <Loader2 className="spin" /> Läser in uppgifter…
    </div>
  );
}
function DataTable({
  columns,
  rows,
  onRow,
}: {
  columns: {
    key: string;
    label: string;
    render?: (r: Row) => React.ReactNode;
  }[];
  rows: Row[];
  onRow?: (r: Row) => void;
}) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key}>{c.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.id || i}>
              {columns.map((c, j) => (
                <td key={c.key}>
                  {onRow && j === 0 ? (
                    <button className="row-link" onClick={() => onRow(r)}>
                      {c.render ? c.render(r) : r[c.key] || "—"}
                    </button>
                  ) : c.render ? (
                    c.render(r)
                  ) : (
                    (r[c.key] ?? "—")
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <MoreRows rows={rows} />
      {!rows.length && (
        <Empty
          title="Inga träffar"
          text="Ändra urvalet eller lägg till en post."
        />
      )}
    </div>
  );
}
function App() {
  const [auth, setAuth] = useState<Row | null>(null),
    [boot, setBoot] = useState<Row | null>(null),
    [route, setRoute] = useState(location.hash.slice(1) || "/overview"),
    [org, setOrg] = useState(localStorage.getItem("forvalta-org") || ""),
    [search, setSearch] = useState(""),
    [menu, setMenu] = useState(false),
    [modal, setModal] = useState<ModalConfig | null>(null),
    [toast, setToast] = useState(""),
    [error, setError] = useState(""),
    [tick, setTick] = useState(0),
    [detail, setDetail] = useState<Row | null>(null);
  const refresh = () => setTick((t) => t + 1);
  const notify = (msg = "Sparat på servern") => {
    setToast(msg);
    setTimeout(() => setToast(""), 4500);
  };
  const fail = (e: any) =>
    setError(e.message || "Kunde inte läsa uppgifterna.");
  const navigate = (path: string) => {
    location.hash = path;
    setDetail(null);
    setSearch("");
    setMenu(false);
  };
  useEffect(() => {
    let lastHash=location.hash;
    const h = () => {
      if(!window.dispatchEvent(new Event('forvalta:before-navigate',{cancelable:true}))){history.replaceState(null,'',location.pathname+location.search+lastHash);return;}
      lastHash=location.hash;
      setRoute(location.hash.slice(1) || "/overview");
      setError("");
    };
    addEventListener("hashchange", h);
    api("auth/").then(setAuth).catch(fail);
    return () => removeEventListener("hashchange", h);
  }, []);
  useEffect(() => {
    let alive=true;
    if (auth?.user)api("bootstrap/?"+query({org})).then(data=>{if(alive)setBoot(data)}).catch(e=>{if(alive)fail(e)});
    return()=>{alive=false};
  }, [auth, org, tick]);
  useEffect(()=>{const expired=()=>{setBoot(null);setDetail(null);setModal(null);api('auth/').then(a=>setAuth({...a,sessionExpired:true})).catch(fail)};addEventListener('forvalta:session-expired',expired);return()=>removeEventListener('forvalta:session-expired',expired)},[]);
  const changeOrg = (id: string) => {
    if(!window.dispatchEvent(new Event('forvalta:before-navigate',{cancelable:true})))return;
    setOrg(id);
    localStorage.setItem("forvalta-org", id);
    setDetail(null);
  };
  const write = async (path: string, data: Row, method = "POST") => {
    try {
      const result = await save(path, data, method);
      refresh();
      notify();
      return result;
    } catch (e) {
      fail(e);
      return null;
    }
  };
  if (route.startsWith("/public") || route.startsWith("/track/"))
    return <PublicPortal route={route} />;
  if (!auth) return <Loading />;
  if (!auth.user)
    return (
      <Login
        auth={auth}
        done={(a) => {
          setAuth({ ...auth, ...a });
          navigate("/overview");
        }}
      />
    );
  if (!boot) return <Loading />;
  const section = route.split("/")[1] || "overview";
  const orgField: Field = {
    key: "org",
    label: "Organisationsenhet",
    type: "select",
    required: true,
    options: orgOptions(boot),
    default:
      org ||
      boot.organizations.find((o: Row) => o.kind === "parish")?.id ||
      boot.organizations[0]?.id,
  };
  const assetField: Field = {
    key: "asset",
    label: "Fastighet eller objekt",
    type: "asset",
    required: true,
    options: assetOptions(boot),
  };
  const fields = { org: orgField, asset: assetField };
  const openForm = (type: string, record?: Row, extra: Row = {}) => {
    const defs = formDefinitions(type, boot, fields);
    setModal({
      ...defs,
      initial: { ...defs.initial, ...extra, ...record },
      endpoint: record ? defs.endpoint + record.id + "/" : defs.endpoint,
      method: record ? "PATCH" : "POST",
    });
  };
  const common = {
    setOrg: changeOrg,
    boot,
    org,
    search,
    tick,
    notify,
    fail,
    openForm,
    write,
    navigate,
    fields,
    setModal,
    refresh,
    detail,
    setDetail,
  };
  const nav = [
    { id: "overview", label: "Översikt", icon: LayoutDashboard },
    { id: "assets", label: "Fastigheter", icon: Building2 },
    {
      id: "work",
      label: "Arbete",
      icon: ClipboardList,
      count: boot.stats.open,
    },
    { id: "calendar", label: "Kalender", icon: CalendarDays },
    { id: "maintenance", label: "Underhåll & budget", icon: Wallet },
    { id: "reports", label: "Rapporter", icon: BarChart3 },
    { id: "ai", label: "AI-assistent", icon: Sparkles },
  ];
  const extraNav = [
    { id: "schedules", label: "Ronder & besiktning", icon: ShieldCheck },
    { id: "inspections", label: "Besiktningsprotokoll", icon: ClipboardList },
    { id: "registry", label: "Planer & inventarier", icon: Layers },
    { id: "energy", label: "Energi & miljö", icon: Leaf },
    { id: "keys", label: "Nycklar", icon: KeyRound },
    { id: "contracts", label: "Entreprenader", icon: Wrench },
    { id: "documents", label: "Dokument", icon: FolderOpen },
  ];
  const heading =
    [
      ...nav,
      ...extraNav,
      { id: "security", label: "Min säkerhet" },
      { id: "admin", label: "Administration" },
    ].find((n) => n.id === section)?.label || "Förvalta";
  return (
    <div className="app">
      <a className="skip" href="#main">
        Hoppa till innehåll
      </a>
      <aside className={"sidebar " + (menu ? "mobile-open" : "")}>
        <button className="brand" onClick={() => navigate("/overview")}>
          <span className="brand-symbol">F</span>förvalta
          <span className="brand-dot">.</span>
        </button>
        <div className="workspace-label">FASTIGHETSFÖRVALTNING</div>
        <nav aria-label="Huvudmeny">
          {nav.map((n) => (
            <button
              key={n.id}
              className={"nav-item " + (section === n.id ? "active" : "")}
              onClick={() => navigate("/" + n.id)}
            >
              <n.icon size={19} />
              <span>{n.label}</span>
              {n.count > 0 && <small>{n.count}</small>}
            </button>
          ))}
        </nav>
        <div className="nav-caption">VERKSAMHET</div>
        <nav aria-label="Verksamhetsmoduler">
          {extraNav.map((n) => (
            <button
              key={n.id}
              className={
                "nav-item compact " + (section === n.id ? "active" : "")
              }
              onClick={() => navigate("/" + n.id)}
            >
              <n.icon size={17} />
              <span>{n.label}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <button
            className={"nav-item " + (section === "security" ? "active" : "")}
            onClick={() => navigate("/security")}
          >
            <ShieldCheck size={18} />
            Min säkerhet
          </button>
          <button
            className={"nav-item " + (section === "admin" ? "active" : "")}
            onClick={() => navigate("/admin")}
          >
            <Settings size={18} />
            Administration
          </button>
          <a className="nav-item" href="#/public" target="_blank">
            <ExternalLink size={17} />
            Publik felanmälan
          </a>
          <div className="profile">
            <span className="avatar">
              {auth.user.name
                .split(" ")
                .map((s: string) => s[0])
                .slice(0, 2)
                .join("")}
            </span>
            <div>
              <strong>{auth.user.name}</strong>
              <small>{boot.demo ? "Demomiljö" : "Inloggad"}</small>
            </div>
            <button
              className="icon-btn"
              aria-label="Logga ut"
              onClick={async () => {
                if(!window.dispatchEvent(new Event("forvalta:before-navigate",{cancelable:true}))) return;
                await api("auth/", { method: "DELETE" });
                setAuth({ ...auth, user: null });
                setBoot(null);
              }}
            >
              <LogOut size={17} />
            </button>
          </div>
        </div>
      </aside>
      <div className="shell">
        <header className="topbar">
          <button
            className="icon-btn mobile-menu"
            aria-label="Öppna meny"
            onClick={() => setMenu(!menu)}
          >
            <Menu />
          </button>
          <div className="breadcrumb">
            <span>Förvaltning</span>
            <ChevronRight size={14} />
            <strong>{heading}</strong>
          </div>
          <div className="top-actions">
            <label className="org-picker">
              <Building2 size={16} />
              <select
                aria-label="Organisationsurval"
                value={org}
                onChange={(e) => changeOrg(e.target.value)}
              >
                <option value="">Alla mina enheter</option>
                {boot.organizations.map((o: Row) => (
                  <option key={o.id} value={o.id}>
                    {o.name}
                  </option>
                ))}
              </select>
            </label>
            <div className="today-label">
              {new Date().toLocaleDateString("sv-SE", {
                day: "numeric",
                month: "long",
                year: "numeric",
              })}
            </div>
          </div>
        </header>
        {boot.demo && (
          <div className="demo-strip">
            <span>DEMO</span> Fiktiv testdata · separat från verksamhetens
            register
          </div>
        )}
        <main id="main">
          {error && (
            <div role="alert" className="alert">
              <AlertCircle size={18} />
              <span>{error}</span>
              <button
                className="icon-btn"
                aria-label="Stäng felmeddelande"
                onClick={() => setError("")}
              >
                <X size={16} />
              </button>
            </div>
          )}
          {section === "overview" ? (
            <Overview {...common} />
          ) : section === "assets" ? (
            <AssetsPage {...common} />
          ) : section === "work" ? (
            <WorkPage {...common} />
          ) : section === "maintenance" ? (
            <BudgetPage {...common} />
          ) : section === "reports" ? (
            <ReportsPage {...common} />
          ) : section === "calendar" ? (
            <CalendarPage {...common} />
          ) : section === "inspections" ? (
            <InspectionsPage p={common} />
          ) : section === "ai" ? (
            <AIPage />
          ) : section === "security" ? (
            <SecurityPage boot={boot} />
          ) : section === "admin" ? (
            <AdminPage {...common} />
          ) : (
            <ModulePage {...common} section={section} heading={heading} />
          )}
        </main>
        <footer className="app-footer">
          <span>Förvalta · Öppen fastighetsförvaltning</span>
          <a
            href={auth.source_url || "/api/schema.json?format=json"}
            target="_blank"
          >
            {auth.source_url ? "Källkod · AGPL-3.0" : "API-dokumentation"}
          </a>
        </footer>
      </div>
      {toast && (
        <div role="status" className="toast">
          <CheckCircle2 size={18} />
          {toast}
        </div>
      )}
      {modal && (
        <FormDialog
          config={modal}
          boot={boot}
          onClose={() => setModal(null)}
          onSaved={(r) => {
            setModal(null);
            refresh();
            notify();
            modal.onDone?.(r);
          }}
        />
      )}
      {detail?.type === "work" && (
        <WorkDrawer
          row={detail.row}
          {...common}
          onClose={() => setDetail(null)}
        />
      )}
    </div>
  );
}
function Heading({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      <div className="heading-actions">{children}</div>
    </div>
  );
}
function FilterBar({
  search,
  onSearch,
  children,
}: {
  search: string;
  onSearch: (v: string) => void;
  children?: React.ReactNode;
}) {
  return (
    <div className="filterbar">
      <label className="search">
        <Search size={17} />
        <input
          placeholder="Sök i vyn…"
          value={search}
          onChange={(e) => onSearch(e.target.value)}
        />
      </label>
      {children}
    </div>
  );
}
function useRows(path: string, tick: number, fail: (e: any) => void) {
  const [rows, setRows] = useState<Row[] | null>(null);
  useEffect(() => {
    let alive = true;
    setRows(null);
    async function load(url: string, previous: Row[] = []) {
      try {
        const data = await api(url);
        if (!alive) return;
        const result = [...previous, ...(data.results || data)];
        Object.assign(result, {
          total: data.count || result.length,
          loadMore: data.next
            ? () => load(String(data.next).split("/api/v1/")[1], result)
            : null,
        });
        setRows(result);
      } catch (e) {
        if (alive) fail(e);
      }
    }
    load(path);
    return () => {
      alive = false;
    };
  }, [path, tick]);
  return rows;
}
function MoreRows({ rows }: { rows: Row[] | null }) {
  return rows && (rows as any).loadMore ? (
    <div className="padded">
      <button className="btn" onClick={(rows as any).loadMore}>
        Visa fler · {rows.length} av {(rows as any).total}
      </button>
    </div>
  ) : null;
}
function BudgetChart({ data }: { data: Row[] }) {
  return (
    <div className="chart" role="img" aria-label="Underhållsbudget per år">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={data.map((d) => ({ ...d, budget: Number(d.budget) }))}
          margin={{ top: 10, right: 5, left: 0, bottom: 0 }}
        >
          <CartesianGrid
            vertical={false}
            stroke="#e8edf1"
            strokeDasharray="3 3"
          />
          <XAxis
            dataKey="year"
            axisLine={false}
            tickLine={false}
            tick={{ fill: "#607084", fontSize: 12 }}
          />
          <YAxis
            axisLine={false}
            tickLine={false}
            tick={{ fill: "#607084", fontSize: 12 }}
            tickFormatter={(v) => num(v / 1000) + " tkr"}
            width={70}
          />
          <Tooltip
            formatter={(v: any) => money(v)}
            labelFormatter={(l) => "År " + l}
            contentStyle={{ borderRadius: 8, border: "1px solid #e2e8ef" }}
          />
          <Bar
            dataKey="budget"
            name="Budget"
            fill="#2a7f76"
            radius={[4, 4, 0, 0]}
            maxBarSize={48}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
function Overview(p: any) {
  const [budget, setBudget] = useState<Row | null>(null);
  useEffect(() => {
    if (p.boot.finance_orgs.length)
      api(
        "reports/?" +
          query({
            type: "budget",
            org: p.org,
            start_year: new Date().getFullYear(),
            years: 5,
          }),
      )
        .then(setBudget)
        .catch(p.fail);
  }, [p.org, p.tick]);
  const stats = p.boot.stats;
  return (
    <>
      <Heading
        eyebrow="DIN ARBETSDAG"
        title={
          "God " +
          (new Date().getHours() < 12 ? "morgon" : "dag") +
          ", " +
          p.boot.user.name.split(" ")[0]
        }
        description="Det viktigaste i förvaltningen, samlat på ett ställe."
      >
        <button className="btn primary" onClick={() => p.openForm("work")}>
          <Plus size={17} />
          Nytt ärende
        </button>
      </Heading>
      <div className="stats-grid">
        {[
          {
            label: "Öppna arbeten",
            value: stats.open,
            sub: "Att planera, utföra eller verifiera",
            icon: ClipboardList,
            route: "work",
          },
          {
            label: "Försenade arbeten",
            value: stats.overdue,
            sub: stats.overdue
              ? "Behöver följas upp"
              : "Inga passerade förfallodatum",
            icon: Clock3,
            route: "work",
            tone: "amber",
          },
          {
            label: "Kommande kontroller",
            value: stats.upcoming,
            sub: "Ronder och besiktningar · 30 dagar",
            icon: ShieldCheck,
            route: "calendar",
          },
          {
            label: "Registerobjekt",
            value: stats.assets,
            sub: "Fastigheter, byggnader och objekt",
            icon: Building2,
            route: "assets",
          },
        ].map((s) => (
          <button
            key={s.label}
            className={"stat-card " + (s.tone || "")}
            onClick={() => p.navigate("/" + s.route)}
          >
            <div className="stat-top">
              <span>{s.label}</span>
              <s.icon size={19} />
            </div>
            <strong>{s.value}</strong>
            <small>{s.sub}</small>
          </button>
        ))}
      </div>
      <div className="overview-grid">
        <section className="panel work-panel">
          <div className="panel-heading">
            <div>
              <h2>Att ta hand om</h2>
              <p>Öppna arbeten i datumordning</p>
            </div>
            <button className="text-btn" onClick={() => p.navigate("/work")}>
              Alla arbeten <ChevronRight size={16} />
            </button>
          </div>
          <div className="task-list">
            {p.boot.work.length ? (
              p.boot.work.map((w: Row) => (
                <button
                  className="task"
                  key={w.id}
                  onClick={() => p.setDetail({ type: "work", row: w })}
                >
                  <span className={"task-icon " + w.priority}>
                    {w.kind === "inspection" ? (
                      <ShieldCheck size={19} />
                    ) : w.kind === "round" ? (
                      <RefreshCw size={19} />
                    ) : (
                      <Wrench size={19} />
                    )}
                  </span>
                  <div className="task-copy">
                    <strong>{w.title}</strong>
                    <small>
                      {w.asset_name} <span>· #{w.number}</span>
                    </small>
                  </div>
                  <div className="task-end">
                    <Badge value={w.status} />
                    <span
                      className={
                        w.due_date && w.due_date < dateNow ? "overdue" : ""
                      }
                    >
                      {day(w.due_date)}
                    </span>
                  </div>
                </button>
              ))
            ) : (
              <Empty
                action={
                  <button className="btn" onClick={() => p.openForm("work")}>
                    Skapa ett ärende
                  </button>
                }
              />
            )}
          </div>
        </section>
        <div className="overview-right">
          <section className="focus-card">
            <div className="eyebrow">PLANERA FRAMÅT</div>
            <h2>
              Ett samlat grepp
              <br />
              om underhållet.
            </h2>
            <p>
              Se kommande åtgärder, fördela kostnader och följ upp årets plan.
            </p>
            <button
              className="btn light"
              onClick={() => p.navigate("/maintenance")}
            >
              Öppna underhållsplan <ArrowUpRight size={16} />
            </button>
            <div className="focus-lines" aria-hidden="true">
              <span />
              <span />
              <span />
            </div>
          </section>
          <section className="panel">
            <div className="panel-heading">
              <h2>Snabbvägar</h2>
            </div>
            <div className="quick-links">
              {[
                {
                  label: "Planera en rond",
                  icon: RefreshCw,
                  type: "schedules",
                },
                {
                  label: "Lägg till fastighet",
                  icon: Building2,
                  type: "assets",
                },
                {
                  label: "Registrera underhåll",
                  icon: Wrench,
                  type: "maintenance",
                },
              ].map((l) => (
                <button key={l.label} onClick={() => p.openForm(l.type)}>
                  <l.icon size={18} />
                  {l.label}
                  <Plus size={16} />
                </button>
              ))}
            </div>
          </section>
        </div>
      </div>
      {budget && (
        <section className="panel budget-overview">
          <div className="panel-heading">
            <div>
              <h2>Underhållet de närmaste fem åren</h2>
              <p>Planerad kostnad inklusive kostnadsfaktor och index</p>
            </div>
            <div className="budget-head-total">
              <strong>{money(budget.totals.Budget)}</strong>
              <button
                className="text-btn"
                onClick={() => p.navigate("/maintenance")}
              >
                Se underlaget <ChevronRight size={15} />
              </button>
            </div>
          </div>
          <BudgetChart data={budget.totals["Per år"] || []} />
        </section>
      )}
    </>
  );
}
function WorkPage(p: any) {
  const [search, setSearch] = useState(""),
    [status, setStatus] = useState(""),
    [kind, setKind] = useState("");
  const rows = useRows(
    "work/?" + query({ org: p.org, q: search, status, kind }),
    p.tick,
    p.fail,
  );
  return (
    <>
      <Heading
        eyebrow="DRIFT & TILLSYN"
        title="Arbete"
        description="Från felanmälan till utförd och verifierad åtgärd."
      >
        <button className="btn primary" onClick={() => p.openForm("work")}>
          <Plus size={17} />
          Nytt ärende
        </button>
      </Heading>
      <div className="tabs">
        {[
          ["", "Alla arbeten"],
          ["issue", "Ärenden"],
          ["round", "Ronder"],
          ["inspection", "Besiktningar"],
        ].map(([v, t]) => (
          <button
            key={v}
            className={kind === v ? "selected" : ""}
            onClick={() => setKind(v)}
          >
            {t}
          </button>
        ))}
      </div>
      <section className="panel">
        <FilterBar search={search} onSearch={setSearch}>
          <select
            aria-label="Status"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="">Alla statusar</option>
            {Object.entries(stateNames)
              .slice(0, 6)
              .map(([v, n]) => (
                <option key={v} value={v}>
                  {String(n)}
                </option>
              ))}
          </select>
          <span className="result-count">{rows?.length ?? "…"} visade</span>
        </FilterBar>
        {rows ? (
          <DataTable
            rows={rows}
            onRow={(r) => p.setDetail({ type: "work", row: r })}
            columns={[
              {
                key: "title",
                label: "Arbete",
                render: (r) => (
                  <>
                    <strong>{r.title}</strong>
                    <small>
                      #{r.number} · {kindNames[r.kind]}
                    </small>
                  </>
                ),
              },
              { key: "asset_name", label: "Fastighet / objekt" },
              {
                key: "priority",
                label: "Prioritet",
                render: (r) => <Badge value={r.priority} />,
              },
              {
                key: "status",
                label: "Status",
                render: (r) => <Badge value={r.status} />,
              },
              { key: "assigned_name", label: "Utförare" },
              {
                key: "due_date",
                label: "Senast",
                render: (r) => (
                  <span
                    className={
                      r.due_date &&
                      r.due_date < dateNow &&
                      !["verified", "cancelled"].includes(r.status)
                        ? "overdue"
                        : ""
                    }
                  >
                    {day(r.due_date)}
                  </span>
                ),
              },
            ]}
          />
        ) : (
          <Loading />
        )}
      </section>
    </>
  );
}
function AssetsPage(p: any) {
  const [search, setSearch] = useState(""),
    [kind, setKind] = useState("property"),
    [selected, setSelected] = useState<Row | null>(null),
    [tab, setTab] = useState("overview");
  const rows = useRows(
    "assets/?" + query({ org: p.org, q: search, kind }),
    p.tick,
    p.fail,
  );
  useEffect(() => {setSelected(null);}, [p.org]);
  if(selected)return <PropertyWorkspace p={p} selected={selected} onSelect={setSelected} onBack={()=>setSelected(null)}/>;
  return (
    <>
      <Heading
        eyebrow="FASTIGHETSREGISTER"
        title="Fastigheter & objekt"
        description="Organisationens platser, byggnader och tekniska objekt."
      >
        <button className="btn primary" onClick={() => p.openForm("assets")}>
          <Plus size={17} />
          Lägg till fastighet
        </button>
      </Heading>
      <FilterBar search={search} onSearch={setSearch}>
        <select
          aria-label="Objekttyp"
          value={kind}
          onChange={(e) => setKind(e.target.value)}
        >
          <option value="">Alla typer</option>
          {choices([
            "property",
            "building",
            "land",
            "premises",
            "room",
            "object",
          ]).map(([v, n]) => (
            <option key={v} value={v}>
              {n}
            </option>
          ))}
        </select>
        <span className="result-count">{rows?.length ?? "…"} visade</span>
      </FilterBar>
      {!rows ? (
        <Loading />
      ) : !rows.length ? (
        <Empty
          action={
            <button
              className="btn primary"
              onClick={() => p.openForm("assets")}
            >
              Lägg till fastighet
            </button>
          }
        />
      ) : (
        <div className="asset-grid">
          {rows.map((r, i) => (
            <button
              key={r.id}
              className="asset-card"
              onClick={() => {
                setSelected(r);
                setTab("overview");
              }}
            >
              <div className={"asset-cover cover-" + (i % 4)}>
                <Building2 size={45} strokeWidth={1.15} />
                <span>{kindNames[r.kind]}</span>
              </div>
              <div className="asset-body">
                <div className="asset-title">
                  <h2>{r.name}</h2>
                  <ArrowUpRight size={19} />
                </div>
                <p>{r.address || "Adress saknas"}</p>
                <div className="asset-meta">
                  <span>{r.org_name}</span>
                  <span>
                    {r.public
                      ? "Felanmälan öppen"
                      : r.area
                        ? num(r.area) + " m²"
                        : "Internt objekt"}
                  </span>
                </div>
              </div>
            </button>
          ))}
        </div>
      )}
      <MoreRows rows={rows} />
    </>
  );
}
function BudgetPage(p: any) {
  const [years, setYears] = useState(10),
    [start, setStart] = useState(new Date().getFullYear()),
    [tab, setTab] = useState("plan"),
    [report, setReport] = useState<Row | null>(null),
    [scenario, setScenario] = useState<Row | null>(null);
  const rows = useRows("maintenance/?" + query({ org: p.org }), p.tick, p.fail),
    scenarios = useRows("scenarios/?" + query({ org: p.org }), p.tick, p.fail);
  useEffect(() => {
    if (p.boot.finance_orgs.length)
      api(
        "reports/?" +
          query({ type: "budget", org: p.org, years, start_year: start }),
      )
        .then(setReport)
        .catch(p.fail);
  }, [p.org, years, start, p.tick]);
  useEffect(() => {
    if (scenario && scenarios)
      setScenario(scenarios.find((s) => s.id === scenario.id) || null);
  }, [scenarios]);
  if (!p.boot.finance_orgs.length)
    return (
      <Empty
        title="Ekonomibehörighet krävs"
        text="Be din administratör om åtkomst till underhållsbudget och kostnader."
      />
    );
  return (
    <>
      <Heading
        eyebrow="LÅNGSIKTIG FÖRVALTNING"
        title="Underhåll & budget"
        description="Planera åtgärder, jämför scenarier och se vad kostnaderna bygger på."
      >
        <button className="btn" onClick={() => p.openForm("scenarios")}>
          <Copy size={16} />
          Nytt scenario
        </button>
        <button
          className="btn primary"
          onClick={() => p.openForm("maintenance")}
        >
          <Plus size={17} />
          Ny åtgärd
        </button>
      </Heading>
      <div className="tabs">
        <button
          className={tab === "plan" ? "selected" : ""}
          onClick={() => setTab("plan")}
        >
          Underhållsplan
        </button>
        <button
          className={tab === "scenarios" ? "selected" : ""}
          onClick={() => setTab("scenarios")}
        >
          Scenarier & budgetversioner
        </button>
        <button className={tab === "compare" ? "selected" : ""} onClick={()=>setTab("compare")}>Jämför versioner</button>
      </div>
      {tab === "compare" ? <ScenarioComparison p={p} scenarios={scenarios} /> : tab === "plan" ? (
        <>
          <div className="budget-controls">
            <label>
              Från år{" "}
              <input
                type="number"
                min="1900"
                max="2200"
                value={start}
                onChange={(e) => setStart(Number(e.target.value))}
              />
            </label>
            <div className="segmented">
              {[1, 5, 10, 30].map((y) => (
                <button
                  className={years === y ? "selected" : ""}
                  onClick={() => setYears(y)}
                  key={y}
                >
                  {y} år
                </button>
              ))}
            </div>
            <a
              className="btn"
              href={
                "/api/v1/reports/?" +
                query({
                  type: "budget",
                  org: p.org,
                  years,
                  start_year: start,
                  format_file: "xlsx",
                })
              }
            >
              <Download size={16} />
              Excel
            </a>
          </div>
          <div className="budget-summary">
            <div>
              <span>
                Planerad budget · {start}–{start + years - 1}
              </span>
              <strong>{report ? money(report.totals.Budget) : "…"}</strong>
            </div>
            <div>
              <span>Registrerat utfall i perioden</span>
              <strong>{report ? money(report.totals.Utfall) : "…"}</strong>
            </div>
            <div>
              <span>Åtgärder i grundplanen</span>
              <strong>{rows?.length ?? "…"}</strong>
            </div>
          </div>
          <section className="panel">
            <div className="panel-heading">
              <h2>Kostnader över tid</h2>
              <span className="legend">
                <i />
                Planerad budget
              </span>
            </div>
            {report ? (
              <BudgetChart data={report.totals["Per år"] || []} />
            ) : (
              <Loading />
            )}
          </section>
          <section className="panel space-top">
            <div className="panel-heading">
              <div>
                <h2>Planerade åtgärder</h2>
                <p>
                  Klicka på en åtgärd för att se mängd, pris och finansiering.
                </p>
              </div>
            </div>
            {rows ? (
              <DataTable
                rows={rows}
                onRow={(r) => p.openForm("maintenance", r)}
                columns={[
                  {
                    key: "title",
                    label: "Åtgärd",
                    render: (r) => (
                      <>
                        <strong>{r.title}</strong>
                        <small>{r.category}</small>
                      </>
                    ),
                  },
                  { key: "asset_name", label: "Objekt" },
                  { key: "year", label: "År" },
                  {
                    key: "budget",
                    label: "Budget",
                    render: (r) => money(r.budget),
                  },
                  {
                    key: "funding_possible",
                    label: "Möjlig finansiering",
                    render: (r) => money(r.funding_possible),
                  },
                  {
                    key: "funding_granted",
                    label: "Beviljat",
                    render: (r) => money(r.funding_granted),
                  },
                  {
                    key: "order",
                    label: "Arbetsorder",
                    render: (r) =>
                      r.work ? (
                        <span className="subtle">Kopplad</span>
                      ) : (
                        <button
                          className="text-btn"
                          onClick={() =>
                            p.write("maintenance/" + r.id + "/order/", {
                              version: r.version,
                            })
                          }
                        >
                          Skapa order
                        </button>
                      ),
                  },
                ]}
              />
            ) : (
              <Loading />
            )}
          </section>
        </>
      ) : (
        <>
          <section className="panel">
            <DataTable
              rows={scenarios || []}
              onRow={setScenario}
              columns={[
                { key: "name", label: "Budgetversion" },
                {
                  key: "state",
                  label: "Status",
                  render: (r) => <Badge value={r.state} />,
                },
                { key: "start_year", label: "Från år" },
                { key: "years", label: "Antal år" },
                {
                  key: "sum",
                  label: "Summa",
                  render: (r) =>
                    money(
                      r.lines.reduce(
                        (a: number, l: Row) => a + Number(l.Budget),
                        0,
                      ),
                    ),
                },
              ]}
            />
          </section>
          {scenario && (
            <section className="panel space-top">
              <div className="panel-heading">
                <div>
                  <h2>{scenario.name}</h2>
                  <p>
                    {scenario.state === "published"
                      ? "Fastställd version. Underlaget är låst."
                      : "Ändra år i scenariot utan att ändra grundplanen."}
                  </p>
                </div>
                {scenario.state === "draft" && (
                  <button
                    className="btn primary"
                    onClick={() =>
                      p.write("scenarios/" + scenario.id + "/publish/", {
                        version: scenario.version,
                      })
                    }
                  >
                    <Lock size={15} />
                    Fastställ budget
                  </button>
                )}
              </div>
              <div className="scenario-compare">
                <span>
                  Scenario:{" "}
                  <strong>
                    {money(
                      scenario.lines.reduce(
                        (s: number, l: Row) => s + Number(l.Budget),
                        0,
                      ),
                    )}
                  </strong>
                </span>
                <span>
                  Aktuellt rapporturval:{" "}
                  <strong>{report ? money(report.totals.Budget) : "—"}</strong>
                </span>
              </div>
              <DataTable
                rows={scenario.lines}
                columns={[
                  { key: "Åtgärd", label: "Åtgärd" },
                  { key: "Objekt", label: "Objekt" },
                  {
                    key: "År",
                    label: "År",
                    render: (r) =>
                      scenario.state === "published" ? (
                        r["År"]
                      ) : (
                        <input
                          className="year-input"
                          type="number"
                          aria-label={"År för " + r["Åtgärd"]}
                          min={scenario.start_year}
                          max={scenario.start_year + scenario.years - 1}
                          defaultValue={r["År"]}
                          key={
                            scenario.version + String(scenario.lines.indexOf(r))
                          }
                          onBlur={(e) => {
                            if (Number(e.target.value) !== r["År"])
                              p.write("scenarios/" + scenario.id + "/revise/", {
                                version: scenario.version,
                                line: scenario.lines.indexOf(r),
                                year: Number(e.target.value),
                              });
                          }}
                        />
                      ),
                  },
                  {
                    key: "Budget",
                    label: "Budget",
                    render: (r) => money(r.Budget),
                  },
                ]}
              />
            </section>
          )}
        </>
      )}
    </>
  );
}
function ReportsPage(p: any) {
  const [type, setType] = useState("work"),
    [report, setReport] = useState<Row | null>(null),
    [groupBy, setGroupBy] = useState(""),
    [measure, setMeasure] = useState("Antal"),
    [from, setFrom] = useState(""),
    [to, setTo] = useState(""),
    [columns, setColumns] = useState<string[]>([]),
    [showFields, setShowFields] = useState(false),
    [tab, setTab] = useState("live");
  const templates = useRows(
      "templates/?" + query({ org: p.org }),
      p.tick,
      p.fail,
    ),
    snapshots = useRows("snapshots/?" + query({ org: p.org }), p.tick, p.fail);
  const params = {
    type,
    group_by: groupBy, measure,
    org: p.org,
    ...(["budget", "maintenance", "assets"].includes(type) ? {} : { from, to }),
  };
  useEffect(() => {
    setReport(null);
    let active=true;
    api("reports/?" + query(params)).then(r=>{if(active)setReport(r);}).catch(e=>{if(active)p.fail(e);});
    return()=>{active=false;};
  }, [type, p.org, from, to, groupBy, measure, p.tick]);
  const exportLink = (fmt: string) =>
    "/api/v1/reports/?" +
    query({ ...params, columns: columns.join(","), format_file: fmt });
  return (
    <>
      <Heading
        eyebrow="INSIKT & BESLUTSUNDERLAG"
        title="Rapporter"
        description="Från sammanställning till enskild post. Samma urval i vyn och exporten."
      >
        <button
          className="btn"
          onClick={() =>
            p.setModal({
              title: "Spara rapportmall",
              endpoint: "templates/",
              fields: [
                p.fields.org,
                { key: "name", label: "Namn", required: true },
              ],
              initial: { org: p.org || p.boot.organizations[0]?.id },
              transform: (d: Row) => ({
                ...d,
                config: { type, filters: { ...params, columns } },
              }),
            })
          }
        >
          <Copy size={16} />
          Spara mall
        </button>
        <button
          className="btn primary"
          onClick={() =>
            p.setModal({
              title: "Arkivera beslutsrapport",
              endpoint: "reports/",
              fields: [
                {
                  key: "title",
                  label: "Rapportnamn",
                  required: true,
                  default: reportNames[type],
                },
              ],
              transform: (d: Row) => ({
                ...d,
                type,
                filters: {
                  ...params,
                  columns: columns.length ? columns : undefined,
                },
              }),
            })
          }
        >
          <Archive size={16} />
          Arkivera rapport
        </button>
      </Heading>
      <div className="tabs">
        <button
          className={tab === "live" ? "selected" : ""}
          onClick={() => setTab("live")}
        >
          Rapportbyggare
        </button>
        <button
          className={tab === "saved" ? "selected" : ""}
          onClick={() => setTab("saved")}
        >
          Mallar & arkiv
        </button>
        <button
          className={tab === "scheduled" ? "selected" : ""}
          onClick={() => setTab("scheduled")}
        >
          Schemalagda rapporter
        </button>
      </div>
      {tab === "scheduled" ? (
        <ModulePage
          {...p}
          section="subscriptions"
          heading="Schemalagda rapporter"
          embedded
        />
      ) : tab === "saved" ? (
        <div className="two-column">
          <section className="panel">
            <div className="panel-heading">
              <h2>Sparade mallar</h2>
            </div>
            <DataTable
              rows={templates || []}
              columns={[
                { key: "name", label: "Mall" },
                {
                  key: "open",
                  label: "",
                  render: (r) => (
                    <button
                      className="text-btn"
                      onClick={() => {
                        setType(r.config.type);
                        setGroupBy(r.config.filters?.group_by || "");
                        setMeasure(r.config.filters?.measure || "Antal");
                        setColumns(r.config.filters?.columns || []);
                        if (r.config.filters?.org)
                          p.setOrg(r.config.filters.org);
                        setFrom(r.config.filters?.from || "");
                        setTo(r.config.filters?.to || "");
                        setTab("live");
                      }}
                    >
                      Öppna
                    </button>
                  ),
                },
              ]}
            />
          </section>
          <section className="panel">
            <div className="panel-heading">
              <h2>Arkiverade underlag</h2>
            </div>
            <DataTable
              rows={snapshots || []}
              columns={[
                { key: "title", label: "Rapport" },
                {
                  key: "created_at",
                  label: "Skapad",
                  render: (r) => day(r.created_at),
                },
                {
                  key: "download",
                  label: "",
                  render: (r) => (
                    <a
                      className="text-btn"
                      href={
                        "/api/v1/snapshots/" + r.id + "/export/?format_file=pdf"
                      }
                    >
                      PDF <Download size={15} />
                    </a>
                  ),
                },
              ]}
            />
          </section>
        </div>
      ) : (
        <div className="report-layout">
          <aside className="report-menu">
            {Object.entries(reportNames).map(([v, n]) => (
              <button
                key={v}
                className={type === v ? "selected" : ""}
                onClick={() => {
                  setType(v);setGroupBy("");setMeasure("Antal");
                  setColumns([]);
                }}
              >
                <FileText size={17} />
                {String(n)}
                {type === v && <ChevronRight size={16} />}
              </button>
            ))}
          </aside>
          <div>
            <section className="panel">
              <div className="panel-heading">
                <h2>{reportNames[type]}</h2>
                <span className="subtle">{report?.count ?? "…"} poster</span>
              </div>
              <div className="report-controls">
                <label>Gruppera efter<select value={groupBy} onChange={e=>{setGroupBy(e.target.value);setColumns([]);}}><option value="">Enskilda poster</option>{(groupChoices[type]||[]).map((g:string)=><option key={g} value={g}>{g}</option>)}</select></label>
                {groupBy&&<label>Mått<select value={measure} onChange={e=>setMeasure(e.target.value)}>{measureChoices(type).map(m=><option key={m} value={m}>{m}</option>)}</select></label>}

                {!["budget", "maintenance", "assets"].includes(type) && (
                  <>
                    <label>
                      Från datum
                      <input
                        type="date"
                        value={from}
                        onChange={(e) => setFrom(e.target.value)}
                      />
                    </label>
                    <label>
                      Till datum
                      <input
                        type="date"
                        value={to}
                        onChange={(e) => setTo(e.target.value)}
                      />
                    </label>
                  </>
                )}
                <button
                  className="btn small"
                  onClick={() => setShowFields(!showFields)}
                >
                  <Settings size={15} />
                  Kolumner
                </button>
                <div className="export-buttons">
                  {["pdf", "xlsx", "csv"].map((f) => (
                    <a key={f} className="btn small" href={exportLink(f)}>
                      <Download size={14} />
                      {f.toUpperCase()}
                    </a>
                  ))}
                </div>
              </div>
              {showFields && (
                <div className="column-picker">
                  {Object.keys(report?.rows[0] || {})
                    .filter((c) => c !== "id")
                    .map((c) => (
                      <label key={c}>
                        <input
                          type="checkbox"
                          checked={!columns.length || columns.includes(c)}
                          onChange={(e) => {
                            const all = Object.keys(
                              report?.rows[0] || {},
                            ).filter((x) => x !== "id");
                            setColumns(
                              e.target.checked
                                ? [...columns, c]
                                : (columns.length ? columns : all).filter(
                                    (x) => x !== c,
                                  ),
                            );
                          }}
                        />
                        {c}
                      </label>
                    ))}
                </div>
              )}
              {report ? (
                <>
                  <div className="report-definition">
                    <ShieldCheck size={18} />
                    <p>
                      {report.definitions}
                      <small>
                        Beräkning {report.calculation_version} · Skapad{" "}
                        {new Date(report.generated_at).toLocaleString("sv-SE")}
                      </small>
                    </p>
                  </div>
                  <GroupDetails report={report} p={p} />
                  {!report.analysis && report.totals["Per år"] && (
                    <BudgetChart data={report.totals["Per år"]} />
                  )}
                  <DataTable
                    rows={report.rows}
                    columns={Object.keys(report.rows[0] || {})
                      .filter(
                        (c) =>
                          c !== "id" &&
                          (!columns.length || columns.includes(c)),
                      )
                      .map((c) => ({
                        key: c,
                        label: c,
                        render: (r) =>
                          r[c] === null ? (
                            <span className="subtle">Saknas</span>
                          ) : (
                            String(r[c])
                          ),
                      }))}
                    onRow={
                      !report.analysis && ["work", "overdue", "rounds", "inspections"].includes(
                        type,
                      )
                        ? (r) =>
                            api("work/" + r.id + "/")
                              .then((w) =>
                                p.setDetail({ type: "work", row: w }),
                              )
                              .catch(p.fail)
                        : undefined
                    }
                  />
                </>
              ) : (
                <Loading />
              )}
            </section>
          </div>
        </div>
      )}
    </>
  );
}
function CalendarPage(p: any) {
  const [month, setMonth] = useState(new Date().toISOString().slice(0, 7));
  const rows = useRows("work/?" + query({ org: p.org }), p.tick, p.fail);
  const start = new Date(month + "-01T12:00:00"),
    days = new Date(start.getFullYear(), start.getMonth() + 1, 0).getDate(),
    offset = (start.getDay() + 6) % 7;
  return (
    <>
      <Heading
        eyebrow="PLANERING"
        title="Kalender"
        description="Arbeten, ronder och besiktningar efter förfallodatum."
      >
        <input
          aria-label="Månad"
          type="month"
          value={month}
          onChange={(e) => setMonth(e.target.value)}
        />
        <button className="btn primary" onClick={() => p.openForm("schedules")}>
          <Plus size={16} />
          Planera återkommande
        </button>
      </Heading>
      <section className="panel calendar">
        <div className="calendar-week">
          {["Mån", "Tis", "Ons", "Tor", "Fre", "Lör", "Sön"].map((x) => (
            <strong key={x}>{x}</strong>
          ))}
        </div>
        <div className="calendar-grid">
          {Array.from({ length: offset }, (_, i) => (
            <div className="calendar-cell muted" key={"blank" + i} />
          ))}
          {Array.from({ length: days }, (_, i) => {
            const d = month + "-" + String(i + 1).padStart(2, "0");
            return (
              <div
                key={d}
                className={"calendar-cell " + (d === dateNow ? "is-today" : "")}
              >
                <span>{i + 1}</span>
                {rows
                  ?.filter((r) => r.due_date === d)
                  .map((r) => (
                    <button
                      key={r.id}
                      className={"calendar-event " + r.kind}
                      onClick={() => p.setDetail({ type: "work", row: r })}
                    >
                      {r.title}
                    </button>
                  ))}
              </div>
            );
          })}
        </div>
      </section>
    </>
  );
}
function ModulePage(p: any) {
  const { section, heading } = p;
  const [tab, setTab] = useState(
      section === "energy" ? "meters" : section === "keys" ? "keys" : "main",
    ),
    [search, setSearch] = useState("");
  let resource = section;
  let kind = "";
  if (section === "energy") resource = tab;
  if (section === "keys") resource = tab;
  if (section === "contracts") {
    resource = "registry";
    kind = "contract";
  }
  if (section === "registry") resource = "registry";
  const rows = useRows(
    resource + "/?" + query({ org: p.org, q: search, kind }),
    p.tick,
    p.fail,
  );
  if (section === "documents")
    return (
      <>
        <Heading
          eyebrow="GEMENSAM DOKUMENTATION"
          title="Dokument"
          description="Privata bilagor med kontrollsumma och versionshistorik."
        />
        <Documents p={p} />
      </>
    );
  let columns: any[] = [];
  let form = resource;
  if (resource === "schedules")
    columns = [
      { key: "title", label: "Återkommande arbete" },
      { key: "asset_name", label: "Objekt" },
      { key: "kind", label: "Typ", render: (r: Row) => kindNames[r.kind] },
      {
        key: "next_date",
        label: "Nästa gång",
        render: (r: Row) => day(r.next_date),
      },
      {
        key: "interval",
        label: "Intervall",
        render: (r: Row) =>
          r.interval +
          " " +
          ({ day: "dag", week: "vecka", month: "månad", year: "år" } as Row)[
            r.unit
          ],
      },
      {
        key: "generate",
        label: "",
        render: (r: Row) => (
          <button
            className="text-btn"
            onClick={() => p.write("schedules/" + r.id + "/generate/", {})}
          >
            Skapa förfallna arbeten
          </button>
        ),
      },
    ];
  if (resource === "registry")
    columns = [
      { key: "title", label: "Namn" },
      { key: "kind", label: "Typ", render: (r: Row) => kindNames[r.kind] },
      { key: "asset_name", label: "Objekt" },
      { key: "responsible", label: "Ansvarig" },
      {
        key: "due_date",
        label: "Nästa datum",
        render: (r: Row) => day(r.due_date),
      },
    ];
  if (resource === "meters")
    columns = [
      { key: "name", label: "Mätare" },
      { key: "asset_name", label: "Objekt" },
      {
        key: "medium",
        label: "Medium",
        render: (r: Row) => kindNames[r.medium],
      },
      { key: "serial", label: "Serienummer" },
      { key: "unit", label: "Enhet" },
    ];
  if (resource === "readings")
    columns = [
      { key: "date", label: "Avläsningsdatum" },
      {
        key: "meter",
        label: "Mätare",
        render: (r: Row) => r.meter.slice(0, 8),
      },
      { key: "value", label: "Mätarställning" },
      {
        key: "replacement",
        label: "Mätarbyte",
        render: (r: Row) => (r.replacement ? "Ja" : "Nej"),
      },
    ];
  if (resource === "keys")
    columns = [
      { key: "name", label: "Nyckel" },
      { key: "system", label: "System" },
      { key: "serial", label: "Nummer" },
      { key: "asset_name", label: "Objekt" },
      {
        key: "condition",
        label: "Skick",
        render: (r: Row) =>
          (({ ok: "Hel", lost: "Borttappad", broken: "Trasig" }) as Row)[
            r.condition
          ],
      },
    ];
  if (resource === "loans")
    columns = [
      { key: "borrower", label: "Låntagare" },
      {
        key: "due_date",
        label: "Åter senast",
        render: (r: Row) => day(r.due_date),
      },
      {
        key: "returned_at",
        label: "Status",
        render: (r: Row) => (r.returned_at ? "Återlämnad" : "Utlånad"),
      },
      {
        key: "return",
        label: "",
        render: (r: Row) =>
          !r.returned_at && (
            <button
              className="text-btn"
              onClick={() =>
                p.write("loans/" + r.id + "/return_key/", {
                  version: r.version,
                })
              }
            >
              Registrera återlämning
            </button>
          ),
      },
    ];
  if (resource === "subscriptions")
    columns = [
      { key: "name", label: "Utskick" },
      {
        key: "report_type",
        label: "Rapport",
        render: (r: Row) => reportNames[r.report_type],
      },
      { key: "next_date", label: "Nästa datum" },
      { key: "interval_days", label: "Dagar mellan utskick" },
    ];
  return (
    <>
      {!p.embedded && (
        <Heading
          eyebrow="VERKSAMHET"
          title={heading}
          description={
            section === "schedules"
              ? "Återkommande kontroller med checklistor och spårbar kvittering."
              : undefined
          }
        >
          <button
            className="btn primary"
            onClick={() => p.openForm(form, undefined, kind ? { kind } : {})}
          >
            <Plus size={17} />
            Lägg till
          </button>
        </Heading>
      )}
      {p.embedded && (
        <button
          className="btn primary space-bottom"
          onClick={() => p.openForm(form)}
        >
          <Plus size={16} />
          Nytt utskick
        </button>
      )}
      {["energy", "keys"].includes(section) && (
        <div className="tabs">
          {(section === "energy"
            ? [
                ["meters", "Mätare"],
                ["readings", "Avläsningar"],
              ]
            : [
                ["keys", "Nyckelregister"],
                ["loans", "Utlåning"],
              ]
          ).map(([v, t]) => (
            <button
              key={v}
              className={tab === v ? "selected" : ""}
              onClick={() => setTab(v)}
            >
              {t}
            </button>
          ))}
        </div>
      )}
      <section className="panel">
        <FilterBar search={search} onSearch={setSearch} />
        {rows ? (
          <DataTable
            rows={rows}
            columns={columns}
            onRow={
              ["readings", "loans"].includes(resource)
                ? undefined
                : (r) => p.openForm(form, r)
            }
          />
        ) : (
          <Loading />
        )}
      </section>
    </>
  );
}
function Documents({ p, asset }: { p: any; asset?: string }) {
  const rows = useRows(
    "documents/?" + query({ org: p.org, asset }),
    p.tick,
    p.fail,
  );
  const upload = (revision?: Row) =>
    p.setModal({
      title: revision ? "Ny dokumentversion" : "Ladda upp dokument",
      endpoint: "documents/",
      fields: [
        { ...p.fields.asset, default: asset },
        { key: "title", label: "Dokumentnamn", required: true },
        {
          key: "file",
          label: "Fil · PDF, JPEG eller PNG",
          type: "file",
          required: true,
        },
        {
          key: "shared_contractor",
          label: "Dela med tilldelad entreprenör (kräver arbetsorder)",
          type: "checkbox",
        },
        { key: "work", label: "Arbetsorder", type: "remote:work", options: [] },
      ],
      initial: revision
        ? {
            asset: revision.asset,
            title: revision.title,
            revision_of: revision.id,
          }
        : undefined,
    });
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>Dokumentbibliotek</h2>
        <button className="btn primary" onClick={() => upload()}>
          <Plus size={16} />
          Ladda upp
        </button>
      </div>
      {rows ? (
        <DataTable
          rows={rows}
          columns={[
            {
              key: "title",
              label: "Dokument",
              render: (r) => (
                <span className="inline-icon">
                  <FileText size={18} />
                  {r.title}
                </span>
              ),
            },
            { key: "asset_name", label: "Objekt" },
            {
              key: "size",
              label: "Storlek",
              render: (r) => num(Math.ceil(r.size / 1024)) + " kB",
            },
            {
              key: "created_at",
              label: "Uppladdad",
              render: (r) => day(r.created_at),
            },
            {
              key: "revision",
              label: "Version",
              render: (r) => (r.revision_of ? "Ny revision" : "Original"),
            },
            {
              key: "actions",
              label: "",
              render: (r) => (
                <div className="inline-actions">
                  <a
                    className="text-btn"
                    href={"/api/v1/documents/" + r.id + "/download/"}
                  >
                    <Download size={16} />
                    Hämta
                  </a>
                  <button className="text-btn" onClick={() => upload(r)}>
                    Ny version
                  </button>
                </div>
              ),
            },
          ]}
        />
      ) : (
        <Loading />
      )}
    </section>
  );
}
function AdminPage(p: any) {
  const audit = useRows("audit/", p.tick, p.fail);
  return (
    <>
      <Heading
        eyebrow="ORGANISATION & ÅTKOMST"
        title="Administration"
        description="Behörigheter följer uttryckliga tilldelningar inom organisationshierarkin."
      >
        <button className="btn" onClick={() => p.openForm("users")}>
          <Users size={16} />
          Ny användare
        </button>
        <button
          className="btn primary"
          onClick={() => p.openForm("organizations")}
        >
          <Plus size={16} />
          Ny enhet
        </button>
      </Heading>
      {(p.boot.user.superuser || p.boot.demo) && <AISettingsPanel demo={!p.boot.user.superuser} />}
      <div className="two-column">
        <section className="panel">
          <div className="panel-heading">
            <h2>Organisation</h2>
            <Layers size={20} />
          </div>
          {p.boot.user.superuser && (
            <p className="padded">
              <a className="text-btn" href="/api/v1/full-export/">
                Hämta fullständig dataexport (ZIP)
              </a>
            </p>
          )}
          <div className="org-tree">
            {p.boot.organizations.map((o: Row) => {
              const level = [
                "church",
                "diocese",
                "pastorate",
                "parish",
              ].indexOf(o.kind);
              return (
                <button
                  key={o.id}
                  style={{ paddingLeft: 24 + level * 23 }}
                  onClick={() => p.openForm("organizations", o)}
                >
                  <span className={"org-node level-" + level}>
                    <Building2 size={17} />
                  </span>
                  <span>
                    <strong>{o.name}</strong>
                    <small>{kindNames[o.kind]}</small>
                  </span>
                  <ChevronRight size={16} />
                </button>
              );
            })}
          </div>
        </section>
        <section className="panel padded">
          <div className="panel-heading flush">
            <h2>Dina åtkomster</h2>
            <ShieldCheck size={20} />
          </div>
          <p className="subtle">
            Rapporter och exporter använder samma behörigheter som övriga
            tjänsten.
          </p>
          {p.boot.grants.map((g: Row, i: number) => (
            <div className="grant" key={i}>
              <strong>
                {p.boot.organizations.find((o: Row) => o.id === g.org_id)
                  ?.name || g.org_id}
              </strong>
              <span>
                {
                  (
                    {
                      admin: "Administratör",
                      manager: "Förvaltare",
                      worker: "Medarbetare",
                      reader: "Läsare",
                      contractor: "Entreprenör",
                    } as Row
                  )[g.role]
                }
                {g.descendants ? " · inklusive underenheter" : ""}
                {g.finance ? " · ekonomi" : ""}
              </span>
            </div>
          ))}
          <div className="info-box">
            <Lock size={19} />
            <div>
              <strong>
                {p.boot.demo ? "Avskild demomiljö" : "Skyddad åtkomst"}
              </strong>
              <p>
                {p.boot.demo
                  ? "Flerfaktorsinloggning är avstängd endast i den lokala demonstrationen."
                  : "Inloggning och serverbehörigheter styr åtkomsten."}
              </p>
            </div>
          </div>
        </section>
      </div>
      <section className="panel space-top">
        <div className="panel-heading">
          <h2>Ändringshistorik</h2>
          <span className="subtle">Senaste 100 händelserna</span>
        </div>
        <DataTable
          rows={audit || []}
          columns={[
            {
              key: "created_at",
              label: "Tid",
              render: (r) => new Date(r.created_at).toLocaleString("sv-SE"),
            },
            { key: "actor__username", label: "Användare" },
            { key: "entity", label: "Posttyp" },
            { key: "action", label: "Händelse" },
            {
              key: "entity_id",
              label: "Post",
              render: (r) => <code>{r.entity_id.slice(0, 12)}</code>,
            },
          ]}
        />
      </section>
      <AccessPanel boot={p.boot} onChanged={p.refresh} />

    </>
  );
}
function WorkDrawer(p: any) {
  const [row, setRow] = useState(p.row),
    [comments, setComments] = useState<Row[]>([]),
    [text, setText] = useState(""),
    [visibility, setVisibility] = useState("internal"),
    [busy, setBusy] = useState(false);
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
    return () => ref.current?.close();
  }, []);
  useEffect(() => {
    api("work/" + p.row.id + "/")
      .then(setRow)
      .catch(p.fail);
    list("work/" + p.row.id + "/comments/")
      .then(setComments)
      .catch(p.fail);
  }, [p.row.id, p.tick]);
  const edit = p.boot.edit_orgs.includes(row.org),
    manage = p.boot.manage_orgs.includes(row.org);
  const transitions: Row = {
    new: ["planned", "in_progress", "cancelled"],
    planned: ["in_progress", "cancelled"],
    in_progress: ["completed", "cancelled"],
    completed: ["verified", "in_progress"],
    verified: ["in_progress"],
    cancelled: ["planned"],
  };
  const actions: Row = {
    planned: "Planera",
    in_progress:
      row.status === "new" || row.status === "planned"
        ? "Påbörja"
        : "Återöppna",
    completed: "Kvittera arbete",
    verified: "Verifiera",
    cancelled: "Avbryt",
  };
  return (
    <dialog ref={ref} className="drawer" onCancel={p.onClose}>
      <div className="drawer-top">
        <span>ARBETSORDER #{row.number}</span>
        <button
          className="icon-btn"
          aria-label="Stäng arbetsorder"
          onClick={p.onClose}
        >
          <X />
        </button>
      </div>
      <div className="drawer-body">
        <div className="inline-actions">
          <Badge value={row.status} />
          <Badge value={row.priority} />
        </div>
        <h2>{row.title}</h2>
        <p className="subtle">{row.asset_name}</p>
        <dl>
          <div>
            <dt>Ansvarig utförare</dt>
            <dd>{row.assigned_name || "Inte tilldelad"}</dd>
          </div>
          <div>
            <dt>Förfallodatum</dt>
            <dd>{day(row.due_date)}</dd>
          </div>
          <div>
            <dt>Typ</dt>
            <dd>{kindNames[row.kind]}</dd>
          </div>
        </dl>
        <p className="description">{row.description || "Ingen beskrivning."}</p>
        {edit && !["verified", "cancelled"].includes(row.status) && (
          <button className="btn small" onClick={() => p.openForm("work", row)}>
            Redigera uppgifter
          </button>
        )}
        {row.checklist.length > 0 && (
          <section className="drawer-section">
            <h3>Kontrollpunkter</h3>
            {row.checklist.map((item: string, i: number) => (
              <div className="checklist-item" key={i}>
                <label>
                  {item}
                  <select
                    aria-label={item}
                    value={row.checklist_results[String(i)] || ""}
                    onChange={async (e) => {
                      await p.write(
                        "work/" + row.id + "/",
                        {
                          version: row.version,
                          checklist_results: {
                            ...row.checklist_results,
                            [String(i)]: e.target.value,
                          },
                        },
                        "PATCH",
                      );
                    }}
                  >
                    <option value="">Välj svar</option>
                    <option value="ok">Godkänd</option>
                    <option value="deviation">Avvikelse</option>
                    <option value="na">Ej tillämplig</option>
                  </select>
                </label>
                {row.checklist_results[String(i)] === "deviation" && (
                  <button
                    className="text-btn"
                    onClick={() =>
                      p.write("work/" + row.id + "/deviation/", { index: i })
                    }
                  >
                    Skapa åtgärdsärende
                  </button>
                )}
              </div>
            ))}
          </section>
        )}
        <section className="drawer-section">
          <h3>Nästa steg</h3>
          <div className="transition-actions">
            {(transitions[row.status] || [])
              .filter(
                (s: string) => !["verified", "cancelled"].includes(s) || manage,
              )
              .filter(
                () => !["verified", "cancelled"].includes(row.status) || manage,
              )
              .map((s: string) => (
                <button
                  disabled={busy}
                  className={"btn " + (s === "cancelled" ? "" : "primary")}
                  key={s}
                  onClick={async () => {
                    setBusy(true);
                    await p.write("work/" + row.id + "/transition/", {
                      version: row.version,
                      status: s,
                    });
                    setBusy(false);
                  }}
                >
                  {actions[s]}
                </button>
              ))}
          </div>
          <small className="subtle">
            Version {row.version} · Senast ändrad{" "}
            {new Date(row.updated_at).toLocaleString("sv-SE")}
          </small>
        </section>
        {p.boot.finance_orgs.includes(row.org) && (
          <section className="drawer-section">
            <h3>Tid, material & kostnader</h3>
            <button
              className="btn small"
              onClick={() =>
                p.openForm("costs", undefined, { org: row.org, work: row.id })
              }
            >
              <Plus size={16} />
              Registrera kostnad
            </button>
            <CostList work={row.id} tick={p.tick} fail={p.fail} />
          </section>
        )}
        <section className="drawer-section">
          <h3>Kommentarer & återkoppling</h3>
          <div className="comments">
            {comments.map((c) => (
              <article key={c.id}>
                <div>
                  <strong>{c.author_name}</strong>
                  <span>
                    {
                      (
                        {
                          internal: "Internt",
                          contractor: "Uppdrag",
                          public: "Till anmälare",
                        } as Row
                      )[c.visibility]
                    }
                  </span>
                </div>
                <p>{c.text}</p>
                <small>{new Date(c.created_at).toLocaleString("sv-SE")}</small>
              </article>
            ))}
          </div>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              if (!text.trim()) return;
              const result = await p.write("work/" + row.id + "/comments/", {
                text,
                visibility: edit ? visibility : "contractor",
              });
              if (result) setText("");
            }}
          >
            <label className="field">
              <span>Ny kommentar</span>
              <textarea
                required
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Skriv en uppdatering…"
              />
            </label>
            <div className="comment-actions">
              {edit && (
                <select
                  aria-label="Synlighet"
                  value={visibility}
                  onChange={(e) => setVisibility(e.target.value)}
                >
                  <option value="internal">Endast internt</option>
                  <option value="contractor">Dela med entreprenör</option>
                  <option value="public">Återkoppling till anmälare</option>
                </select>
              )}
              <button className="btn primary" type="submit">
                <Send size={15} />
                Spara kommentar
              </button>
            </div>
          </form>
        </section>
      </div>
    </dialog>
  );
}
function CostList({
  work,
  tick,
  fail,
}: {
  work: string;
  tick: number;
  fail: (e: any) => void;
}) {
  const rows = useRows("costs/?work=" + work, tick, fail);
  return (
    <div>
      {rows?.map((r) => (
        <div className="cost-line" key={r.id}>
          <span>{r.description}</span>
          <strong>{money(r.total)}</strong>
        </div>
      ))}
    </div>
  );
}
function formDefinitions(type: string, boot: Row, fields: any): ModalConfig {
  const { org, asset } = fields;
  const name = (label = "Namn"): Field => ({
    key: "name",
    label,
    required: true,
  });
  const title: Field = { key: "title", label: "Rubrik", required: true };
  const description: Field = {
    key: "description",
    label: "Beskrivning",
    type: "textarea",
  };
  const date: Field = { key: "due_date", label: "Senast datum", type: "date" };
  const moneyField = (key: string, label: string, def = 0): Field => ({
    key,
    label,
    type: "number",
    min: 0,
    default: def,
  });
  const user: Field = {
    key: "assigned_to",
    label: "Utförare",
    type: "remote:users",
    options: [],
  };
  const check: Field = {
    key: "checklist",
    label: "Kontrollpunkter · en per rad",
    type: "lines",
  };
  const defs: Record<string, ModalConfig> = {
    assets: {
      title: "Fastighet eller objekt",
      endpoint: "assets/",
      fields: [
        org,
        name(),
        {
          key: "kind",
          label: "Typ",
          type: "select",
          options: choices([
            "property",
            "building",
            "land",
            "premises",
            "room",
            "object",
          ]),
          default: "property",
          required: true,
        },
        {
          key: "parent",
          label: "Överordnat objekt",
          type: "asset",
          options: assetOptions(boot),
        },
        { key: "address", label: "Adress" },
        { key: "designation", label: "Beteckning" },
        { key: "area", label: "Area, m²", type: "number", min: 0 },
        { key: "owner", label: "Ägare" },
        { key: "manager", label: "Förvaltningsansvarig" },
        description,
        {
          key: "public",
          label: "Visa platsen i publik felanmälan",
          type: "checkbox",
        },
      ],
    },
    work: {
      title: "Arbetsorder",
      endpoint: "work/",
      fields: [
        org,
        asset,
        title,
        description,
        {
          key: "kind",
          label: "Typ",
          type: "select",
          options: choices(["issue", "round", "inspection"]),
          default: "issue",
        },
        {
          key: "priority",
          label: "Prioritet",
          type: "select",
          options: choices(["low", "normal", "high", "urgent"], priorityNames),
          default: "normal",
        },
        date,
        user,
        { key: "category", label: "Kategori", default: "Drift" },
        check,
      ],
    },
    maintenance: {
      title: "Planerad underhållsåtgärd",
      endpoint: "maintenance/",
      fields: [
        org,
        asset,
        title,
        { key: "category", label: "Kategori", default: "Byggnad" },
        {
          key: "year",
          label: "Planerat år",
          type: "number",
          default: new Date().getFullYear(),
          min: 1900,
          max: 2200,
          required: true,
        },
        {
          key: "interval_years",
          label: "Återkommer efter antal år · 0 = en gång",
          type: "number",
          default: 0,
          min: 0,
          max: 100,
        },
        moneyField("quantity", "Mängd", 1),
        { key: "unit", label: "Enhet", default: "st" },
        moneyField("unit_price", "À-pris, kr"),
        moneyField("cost_factor", "Kostnadsfaktor", 1.25),
        {
          key: "price_year",
          label: "Prisår",
          type: "number",
          default: new Date().getFullYear(),
          required: true,
        },
        moneyField("index_percent", "Årlig indexering, %"),
        { key: "account", label: "Kontering" },
        moneyField("funding_possible", "Möjlig finansiering, kr"),
        moneyField("funding_granted", "Beviljad finansiering, kr"),
        { key: "note", label: "Notering", type: "textarea" },
      ],
    },
    schedules: {
      title: "Återkommande kontroll",
      endpoint: "schedules/",
      fields: [
        org,
        asset,
        title,
        {
          key: "kind",
          label: "Typ",
          type: "select",
          options: choices(["round", "inspection"]),
          default: "round",
        },
        { key: "category", label: "Kategori", default: "Tillsyn" },
        {
          key: "anchor_date",
          label: "Första planeringsdatum",
          type: "date",
          default: today(),
          required: true,
        },
        {
          key: "next_date",
          label: "Nästa tillfälle",
          type: "date",
          default: today(),
          required: true,
        },
        {
          key: "interval",
          label: "Intervall",
          type: "number",
          min: 1,
          default: 1,
          required: true,
        },
        {
          key: "unit",
          label: "Tidsenhet",
          type: "select",
          options: [
            ["day", "Dagar"],
            ["week", "Veckor"],
            ["month", "Månader"],
            ["year", "År"],
          ],
          default: "month",
        },
        user,
        check,
      ],
    },
    registry: {
      title: "Plan, kontroll eller inventarium",
      endpoint: "registry/",
      fields: [
        org,
        asset,
        title,
        {
          key: "kind",
          label: "Typ",
          type: "select",
          options: choices([
            "care_plan",
            "tree",
            "inventory",
            "inspection",
            "sba",
            "safety",
            "contract",
            "warranty",
            "nki",
          ]),
          default: "care_plan",
        },
        description,
        { key: "reference", label: "Referens" },
        { key: "responsible", label: "Ansvarig" },
        { key: "start_date", label: "Startdatum", type: "date" },
        date,
        {
          key: "score",
          label: "Betyg 0–10 · endast NKI",
          type: "number",
          min: 0,
          max: 10,
        },
      ],
    },
    meters: {
      title: "Energimätare",
      endpoint: "meters/",
      fields: [
        org,
        asset,
        name(),
        {
          key: "medium",
          label: "Medium",
          type: "select",
          options: choices([
            "electricity",
            "heat",
            "water",
            "cooling",
            "hours",
          ]),
          default: "electricity",
        },
        {
          key: "unit",
          label: "Enhet",
          type: "select",
          options: [
            ["kWh", "kWh"],
            ["m³", "m³"],
            ["h", "h"],
          ],
          default: "kWh",
        },
        { key: "serial", label: "Serienummer" },
      ],
    },
    readings: {
      title: "Mätaravläsning",
      endpoint: "readings/",
      fields: [
        org,
        {
          key: "meter",
          label: "Mätare",
          type: "remote:meters",
          required: true,
        },
        {
          key: "date",
          label: "Datum",
          type: "date",
          default: today(),
          required: true,
        },
        moneyField("value", "Mätarställning"),
        { key: "replacement", label: "Mätaren har bytts", type: "checkbox" },
        {
          key: "old_final",
          label: "Slutvärde gammal mätare",
          type: "number",
          min: 0,
        },
        {
          key: "new_initial",
          label: "Startvärde ny mätare",
          type: "number",
          min: 0,
        },
        { key: "serial", label: "Ny mätares serienummer" },
      ],
    },
    keys: {
      title: "Registrera fysisk nyckel",
      endpoint: "keys/",
      fields: [
        org,
        asset,
        name(),
        { key: "system", label: "Nyckelsystem", required: true },
        { key: "serial", label: "Nyckelnummer", required: true },
        {
          key: "condition",
          label: "Skick",
          type: "select",
          options: [
            ["ok", "Hel"],
            ["lost", "Borttappad"],
            ["broken", "Trasig"],
          ],
          default: "ok",
        },
      ],
    },
    loans: {
      title: "Låna ut nyckel",
      endpoint: "loans/",
      fields: [
        org,
        { key: "key", label: "Nyckel", type: "remote:keys", required: true },
        { key: "borrower", label: "Låntagare", required: true },
        { ...date, required: true },
      ],
    },
    scenarios: {
      title: "Nytt budgetscenario",
      endpoint: "scenarios/",
      fields: [
        org,
        name("Scenarionamn"),
        {
          key: "start_year",
          label: "Från år",
          type: "number",
          default: new Date().getFullYear(),
          min: 1900,
          max: 2200,
        },
        {
          key: "years",
          label: "Antal år",
          type: "select",
          options: [
            ["1", "1 år"],
            ["5", "5 år"],
            ["10", "10 år"],
            ["30", "30 år"],
          ],
          default: "10",
        },
      ],
    },
    organizations: {
      title: "Organisationsenhet",
      endpoint: "organizations/",
      fields: [
        name(),
        {
          key: "kind",
          label: "Nivå",
          type: "select",
          options: choices(["church", "diocese", "pastorate", "parish"]),
          default: "parish",
        },
        {
          key: "parent",
          label: "Överordnad enhet",
          type: "select",
          options: orgOptions(boot),
        },
      ],
    },
    costs: {
      title: "Tid, material eller kostnad",
      endpoint: "costs/",
      fields: [
        org,
        {
          key: "work",
          label: "Arbetsorder",
          type: "remote:work",
          required: true,
        },
        {
          key: "kind",
          label: "Typ",
          type: "select",
          options: [
            ["time", "Arbetstid"],
            ["material", "Material"],
            ["expense", "Övrig kostnad"],
          ],
          default: "time",
        },
        { key: "description", label: "Beskrivning", required: true },
        moneyField("quantity", "Antal / timmar", 1),
        moneyField("unit_price", "Pris per enhet, kr"),
        {
          key: "date",
          label: "Datum",
          type: "date",
          default: today(),
          required: true,
        },
      ],
    },
    users: {
      title: "Ny användare och behörighet",
      endpoint: "users/",
      fields: [
        org,
        name("Namn"),
        { key: "username", label: "Användarnamn", required: true },
        { key: "email", label: "E-post", type: "email", required: true },
        {
          key: "password",
          label: "Tillfälligt lösenord · minst 12 tecken",
          type: "password",
          required: true,
        },
        {
          key: "role",
          label: "Roll",
          type: "select",
          options: [
            ["reader", "Läsare"],
            ["worker", "Medarbetare"],
            ["manager", "Förvaltare"],
            ["admin", "Administratör"],
            ["contractor", "Entreprenör"],
          ],
          default: "worker",
        },
        {
          key: "descendants",
          label: "Ge åtkomst till underliggande enheter",
          type: "checkbox",
        },
        { key: "finance", label: "Ge ekonomibehörighet", type: "checkbox" },
      ],
    },
    subscriptions: {
      title: "Schemalagd rapport",
      endpoint: "subscriptions/",
      fields: [
        org,
        name("Utskickets namn"),
        {
          key: "report_type",
          label: "Rapport",
          type: "select",
          options: Object.entries(reportNames) as [string, string][],
          default: "work",
        },
        {
          key: "recipient",
          label: "Mottagare",
          type: "remote:users",
          required: true,
        },
        {
          key: "next_date",
          label: "Första utskick",
          type: "date",
          default: today(),
          required: true,
        },
        {
          key: "interval_days",
          label: "Dagar mellan utskick",
          type: "number",
          min: 1,
          max: 366,
          default: 7,
          required: true,
        },
      ],
      transform: (d) => ({ ...d, config: {} }),
    },
  };
  return defs[type];
}
function FormDialog({
  config,
  boot,
  onClose,
  onSaved,
}: {
  config: ModalConfig;
  boot: Row;
  onClose: () => void;
  onSaved: (r: Row) => void;
}) {
  const [values, setValues] = useState<Row>(() =>
      Object.fromEntries(
        config.fields.map((f) => [
          f.key,
          config.initial?.[f.key] ??
            f.default ??
            (f.type === "checkbox" ? false : ""),
        ]),
      ),
    ),
    [remote, setRemote] = useState<Record<string, Row[]>>({}),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [dirty, setDirty] = useState(false);
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    addEventListener("beforeunload", warn);
    config.fields
      .filter((f) => f.type?.startsWith("remote:"))
      .forEach((f) => {
        const resource = f.type!.split(":")[1];
        list(resource + "/?" + query({ org: values.org }))
          .then((rows) => setRemote((r) => ({ ...r, [resource]: rows })))
          .catch((e) => setError(e.message));
      });
    return () => {
      removeEventListener("beforeunload", warn);
      ref.current?.close();
    };
  }, []);
  const close = () => {
    if (
      !busy &&
      (!dirty || window.confirm("Stäng utan att spara dina ändringar?"))
    )
      onClose();
  };
  const change = (key: string, value: any) => {
    setValues((v) => ({
      ...v,
      [key]: value,
      ...(key === "org"
        ? {
            asset: "",
            parent: config.endpoint.startsWith("organizations") ? v.parent : "",
          }
        : {}),
    }));
    setDirty(true);
  };
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      let payload: Row = { ...values };
      for (const f of config.fields) {
        if (f.type === "lines")
          payload[f.key] =
            typeof payload[f.key] === "string"
              ? payload[f.key]
                  .split("\n")
                  .map((x: string) => x.trim())
                  .filter(Boolean)
              : payload[f.key];
        if (
          (payload[f.key] === "" &&
            ["date", "number", "asset"].includes(f.type || "")) ||
          (payload[f.key] === "" && f.type?.startsWith("remote:"))
        )
          payload[f.key] = null;
        if (
          f.type === "select" &&
          payload[f.key] === "" &&
          ["parent", "assigned_to"].includes(f.key)
        )
          payload[f.key] = null;
      }
      if (values.asset) {
        const a = boot.assets.find((a: Row) => a.id === values.asset);
        if (a) payload.org = a.org;
      }
      if (config.initial?.version) payload.version = config.initial.version;
      if (config.initial?.revision_of)
        payload.revision_of = config.initial.revision_of;
      if (config.transform) payload = config.transform(payload);
      let body: Row | FormData = payload;
      if (config.fields.some((f) => f.type === "file")) {
        const form = new FormData();
        Object.entries(payload).forEach(([k, v]) => {
          if (v !== null && v !== undefined)
            form.append(k, v instanceof File ? v : String(v));
        });
        body = form;
      }
      const result = await save(config.endpoint, body, config.method || "POST");
      onSaved(result);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <dialog
      ref={ref}
      className="form-dialog"
      onCancel={(e) => {
        e.preventDefault();
        close();
      }}
    >
      <div className="modal-heading">
        <div className="inline-icon">
          <span className="modal-icon">
            <Plus size={21} />
          </span>
          <h2>{config.title}</h2>
        </div>
        <button
          className="icon-btn"
          aria-label="Stäng formulär"
          onClick={close}
        >
          <X />
        </button>
      </div>
      <form onSubmit={submit}>
        <div className="modal-content">
          {error && (
            <div className="alert" role="alert">
              <AlertCircle size={18} />
              <span>{error}</span>
            </div>
          )}
          <div className="form-grid">
            {config.fields.map((f) => {
              const options =
                f.type === "asset"
                  ? assetOptions(boot, values.org)
                  : f.type?.startsWith("remote:")
                    ? (remote[f.type.split(":")[1]] || []).map((r) => [
                        String(r.id),
                        r.name || r.title || r.username || r.id,
                      ])
                    : f.options;
              return (
                <label
                  key={f.key}
                  className={
                    "field " +
                    (["textarea", "lines", "file", "checkbox"].includes(
                      f.type || "",
                    )
                      ? "full"
                      : "")
                  }
                >
                  <span>
                    {f.label}
                    {f.required && <b aria-hidden="true"> *</b>}
                  </span>
                  {f.type === "checkbox" ? (
                    <span className="checkbox-line">
                      <input
                        type="checkbox"
                        checked={!!values[f.key]}
                        onChange={(e) => change(f.key, e.target.checked)}
                      />
                      Aktivera
                    </span>
                  ) : ["textarea", "lines"].includes(f.type || "") ? (
                    <textarea
                      rows={f.type === "lines" ? 4 : 3}
                      value={
                        Array.isArray(values[f.key])
                          ? values[f.key].join("\n")
                          : values[f.key] || ""
                      }
                      onChange={(e) => change(f.key, e.target.value)}
                      required={f.required}
                    />
                  ) : options ? (
                    <select
                      value={values[f.key] ?? ""}
                      onChange={(e) => change(f.key, e.target.value)}
                      required={f.required}
                    >
                      <option value="">Välj…</option>
                      {options.map(([v, n]: any) => (
                        <option key={v} value={v}>
                          {n}
                        </option>
                      ))}
                    </select>
                  ) : f.type === "file" ? (
                    <input
                      type="file"
                      accept=".pdf,.jpg,.jpeg,.png"
                      required={f.required}
                      onChange={(e) => change(f.key, e.target.files?.[0])}
                    />
                  ) : (
                    <input
                      type={f.type || "text"}
                      value={values[f.key] ?? ""}
                      min={f.min}
                      max={f.max}
                      step={f.type === "number" ? "any" : undefined}
                      required={f.required}
                      autoComplete={
                        f.type === "password" ? "new-password" : "off"
                      }
                      onChange={(e) => change(f.key, e.target.value)}
                    />
                  )}
                </label>
              );
            })}
          </div>
        </div>
        <div className="modal-footer">
          <span className="subtle">
            <Lock size={14} />
            Sparas först när servern bekräftat
          </span>
          <button className="btn" type="button" disabled={busy} onClick={close}>
            Avbryt
          </button>
          <button className="btn primary" disabled={busy} type="submit">
            {busy ? (
              <Loader2 size={16} className="spin" />
            ) : (
              <Check size={16} />
            )}{" "}
            {busy ? "Sparar…" : "Spara"}
          </button>
        </div>
      </form>
    </dialog>
  );
}
function Login({ auth, done }: { auth: Row; done: (a: Row) => void }) {
  const [username, setUsername] = useState(""),
    [password, setPassword] = useState(""),
    [mfa, setMfa] = useState<Row | null>(null),
    [recovery, setRecovery] = useState(false),
    [recoveryCode, setRecoveryCode] = useState(""),
    [enrolled, setEnrolled] = useState<Row | null>(null),
    [code, setCode] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await api(
        recovery ? "auth/recover/" : mfa ? "auth/mfa/" : "auth/",
        {
          method: "POST",
          body: JSON.stringify(
            recovery
              ? { recovery_code: recoveryCode }
              : mfa
                ? { code }
                : { username, password },
          ),
        },
      );
      if (recovery) {
        setRecovery(false);
        setRecoveryCode("");
        setCode("");
        setMfa(await api("auth/mfa/"));
      } else if (result.mfa) {
        const next = await api("auth/mfa/");
        setMfa(next);
        if (next.recovery_required) setRecovery(true);
      } else if (result.recovery_codes) setEnrolled(result);
      else done(result);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  if (enrolled)
    return (
      <div className="login-page">
        <RecoveryCodes
          codes={enrolled.recovery_codes}
          onClose={() => done(enrolled)}
        />
      </div>
    );
  return (
    <div className="login-page">
      <div className="login-brand">
        <span className="brand-symbol">F</span>förvalta.
      </div>
      <div className="login-card">
        <span className="eyebrow">FASTIGHETSFÖRVALTNING</span>{auth.sessionExpired&&<p role="status" className="info-box">Din tidigare inloggning har återkallats. Logga in igen om du fortfarande har åtkomst.</p>}
        <h1>{mfa ? "Verifiera din inloggning" : "Välkommen tillbaka"}</h1>
        <p>
          {mfa
            ? "Ange koden från din autentiseringsapp, eller använd en återställningskod."
            : "Dina fastigheter, arbeten och planer på ett ställe."}
        </p>
        {error && (
          <div className="alert" role="alert">
            {error}
          </div>
        )}
        <form onSubmit={submit}>
          {recovery ? (
            <label className="field">
              <span>Återställningskod</span>
              <input
                autoComplete="off"
                value={recoveryCode}
                onChange={(e) => setRecoveryCode(e.target.value)}
                required
              />
              <small>
                Du registrerar en ny autentiseringsapp efter kontrollen.
              </small>
            </label>
          ) : mfa ? (
            <>
              {mfa.enroll && (
                <div className="info-box">
                  <div>
                    <strong>Lägg till Förvalta i din autentiseringsapp</strong>
                    <p>Ange den här installationsnyckeln manuellt:</p>
                    <code className="mfa-secret">{mfa.secret}</code>
                  </div>
                </div>
              )}
              <label className="field">
                <span>Engångskod</span>
                <input
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  pattern="[0-9]{6}"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  required
                />
              </label>
            </>
          ) : (
            <>
              <label className="field">
                <span>Användarnamn</span>
                <input
                  autoComplete="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                />
              </label>
              <label className="field">
                <span>Lösenord</span>
                <input
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </label>
            </>
          )}
          <button className="btn primary full-width" disabled={busy}>
            {busy ? "Kontrollerar…" : mfa ? "Verifiera" : "Logga in"}
          </button>
        </form>
        {mfa && !mfa.enroll && !recovery && (
          <button
            className="text-btn"
            onClick={() => {
              setRecovery(true);
              setCode("");
            }}
          >
            Jag behöver återställa min autentiseringsapp
          </button>
        )}
        {auth.demo && (
          <button
            className="btn full-width demo-login"
            onClick={() =>
              api("auth/demo/", { method: "POST", body: "{}" })
                .then(done)
                .catch((e) => setError(e.message))
            }
          >
            Öppna demonstrationen
          </button>
        )}
        <a href="#/public" className="public-link">
          Gör en felanmälan <ExternalLink size={15} />
        </a>
      </div>
      <p className="login-footer">
        Öppen källkod. Egen data. Egen förvaltning.
      </p>
    </div>
  );
}
function PublicPortal({ route }: { route: string }) {
  const [assets, setAssets] = useState<Row[]>([]),
    [asset, setAsset] = useState(""),
    [title, setTitle] = useState(""),
    [description, setDescription] = useState(""),
    [email, setEmail] = useState(""),
    [receipt, setReceipt] = useState<Row | null>(null),
    [track, setTrack] = useState<Row | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const requestKey = useRef(crypto.randomUUID());
  useEffect(() => {
    if (route.startsWith("/track/"))
      api("public/track/", {
        method: "POST",
        body: JSON.stringify({ token: route.split("/")[2] }),
      })
        .then(setTrack)
        .catch(() =>
          setError("Ärendet kunde inte hittas. Kontrollera länken."),
        );
    else
      list("public/assets/")
        .then(setAssets)
        .catch((e) => setError(e.message));
  }, [route]);
  return (
    <div className="public-page">
      <header>
        <a href="#/public" className="login-brand">
          <span className="brand-symbol">F</span>förvalta.
        </a>
        <span>Felanmälan</span>
      </header>
      <main>
        <div className="public-title">
          <span className="eyebrow">HJÄLP OSS TA HAND OM PLATSEN</span>
          <h1>
            {track
              ? "Din felanmälan"
              : receipt
                ? "Tack, din anmälan är sparad"
                : "Vad behöver åtgärdas?"}
          </h1>
          <p>
            {receipt
              ? "Spara länken nedan för att följa ärendet."
              : "Beskriv vad du har upptäckt, så kan ansvarig personal följa upp."}
          </p>
        </div>
        {error && (
          <div className="alert" role="alert">
            {error}
          </div>
        )}
        {track ? (
          <section className="panel padded">
            <Badge value={track.status} />
            <h2>
              #{track.number} · {track.title}
            </h2>
            {track.comments.map((c: Row, i: number) => (
              <article className="public-comment" key={i}>
                <p>{c.text}</p>
                <small>{new Date(c.created_at).toLocaleString("sv-SE")}</small>
              </article>
            ))}
            {!track.comments.length && <p>Ingen återkoppling ännu.</p>}
          </section>
        ) : receipt ? (
          <section className="panel padded receipt">
            <CheckCircle2 size={45} />
            <h2>Ärende #{receipt.number}</h2>
            <a className="btn primary" href={"#/track/" + receipt.token}>
              Följ ditt ärende
            </a>
            <p>Om du angav e-post skickas även en bekräftelse.</p>
          </section>
        ) : (
          <form
            className="panel padded"
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              setError("");
              try {
                const r = await api("public/issues/", {
                  method: "POST",
                  headers: { "Idempotency-Key": requestKey.current },
                  body: JSON.stringify({ asset, title, description, email }),
                });
                setReceipt(r);
              } catch (e: any) {
                setError(e.message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <label className="field">
              <span>Vilken plats gäller det?</span>
              <select
                required
                value={asset}
                onChange={(e) => setAsset(e.target.value)}
              >
                <option value="">Välj plats…</option>
                {assets.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name} {a.address ? "· " + a.address : ""}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Kort rubrik</span>
              <input
                required
                maxLength={200}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Till exempel: belysningen vid entrén fungerar inte"
              />
            </label>
            <label className="field">
              <span>Beskriv felet</span>
              <textarea
                required
                maxLength={10000}
                rows={5}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Var finns felet och vad har hänt?"
              />
            </label>
            <label className="field">
              <span>E-post för återkoppling · frivilligt</span>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
              />
            </label>
            <p className="form-note">
              Ange bara uppgifter som behövs för att hantera felet. Använd inte
              formuläret vid akut fara.
            </p>
            <button
              className="btn primary full-width"
              disabled={busy || !assets.length}
            >
              {busy ? (
                <Loader2 className="spin" size={18} />
              ) : (
                <Send size={18} />
              )}{" "}
              {busy ? "Skickar…" : "Skicka felanmälan"}
            </button>
            {!assets.length && (
              <p>Inga platser är öppna för felanmälan ännu.</p>
            )}
          </form>
        )}
      </main>
      <footer>Förvalta · Säker återkoppling till ditt ärende</footer>
    </div>
  );
}

const mount = document.getElementById("root")! as HTMLElement & {
  forvaltaRoot?: ReturnType<typeof createRoot>;
};
mount.forvaltaRoot ??= createRoot(mount);
mount.forvaltaRoot.render(<App />);
