// Pass 1 of the promo: run the real FlowMind (the API with the scripted model and its MCP servers, and the Vite UI),
// drive it like a user would, and save DOM snapshots of each moment to promo/out/snaps. Pass 2 (kit/render.mjs)
// films them.
//
//   cd promo && pnpm install && node capture.mjs
import { readFileSync, rmSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { freePort, launch, serve, sleep, snapper, until } from "./kit/snap.mjs";

const ROOT = resolve(import.meta.dirname, "..");
const SNAPS = resolve(import.meta.dirname, "out/snaps");
rmSync(SNAPS, { recursive: true, force: true });
const data = resolve(import.meta.dirname, "out/data");
rmSync(data, { recursive: true, force: true });

const api = await freePort();
const web = await freePort();
const stopApi = await serve("uv", ["run", "flowmind", "serve", "--port", String(api)], {
  cwd: resolve(ROOT, "backend"),
  env: { FLOWMIND_LLM: "scripted", FLOWMIND_SCRIPTED_DELAY: "0.06", FLOWMIND_DATA_DIR: data, FLOWMIND_TICK_SECONDS: "1" },
  url: `http://127.0.0.1:${api}/api/health`,
});
const stopWeb = await serve("pnpm", ["exec", "vite", "--host", "127.0.0.1", "--port", String(web), "--strictPort"], {
  cwd: resolve(ROOT, "frontend"),
  env: { FLOWMIND_API: `http://127.0.0.1:${api}` },
  url: `http://127.0.0.1:${web}/`,
});

try {
  const { browser, page } = await launch();
  await page.goto(`http://127.0.0.1:${web}/`);
  await until(page, () => document.querySelectorAll(".registry .server").length >= 4);
  await sleep(500);
  const shot = snapper(page, SNAPS);

  /** Snapshot every `every` ms until done() is true in the page, then once more when it settles. */
  async function seq(prefix, done, { every = 250, max = 80, settle = 900 } = {}) {
    let i = 0;
    for (; i < max; i++) {
      await shot(`${prefix}-${String(i).padStart(2, "0")}`);
      if (await page.evaluate(done)) break;
      await sleep(every);
    }
    await sleep(settle);
    await shot(`${prefix}-done`);
    console.log(`${prefix}: ${i + 1} frames`);
  }

  // 1. Describe: the home page, empty and then with the process typed in.
  await shot("home");
  // The tool registry, centred. The page ends just below it, so give it room to scroll (blank space only).
  await page.evaluate(() => {
    document.querySelector("main").style.paddingBottom = "600px";
    document.querySelector(".registry").scrollIntoView({ block: "center" });
  });
  await sleep(300);
  await shot("registry");
  await page.evaluate(() => {
    document.querySelector("main").style.paddingBottom = "";
    scrollTo(0, 0);
  });
  const PROCESS = "When a new invoice lands in the inbox, log it to the ledger, alert finance if it's over 5,000, email the vendor to confirm we got it, and file it away.";
  await page.click(".ask textarea");
  await page.keyboard.type(PROCESS, { delay: 4 });
  await sleep(200);
  await shot("home-typed");

  // 2. Build: analyse, design, validate, fix, dry run, streamed into the build view.
  await page.click(".ask .btn.primary");
  await until(page, () => location.pathname.startsWith("/w/"));
  await seq("build", () => !document.querySelector(".pill.building"), { every: 250 });
  const wid = await page.evaluate(() => location.pathname.split("/").pop());
  // The canvas lower down, scrolled into view.
  await page.evaluate(() => scrollTo(0, document.querySelector(".board").getBoundingClientRect().top + scrollY - 90));
  await sleep(300);
  await shot("canvas");
  // The dry-run verdict under the canvas, centred.
  await page.evaluate(() => document.querySelector(".dry").scrollIntoView({ block: "center" }));
  await sleep(300);
  await shot("sandbox");
  // Open the AI step at the canvas's scroll (the film scrolls down to its dry-run output): its instruction, typed
  // fields, and what it read and returned in the dry run.
  await page.evaluate(() => scrollTo(0, document.querySelector(".board").getBoundingClientRect().top + scrollY - 90));
  const extract = () => [...document.querySelectorAll(".canvas .node")].find((n) => n.textContent.includes("Pull out the key fields")).click();
  await page.evaluate(extract);
  await sleep(500);
  await shot("inspect");
  await page.evaluate(extract);
  await page.evaluate(() => scrollTo(0, 0));
  await sleep(400);

  // 3. Deploy, then watch the waiting invoice get handled on the Live page.
  await shot("ready");
  await page.click(".actions .btn.primary");
  await until(page, () => document.querySelector(".pill.deployed"));
  await sleep(300);
  await shot("deployed");
  await page.click(".actions .btn.ghost");
  await until(page, () => document.querySelector(".ledger tbody tr"));
  await seq("live", () => document.querySelectorAll(".ledger tbody tr").length >= 2 && !document.querySelector(".files:not(.done) li:not(.muted)"), { every: 250, settle: 600 });

  // 4. Drop another invoice and watch the ledger, outbox and notifications change.
  await sleep(3800); // let the toast clear
  await shot("drop");
  await page.click(".drops .chip");
  await seq("drop", () => document.querySelectorAll(".ledger tbody tr").length >= 3 && !document.querySelector(".files:not(.done) li:not(.muted)"), { every: 250, settle: 400 });

  // 5. Monitoring: someone renames a ledger column under the deployed workflow; the next run fails and raises an alert.
  await sleep(3800);
  const ledger = resolve(data, "workspace/ledger.csv");
  writeFileSync(ledger, readFileSync(ledger, "utf8").replace(/^vendor,invoice,amount,/, "vendor,invoice,total,"));
  await page.click(".drops .chip:nth-child(2)");
  await until(page, () => document.querySelector(".alert"), null, 30000);
  await sleep(800);
  await shot("alert");

  console.log(`workflow ${wid}`);
  await browser.close();
  console.log(`${shot.names.length} snapshots in promo/out/snaps`);
} finally {
  stopWeb();
  stopApi();
}
process.exit(0);
