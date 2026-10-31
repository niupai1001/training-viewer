const vscode = require("vscode");

const APPLICATION_NAME = "training-viewer";
const HEALTH_PATH = "/api/v1/health";
const RUNS_PATH = "/api/v1/runs?limit=1000&sort=-last_updated_at";
const ROOTS_PATH = "/api/v1/roots";

function activate(context) {
  const provider = new RunsProvider();
  const treeView = vscode.window.createTreeView("trainingViewer.runs", {
    treeDataProvider: provider,
    showCollapseAll: true,
  });
  context.subscriptions.push(treeView);
  context.subscriptions.push(provider);
  context.subscriptions.push(
    treeView.onDidChangeCheckboxState((event) => {
      for (const [item, state] of event.items) {
        provider.handleCheckboxChange(
          item.id,
          state === vscode.TreeItemCheckboxState.Checked,
        );
      }
      provider.refresh();
    }),
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("trainingViewer.open", async () => {
      const folders = await vscode.window.showOpenDialog({
        canSelectFolders: true,
        canSelectFiles: false,
        canSelectMany: true,
        openLabel: "选择训练日志目录",
      });
      if (!folders || folders.length === 0) {
        return;
      }
      await openViewer(folders.map((uri) => uri.fsPath), provider);
    }),
    vscode.commands.registerCommand("trainingViewer.openCurrentFolder", async () => {
      const folders = vscode.workspace.workspaceFolders ?? [];
      if (folders.length === 0) {
        void vscode.window.showWarningMessage("当前没有打开的工作区目录。");
        return;
      }
      await openViewer(folders.map((folder) => folder.uri.fsPath), provider);
    }),
    vscode.commands.registerCommand("trainingViewer.addFolder", async () => {
      const folders = await vscode.window.showOpenDialog({
        canSelectFolders: true,
        canSelectFiles: false,
        canSelectMany: true,
        openLabel: "添加到 Training Viewer",
      });
      if (!folders || folders.length === 0) {
        return;
      }
      await openViewer(folders.map((uri) => uri.fsPath), provider);
    }),
    vscode.commands.registerCommand("trainingViewer.refreshRuns", () => provider.refresh()),
    vscode.commands.registerCommand("trainingViewer.compareSelectedRuns", async () => {
      const selected = provider.selectedRunIds();
      if (selected.length === 0) {
        void vscode.window.showInformationMessage(
          "请先在“运行与项目”列表中勾选要对比的运行。",
        );
        return;
      }
      const base = provider.serverBaseUrl();
      if (!base) {
        void vscode.window.showWarningMessage(
          "Training Viewer 服务尚未运行，请先执行“Training Viewer: 打开查看器”。",
        );
        return;
      }
      const encoded = encodeURIComponent(selected.join(","));
      await vscode.env.openExternal(
        vscode.Uri.parse(`${base}/#/compare?runs=${encoded}`),
      );
    }),
  );

  const configuration = vscode.workspace.getConfiguration("trainingViewer");
  const refreshSeconds = Math.max(5, configuration.get("autoRefreshSeconds", 10));
  const timer = setInterval(() => provider.refresh(), refreshSeconds * 1000);
  context.subscriptions.push({
    dispose: () => clearInterval(timer),
  });

  provider.refresh();
}

