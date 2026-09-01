import type { RunRecord, SSEEvent, Stage } from "@/contracts";
import { STAGES } from "@/contracts";
import { MOCK_RUNS, liveRunRecord, LIVE_SEED } from "@/mock/data";

// ── data source mode ────────────────────────────────────────────────
export type Mode = "auto" | "mock" | "live";
const MODE_KEY = "verdict-mode";
// Dev: Vite proxies /api → :8000. Prod build sets VITE_API_BASE="" → same-origin (FastAPI serves both).
const API_BASE = (import.meta.env.VITE_API_BASE ?? "/api") as string;
// Mock data + all fallbacks exist ONLY in dev. A production build never fabricates data.
const ALLOW_MOCK = import.meta.env.DEV;

let _mode: Mode = ALLOW_MOCK
  ? ((typeof localStorage !== "undefined" &&
      (localStorage.getItem(MODE_KEY) as Mode)) || "auto")
  : "live";

// After an auto-mode fetch fails, we remember the backend is down so the
// rest of the session serves mock data without hammering a dead port.
let _backendDown = false;

export function getMode(): Mode {
  return _mode;
}
export function setMode(m: Mode) {
  _mode = m;
  _backendDown = false;
  try {
    localStorage.setItem(MODE_KEY, m);
  } catch {
    /* ignore */
  }
  _listeners.forEach((fn) => fn());
}

// live status observability for the UI badge
export type LiveStatus = "mock" | "live" | "unknown";
let _liveStatus: LiveStatus = "unknown";
export function getLiveStatus(): LiveStatus {
  return _liveStatus;
}
const _listeners = new Set<() => void>();
export function onModeChange(fn: () => void): () => void {
  _listeners.add(fn);
  return () => _listeners.delete(fn);
}
function setLiveStatus(s: LiveStatus) {
  if (s !== _liveStatus) {
    _liveStatus = s;
    _listeners.forEach((fn) => fn());
  }
}

function useMock(): boolean {
  if (!ALLOW_MOCK) return false; // production: never mock
  if (_mode === "mock") return true;
  if (_mode === "live") return false;
  return _backendDown; // auto
}

async function tryFetch(path: string, init?: RequestInit): Promise<Response> {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), 2500);
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      ...init,
      signal: ctrl.signal,
      headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    });
    clearTimeout(t);
    return res;
  } catch (e) {
    clearTimeout(t);
    throw e;
  }
}

// ── REST ─────────────────────────────────────────────────────────────
export async function listRuns(): Promise<RunRecord[]> {
  if (!useMock()) {
    try {
      const res = await tryFetch("/runs");
      if (res.ok) {
        setLiveStatus("live");
        return (await res.json()) as RunRecord[];
      }
      throw new Error(`status ${res.status}`);
    } catch {
      if (_mode === "live") {
        setLiveStatus("unknown");
        return ALLOW_MOCK ? MOCK_RUNS : []; // prod: honest empty, never fake
      }
      _backendDown = true;
    }
  }
  setLiveStatus(ALLOW_MOCK ? "mock" : "unknown");
  return ALLOW_MOCK ? MOCK_RUNS : [];
}

export async function getRun(id: string): Promise<RunRecord | undefined> {
  if (!useMock()) {
    try {
      const res = await tryFetch(`/runs/${encodeURIComponent(id)}`);
      if (res.ok) {
        setLiveStatus("live");
        return (await res.json()) as RunRecord;
      }
      throw new Error(`status ${res.status}`);
    } catch {
      if (_mode !== "live") _backendDown = true;
    }
  }
  setLiveStatus(useMock() ? "mock" : _liveStatus);
  if (!ALLOW_MOCK) return undefined;
  return MOCK_RUNS.find((r) => r.run_id === id) ?? liveMatch(id);
}

function liveMatch(id: string): RunRecord | undefined {
  return id === LIVE_SEED.id ? liveRunRecord() : undefined;
}

// POST /runs — kick off a new processing run. Returns the run id.
export async function createRun(fileName?: string): Promise<string> {
  if (!useMock()) {
    try {
      const res = await tryFetch("/runs", {
        method: "POST",
        body: JSON.stringify({ invoice_file: fileName ?? null }),
      });
      if (res.ok) {
        setLiveStatus("live");
        const j = (await res.json()) as { run_id: string };
        return j.run_id;
      }
      throw new Error(`status ${res.status}`);
    } catch {
      if (_mode !== "live") _backendDown = true;
    }
  }
  setLiveStatus(ALLOW_MOCK ? "mock" : "unknown");
  return LIVE_SEED.id;
}

