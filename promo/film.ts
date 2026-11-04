// FlowMind's promo: the problem, the product, then each feature given room on the real UI (DOM snapshots from
// capture.mjs), and what's under the hood. Airy and light like the app's own node canvas. 124 bpm; shots are
// counted in beats.
import { big, chips, eyebrow, grad, makeFilm, sub } from "./kit/film";

// The app's favicon, large: three nodes joined on a violet tile.
const logo = `<svg width="150" height="150" viewBox="0 0 32 32" style="margin:0 auto;display:block;filter:drop-shadow(0 26px 40px rgba(108,92,231,.38))"><rect width="32" height="32" rx="9" fill="#6c5ce7"/><circle cx="9" cy="10" r="3" fill="#fff"/><circle cx="23" cy="16" r="3" fill="#ffd6a5"/><circle cx="9" cy="22" r="3" fill="#b8f2e6"/><path d="M12 10c6 0 6 6 8 6M12 22c6 0 6-6 8-6" stroke="#fff" stroke-width="1.6" fill="none"/></svg>`;
// The app's dotted canvas behind every light card.
const dots = (bg: string, dot = "#d7daea") => `radial-gradient(${dot} 1.6px, transparent 1.8px) 0 0 / 34px 34px, ${bg}`;
const INK = "#1c1d29";
const { word, ui, run, BEAT } = makeFilm({
  name: "flowmind",
  style: "air",
  bpm: 124,
  bgs: {
    light: [dots("#f6f7fb"), INK],
    dark: [dots(INK, "#2c2e40"), "#f6f7fb"],
    lilac: [dots("#f3e8ff", "#e4d2fb"), INK],
    sky: [dots("#e3f1ff", "#cbe2fb"), INK],
    mint: [dots("#ddf7ee", "#c3ecdd"), INK],
    peach: [dots("#ffeedd", "#f7dcc2"), INK],
  },
  grad: "linear-gradient(90deg, #6c5ce7, #c86fd6 55%, #ff9f8c)",
  font: `"Inter", -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Helvetica, Arial, sans-serif`,
  stage: "radial-gradient(1000px 640px at 22% 18%, #e9e5ff, transparent 70%), radial-gradient(900px 620px at 82% 86%, #ffe9dc, transparent 70%), radial-gradient(800px 600px at 85% 12%, #ddf7ee, transparent 70%), #f6f7fb",
  caption: { bg: "rgba(255, 255, 255, .86)", ink: INK, shadow: "0 22px 50px -22px rgba(108, 92, 231, .45), 0 0 0 1px rgba(28, 29, 41, .07)" },
  logo,
  css: `
    #camera.window { box-shadow: 0 50px 120px -36px rgba(108, 92, 231, .45), 0 0 0 1px rgba(28, 29, 41, .08); }
    #ring { box-shadow: 0 0 0 3px #6c5ce7, 0 0 0 9px rgba(108, 92, 231, .2), 0 18px 50px -12px rgba(108, 92, 231, .5); }
    #ripple { background: rgba(108, 92, 231, .35); box-shadow: 0 0 0 2px rgba(108, 92, 231, .5); }
    #type .chips span { border-color: rgba(28, 29, 41, .18); background: #fff; }
    #type[data-bg=dark] .sub { opacity: .72; }
  `,
});
const C = { x: 960, y: 540 };
/** Snapshots prefix-a … prefix-b, one every `every` seconds from `from`. */
const frames = (prefix: string, a: number, b: number, from = 0, every = 0.3): [number, string][] =>
  Array.from({ length: b - a + 1 }, (_, k) => [from + k * every, `${prefix}-${String(a + k).padStart(2, "0")}`]);

// The build streams in phases; find each phase by what's on screen, since the frame count varies run to run.
const SNAPS = (window as unknown as { SNAPS: Record<string, string> }).SNAPS;
const BUILD = Object.keys(SNAPS).filter((n) => /^build-\d+$/.test(n)).sort();
const firstWith = (text: string) => BUILD.findIndex((n) => SNAPS[n].includes(text));
const PROBLEMS = firstWith('class="problems"'); // the validator's findings
const FIXED = firstWith("valid against the tool registry"); // the fix passed validation
const BADGE = firstWith('class="badge'); // the dry run's first finished step
const LAST = BUILD.length - 1;

