export type Row = Record<string, any>;
let csrf = "";
const pending = new Map<string, string>();
export class ApiError extends Error {
  constructor(
    public status: number,
    public data: any,
  ) {
    super(message(data));
  }
}
export function message(data: any): string {
  if (typeof data === "string") return data;
  if (Array.isArray(data)) return data.map(message).join(" ");
  if (data && typeof data === "object")
    return Object.entries(data)
      .map(([k, v]) => (k === "detail" ? "" : k + ": ") + message(v))
      .join(" ");
  return "Något gick fel. Försök igen.";
}
export async function api(
  path: string,
  options: RequestInit = {},
): Promise<any> {
  const res = await fetch("/api/v1/" + path, {
    credentials: "same-origin",
    ...options,
    headers: {
      ...(options.body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
      "X-CSRFToken": csrf,
      ...options.headers,
    },
  });
  const data = await res
    .json()
    .catch(() => ({ detail: "Servern kunde inte behandla begäran." }));
  if(res.status===401&&data.code==='session_revoked'&&typeof window!=='undefined')window.dispatchEvent(new Event('forvalta:session-expired'));
  if (!res.ok) throw new ApiError(res.status, data);
  if (data.csrf) csrf = data.csrf;
  return data;
}
export async function save(
  path: string,
  data: Row | FormData,
  method = "POST",
) {
  const signature =
    path +
    method +
    (data instanceof FormData
      ? JSON.stringify(
          [...data.entries()].map(([k, v]) => [
            k,
            v instanceof File ? v.name + v.size + v.lastModified : v,
          ]),
        )
      : JSON.stringify(data));
  const key = pending.get(signature) || crypto.randomUUID();
  pending.set(signature, key);
  try {
    const result = await api(path, {
      method,
      body: data instanceof FormData ? data : JSON.stringify(data),
      headers: { "Idempotency-Key": key },
    });
    pending.delete(signature);
    return result;
  } catch (e) {
    if (e instanceof ApiError && e.status < 500) {
      pending.delete(signature);
      throw e;
    }
    try {
      const receipt = await api("receipts/" + key + "/");
      if (receipt.saved) {
        pending.delete(signature);
        return receipt.result;
      }
    } catch {}
    throw new Error(
      "Ingen bekräftelse från servern. Uppgifterna finns kvar i formuläret. Försök igen med samma uppgifter för att kontrollera sparningen.",
    );
  }
}
export function query(data: Row) {
  const p = new URLSearchParams();
  Object.entries(data).forEach(([k, v]) => {
    if (v !== "" && v !== null && v !== undefined) p.set(k, String(v));
  });
  return p.toString();
}
export async function list(path: string) {
  const data = await api(path);
  return data.results || data;
}
export const money = (v: any) =>
  v === null || v === undefined
    ? "Saknas"
    : new Intl.NumberFormat("sv-SE", {
        style: "currency",
        currency: "SEK",
        maximumFractionDigits: 0,
      }).format(Number(v));
export const num = (v: any) =>
  new Intl.NumberFormat("sv-SE").format(Number(v || 0));
export const day = (v: any) =>
  v
    ? new Date(String(v).slice(0, 10) + "T12:00:00").toLocaleDateString(
        "sv-SE",
        { day: "numeric", month: "short" },
      )
    : "Ej planerat";
export const today = () => new Date().toLocaleDateString("sv-SE");
export const stateNames: Row = {
  new: "Ny",
  planned: "Planerad",
  in_progress: "Pågår",
  completed: "Kvitterad",
  verified: "Verifierad",
  cancelled: "Avbruten",
  active: "Aktiv",
  closed: "Avslutad",
  draft: "Utkast",
  published: "Fastställd",
};
export const kindNames: Row = {
  property: "Fastighet",
  building: "Byggnad",
  land: "Markområde",
  premises: "Lokal",
  room: "Rum",
  object: "Tekniskt objekt",
  issue: "Ärende",
  round: "Rond",
  inspection: "Besiktning",
  care_plan: "Vårdplan",
  tree: "Trädvård",
  inventory: "Inventarium",
  sba: "Brandskydd",
  safety: "Skyddsrond",
  contract: "Entreprenad",
  warranty: "Garanti",
  nki: "Kundomdöme",
  church: "Svenska kyrkan",
  diocese: "Stift",
  pastorate: "Pastorat",
  parish: "Församling",
  electricity: "El",
  heat: "Värme",
  water: "Vatten",
  cooling: "Kyla",
  hours: "Drifttid",
};
