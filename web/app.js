const state = {
  status: null,
  contacts: [],
  filtered: [],
  selected: null,
  busy: false,
  logs: [],
  latestReportUrl: "",
  pendingApiKey: "",
};

const $ = (id) => document.getElementById(id);
const API_BASE = window.location.protocol === "file:" ? "http://127.0.0.1:8765" : "";
const MASKED_KEY = "••••••••••••";
const PROVIDER_DEFAULTS = {
  openai: { baseUrl: "https://api.openai.com/v1", model: "gpt-4.1" },
  anthropic: { baseUrl: "https://api.anthropic.com/v1", model: "claude-3-5-sonnet-latest" },
  gemini: { baseUrl: "https://generativelanguage.googleapis.com/v1beta", model: "gemini-1.5-pro" },
};

function log(message, data) {
  const line = `[${new Date().toLocaleTimeString()}] ${message}`;
  const extra = data ? `\n${typeof data === "string" ? data : JSON.stringify(data, null, 2)}` : "";
  state.logs.unshift(`${line}${extra}`);
  state.logs = state.logs.slice(0, 80);
  if ($("logLatest")) $("logLatest").textContent = message;
  if ($("log")) $("log").textContent = state.logs.join("\n\n");
}

async function api(path, options = {}) {
  setBusy(true);
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: options.method || "GET",
      headers: { "Content-Type": "application/json" },
      body: options.body ? JSON.stringify(options.body) : undefined,
    });
    const data = await res.json();
    if (!res.ok) {
      throw Object.assign(new Error(data.error || "请求失败"), { data });
    }
    return data;
  } finally {
    setBusy(false);
  }
}

function setBusy(value) {
  state.busy = value;
  document.body.classList.toggle("busy", value);
  document.querySelectorAll("button").forEach((button) => {
    if (button.id !== "clearLog") button.toggleAttribute("aria-busy", value);
  });
}

function switchPane(name) {
  const aliases = {
    setup: "settings",
    decrypt: "main",
    contact: "main",
    analysis: "main",
    report: "main",
  };
  name = aliases[name] || name;
  document.querySelectorAll(".step").forEach((el) => el.classList.toggle("active", el.dataset.step === name));
  document.querySelectorAll(".nav-item").forEach((el) => el.classList.toggle("active", el.dataset.step === name));
  document.querySelectorAll(".pane").forEach((el) => el.classList.toggle("visible", el.id === `pane-${name}`));
  const titles = {
    main: "分析主线",
    archive: "角色档案",
    personality: "恋爱人格",
    settings: "设置",
  };
  $("panelTitle").textContent = titles[name] || "分析主线";
}

function renderStatus(status) {
  state.status = status;
  $("runtimePath").textContent = status.runtime_root || "-";
  $("llmState").textContent = status.llm_configured ? `${status.llm_provider || "openai"} · ${status.llm_model || "已配置"}` : "未配置";
  if ($("llmProvider")) $("llmProvider").value = status.llm_provider || "openai";
  if ($("llmBaseUrl")) $("llmBaseUrl").value = status.llm_base_url || "";
  if ($("llmModel")) $("llmModel").value = status.llm_model || "";
  if ($("environmentBadge")) {
    $("environmentBadge").textContent = status.environment_label || (status.environment_ready ? "环境就绪" : "环境异常");
    $("environmentBadge").classList.toggle("bad", !status.environment_ready);
  }
  if ($("configHint")) {
    const provider = status.llm_provider || "openai";
    const base = status.llm_base_url || "未设置 BaseURL";
    const key = status.llm_key_hint || "未设置";
    $("configHint").textContent = `当前：${provider} · ${base} · ${status.llm_model || "未设置模型"} · ${key}`;
  }

  const ready = status.scripts_ready;
  const strip = $("runtimeStatus");
  strip.querySelector(".dot").className = `dot ${status.environment_ready ? "ok" : "bad"}`;
  strip.querySelector("span:last-child").textContent = status.environment_label || (status.environment_ready ? "环境就绪" : "环境异常");

  renderArchives(status.archives || []);

  if (status.latest_report) {
    setReport(status.latest_report);
  }
}

function renderArchives(archives) {
  const el = $("archives");
  if (!el) return;
  if (!archives.length) {
    el.innerHTML = `<div class="archive-empty">暂无角色档案。完成一次识别并生成报告后，会自动存档在这里。</div>`;
    return;
  }
  el.innerHTML = archives.map((item, index) => `
    <button class="archive-card" data-index="${index}">
      <span>${item.relationship_type || "角色档案"}</span>
      <strong title="${item.contact || "未命名"}">${item.contact || "未命名"}</strong>
      <p>${item.message_count ? `${Number(item.message_count).toLocaleString()} 条消息 · ` : ""}${formatArchiveDate(item.created_at)}</p>
    </button>
  `).join("");
  el.querySelectorAll(".archive-card").forEach((button) => {
    button.addEventListener("click", () => {
      const item = archives[Number(button.dataset.index)];
      if (item?.report_url) {
        setReport({ name: item.report_name || "报告", url: item.report_url });
        switchPane("report");
      }
    });
  });
}

