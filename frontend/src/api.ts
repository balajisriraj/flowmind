export type Condition = { left: string; op: string; right: string };
export type Step = {
  id: string;
  title: string;
  kind: "tool" | "llm";
  tool: string;
  args: { name: string; value: string }[];
  instruction: string;
  input: string;
  fields: { name: string; type: string; description: string }[];
  when: Condition | null;
};
export type Trigger = { type: "manual" | "schedule" | "file"; every_minutes: number; folder: string; pattern: string };
export type Workflow = { name: string; summary: string; trigger: Trigger; steps: Step[] };
export type Analysis = { process: string; goal: string; trigger: string; steps: string[]; rules: string[]; systems: string[]; assumptions: string[] };
export type TraceStep = { id: string; title: string; kind: string; tool: string; status: "ok" | "skipped" | "failed"; input?: unknown; output?: unknown; error?: string; reason?: string; ms?: number };
export type RunResult = { status: "succeeded" | "failed"; error: string | null; trace: TraceStep[]; ms: number; trigger?: Record<string, unknown> };
export type Run = RunResult & { id: string; workflow_id: string; started_at: string; trigger: Record<string, unknown> };
export type WorkflowRow = {
  id: string;
  description: string;
  name: string | null;
  status: "building" | "ready" | "needs_work" | "failed" | "deployed" | "paused";
  error: string | null;
  analysis: Analysis | null;
  workflow: Workflow | null;
  validation: string[][] | null; // one entry per validation round
  dry_run: RunResult | null;
  fixes: number;
  created_at: string;
  deployed_at: string | null;
  runs: Run[];
};
export type WorkflowSummary = Pick<WorkflowRow, "id" | "name" | "description" | "status" | "created_at"> & { trigger: Trigger | null; runs: number; success_rate: number | null };
export type Tool = { id: string; server: string; name: string; description: string; read_only: boolean; input_schema: { properties?: Record<string, { type?: string }> } };
export type Alert = { id: string; workflow_id: string; run_id: string; level: "error" | "warning"; message: string; at: string; acknowledged: number };
export type Workspace = {
  inbox: string[];
  processed: string[];
  ledger: Record<string, string>[];
  tasks: Record<string, string>[];
  outbox: { id: string; to: string; subject: string; body: string; drafted_at: string }[];
  notifications: { id: string; channel: string; text: string; level: string; at: string }[];
  samples: string[];
};
export type BuildEvent =
  | { type: "stage"; stage: "analyse" | "design" | "fix" | "dry_run"; status: string; attempt?: number }
  | { type: "analysis"; analysis: Analysis }
  | { type: "workflow"; workflow: Workflow }
  | { type: "validation"; problems: string[] }
  | { type: "dry_step"; step: TraceStep }
  | { type: "dry_run"; result: RunResult }
  | { type: "done"; status: string; fixes: number }
  | { type: "error"; message: string };

export function parseSSE<T>(buffer: string, emit: (e: T) => void): string {
  const frames = buffer.split(/\r?\n\r?\n/);
  const rest = frames.pop() ?? "";
  for (const frame of frames) {
    const data = frame
      .split(/\r?\n/)
      .filter((l) => l.startsWith("data:"))
      .map((l) => l.slice(5).trimStart())
      .join("\n");
    if (data) emit(JSON.parse(data) as T);
  }
  return rest;
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : `Request failed (${res.status})`);
  }
  return (await res.json()) as T;
}

async function stream<T>(url: string, onEvent: (e: T) => void, signal: AbortSignal) {
  const res = await fetch(url, { signal });
  if (!res.ok || !res.body) return;
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer = parseSSE(buffer + value, onEvent);
  }
}

const post = (url: string, body?: unknown) =>
  fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  health: () => fetch("/api/health").then(json<{ model: string; tools: number }>),
  registry: () => fetch("/api/registry").then(json<Tool[]>),
  list: () => fetch("/api/workflows").then(json<WorkflowSummary[]>),
  get: (id: string) => fetch(`/api/workflows/${id}`).then(json<WorkflowRow>),
  create: (description: string) => post("/api/workflows", { description }).then(json<{ id: string }>),
  remove: (id: string) => fetch(`/api/workflows/${id}`, { method: "DELETE" }).then(json<{ deleted: boolean }>),
  rebuild: (id: string, note: string) => post(`/api/workflows/${id}/rebuild`, { note }).then(json<{ ok: boolean }>),
  deploy: (id: string) => post(`/api/workflows/${id}/deploy`).then(json<{ ok: boolean }>),
  pause: (id: string) => post(`/api/workflows/${id}/pause`).then(json<{ ok: boolean }>),
  runNow: (id: string) => post(`/api/workflows/${id}/run`).then(json<Run>),
  alerts: () => fetch("/api/alerts").then(json<Alert[]>),
  ack: (id: string) => post(`/api/alerts/${id}/ack`).then(json<{ ok: boolean }>),
  runs: () => fetch("/api/runs").then(json<Run[]>),
  workspace: () => fetch("/api/workspace").then(json<Workspace>),
  dropSample: (name: string) => post(`/api/workspace/samples/${encodeURIComponent(name)}`).then(json<{ path: string }>),
  dropFile: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return fetch("/api/workspace/inbox", { method: "POST", body: form }).then(json<{ path: string }>);
  },
  events: (id: string, onEvent: (e: BuildEvent) => void, signal: AbortSignal) => stream(`/api/workflows/${id}/events`, onEvent, signal),
  activity: (onEvent: (e: { type: "run"; workflow_id: string; name: string; status: string; ms: number }) => void, signal: AbortSignal) =>
    stream("/api/activity", onEvent, signal),
};

export const SERVER_COLOR: Record<string, string> = { files: "sky", sheets: "mint", mail: "peach", notify: "lilac", llm: "violet" };
export const OP: Record<string, string> = { eq: "=", ne: "≠", gt: ">", lt: "<", gte: "≥", lte: "≤", contains: "contains", exists: "is present" };
export const pretty = (template: string) => template.replace(/\{\{\s*(?:steps\.)?([\w.]+)\s*\}\}/g, "$1");
