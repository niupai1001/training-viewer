import { chromium } from "playwright-core";
import path from "node:path";
import process from "node:process";

const baseUrl = process.env.TRAINING_VIEWER_URL ?? "http://127.0.0.1:8799/";
const executablePath =
  process.env.CHROME_PATH ?? "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const screenshotDir =
  process.env.TRAINING_VIEWER_SCREENSHOT_DIR ?? path.resolve("../.devtools/e2e");

const browser = await chromium.launch({
  executablePath,
  headless: true,
  args: ["--no-sandbox", "--disable-gpu", "--no-proxy-server"],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
const errors = [];
page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));
page.on("console", (message) => {
  if (message.type() === "error") {
    errors.push(`console: ${message.text()}`);
  }
});

await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
await page.getByRole("heading", { name: "监控", exact: true }).waitFor();
await page.getByText("当前/最近训练").waitFor();
await page.locator(".metric-chart-canvas canvas").first().waitFor({ timeout: 15000 });
await page.screenshot({ path: path.join(screenshotDir, "overview.png"), fullPage: true });

await page.goto(`${baseUrl}#/runs`, { waitUntil: "domcontentloaded" });
await page.getByRole("heading", { name: "实验库", exact: true }).waitFor();
await page.locator(".experiment-table thead th").first().waitFor({ timeout: 15000 });
const defaultHeaders = await page.locator(".experiment-table thead th").allInnerTexts();
if (!defaultHeaders.includes("状态") || !defaultHeaders.includes("关键指标")) {
  throw new Error(`实验库默认列异常：${defaultHeaders.join(" | ")}`);
}
await page.screenshot({ path: path.join(screenshotDir, "experiments.png"), fullPage: true });

const firstRun = page.locator('.experiment-table tbody a[href^="#/runs/"]').first();
await firstRun.click();
await page.locator(".metric-chart-canvas canvas").first().waitFor({ timeout: 15000 });
await page.screenshot({ path: path.join(screenshotDir, "run-detail.png"), fullPage: true });

await page.goto(`${baseUrl}#/compare`, { waitUntil: "domcontentloaded" });
await page.getByRole("heading", { name: "实验对比", exact: true }).waitFor();
await page.screenshot({ path: path.join(screenshotDir, "compare.png"), fullPage: true });

await browser.close();
if (errors.length > 0) {
  console.error(errors.join("\n"));
  process.exitCode = 1;
} else {
  console.log(`UI smoke passed; screenshots in ${screenshotDir}`);
}