// The hook: what's broken.
word(4, big("Every team has a process someone still does by hand.", "s"), "light");
word(5, `${big("Automating it means wiring tools together.", "s")}${sub("Then finding out on real data what you got wrong.")}`, "light");
word(4, big(`What if you could just ${grad("describe it?")}`, "s"), "light");
word(3, big("And know it works before it runs.", "s"), "light");
// The product.
word(7, `${logo}${big("FlowMind")}${sub("Describe the process. Get the automation.")}`, "light", { mark: "reveal", hit: true });
ui(5, { snap: "home", cam: [0.7, C, 0.78, C] });

// 1. Describe.
word(5, `${eyebrow("01 · Describe")}${big("Say it like you'd tell a colleague.", "s")}${sub("A trigger, the steps, the rules. In plain words.")}`, "lilac");
const PROCESS = "When a new invoice lands in the inbox, log it to the ledger, alert finance if it's over 5,000, email the vendor to confirm we got it, and file it away.";
ui(12, {
  snap: [[0, "home"], [4.3, "home-typed"]],
  type: { sel: ".ask textarea", text: PROCESS, from: 0.4, to: 4.2, until: 4.3 },
  cursor: { path: [[0, { x: 1100, y: 700 }], [4.4, ".ask .btn.primary"], [5.2, ".ask .btn.primary"]], click: [4.8] },
  cam: [1.6, { x: 810, y: 610 }, 1.7, { x: 810, y: 610 }],
  caption: ["Describe", "A process, in plain words"],
});
ui(10, {
  snap: frames("build", 0, PROBLEMS - 1, 0, 0.25),
  cam: [1.55, { x: 640, y: 480 }, 1.75, { x: 600, y: 640 }],
  ring: [{ sel: ".understanding .card:nth-child(2)", from: 2.6 }],
  caption: ["Understand", "Steps, rules and assumptions"],
});

// 2. Design.
word(5, `${eyebrow("02 · Design")}${big("It designs the workflow.", "m")}${sub("On real MCP tools, read live from their own schemas.")}`, "sky");
ui(10, { snap: "registry", cam: [2.4, { x: 770, y: 535 }, 2.4, { x: 915, y: 535 }], caption: ["Real tools", "A registry built from four MCP servers"] });
ui(11, { snap: "canvas", cam: [1.02, { x: 960, y: 560 }, 1.5, { x: 1142, y: 520 }], caption: ["The workflow", "Every step on one canvas"] });
ui(12, {
  snap: [[0, "canvas"], [1.3, "inspect"]],
  cursor: { path: [[0, { x: 1500, y: 700 }], [1.0, { x: 1180, y: 400 }], [2.2, { x: 1180, y: 400 }], [3.2, { x: 1500, y: 760 }]], click: [1.15] },
  scroll: { sel: "html", px: [204, 680], at: [2.4, 4.8] },
  cam: [1.6, { x: 1142, y: 560 }, 1.6, { x: 1142, y: 560 }],
  caption: ["AI steps", "Typed fields, checked in the dry run"],
});
ui(9, { snap: "canvas", cam: [1.7, ".edge.gated .gate", 2.0, ".edge.gated .gate"], ring: [{ sel: ".edge.gated .gate", from: 1.0 }], caption: ["Business rules", "A step runs only when its rule holds"] });