function formatArchiveDate(value) {
  if (!value) return "未知时间";
  return String(value).replace("T", " ").slice(0, 16);
}

function setReport(report) {
  const url = `${API_BASE}${encodeURI(report.url)}`;
  const openReport = $("openReport");
  state.latestReportUrl = url;
  if (openReport) {
    openReport.href = url;
    openReport.dataset.href = url;
    openReport.removeAttribute("aria-disabled");
    openReport.classList.remove("disabled");
  }
  if ($("reportSlot")) {
    $("reportSlot").innerHTML = `当前报告：<button class="inline-report-link" id="reloadReportBtn">${report.name}</button>`;
  }
  showReport(url);
  const reload = $("reloadReportBtn");
  if (reload) {
    reload.addEventListener("click", () => showReport(url));
  }
}

function showReport(url) {
  const frame = $("reportFrame");
  if (!frame || !$("reportStage")) return;
  $("reportStage").classList.add("has-report");
  if (frame.src !== url) {
    frame.src = url;
  }
}

function renderContacts() {
  const q = $("contactSearch").value.trim().toLowerCase();
  state.filtered = state.contacts.filter((item) => {
    const text = `${item.display_name || ""} ${item.nick_name || ""} ${item.remark || ""} ${item.username || ""}`.toLowerCase();
    return !q || text.includes(q);
  }).slice(0, 120);

  if (!state.filtered.length) {
    $("contactList").innerHTML = `<div class="report-slot">没有联系人。先完成解密，或换个关键词。</div>`;
    return;
  }

  $("contactList").innerHTML = state.filtered.map((item, index) => {
    const name = item.display_name || item.username;
    const selected = state.selected && state.selected.username === item.username;
    return `
      <button class="contact ${selected ? "selected" : ""}" data-index="${index}">
        <strong title="${name}">${name}</strong>
        <span>${item.message_count.toLocaleString()} 条 · ${item.username}</span>
      </button>
    `;
  }).join("");
}

async function refreshStatus() {
  const data = await api("/api/status");
  renderStatus(data);
}

async function runSetup() {
  log("开始环境检查");
  const data = await api("/api/setup", { method: "POST" });
  renderStatus(data.status);
  log("环境检查完成", data.result.json || data.result.stderr || data.result.stdout);
}

async function saveConfig() {
  const inputValue = $("llmApiKey").value.trim();
  const body = {
    provider: $("llmProvider").value,
    base_url: $("llmBaseUrl").value.trim(),
    model: $("llmModel").value.trim(),
    api_key: state.pendingApiKey || (inputValue === MASKED_KEY ? "" : inputValue),
  };
  log("保存模型中转配置");
  const data = await api("/api/config", { method: "POST", body });
  renderStatus(data.status);
  state.pendingApiKey = "";
  $("llmApiKey").value = "";
  log("模型配置已保存", data.config);
}

function applyProviderDefaults(provider) {
  const defaults = PROVIDER_DEFAULTS[provider] || PROVIDER_DEFAULTS.openai;
  $("llmBaseUrl").value = defaults.baseUrl;
  $("llmModel").value = defaults.model;
}

function applyUiTheme(theme) {
  const selected = ["theater", "neutral", "sweet"].includes(theme) ? theme : "theater";
  document.body.classList.remove("ui-neutral", "ui-sweet");
  if (selected !== "theater") {
    document.body.classList.add(`ui-${selected}`);
  }
  localStorage.setItem("ta-ui-theme", selected);
  document.querySelectorAll(".theme-choice").forEach((button) => {
    button.classList.toggle("active", button.dataset.theme === selected);
  });
}

function maskApiKeyFromPaste(event) {
  event.preventDefault();
  const pasted = event.clipboardData?.getData("text")?.trim() || "";
  if (!pasted) return;
  state.pendingApiKey = pasted;
  $("llmApiKey").value = MASKED_KEY;
  $("llmApiKey").blur();
  log("API Key 已粘贴并隐藏。");
}

async function runDecrypt() {
  log("开始解密。这一步可能需要几分钟。");
  const data = await api("/api/decrypt", { method: "POST" });
  renderStatus(data.status);
  log("解密完成", data.result.stderr || data.result.stdout);
}

