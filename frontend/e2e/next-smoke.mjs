import { chromium } from "playwright-core";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
const browser = await chromium.launch({
  executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
  headless: true,
});
try {
  const page = await browser.newPage({
    viewport: { width: 1366, height: 768 },
  });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto("http://127.0.0.1:8879/#token=smoke-token");
  await page.getByRole("heading", { name: "核心指标" }).waitFor();
  await page.locator(".chart-card canvas").first().waitFor();
  await page.waitForTimeout(1500);
  assert.equal(await page.locator(".chart-card").count(), 2);
  await page.screenshot({ path: "../work/next-workspace.png", fullPage: true });
  await page
    .getByRole("button", { name: "完整过程", exact: true })
    .first()
    .click();
  await page.waitForTimeout(500);
  await page
    .getByRole("button", { name: "后期细节", exact: true })
    .first()
    .click();
  const first = page.locator(".chart-card").first();
  const box = await first.locator(".plot").boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.wheel(0, -350);
  await first.getByRole("button", { name: "返回实时" }).waitFor();
  await page.waitForTimeout(500);
  const before = await first.locator("footer").innerText();
  const headers = { "x-viewer-token": "smoke-token" };
  const selected = await (
    await page.request.get("http://127.0.0.1:8879/api/v2/settings/workspace", {
      headers,
    })
  ).json();
  const run = await (
    await page.request.get("http://127.0.0.1:8879/api/v2/runs/" + selected, {
      headers,
    })
  ).json();
  await fs.appendFile(
    run.source + "/metrics.jsonl",
    JSON.stringify({
      seq: 2000000,
      session_id: run.sessions.at(-1),
      step: 2000,
      time: new Date().toISOString(),
      values: { [run.meta.view.charts[0]]: 0.0202 },
    }) + "\n",
  );
  await page.waitForTimeout(4500);
  assert.equal(
    await first.locator("footer").innerText(),
    before,
    "new data must preserve manual zoom",
  );
  await first.getByRole("button", { name: "返回实时" }).click();
  await page.waitForTimeout(500);
  assert.equal(
    await first.getByRole("button", { name: "返回实时" }).count(),
    0,
  );
  await page.getByRole("button", { name: "全部指标", exact: false }).click();
  await page.getByRole("dialog").waitFor();
  await page.keyboard.press("Escape");
  assert.equal(await page.getByRole("dialog").count(), 0);
  await page.getByRole("button", { name: "＋ 添加实验" }).click();
  await page.getByRole("button", { name: "接入新训练", exact: true }).click();
  await page.getByPlaceholder("例如：注意力模块消融").fill("浏览器接入测试");
  await page
    .getByPlaceholder("选择包含训练记录的目录")
    .fill(process.cwd() + "/../examples-v2");
  await page.getByRole("button", { name: "生成接入代码并监视目录" }).click();
  await page.getByRole("dialog").locator("pre").waitFor();
  assert.match(
    await page.getByRole("dialog").locator("pre").innerText(),
    /RunWriter/,
  );
  await page.getByRole("button", { name: "完成", exact: true }).click();
  assert.deepEqual(errors, []);
  console.log(
    "PASS: workspace, charts, modes, drawer, keyboard, onboarding; no browser errors",
  );
} finally {
  await browser.close();
}