// 3. The hero: it tests itself before it's trusted.
word(4, big("Most automations get tested in production.", "s"), "dark", { mark: "heroIn" });
word(3, big("On your real data.", "m"), "dark");
word(5, `${eyebrow("03 · Test")}${big(grad("This one tests itself first."), "s")}${sub("Checked against every tool's schema, then run in a sandbox.")}`, "dark", { mark: "hero", hit: true });
ui(13, {
  snap: [[0, BUILD[PROBLEMS]], [3.2, BUILD[FIXED]]],
  cam: [1.9, { x: 560, y: 450 }, 1.6, { x: 820, y: 640 }],
  ring: [{ sel: ".problems", from: 0.8, to: 3.2 }, { sel: ".canvas .link-wrap:nth-of-type(5) .node", from: 4.4 }],
  caption: ["Validate, then fix", "Caught by the validator, repaired by the designer"],
});
ui(12, { snap: [[0, BUILD[FIXED]], ...frames("build", BADGE - 1, LAST, 1.4, 0.4)], cam: [1.15, { x: 1142, y: 640 }, 1.45, { x: 1142, y: 560 }], caption: ["Dry run", "Every step, on real tools"] });
ui(9, { snap: "sandbox", cam: [1.5, { x: 1142, y: 900 }, 1.6, { x: 1142, y: 900 }], ring: [{ sel: ".dry", from: 1.0 }], caption: ["Sandboxed", "A throwaway copy. Nothing real touched."] }, { mark: "heroEnd" });

// 4. Deploy.
word(5, `${eyebrow("04 · Deploy")}${big("One click, and it's live.", "m")}${sub("Nothing deploys until it has passed a dry run.")}`, "mint");
ui(10, {
  snap: [[0, "ready"], [1.7, "deployed"]],
  cursor: { path: [[0, { x: 900, y: 420 }], [1.2, ".actions .btn.primary"], [2.4, ".actions .btn.primary"], [3.4, { x: 820, y: 330 }]], click: [1.4] },
  cam: [1.9, { x: 700, y: 220 }, 2.0, { x: 700, y: 220 }],
  ring: [{ sel: ".pill.deployed", from: 2.1 }],
  caption: ["Deploy", "It watches the inbox from now on"],
});
ui(11, { snap: [[0, "live-00"], [1.2, "live-01"], [1.6, "live-done"]], cam: [1.3, { x: 960, y: 400 }, 1.4, { x: 960, y: 420 }], ring: [{ sel: ".ledger tr.new", from: 2.0 }], caption: ["Live", "The waiting invoice, handled"] });

// 5. Monitor.
word(5, `${eyebrow("05 · Monitor")}${big("Then it watches every run.", "s")}${sub("Failures, slow runs and extraction drift, checked against the dry run.")}`, "peach");
ui(13, {
  snap: [[0, "drop"], [1.4, "drop-00"], ...frames("drop", 1, 4, 1.7, 0.3), [3.2, "drop-done"]],
  cursor: { path: [[0, { x: 760, y: 520 }], [1.0, ".drops .chip"], [1.8, ".drops .chip"], [2.8, { x: 900, y: 560 }]], click: [1.2] },
  cam: [1.7, { x: 680, y: 330 }, 1.15, { x: 960, y: 640 }],
  caption: ["The real workspace", "Logged, confirmed, flagged for finance"],
});
ui(11, { snap: "alert", cam: [1.45, { x: 960, y: 360 }, 1.6, { x: 960, y: 330 }], ring: [{ sel: ".alert", from: 1.0 }], caption: ["Alerts", "A renamed ledger column, caught on the next run"] });

// The angles: how it's built, and who it's for.
word(8, `${eyebrow("Under the hood")}${big("The model designs it once. Code runs it every time.", "s")}${chips("MCP over stdio", "LangGraph", "Structured outputs", "Sandboxed dry runs", "Mail drafted, never sent", "End-to-end evals")}`, "light");
word(7, `${big("For ops teams, automation in plain words.", "s")}${sub("For engineers, a reference for agents that act on real tools, safely.")}`, "lilac");
word(8, `${logo}${big(grad("FlowMind"))}${sub("Describe the process · by Balaji Sri Raj")}`, "light", { mark: "outro" });

run((m) => ({ teaser: [m.reveal, m.reveal + 44 * BEAT], poster: [m.hero + 5 * BEAT + 13 * BEAT + 9 * BEAT, 0] }));
