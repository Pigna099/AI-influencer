// Keyboard tab-order smoke check: presses Tab through each route and reports the focused
// elements, flagging invisible or off-viewport focus targets.
// Usage (from backend-v6/webui): npm i -D puppeteer && API_KEY=... node ../scripts/ui/tab_order_check.mjs
import { createRequire } from "module";
import { pathToFileURL } from "url";
const require = createRequire(new URL("../../webui/package.json", import.meta.url));
const puppeteer = (await import(pathToFileURL(require.resolve("puppeteer")).href)).default;

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

for (const route of ROUTES) {
  await page.goto("http://127.0.0.1:8010" + route, { waitUntil: "networkidle2", timeout: 45000 }).catch(() => {});
  await new Promise(r => setTimeout(r, 1200));
  await page.evaluate(() => document.body.focus());
  const sequence = [];
  for (let index = 0; index < 18; index++) {
    await page.keyboard.press("Tab");
    const info = await page.evaluate(() => {
      const el = document.activeElement;
      if (!el) return null;
      const rect = el.getBoundingClientRect();
      const label = (el.getAttribute("aria-label") || el.textContent || el.tagName).trim().slice(0, 40);
      return {
        tag: el.tagName.toLowerCase(),
        label,
        visible: !!(el.offsetParent || el === document.body),
        inViewport: rect.top >= -2 && rect.left >= -2 && rect.bottom <= window.innerHeight + 2 && rect.right <= window.innerWidth + 2,
      };
    });
    if (info) sequence.push(info);
  }
  const problems = sequence.filter(item => !item.visible || !item.inViewport);
  console.log(`\n${route}: ${sequence.length} stops, ${problems.length} problems`);
  console.log("  " + sequence.slice(0, 8).map(item => `${item.tag}:${item.label}`).join(" -> "));
  for (const problem of problems.slice(0, 3)) console.log("  PROBLEM", JSON.stringify(problem));
}
await browser.close();
