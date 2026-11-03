import { useEffect, useState } from "react";
import { api, SERVER_COLOR, type Tool, type WorkflowSummary } from "./api";
import { navigate } from "./router";

const EXAMPLES = [
  "When a new invoice lands in the inbox, log it to the ledger, alert finance if it's over 5,000, email the vendor to confirm we got it, and file it away.",
  "Every minute, check the task tracker for overdue tasks and post a digest to the team channel.",
];

export function Home() {
  const [text, setText] = useState("");
  const [flows, setFlows] = useState<WorkflowSummary[]>([]);
  const [tools, setTools] = useState<Tool[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.list().then(setFlows).catch(() => setError("The FlowMind API isn't reachable."));
    api.registry().then(setTools).catch(() => {});
  }, []);

  const go = async (description: string) => {
    setBusy(true);
    setError(null);
    try {
      navigate(`/w/${(await api.create(description)).id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  };

  const servers = [...new Set(tools.map((t) => t.server))];

  return (
    <main className="page home">
      <section className="hero">
        <h1>
          Describe the process.
          <br />
          <span className="grad">Get the automation.</span>
        </h1>
        <p className="lede">Explain a process the way you'd tell a colleague. An agent designs the workflow over real MCP tools, dry-runs it in a sandbox, fixes what breaks, and runs it for you with monitoring.</p>
        <form
          className="ask"
          onSubmit={(e) => {
            e.preventDefault();
            if (text.trim().length >= 10) go(text);
          }}
        >
          <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="When… then… unless…" rows={3} aria-label="Describe a process" />
          <button className="btn primary" disabled={text.trim().length < 10 || busy}>
            {busy ? "Starting…" : "Build it"}
          </button>
        </form>
        <div className="examples">
          {EXAMPLES.map((e) => (
            <button key={e} className="chip" disabled={busy} onClick={() => go(e)}>
              {e}
            </button>
          ))}
        </div>
        {error && <p className="error">{error}</p>}
      </section>

      {flows.length > 0 && (
        <section>
          <h2>Your automations</h2>
          <div className="flows">
            {flows.map((f) => (
              <button key={f.id} className="flow-card" onClick={() => navigate(`/w/${f.id}`)}>
                <span className={`pill ${f.status}`}>{f.status.replace("_", " ")}</span>
                <b>{f.name ?? "untitled"}</b>
                <span className="muted">{f.description}</span>
                <span className="meta">
                  {f.trigger ? (f.trigger.type === "file" ? `watches ${f.trigger.folder}/` : f.trigger.type === "schedule" ? `every ${f.trigger.every_minutes} min` : "manual") : ""}
                  {f.runs ? ` · ${f.runs} runs · ${Math.round((f.success_rate ?? 0) * 100)}% ok` : ""}
                </span>
              </button>
            ))}
          </div>
        </section>
      )}

      <section>
        <h2>
          Tool registry <span className="muted small">live from {servers.length} MCP servers</span>
        </h2>
        <div className="registry">
          {servers.map((s) => (
            <div key={s} className={`server ${SERVER_COLOR[s] ?? "sky"}`}>
              <b>{s}</b>
              {tools
                .filter((t) => t.server === s)
                .map((t) => (
                  <span key={t.id} title={t.description}>
                    {t.name}
                    {t.read_only && <em>read-only</em>}
                  </span>
                ))}
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