// POST /runs/upload — multipart upload of a fresh PDF → live extraction. Returns run id.
export async function uploadRun(file: File): Promise<string> {
  if (!useMock()) {
    try {
      const fd = new FormData();
      fd.append("file", file);
      // raw fetch, NOT tryFetch — tryFetch forces application/json and breaks the multipart boundary.
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), 20000);
      const res = await fetch(`${API_BASE}/runs/upload`, { method: "POST", body: fd, signal: ctrl.signal })
        .finally(() => clearTimeout(timer));
      if (res.ok) {
        setLiveStatus("live");
        return ((await res.json()) as { run_id: string }).run_id;
      }
      throw new Error(`status ${res.status}`);
    } catch {
      if (_mode !== "live") _backendDown = true;
    }
  }
  setLiveStatus(ALLOW_MOCK ? "mock" : "unknown");
  return LIVE_SEED.id;
}

// ── SSE / live stage stream ─────────────────────────────────────────
export type StreamHandle = { close: () => void };

/**
 * Stream stage events for a run. Uses EventSource against the backend when
 * live; otherwise replays a realistic mock cadence off the run's durations.
 */
export function streamRun(
  runId: string,
  onEvent: (ev: SSEEvent) => void,
  onDone?: (rec: RunRecord) => void,
): StreamHandle {
  if (!useMock() && _mode !== "mock") {
    try {
      const es = new EventSource(
        `${API_BASE}/runs/${encodeURIComponent(runId)}/stream`,
      );
      let gotAny = false;
      const fallbackTimer = setTimeout(() => {
        if (!gotAny) {
          es.close();
          startMock();
        }
      }, 2500);
      es.onmessage = (m) => {
        gotAny = true;
        clearTimeout(fallbackTimer);
        setLiveStatus("live");
        try {
          const ev = JSON.parse(m.data) as SSEEvent;
          onEvent(ev);
          if (ev.type === "run_completed") {
            es.close();
            getRun(runId).then((r) => r && onDone?.(r));
          }
        } catch {
          /* ignore malformed */
        }
      };
      es.onerror = () => {
        clearTimeout(fallbackTimer);
        es.close();
        if (!gotAny) {
          if (_mode !== "live") _backendDown = true;
          startMock();
        }
      };
      return { close: () => es.close() };
    } catch {
      if (_mode !== "live") _backendDown = true;
    }
  }

  let handle: StreamHandle;
  function startMock() {
    if (!ALLOW_MOCK) return; // production: no fabricated stream, ever
    handle = mockStream(onEvent, onDone);
  }
  startMock();
  return { close: () => handle?.close() };
}

function mockStream(
  onEvent: (ev: SSEEvent) => void,
  onDone?: (rec: RunRecord) => void,
): StreamHandle {
  setLiveStatus(useMock() ? "mock" : _liveStatus);
  const rec = liveRunRecord();
  const timers: number[] = [];
  let elapsed = 0;
  const SPEED = 0.55; // compress real durations a touch for demo snappiness

  rec.stages.forEach((st) => {
    const startAt = elapsed;
    const dur = Math.max(320, st.duration_ms * SPEED);
    elapsed += dur;
    const endAt = elapsed;

    timers.push(
      window.setTimeout(() => {
        onEvent({
          type: "stage_started",
          run_id: rec.run_id,
          stage: st.stage as Stage,
          status: "running",
          payload: {},
          ts: new Date().toISOString(),
        });
      }, startAt),
    );
    timers.push(
      window.setTimeout(() => {
        onEvent({
          type: "stage_completed",
          run_id: rec.run_id,
          stage: st.stage as Stage,
          status: st.status,
          payload: st.output,
          ts: new Date().toISOString(),
        });
      }, endAt),
    );
  });

  timers.push(
    window.setTimeout(() => {
      onEvent({
        type: "run_completed",
        run_id: rec.run_id,
        status: rec.result?.decision,
        payload: { decision: rec.result?.decision },
        ts: new Date().toISOString(),
      });
      onDone?.(rec);
    }, elapsed + 250),
  );

  return {
    close: () => timers.forEach((t) => clearTimeout(t)),
  };
}

export interface InvoiceMeta { filename: string; scenario?: string; expected_decision?: string; }

export async function listInvoices(): Promise<InvoiceMeta[]> {
  try {
    const res = await tryFetch("/invoices");
    if (res.ok) return (await res.json()) as InvoiceMeta[];
  } catch { /* backend down → empty */ }
  return [];
}

export function invoiceUrl(name: string): string {
  return `${API_BASE}/invoices/${encodeURIComponent(name)}`;
}

export { STAGES };