async function loadContacts() {
  log("读取联系人列表");
  const data = await api("/api/contacts", { method: "POST" });
  state.contacts = data.contacts || [];
  state.selected = null;
  $("extractBtn").disabled = true;
  renderContacts();
  switchPane("contact");
  log(`读取到 ${state.contacts.length} 个联系人`);
}

async function discoverWechat() {
  log("开始一键识别微信：检查环境、解密数据库、扫描联系人");
  const data = await api("/api/discover", { method: "POST" });
  renderStatus(data.status);
  state.contacts = data.contacts || [];
  state.selected = null;
  $("extractBtn").disabled = true;
  renderContacts();
  switchPane("contact");
  log(`微信识别完成，读取到 ${state.contacts.length} 个联系人`, {
    setup: data.setup?.json || data.setup?.stderr,
    decrypt: data.decrypt?.stderr || data.decrypt?.stdout,
  });
}

async function extractAndStats() {
  if (!state.selected) return;
  const contact = state.selected.display_name || state.selected.username;
  log(`提取联系人：${contact}`);
  const extracted = await api("/api/extract", { method: "POST", body: { contact } });
  log("消息提取完成", extracted.result.json || extracted.result.stderr);
  const stats = await api("/api/stats", { method: "POST" });
  log("统计完成", stats.stats.scores || stats.result.stdout);
  switchPane("analysis");
}

async function analyze() {
  const useLlm = $("useLlm").checked;
  log(useLlm ? "调用模型生成分析" : "使用本地启发式生成分析");
  const data = await api("/api/analyze", { method: "POST", body: { use_llm: useLlm } });
  renderStatus(data.status);
  $("analysisPreview").textContent = JSON.stringify(data.analysis, null, 2);
  log("analysis.json 已生成", { mode: data.analysis._analysis_mode });
  switchPane("report");
}

async function report() {
  log("生成 HTML 报告");
  const data = await api("/api/report", { method: "POST" });
  renderStatus(data.status);
  setReport(data.report);
  log("报告已生成", data.report);
  switchPane("report");
}

function bind() {
  const on = (id, event, handler) => {
    const el = $(id);
    if (el) el.addEventListener(event, handler);
  };

  document.querySelectorAll(".step").forEach((button) => {
    button.addEventListener("click", () => switchPane(button.dataset.step));
  });
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.addEventListener("click", () => switchPane(button.dataset.step));
  });
  on("discoverBtn", "click", () => discoverWechat().catch(handleError));
  on("discoverBtn2", "click", () => discoverWechat().catch(handleError));
  on("saveConfigBtn", "click", () => saveConfig().catch(handleError));
  on("llmProvider", "change", (event) => applyProviderDefaults(event.target.value));
  on("llmApiKey", "paste", maskApiKeyFromPaste);
  on("llmApiKey", "input", () => {
    if ($("llmApiKey")?.value !== MASKED_KEY) state.pendingApiKey = "";
  });
  on("setupBtn", "click", () => runSetup().catch(handleError));
  on("decryptBtn", "click", () => runDecrypt().catch(handleError));
  on("loadContactsBtn", "click", () => loadContacts().catch(handleError));
  on("contactsRefreshBtn", "click", () => loadContacts().catch(handleError));
  on("extractBtn", "click", () => extractAndStats().catch(handleError));
  on("analyzeBtn", "click", () => analyze().catch(handleError));
  on("reportBtn", "click", () => report().catch(handleError));
  on("openReport", "click", (event) => {
    const href = $("openReport").dataset.href || $("openReport").href;
    if (!href) {
      event.preventDefault();
      log("还没有可打开的报告，请先生成报告。");
      return;
    }
    $("openReport").classList.remove("disabled");
    return;
  });
  on("consoleHead", "click", (event) => {
    if (event.target.closest("#clearLog")) return;
    $("consoleWrap").classList.toggle("expanded");
  });
  on("clearLog", "click", () => {
    state.logs = [];
    $("log").textContent = "";
    $("logLatest").textContent = "日志已清空。";
  });
  on("contactSearch", "input", renderContacts);
  on("contactList", "click", (event) => {
    const button = event.target.closest(".contact");
    if (!button) return;
    state.selected = state.filtered[Number(button.dataset.index)];
    $("extractBtn").disabled = false;
    renderContacts();
  });
  document.querySelectorAll(".theme-choice").forEach((button) => {
    button.addEventListener("click", () => applyUiTheme(button.dataset.theme));
  });
}

function handleError(error) {
  const detail = error.data?.details || error.message;
  log(`失败：${error.message}`, detail);
}

applyUiTheme(localStorage.getItem("ta-ui-theme") || "neutral");
bind();
switchPane("main");
refreshStatus().catch(handleError);
