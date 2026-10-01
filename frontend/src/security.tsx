import { useEffect, useState } from "react";
import { ShieldCheck, Lock, RefreshCw } from "lucide-react";
import { api, save, Row } from "./api";
export function RecoveryCodes({
  codes,
  onClose,
}: {
  codes: string[];
  onClose: () => void;
}) {
  return (
    <section className="panel padded" aria-label="Dina engångskoder">
      <h2>Spara återställningskoderna</h2>
      <p>
        Varje kod fungerar en gång, tillsammans med ditt lösenord. Förvara dem
        separat från autentiseringsappen. De visas bara nu.
      </p>
      <ul className="recovery-codes">
        {codes.map((c) => (
          <li key={c}>
            <code>{c}</code>
          </li>
        ))}
      </ul>
      <button className="btn primary" onClick={onClose}>
        Jag har sparat koderna
      </button>
    </section>
  );
}
function Credentials({
  password,
  setPassword,
  code,
  setCode,
  mfa,
}: {
  password: string;
  setPassword: (s: string) => void;
  code: string;
  setCode: (s: string) => void;
  mfa: boolean;
}) {
  return (
    <div className="form-grid">
      <label className="field">
        <span>Ditt nuvarande lösenord</span>
        <input
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </label>
      {mfa && (
        <label className="field">
          <span>Ny kod från din autentiseringsapp</span>
          <input
            inputMode="numeric"
            autoComplete="one-time-code"
            pattern="[0-9]{6}"
            required
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
        </label>
      )}
    </div>
  );
}
export function SecurityPage({ boot }: { boot: Row }) {
  const [state, setState] = useState<Row | null>(null),
    [codes, setCodes] = useState<string[]>([]),
    [action, setAction] = useState("revoke_sessions"),
    [password, setPassword] = useState(""),
    [code, setCode] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [message, setMessage] = useState("");
  const refresh = () =>
    api("security/")
      .then(setState)
      .catch((e) => setError(e.message));
  useEffect(() => {
    refresh();
  }, []);
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">KONTO & INLOGGNING</span>
          <h1>Min säkerhet</h1>
          <p>Hantera aktiva inloggningar och dina återställningskoder.</p>
        </div>
      </div>
      {error && (
        <p role="alert" className="alert">
          {error}
        </p>
      )}
      {message && (
        <p role="status" className="info-box">
          {message}
        </p>
      )}
      {codes.length ? (
        <RecoveryCodes
          codes={codes}
          onClose={() => {
            setCodes([]);
            refresh();
          }}
        />
      ) : (
        <section className="panel padded">
          <h2>
            <ShieldCheck size={20} /> Skyddad inloggning
          </h2>
          <p>
            {state?.mfa_enabled
              ? "Autentiseringsapp registrerad."
              : "Ingen autentiseringsapp registrerad."}{" "}
            {state?.mfa_enabled &&
              `${state.recovery_codes_remaining} oanvända återställningskoder.`}
          </p>
          {boot.demo && (
            <p>
              Demokontot saknar lösenord. Dessa säkerhetsåtgärder provas med
              separata testkonton.
            </p>
          )}
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              setError("");
              setMessage("");
              try {
                const r = await api("security/", {
                  method: "POST",
                  body: JSON.stringify({ action, password, code }),
                });
                if (r.recovery_codes) setCodes(r.recovery_codes);
                else
                  setMessage(
                    "Övriga inloggningar har återkallats. Den här sessionen är kvar.",
                  );
                refresh();
              } catch (e: any) {
                setError(e.message);
              } finally {
                setPassword("");
                setCode("");
                setBusy(false);
              }
            }}
          >
            <label className="field">
              <span>Åtgärd</span>
              <select
                value={action}
                onChange={(e) => setAction(e.target.value)}
              >
                <option value="revoke_sessions">
                  Logga ut från övriga sessioner
                </option>
                {state?.mfa_enabled && (
                  <option value="recovery_codes">
                    Ersätt alla återställningskoder
                  </option>
                )}
              </select>
            </label>
            <p>
              {action === "recovery_codes"
                ? "Alla äldre återställningskoder slutar fungera när nya koder skapas."
                : "Alla andra sessioner och påbörjade inloggningar avslutas."}
            </p>
            <Credentials
              {...{ password, setPassword, code, setCode }}
              mfa={!boot.demo}
            />
            <button className="btn primary" disabled={busy || boot.demo}>
              {busy ? "Verifierar…" : "Verifiera och genomför"}
            </button>
          </form>
        </section>
      )}
    </>
  );
}
export function AccessPanel({
  boot,
  onChanged,
}: {
  boot: Row;
  onChanged: () => void;
}) {
  const [users, setUsers] = useState<Row[]>([]),
    [resets, setResets] = useState<Row[]>([]),
    [task, setTask] = useState<Row | null>(null),
    [reason, setReason] = useState(""),
    [password, setPassword] = useState(""),
    [code, setCode] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [issued, setIssued] = useState<Row | null>(null),
    [notice, setNotice] = useState("");
  const refresh = () => {
    api("access/users/")
      .then(setUsers)
      .catch((e) => setError(e.message));
    if (boot.user.superuser)
      api("access/resets/")
        .then(setResets)
        .catch((e) => setError(e.message));
  };
  useEffect(() => {
    refresh();
  }, []);
  const choose = (t: Row) => {
    setTask(t);
    setReason("");
    setPassword("");
    setCode("");
    setError("");
    setNotice("");
  };
  return (
    <section className="panel padded space-top">
      <div className="panel-heading flush">
        <h2>Åtkomst & konton</h2>
        <button className="btn small" onClick={refresh}>
          <RefreshCw size={15} />
          Uppdatera
        </button>
      </div>
      <p>
        Återkallad tilldelning avslutar även användarens befintliga sessioner.
        Kontostängning gäller hela tjänsten och kräver systemadministratör.
      </p>
      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="info-box" role="status">
          {notice}
        </p>
      )}
      {users.map((u) => (
        <article key={u.id} className="security-user">
          <div>
            <strong>{u.name}</strong>{" "}
            <span className="subtle">
              {u.username} · {u.is_active ? "Aktiv" : "Stängt konto"}
            </span>
          </div>
          {u.grants.map((g: Row) => (
            <div className="security-grant" key={g.id}>
              <span>
                {g.org_name} · {({admin:"Administratör",manager:"Förvaltare",worker:"Medarbetare",reader:"Läsare",contractor:"Entreprenör"} as Record<string,string>)[g.role]||g.role}
                {g.descendants ? " · underenheter" : ""}
                {g.finance ? " · ekonomi" : ""} ·{" "}
                {g.active ? "Aktiv" : "Återkallad"}
              </span>
              {g.active && !u.is_superuser && u.id !== boot.user.id && (
                <button
                  className="btn small"
                  onClick={() =>
                    choose({
                      action: "revoke_grant",
                      user: u.id,
                      grant: g.id,
                      version: g.version,
                      label: `Återkalla ${u.name}s tilldelning till ${g.org_name}`,
                    })
                  }
                >
                  Återkalla tilldelning
                </button>
              )}
            </div>
          ))}
          {boot.user.superuser && u.id !== boot.user.id && u.is_active && (
            <div className="inline-actions">
              <button
                className="btn small"
                onClick={() =>
                  choose({
                    action: "revoke_sessions",
                    user: u.id,
                    version: u.version,
                    label: `Avsluta alla inloggningar för ${u.name}`,
                  })
                }
              >
                Avsluta sessioner
              </button>
              <button
                className="btn small"
                onClick={() =>
                  choose({
                    action: "disable_account",
                    user: u.id,
                    version: u.version,
                    label: `Stäng kontot för ${u.name} i hela tjänsten`,
                  })
                }
              >
                Stäng konto
              </button>
              <button
                className="btn small"
                onClick={() =>
                  choose({
                    action: "request_reset",
                    user: u.id,
                    label: `Begär MFA-återställning för ${u.name}`,
                  })
                }
              >
                Begär MFA-återställning
              </button>
            </div>
          )}
        </article>
      ))}
      {boot.user.superuser && (
        <>
          <h3>MFA-begäranden</h3>
          <p>
            Kontrollera användarens identitet utanför tjänsten. En annan
            systemadministratör måste godkänna. Användaren behöver även sitt
            lösenord.
          </p>
          {resets.map((r) => (
            <article className="security-user" key={r.id}>
              <strong>
                {r.user__username} · {r.state}
              </strong>
              <p>{r.reason}</p>
              <small>
                Giltig till {new Date(r.expires_at).toLocaleString("sv-SE")}
              </small>
              {r.state === "pending" &&
                r.requested_by_id !== boot.user.id &&
                r.user_id !== boot.user.id && (
                  <button
                    className="btn small"
                    onClick={() =>
                      choose({
                        action: "approve_reset",
                        id: r.id,
                        version: r.version,
                        label: `Godkänn MFA-återställning för ${r.user__username}`,
                      })
                    }
                  >
                    Granska och godkänn
                  </button>
                )}
            </article>
          ))}
        </>
      )}
      {task && (
        <form
          className="security-review"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError("");
            try {
              const credentials = { password, code };
              let r;
              if (task.action === "approve_reset")
                r = await api(`access/resets/${task.id}/approve/`, {
                  method: "POST",
                  body: JSON.stringify({
                    version: task.version,
                    ...credentials,
                  }),
                });
              else if (task.action === "request_reset")
                r = await save("access/resets/", {
                  user: task.user,
                  reason,
                  ...credentials,
                });
              else
                r = await save("access/reduce/", {
                  ...task,
                  reason,
                  ...credentials,
                });
              if (r.recovery_code) setIssued(r);
              setTask(null);
              setNotice(
                "Åtgärden är bekräftad och registrerad i ändringsloggen.",
              );
              refresh();
              onChanged();
            } catch (e: any) {
              setError(e.message);
              refresh();
            } finally {
              setPassword("");
              setCode("");
              setBusy(false);
            }
          }}
        >
          <h3>
            <Lock size={18} /> {task.label}
          </h3>
          <p>
            {task.action === "approve_reset"
              ? "Detta spärrar nuvarande sessioner och ger en tillfällig engångskod, giltig i en timme."
              : "Granska användare och omfattning. Åtgärden registreras med din identitet och orsak."}
          </p>
          {task.action !== "approve_reset" && (
            <label className="field">
              <span>Orsak · inga lösenord eller andra hemligheter</span>
              <textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                required
                minLength={10}
                maxLength={500}
              />
            </label>
          )}
          <Credentials
            {...{ password, setPassword, code, setCode }}
            mfa={!boot.demo}
          />
          {boot.demo && (
            <p>
              Demokontot saknar lösenord. Använd ett separat testkonto för att
              prova ändringar av åtkomst.
            </p>
          )}
          <div className="inline-actions">
            <button type="button" className="btn" onClick={() => setTask(null)}>
              Avbryt
            </button>
            <button className="btn primary" disabled={busy || boot.demo}>
              {busy ? "Verifierar…" : "Verifiera och genomför"}
            </button>
          </div>
        </form>
      )}
      {issued && (
        <section className="info-box">
          <div>
            <h3>Återställningskod · visas bara nu</h3>
            <p>
              Lämna koden till den identifierade användaren via en separat säker
              kanal. Giltig till{" "}
              {new Date(issued.expires_at).toLocaleString("sv-SE")}.
            </p>
            <code className="mfa-secret">{issued.recovery_code}</code>
            <p>
              Vid förlorad kod behöver en ny begäran godkännas av två
              administratörer.
            </p>
            <button className="btn" onClick={() => setIssued(null)}>
              Jag har hanterat koden
            </button>
          </div>
        </section>
      )}
    </section>
  );
}
