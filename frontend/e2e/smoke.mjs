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
  if (await page.locator(".project-tree").count()) {
    throw new Error("工作区仍存在重复的项目树导航");
  }
  await page.locator(".workspace-tree").waitFor();
  await page.locator(".summary-card").first().waitFor({ timeout: 15000 });
  if ((await page.locator(".summary-card").count()) !== 6) {
    throw new Error("首屏六项监控摘要不完整");
  }
  if (await page.locator(".metric-chip").count()) {
    throw new Error("默认工作区仍平铺指标按钮");
  }
  await page.locator(".core-chart-card .metric-chart-canvas canvas").first().waitFor({ timeout: 15000 });
  await page.screenshot({
    path: path.join(screenshotDir, `workspace-${suffix}.png`),
    fullPage: true,
  });

  await page.getByRole("button", { name: "后期", exact: true }).click();
  await page.getByText(/后期聚焦/).waitFor({ timeout: 10000 });
  await page.getByRole("button", { name: "全程", exact: true }).click();
  await page.getByText(/后期聚焦/).waitFor({ state: "hidden", timeout: 10000 });

  await page.getByRole("button", { name: /添加图表/ }).click();
  await page.getByRole("dialog", { name: "添加图表或指标" }).waitFor();
  await page.getByRole("searchbox", { name: "搜索指标" }).fill("accuracy");
  await page.locator(".metric-row").first().waitFor({ timeout: 10000 });
  await page.locator(".metric-row input[type=checkbox]").first().check();
  await page.getByRole("button", { name: "添加为新图" }).click();
  await page.locator(".custom-chart-card").first().waitFor({ timeout: 10000 });

  const groupIndex = await page.locator(".run-selector-experiment").evaluateAll((groups) =>
    groups.findIndex((group) => group.querySelectorAll(".run-selector-item").length >= 2),
  );
  if (groupIndex >= 0) {
    const group = page.locator(".run-selector-experiment").nth(groupIndex);
    await group.locator(".run-selector-item input").nth(0).check();
    await group.locator(".run-selector-item input").nth(1).check();
  } else {
    const items = page.locator(".run-selector-item");
    await items.nth(0).locator('input[type="checkbox"]').check();
    await items.nth(1).locator('input[type="checkbox"]').check();
  }
  await page.getByText(/个训练叠加/).waitFor({ timeout: 15000 });
  await page.locator(".metric-chart-canvas canvas").first().waitFor({ timeout: 15000 });
  await page.screenshot({
    path: path.join(screenshotDir, `comparison-${suffix}.png`),
    fullPage: true,
  });

  const projectLink = page.locator(".run-selector-project h3 a").first();
  const projectName = (await projectLink.innerText()).trim();
  const escapedProject = projectName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const projectHref = await projectLink.getAttribute("href");
  await page.goto(new URL(projectHref, baseUrl).toString(), { waitUntil: "domcontentloaded" });
  await page.getByText(new RegExp(`筛选：${escapedProject}`)).waitFor({ timeout: 15000 });
  if ((await page.locator(".run-selector-project").count()) !== 1) {
    throw new Error("项目/实验组筛选没有收敛到单个项目");
  }
  await page.getByRole("link", { name: "清除" }).click();
  await page.getByText(new RegExp(`筛选：${escapedProject}`)).waitFor({
    state: "hidden",
    timeout: 15000,
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
