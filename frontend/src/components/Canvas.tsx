import { useState } from "react";
import { OP, pretty, SERVER_COLOR, type TraceStep, type Workflow } from "../api";

const TRIGGER_TEXT = (w: Workflow) =>
  w.trigger.type === "file"
    ? `When a file matching ${w.trigger.pattern || "*"} lands in ${w.trigger.folder}/`
    : w.trigger.type === "schedule"
      ? `Every ${w.trigger.every_minutes} minute${w.trigger.every_minutes === 1 ? "" : "s"}`
      : "When you press Run";

function Json({ value }: { value: unknown }) {
  return <pre className="json">{JSON.stringify(value, null, 2)}</pre>;
}

/** The workflow as a vertical flow of cards, with dry-run results on each node. */
export function Canvas({ workflow, trace }: { workflow: Workflow; trace?: TraceStep[] }) {
  const [open, setOpen] = useState<string | null>(null);
  const result = (id: string) => trace?.find((t) => t.id === id);

  return (
    <div className="canvas">
      <div className="node trigger">
        <span className="kind">Trigger</span>
        <b>{TRIGGER_TEXT(workflow)}</b>
      </div>
      {workflow.steps.map((step, i) => {
        const r = result(step.id);
        const server = step.kind === "llm" ? "llm" : step.tool.split(".")[0];
        const color = SERVER_COLOR[server] ?? "sky";
        return (
          <div key={step.id} className="link-wrap" style={{ animationDelay: `${i * 60}ms` }}>
            <div className={`edge ${step.when ? "gated" : ""}`}>
              {step.when && (
                <span className="gate">
                  only if {pretty(step.when.left)} {OP[step.when.op] ?? step.when.op} {step.when.right}
                </span>
              )}
            </div>
            <button className={`node ${color} ${r?.status ?? ""} ${open === step.id ? "open" : ""}`} onClick={() => setOpen(open === step.id ? null : step.id)}>
              <span className="kind">
                {step.kind === "llm" ? "AI step" : step.tool}
                {r && <i className={`badge ${r.status}`}>{r.status === "ok" ? `✓ ${r.ms ?? 0} ms` : r.status}</i>}
              </span>
              <b>{step.title}</b>
              {step.kind === "llm" ? (
                <span className="detail">returns {step.fields.map((f) => f.name).join(", ")}</span>
              ) : (
                <span className="detail">{step.args.map((a) => a.name).join(" · ")}</span>
              )}
              {r?.status === "failed" && <span className="err">{r.error}</span>}
            </button>
            {open === step.id && (
              <div className="inspect">
                {step.kind === "llm" ? (
                  <>
                    <h4>Instruction</h4>
                    <p>{step.instruction}</p>
                    <h4>Reads</h4>
                    <code>{step.input}</code>
                    <h4>Returns</h4>
                    <ul>
                      {step.fields.map((f) => (
                        <li key={f.name}>
                          <code>{f.name}</code> <em>{f.type}</em> {f.description}
                        </li>
                      ))}
                    </ul>
                  </>
                ) : (
                  <>
                    <h4>Arguments</h4>
                    <ul>
                      {step.args.map((a) => (
                        <li key={a.name}>
                          <code>{a.name}</code> = <span className="val">{a.value}</span>
                        </li>
                      ))}
                    </ul>
                  </>
                )}
                {r?.input !== undefined && (
                  <>
                    <h4>Dry-run input</h4>
                    <Json value={r.input} />
                  </>
                )}
                {r?.output !== undefined && (
                  <>
                    <h4>Dry-run output</h4>
                    <Json value={r.output} />
                  </>
                )}
                {r?.status === "skipped" && <p className="muted">Skipped: condition {r.reason} was false.</p>}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
