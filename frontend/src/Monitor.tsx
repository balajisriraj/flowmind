import { useCallback, useEffect, useRef, useState } from "react";
import { type Alert, api, type Run, type Workspace } from "./api";
import { navigate } from "./router";

export function Monitor() {
  const [ws, setWs] = useState<Workspace | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [flash, setFlash] = useState<string | null>(null);
  const file = useRef<HTMLInputElement>(null);

  const refresh = useCallback(() => {
    api.workspace().then(setWs).catch(() => {});
    api.runs().then(setRuns).catch(() => {});
    api.alerts().then(setAlerts).catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
    const ctrl = new AbortController();
    api
      .activity((e) => {
        setFlash(`${e.name} ${e.status} in ${e.ms} ms`);
        refresh();
      }, ctrl.signal)
      .catch(() => {});
    const poll = setInterval(refresh, 5000);
    return () => {
      ctrl.abort();
      clearInterval(poll);
    };
  }, [refresh]);

  useEffect(() => {
    if (!flash) return;
    const t = setTimeout(() => setFlash(null), 3500);
    return () => clearTimeout(t);
  }, [flash]);

  const open = alerts.filter((a) => !a.acknowledged);
  const ok = runs.filter((r) => r.status === "succeeded").length;

  return (
    <main className="page monitor">
      <header className="mon-head">
        <div>
          <h1>Live</h1>
          <p className="muted">Deployed automations run here on their triggers. Everything below is the real workspace their MCP tools act on.</p>
        </div>
        <div className="stats">
          <span>
            <b>{runs.length}</b> runs
          </span>
          <span>
            <b>{runs.length ? Math.round((ok / runs.length) * 100) : 0}%</b> succeeded
          </span>
          <span className={open.length ? "hot" : ""}>
            <b>{open.length}</b> open alerts
          </span>
        </div>
      </header>
      {flash && <div className="toast">● {flash}</div>}

      {open.length > 0 && (
        <section className="alerts">
          {open.map((a) => (
            <div key={a.id} className={`alert ${a.level}`}>
              <span>{a.message}</span>
              <button className="link" onClick={() => api.ack(a.id).then(refresh)}>
                Dismiss
              </button>
            </div>
          ))}
        </section>
      )}

      <div className="mon-grid">
        <section className="card inbox">
          <h3>Inbox</h3>
          <p className="muted">Drop an invoice and any automation watching this folder picks it up within seconds.</p>
          <div className="drops">
            {ws?.samples.map((s) => (
              <button key={s} className="chip" onClick={() => api.dropSample(s).then(refresh)}>
                + {s}
              </button>
            ))}
            <button className="chip ghost" onClick={() => file.current?.click()}>
              Upload a file…
            </button>
            <input ref={file} type="file" hidden onChange={(e) => e.target.files?.[0] && api.dropFile(e.target.files[0]).then(refresh)} />
          </div>
          <ul className="files">
            {ws?.inbox.length ? ws.inbox.map((f) => <li key={f}>{f}</li>) : <li className="muted">Empty. Everything has been handled.</li>}
          </ul>
          <h4>Processed</h4>
          <ul className="files done">{ws?.processed.map((f) => <li key={f}>✓ {f}</li>)}</ul>
        </section>

        <section className="card">
          <h3>Runs</h3>
          <table className="runs">
            <tbody>
              {runs.slice(0, 12).map((r) => (
                <tr key={r.id} onClick={() => navigate(`/w/${r.workflow_id}`)}>
                  <td>
                    <span className={`dot ${r.status}`} />
                  </td>
                  <td>{String(r.trigger.name ?? (r.trigger.manual ? "manual" : "schedule"))}</td>
                  <td className="steps">
                    {r.trace.map((s) => (
                      <i key={s.id} className={s.status} title={`${s.id}: ${s.status}${s.error ? ` - ${s.error}` : ""}`} />
                    ))}
                  </td>
                  <td className="muted">{r.ms} ms</td>
                </tr>
              ))}
              {!runs.length && (
                <tr>
                  <td className="muted">No runs yet. Deploy an automation, then drop a file.</td>
                </tr>
              )}
            </tbody>
          </table>
        </section>

        <section className="card wide">
          <h3>Ledger</h3>
          <table className="ledger">
            <thead>
              <tr>{ws?.ledger[0] && Object.keys(ws.ledger[0]).map((k) => <th key={k}>{k}</th>)}</tr>
            </thead>
            <tbody>
              {ws?.ledger.map((row, i) => (
                <tr key={i} className={i === ws.ledger.length - 1 ? "new" : ""}>
                  {Object.values(row).map((v, j) => (
                    <td key={j}>{v}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="card">
          <h3>Outbox</h3>
          <p className="muted">Drafts only. Nothing is sent without a person.</p>
          {ws?.outbox.map((m) => (
            <article key={m.id} className="mail">
              <span className="to">To {m.to}</span>
              <b>{m.subject}</b>
              <p>{m.body}</p>
            </article>
          ))}
        </section>

        <section className="card">
          <h3>Notifications</h3>
          {ws?.notifications.map((n) => (
            <div key={n.id} className={`note ${n.level}`}>
              <span className="chan">{n.channel}</span>
              {n.text}
            </div>
          ))}
        </section>
      </div>
    </main>
  );
}