async function openViewer(folders, provider) {
  const configuration = vscode.workspace.getConfiguration("trainingViewer");
  const configuredPort = configuration.get("port", 8765);
  const existing = await discoverBaseUrl();
  if (existing) {
    for (const folder of folders) {
      const response = await postJson(`${existing}${ROOTS_PATH}`, { path: folder });
      if (!response.ok) {
        const detail = await safeDetail(response);
        void vscode.window.showWarningMessage(`添加目录失败 ${folder}：${detail}`);
      }
    }
    await vscode.env.openExternal(vscode.Uri.parse(`${existing}/#/runs`));
    provider.refresh();
    return;
  }

  const command = configuration.get("command", "training-viewer");
  const dataDirectory = configuration.get("dataDirectory", "").trim();
  const args = ["open", ...folders, "--port", String(configuredPort), "--no-browser"];
  if (dataDirectory) {
    args.push("--data-dir", dataDirectory);
  }
  const terminal = vscode.window.createTerminal({
    name: "Training Viewer",
    cwd: folders[0],
  });
  terminal.show();
  terminal.sendText(
    [command, ...args].map((part) => quoteForShell(part)).join(" "),
    true,
  );

  const startedBase = await waitForAnyHealth(configuredPort, 25000);
  if (startedBase) {
    await vscode.env.openExternal(vscode.Uri.parse(`${startedBase}/#/runs`));
    provider.refresh();
  } else {
    void vscode.window.showWarningMessage(
      "未在 25 秒内连接到 Training Viewer。请查看终端输出，确认已安装 training-viewer 命令。",
    );
  }
}

async function fetchHealth(base) {
  try {
    const response = await fetch(`${base}${HEALTH_PATH}`, { signal: AbortSignal.timeout(1500) });
    if (!response.ok) {
      return false;
    }
    const payload = await response.json();
    return payload.application === APPLICATION_NAME;
  } catch {
    return false;
  }
}

async function waitForAnyHealth(preferredPort, timeoutMilliseconds) {
  const deadline = Date.now() + timeoutMilliseconds;
  const ports = Array.from({ length: 12 }, (_, index) => preferredPort + index);
  while (Date.now() < deadline) {
    for (const port of ports) {
      const base = `http://127.0.0.1:${port}`;
      if (await fetchHealth(base)) {
        return base;
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 700));
  }
  return null;
}

