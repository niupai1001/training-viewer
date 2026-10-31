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

async function assertViewport(width, height, suffix) {
  const page = await browser.newPage({ viewport: { width, height } });
  const errors = [];
  page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));
  page.on("console", (message) => {
    if (message.type() === "error") {
      errors.push(`console: ${message.text()}`);
    }
  });

  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: "训练工作区", exact: true }).waitFor();
  await page.locator(".workspace-tree").waitFor();
  await page.locator(".metric-chart-canvas canvas").first().waitFor({ timeout: 15000 });
  await page.screenshot({
    path: path.join(screenshotDir, `workspace-${suffix}.png`),
    fullPage: true,
  });

  const chartBox = await page.locator(".metric-chart-canvas").first().boundingBox();
  if (chartBox) {
    await page.mouse.move(chartBox.x + chartBox.width / 2, chartBox.y + chartBox.height / 2);
    await page.mouse.wheel(0, -600);
    await page.getByText(/当前只查询/).waitFor({ timeout: 10000 });
    await page.getByRole("button", { name: "重置区间" }).click();
    await page.getByText(/当前只查询/).waitFor({ state: "hidden", timeout: 10000 });
  }

  const items = page.locator(".run-selector-item");
  const count = Math.min(await items.count(), 2);
  for (let index = 0; index < count; index += 1) {
    await items.nth(index).locator('input[type="checkbox"]').check();
  }
  await page.getByText(/个训练叠加/).waitFor({ timeout: 15000 });
  await page.locator(".metric-chart-canvas canvas").first().waitFor({ timeout: 15000 });
  await page.screenshot({
    path: path.join(screenshotDir, `comparison-${suffix}.png`),
    fullPage: true,
  });

  await page.goto(`${baseUrl}#/diagnostics`, { waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: "设置与诊断", exact: true }).waitFor();
  await page.screenshot({
    path: path.join(screenshotDir, `diagnostics-${suffix}.png`),
    fullPage: true,
  });
  await page.close();
  return errors;
}

const errors = [
  ...(await assertViewport(1440, 900, "1440x900")),
  ...(await assertViewport(1366, 768, "1366x768")),
];
await browser.close();
if (errors.length > 0) {
  console.error(errors.join("\n"));
  process.exitCode = 1;
} else {
  console.log(`UI smoke passed; screenshots in ${screenshotDir}`);
}
