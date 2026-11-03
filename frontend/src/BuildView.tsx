import { useEffect, useRef, useState } from "react";
import { api, type BuildEvent, type TraceStep, type WorkflowRow } from "./api";
import { Canvas } from "./components/Canvas";
import { navigate } from "./router";

type Stage = { stage: string; attempt?: number; problems?: string[]; done?: boolean };

const LABEL: Record<string, string> = { analyse: "Understand the process", design: "Design the workflow", fix: "Fix the design", dry_run: "Dry run in a sandbox" };

/** Rebuild the timeline from what was stored: each design or fix, with the validation result it got. */
function history(row: WorkflowRow): Stage[] {
  const rounds = row.validation ?? [];
  return [
    { stage: "analyse", done: true },
    ...rounds.map((problems, i) => ({ stage: i === 0 ? "design" : "fix", problems, done: true })),
    ...(row.dry_run ? [{ stage: "dry_run", done: true }] : []),
  ];
}

export function BuildView({ id }: { id: string }) {
  const [row, setRow] = useState<WorkflowRow | null>(null);
  const [missing, setMissing] = useState(false);
  const [timeline, setTimeline] = useState<Stage[]>([]);
  const [live, setLive] = useState<TraceStep[]>([]);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ctrl = useRef<AbortController | null>(null);

  const refresh = () => api.get(id).then(setRow);

  const follow = () => {
    ctrl.current?.abort();
    ctrl.current = new AbortController();
    setTimeline([]);
    setLive([]);
    const on = (e: BuildEvent) => {
      if (e.type === "stage") setTimeline((t) => [...t.map((s) => ({ ...s, done: true })), { stage: e.stage, attempt: e.attempt }]);
      if (e.type === "validation") setTimeline((t) => t.map((s, i) => (i === t.length - 1 ? { ...s, problems: e.problems } : s)));
      if (e.type === "dry_step") setLive((l) => [...l, e.step]);
      if (e.type === "analysis" || e.type === "workflow" || e.type === "dry_run") refresh();
      if (e.type === "done" || e.type === "error") {
        setTimeline((t) => t.map((s) => ({ ...s, done: true })));
        refresh();
      }
    };
    api.events(id, on, ctrl.current.signal).catch(() => {});
  };

  useEffect(() => {
    api
      .get(id)
      .then((r) => {
        setRow(r);
        if (r.status === "building") follow();
      })
      .catch(() => setMissing(true));
    return () => ctrl.current?.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  if (missing)
    return (
      <main className="page center">
        <h1>No such automation.</h1>
        <button className="btn" onClick={() => navigate("/")}>
          Home
        </button>
      </main>
    );
  if (!row) return <main className="page center muted">Loading…</main>;

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const wf = row.workflow;
  const trace = row.status === "building" ? live : row.dry_run?.trace;
  const building = row.status === "building";

  return (
    <main className="page build">
      <header className="build-head">
        <button className="back" onClick={() => navigate("/")}>
          ← All automations
        </button>
        <div className="title">
          <h1>{wf?.name ?? "Designing…"}</h1>
          <span className={`pill ${row.status}`}>{row.status.replace("_", " ")}</span>
        </div>
        <p className="summary">{wf?.summary ?? row.description}</p>
        <div className="actions">
          {row.status === "ready" || row.status === "paused" ? (
            <button className="btn primary" disabled={busy} onClick={() => act(() => api.deploy(id))}>
              Deploy
            </button>
          ) : row.status === "deployed" ? (
            <button className="btn" disabled={busy} onClick={() => act(() => api.pause(id))}>
              Pause
            </button>
          ) : null}
          {wf && wf.trigger.type !== "file" && ["ready", "deployed", "paused"].includes(row.status) && (
            <button className="btn" disabled={busy} onClick={() => act(() => api.runNow(id))}>
              Run now
            </button>
          )}
          {row.status === "deployed" && (
            <button className="btn ghost" onClick={() => navigate("/monitor")}>
              Watch it run →
            </button>
          )}
        </div>
        {error && <p className="error">{error}</p>}
      </header>

      <div className="build-grid">
        <aside className="understanding">
          <section className="card">
            <h3>How it was built</h3>
            <ol className="timeline">
              {(timeline.length ? timeline : history(row)).map((s, i) => (
                <li key={i} className={s.done ? "done" : "now"}>
                  <b>{LABEL[s.stage] ?? s.stage}</b>
                  {s.problems && s.problems.length > 0 && (
                    <ul className="problems">
                      {s.problems.map((p) => (
                        <li key={p}>{p}</li>
                      ))}
                    </ul>
                  )}
                  {s.problems && s.problems.length === 0 && <span className="ok">valid against the tool registry</span>}
                </li>
              ))}
            </ol>
            {row.error && <p className="error">{row.error}</p>}
          </section>

          {row.analysis && (
            <section className="card">
              <h3>What I understood</h3>
              <p className="goal">{row.analysis.goal}</p>
              <h4>Starts when</h4>
              <p>{row.analysis.trigger}</p>
              <h4>Rules</h4>
              <ul>{row.analysis.rules.map((r) => <li key={r}>{r}</li>)}</ul>
              {row.analysis.assumptions.length > 0 && (
                <>
                  <h4>Assumptions</h4>
                  <ul className="assume">{row.analysis.assumptions.map((r) => <li key={r}>{r}</li>)}</ul>
                </>
              )}
            </section>
          )}

          {!building && (
            <section className="card">
              <h3>Change something</h3>
              <textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Use 10,000 as the approval limit, and post to #ap instead." rows={3} />
              <button
                className="btn"
                disabled={!note.trim() || busy}
                onClick={() =>
                  act(async () => {
                    await api.rebuild(id, note);
                    setNote("");
                    follow();
                  })
                }
              >
                Rebuild
              </button>
            </section>
          )}
        </aside>

        <section className="board">
          {wf ? <Canvas workflow={wf} trace={trace} /> : <div className="placeholder">Sketching the workflow…</div>}
          {row.dry_run && !building && (
            <p className={`dry ${row.dry_run.status}`}>
              Dry run {row.dry_run.status} in {row.dry_run.ms} ms on a sandbox copy of the workspace
              {row.dry_run.trigger && "file" in row.dry_run.trigger ? `, triggered by ${String(row.dry_run.trigger.file)}` : ""}. Nothing real was touched.
            </p>
          )}
        </section>
      </div>
    </main>
  );
}