async function postJson(url, body) {
  return fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function safeDetail(response) {
  try {
    const payload = await response.json();
    return payload.detail || `HTTP ${response.status}`;
  } catch {
    return `HTTP ${response.status}`;
  }
}

function quoteForShell(value) {
  if (/^[A-Za-z0-9_./:=\\-]+$/.test(value)) {
    return value;
  }
  return `"${value.replaceAll('"', '\\"')}"`;
}

class RunsProvider {
  constructor() {
    this._onDidChangeTreeData = new vscode.EventEmitter();
    this.onDidChangeTreeData = this._onDidChangeTreeData.event;
    this._onDidChangeCheckboxState = new vscode.EventEmitter();
    this.onDidChangeCheckboxState = this._onDidChangeCheckboxState.event;
    this.checked = new Set();
    this.runs = [];
    this.groups = [];
    this.loading = false;
    this.error = null;
    this.baseUrl = null;
  }

  dispose() {
    this._onDidChangeTreeData.dispose();
    this._onDidChangeCheckboxState.dispose();
  }

  selectedRunIds() {
    return [...this.checked];
  }

  serverBaseUrl() {
    return this.baseUrl;
  }

  refresh() {
    void this.load();
  }

  async load() {
    if (this.loading) {
      return;
    }
    this.loading = true;
    try {
      const base = await discoverBaseUrl();
      this.baseUrl = base;
      if (!base) {
        this.runs = [];
        this.groups = [];
        this.error = null;
      } else {
        const response = await fetch(`${base}${RUNS_PATH}`, {
          signal: AbortSignal.timeout(4000),
        });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const payload = await response.json();
        this.runs = payload.runs || [];
        this.groups = groupRuns(this.runs);
        this.error = null;
      }
    } catch (error) {
      this.error = error instanceof Error ? error.message : String(error);
      this.runs = [];
      this.groups = [];
    } finally {
      this.loading = false;
      this._onDidChangeTreeData.fire();
    }
  }

  getChildren(element) {
    if (!this.baseUrl) {
      return [unavailableItem(this.error)];
    }
    if (!element) {
      if (this.error) {
        return [unavailableItem(this.error)];
      }
      return this.groups.map((group) => groupItem(group));
    }
    if (element.kind === "project") {
      return element.group.experiments.map((experiment) => experimentItem(groupKey(element.group), experiment));
    }
    if (element.kind === "experiment") {
      return element.experiment.runs.map((run) =>
        runItem(run, this.checked, this.baseUrl),
      );
    }
    return [];
  }

  getTreeItem(element) {
    return element.item;
  }

  handleCheckboxChange(runId, isChecked) {
    if (isChecked) {
      this.checked.add(runId);
    } else {
      this.checked.delete(runId);
    }
  }
}

async function discoverBaseUrl() {
  const configured = vscode.workspace.getConfiguration("trainingViewer").get("port", 8765);
  const candidates = [configured, 8765, 8766, 8767, 8768, 8769];
  for (const port of [...new Set(candidates)]) {
    const base = `http://127.0.0.1:${port}`;
    if (await fetchHealth(base)) {
      return base;
    }
  }
  return null;
}

function groupRuns(runs) {
  const groups = new Map();
  for (const run of runs) {
    const project = run.project || "未命名项目";
    const experiment = run.experiment || "未分组";
    if (!groups.has(project)) {
      groups.set(project, new Map());
    }
    const experiments = groups.get(project);
    if (!experiments.has(experiment)) {
      experiments.set(experiment, []);
    }
    experiments.get(experiment).push(run);
  }
  return [...groups.entries()].map(([project, experiments]) => ({
    project,
    experiments: [...experiments.entries()].map(([name, list]) => ({ name, runs: list })),
  }));
}

function groupKey(group) {
  return `project:${group.project}`;
}

function groupItem(group) {
  const item = new vscode.TreeItem(
    `${group.project}（${group.experiments.reduce((sum, experiment) => sum + experiment.runs.length, 0)}）`,
    vscode.TreeItemCollapsibleState.Expanded,
  );
  item.contextValue = "trainingViewer.project";
  item.iconPath = new vscode.ThemeIcon("folder");
  return { kind: "project", group, item };
}

function experimentItem(projectKey, experiment) {
  const item = new vscode.TreeItem(
    `${experiment.name}（${experiment.runs.length}）`,
    vscode.TreeItemCollapsibleState.Collapsed,
  );
  item.contextValue = "trainingViewer.experiment";
  item.iconPath = new vscode.ThemeIcon("beaker");
  return { kind: "experiment", experiment, item, projectKey };
}

function runItem(run, checked, base) {
  const item = new vscode.TreeItem(run.name, vscode.TreeItemCollapsibleState.None);
  item.description = run.status_label || run.status;
  item.tooltip = `${run.name}\n状态：${run.status_label || run.status}\n${run.status_reason || ""}\n${run.run_directory || ""}`;
  item.contextValue = "trainingViewer.run";
  item.checkboxState = checked.has(run.run_id)
    ? { state: vscode.TreeItemCheckboxState.Checked }
    : { state: vscode.TreeItemCheckboxState.Unchecked };
  item.id = run.run_id;
  if (base) {
    item.command = {
      command: "vscode.open",
      title: "打开运行详情",
      arguments: [vscode.Uri.parse(`${base}/#/runs/${encodeURIComponent(run.run_id)}`)],
    };
  }
  item.iconPath = new vscode.ThemeIcon(run.status === "running" ? "pulse" : "circle-outline");
  return item;
}

function unavailableItem(error) {
  const item = new vscode.TreeItem(
    error ? `连接失败：${error}` : "Training Viewer 服务未运行",
    vscode.TreeItemCollapsibleState.None,
  );
  item.description = "点击启动";
  item.iconPath = new vscode.ThemeIcon("warning");
  item.command = {
    command: "trainingViewer.open",
    title: "启动 Training Viewer",
  };
  return item;
}

function deactivate() {}

module.exports = { activate, deactivate };
