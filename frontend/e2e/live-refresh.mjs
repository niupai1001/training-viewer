import { chromium } from "playwright-core";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";

const baseUrl = process.env.TRAINING_VIEWER_URL ?? "http://127.0.0.1:8799/";
const executablePath =
  process.env.CHROME_PATH ?? "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const name = `live-refresh-${Date.now()}`;
const root = path.resolve("../.devtools", name);
fs.mkdirSync(root, { recursive: true });
const logFile = path.join(root, `${name}.jsonl`);
fs.writeFileSync(logFile, `${JSON.stringify({ phase: "train", step: 1, loss: 1.0 })}\n`);

const add = await fetch(`${baseUrl}api/v1/roots`, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({ path: root }),
});
if (!add.ok) {
  throw new Error(`add root failed: ${add.status} ${await add.text()}`);
}
const rootId = (await add.json()).id;
for (let attempt = 0; attempt < 30; attempt += 1) {
  const listed = await fetch(`${baseUrl}api/v1/runs?q=${encodeURIComponent(name)}`).then((response) =>
    response.json(),
  );
  if (listed.runs.some((run) => run.name === name)) {
    break;
  }
  await new Promise((resolve) => setTimeout(resolve, 500));
}

const browser = await chromium.launch({
  executablePath,
  headless: true,
  args: ["--no-sandbox", "--disable-gpu", "--no-proxy-server"],
});
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: "训练工作区", exact: true }).waitFor();
  await page
    .locator(".run-selector-name")
    .filter({ hasText: new RegExp(`^${name}$`) })
    .click();
  const lossCard = page.locator(".summary-card").filter({ hasText: "Train Loss" });
  await lossCard.locator("strong").waitFor();
  await page.waitForFunction(() =>
    Array.from(document.querySelectorAll(".summary-card"))
      .find((card) => card.textContent?.includes("Train Loss"))
      ?.querySelector("strong")?.textContent?.includes("1"),
  );

  fs.appendFileSync(logFile, `${JSON.stringify({ phase: "train", step: 2, loss: 0.8 })}\n`);
  await page.waitForFunction(() =>
    Array.from(document.querySelectorAll(".summary-card"))
      .find((card) => card.textContent?.includes("Train Loss"))
      ?.querySelector("strong")?.textContent?.includes("0.8"),
  );
  console.log("Imported JSONL live refresh passed");
} finally {
  await fetch(`${baseUrl}api/v1/roots/${rootId}`, { method: "DELETE" });
  await browser.close();
  fs.rmSync(root, { recursive: true, force: true });
}
