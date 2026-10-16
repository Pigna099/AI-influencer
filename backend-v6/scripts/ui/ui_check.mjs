// Visual/responsive smoke check: verifies no horizontal overflow on every route at 812/1280/1440 px
// and saves screenshots to /tmp/ui_shots. Usage (from backend-v6/webui):
//   npm i -D puppeteer && node ../scripts/ui/ui_check.mjs && npm uninstall puppeteer
import puppeteer from 'puppeteer';

const API_KEY = "bBDAZASPSUGES0ydj8KAh-E78H3yyXWP-YgKMR7kMts";
const ROUTES = ["/", "/chat", "/images", "/video", "/dataset", "/loras", "/jobs"];
const WIDTHS = [812, 1280, 1440];

const browser = await puppeteer.launch({ args: ["--no-sandbox", "--disable-dev-shm-usage"] });
const page = await browser.newPage();
await page.goto("http://127.0.0.1:8010/", { waitUntil: "domcontentloaded", timeout: 30000 });
await page.evaluate(key => {
  sessionStorage.setItem("api_key", key);
  sessionStorage.setItem("api_key_at", String(Date.now()));
}, API_KEY);

const results = [];
for (const width of WIDTHS) {
  for (const route of ROUTES) {
    await page.setViewport({ width, height: 900, deviceScaleFactor: 1 });
    await page.goto("http://127.0.0.1:8010" + route, { waitUntil: "networkidle2", timeout: 45000 }).catch(() => {});
    await new Promise(r => setTimeout(r, 1500));
    const metrics = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      innerWidth: window.innerWidth,
      bodyScroll: document.body.scrollWidth,
    }));
    const overflow = metrics.scrollWidth > metrics.innerWidth + 2;
    results.push({ width, route, overflow, scrollWidth: metrics.scrollWidth });
    await page.screenshot({ path: `/tmp/ui_shots/${route === "/" ? "home" : route.slice(1)}-${width}.png` });
  }
}
await browser.close();
for (const row of results) {
  console.log(`${row.width}px ${row.route.padEnd(8)} overflow=${row.overflow ? "YES (" + row.scrollWidth + ")" : "no"}`);
}
