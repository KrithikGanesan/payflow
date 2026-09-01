// Local, in-session store for human actions (approve/reject with reason).
// Persists to localStorage so the demo keeps decisions across reloads.
import { useSyncExternalStore } from "react";

export type HumanAction = {
  run_id: string;
  action: "APPROVE" | "REJECT" | "NOTE";
  actor: string;
  reason: string;
  ts: string;
};

const KEY = "verdict-actions";
let _actions: HumanAction[] = load();
const listeners = new Set<() => void>();

function load(): HumanAction[] {
  try {
    return JSON.parse(localStorage.getItem(KEY) || "[]");
  } catch {
    return [];
  }
}
function persist() {
  try {
    localStorage.setItem(KEY, JSON.stringify(_actions));
  } catch {
    /* ignore */
  }
  listeners.forEach((fn) => fn());
}

export function addAction(a: Omit<HumanAction, "ts">) {
  _actions = [..._actions, { ...a, ts: new Date().toISOString() }];
  persist();
}
export function actionsFor(runId: string): HumanAction[] {
  return _actions.filter((a) => a.run_id === runId);
}
export function latestResolution(runId: string): HumanAction | undefined {
  return [..._actions]
    .reverse()
    .find((a) => a.run_id === runId && a.action !== "NOTE");
}

function subscribe(fn: () => void) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
function snapshot() {
  return _actions;
}

export function useActions() {
  return useSyncExternalStore(subscribe, snapshot);
}
