// Accessibility smoke check with axe-core on every route.
// Usage (from backend-v6/webui): npm i -D puppeteer @axe-core/puppeteer
//   API_KEY=... node ../scripts/ui/a11y_check.mjs
import { createRequire } from "module";
import { pathToFileURL } from "url";
const require = createRequire(new URL("../../webui/package.json", import.meta.url));
const puppeteer = (await import(pathToFileURL(require.resolve("puppeteer")).href)).default;
const { AxePuppeteer } = require("@axe-core/puppeteer");

const API_KEY = process.env.API_KEY || "";
const ROUTES = ["/", "/chat", "/images", "/video", "/dataset", "/loras", "/jobs"];

const browser = await puppeteer.launch({ args: ["--no-sandbox", "--disable-dev-shm-usage"] });
const page = await browser.newPage();
await page.setViewport({ width: 1280, height: 900 });
await page.goto("http://127.0.0.1:8010/", { waitUntil: "domcontentloaded", timeout: 30000 });
await page.evaluate(key => {
  sessionStorage.setItem("api_key", key);
  sessionStorage.setItem("api_key_at", String(Date.now()));
}, API_KEY);

let total = 0;
for (const route of ROUTES) {
  await page.goto("http://127.0.0.1:8010" + route, { waitUntil: "networkidle2", timeout: 45000 }).catch(() => {});
  await new Promise(r => setTimeout(r, 1200));
  const results = await new AxePuppeteer(page).analyze();
  const violations = results.violations.filter(v => v.impact === "critical" || v.impact === "serious");
  total += violations.length;
  console.log(`\n${route}: ${violations.length} serious/critical violations`);
  for (const v of violations) {
    console.log(`  [${v.impact}] ${v.id}: ${v.help} (${v.nodes.length} nodes) e.g. ${v.nodes[0]?.target?.join(" ")}`);
  }
}
await browser.close();
console.log(`\nTOTAL serious/critical: ${total}`);
