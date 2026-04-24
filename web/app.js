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
const PANE_META = {
  main: "TA回我了",
  archive: "角色档案",
  personality: "恋爱人格",
  settings: "设置",
};

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

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
    if (!res.ok) throw Object.assign(new Error(data.error || "请求失败"), { data });
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
  const aliases = { setup: "settings", decrypt: "main", contact: "main", analysis: "main", report: "main" };
  name = aliases[name] || name;
  document.body.dataset.pane = name;
  document.querySelectorAll(".nav-item").forEach((el) => el.classList.toggle("active", el.dataset.step === name));
  document.querySelectorAll(".pane").forEach((el) => el.classList.toggle("visible", el.id === `pane-${name}`));
  $("panelTitle").textContent = PANE_META[name] || PANE_META.main;
}

function renderStatus(status, options = {}) {
  const { loadLatestReport = true } = options;
  state.status = status;
  if ($("runtimePath")) $("runtimePath").textContent = status.runtime_root || "-";
  if ($("llmState")) $("llmState").textContent = status.llm_configured ? `${status.llm_provider || "openai"} · ${status.llm_model || "已配置"}` : "未配置";
  if ($("environmentBadge")) {
    $("environmentBadge").textContent = status.environment_label || (status.environment_ready ? "环境就绪" : "环境异常");
    $("environmentBadge").classList.toggle("bad", !status.environment_ready);
  }

  if ($("llmProvider")) $("llmProvider").value = status.llm_provider || "openai";
  if ($("llmBaseUrl")) $("llmBaseUrl").value = status.llm_base_url || "";
  if ($("llmModel")) $("llmModel").value = status.llm_model || "";
  if ($("configHint")) {
    $("configHint").textContent = `当前：${status.llm_provider || "openai"} · ${status.llm_base_url || "未设置 BaseURL"} · ${status.llm_model || "未设置模型"} · ${status.llm_key_hint || "未设置"}`;
  }

  const strip = $("runtimeStatus");
  strip.querySelector("i").className = status.environment_ready ? "ok" : "bad";
  strip.querySelector("span").textContent = status.environment_label || (status.environment_ready ? "环境就绪" : "环境异常");
  renderArchives(status.archives || []);
  if (loadLatestReport && status.latest_report) setReport(status.latest_report, { silent: true });
}

function clearMainAnalysis() {
  state.latestReportUrl = "";
  const openReport = $("openReport");
  if (openReport) {
    openReport.href = "#";
    delete openReport.dataset.href;
    openReport.setAttribute("aria-disabled", "true");
    openReport.classList.add("disabled");
  }
  if ($("reportSlot")) $("reportSlot").textContent = "暂无报告。";
  const stage = $("reportStage");
  if (stage) stage.classList.remove("has-report");
  const mount = $("reportMount");
  if (mount) {
    if (mount.shadowRoot) mount.shadowRoot.innerHTML = "";
    mount.innerHTML = "";
  }
  if ($("analysisPreview")) $("analysisPreview").textContent = "尚未生成分析。";
}

function renderArchives(archives) {
  const el = $("archives");
  if (!el) return;
  if (!archives.length) {
    el.innerHTML = `<div class="archive-empty">暂无角色档案。完成一次识别并生成报告后，会自动存档在这里。</div>`;
    return;
  }
  el.innerHTML = archives.map((item, index) => {
    const contact = item.contact || "未命名";
    const count = item.message_count ? `${Number(item.message_count).toLocaleString()} 条消息 · ` : "";
    return `
      <article class="archive-card" data-index="${index}">
        <button class="archive-open" type="button">
          <span>${esc(item.relationship_type || "角色档案")}</span>
          <strong title="${esc(contact)}">${esc(contact)}</strong>
          <p>${count}${formatArchiveDate(item.created_at)}</p>
        </button>
        <button class="archive-delete" type="button" aria-label="删除 ${esc(contact)} 的档案">删除</button>
      </article>
    `;
  }).join("");
  el.querySelectorAll(".archive-open").forEach((button) => {
    button.addEventListener("click", () => {
      const item = archives[Number(button.closest(".archive-card").dataset.index)];
      if (item?.report_url) {
        setReport({ name: item.report_name || "报告", url: item.report_url });
        switchPane("main");
      }
    });
  });
  el.querySelectorAll(".archive-delete").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      const item = archives[Number(button.closest(".archive-card").dataset.index)];
      deleteArchive(item).catch(handleError);
    });
  });
}

function formatArchiveDate(value) {
  if (!value) return "未知时间";
  return String(value).replace("T", " ").slice(0, 16);
}

async function deleteArchive(item) {
  if (!item) return;
  log(`删除角色档案：${item.contact || item.report_name || item.id}`);
  const data = await api("/api/archive/delete", {
    method: "POST",
    body: { id: item.id, report_name: item.report_name },
  });
  renderStatus(data.status, { loadLatestReport: false });
  clearMainAnalysis();
  log("角色档案已删除", data.deleted);
}

function setReport(report, options = {}) {
  const url = `${API_BASE}${encodeURI(report.url)}`;
  state.latestReportUrl = url;
  const openReport = $("openReport");
  if (openReport) {
    openReport.href = url;
    openReport.dataset.href = url;
    openReport.removeAttribute("aria-disabled");
    openReport.classList.remove("disabled");
  }
  $("reportSlot").innerHTML = `当前报告：<button class="inline-report-link" id="reloadReportBtn">${esc(report.name)}</button>`;
  $("reloadReportBtn")?.addEventListener("click", () => showReport(url));
  showReport(url).catch(handleError);
  if (!options.silent) log("报告已载入当前页面。");
}

async function loadScriptOnce(src) {
  if (document.querySelector(`script[data-report-src="${CSS.escape(src)}"]`)) return;
  await new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = src;
    script.dataset.reportSrc = src;
    script.onload = resolve;
    script.onerror = reject;
    document.head.appendChild(script);
  });
}

function adaptReportCss(css, bodyClass) {
  return css
    .replaceAll(":root", ":host")
    .replaceAll("html", ":host")
    .replace(/body\.report-tone-/g, ".report-document.report-tone-")
    .replace(/body::/g, ".report-document::")
    .replace(/body\s*\{/g, ".report-document {")
    .concat(`
      :host { display:block; contain: content; }
      .report-document { min-height: 100%; overflow: visible; }
      .report-document::before,
      .report-document::after { position: absolute; }
    `);
}

async function showReport(url) {
  const mount = $("reportMount");
  const stage = $("reportStage");
  if (!mount || !stage) return;
  stage.classList.add("has-report");
  const shadow = mount.shadowRoot || (mount.attachShadow ? mount.attachShadow({ mode: "open" }) : null);
  const root = shadow || mount;
  root.innerHTML = "";
  const html = await fetch(url).then((res) => {
    if (!res.ok) throw new Error("报告读取失败");
    return res.text();
  });
  const doc = new DOMParser().parseFromString(html, "text/html");
  const scripts = [...doc.querySelectorAll("script")];
  const styles = [...doc.querySelectorAll("style")].map((style) => style.textContent || "").join("\n");
  const externalScripts = scripts.map((script) => script.src).filter(Boolean);
  const inlineScripts = scripts.filter((script) => !script.src).map((script) => script.textContent || "");
  scripts.forEach((script) => script.remove());
  const bodyClass = doc.body.className || "";

  root.innerHTML = `
    <style>${adaptReportCss(styles, bodyClass)}</style>
    <div class="report-document ${esc(bodyClass)}">${doc.body.innerHTML}</div>
  `;
  for (const src of externalScripts) await loadScriptOnce(src);
  for (const code of inlineScripts) {
    new Function("document", "window", "Chart", code)(root, window, window.Chart);
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
        <strong title="${esc(name)}">${esc(name)}</strong>
        <span>${Number(item.message_count || 0).toLocaleString()} 条 · ${esc(item.username)}</span>
      </button>
    `;
  }).join("");
}

async function refreshStatus() {
  renderStatus(await api("/api/status"));
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
  log("保存模型接口配置");
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

const UI_THEMES = ["neon", "cyan", "ember"];

function normalizeUiTheme(theme) {
  return UI_THEMES.includes(theme) ? theme : "neon";
}

function applyUiTheme(theme) {
  const selected = normalizeUiTheme(theme);
  document.body.classList.remove("ui-neon", "ui-cyan", "ui-ember", "ui-rose", "ui-blue", "ui-graphite", "ui-gold", "ui-minimal");
  document.body.classList.add(`ui-${selected}`);
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

async function loadContacts() {
  log("读取联系人列表");
  const data = await api("/api/contacts", { method: "POST" });
  state.contacts = data.contacts || [];
  state.selected = null;
  $("extractBtn").disabled = true;
  renderContacts();
  switchPane("main");
  log(`读取到 ${state.contacts.length} 个联系人`);
}

async function discoverWechat() {
  log("开始识别微信：检查环境、解密数据库、扫描联系人");
  const data = await api("/api/discover", { method: "POST" });
  renderStatus(data.status);
  state.contacts = data.contacts || [];
  state.selected = null;
  $("extractBtn").disabled = true;
  renderContacts();
  switchPane("main");
  log(`微信识别完成，读取到 ${state.contacts.length} 个联系人`);
}

async function extractAndStats() {
  if (!state.selected) return;
  const contact = state.selected.display_name || state.selected.username;
  log(`提取联系人：${contact}`);
  const extracted = await api("/api/extract", { method: "POST", body: { contact } });
  log("消息提取完成", extracted.result.json || extracted.result.stderr);
  const stats = await api("/api/stats", { method: "POST" });
  log("统计完成", stats.stats.scores || stats.result.stdout);
}

async function runSubtextScan() {
  log("调用模型生成潜台词扫描");
  const data = await api("/api/analyze", { method: "POST", body: { use_llm: true } });
  renderStatus(data.status);
  $("analysisPreview").textContent = JSON.stringify(data.analysis, null, 2);
  log("analysis.json 已生成", { mode: data.analysis._analysis_mode });
  return data;
}

async function analyze() {
  await runSubtextScan();
}

async function report() {
  log("先执行潜台词扫描，再生成报告");
  await runSubtextScan();
  const data = await api("/api/report", { method: "POST" });
  renderStatus(data.status);
  setReport(data.report);
  log("报告已生成", data.report);
}

function bind() {
  const on = (id, event, handler) => {
    const el = $(id);
    if (el) el.addEventListener(event, handler);
  };

  document.querySelectorAll(".nav-item").forEach((button) => {
    button.addEventListener("click", () => switchPane(button.dataset.step));
  });
  on("discoverBtn", "click", () => discoverWechat().catch(handleError));
  on("saveConfigBtn", "click", () => saveConfig().catch(handleError));
  on("llmProvider", "change", (event) => applyProviderDefaults(event.target.value));
  on("llmApiKey", "paste", maskApiKeyFromPaste);
  on("llmApiKey", "input", () => {
    if ($("llmApiKey")?.value !== MASKED_KEY) state.pendingApiKey = "";
  });
  on("setupBtn", "click", () => runSetup().catch(handleError));
  on("loadContactsBtn", "click", () => loadContacts().catch(handleError));
  on("contactsRefreshBtn", "click", () => loadContacts().catch(handleError));
  on("extractBtn", "click", () => extractAndStats().catch(handleError));
  on("analyzeBtn", "click", () => analyze().catch(handleError));
  on("reportBtn", "click", () => report().catch(handleError));
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

const initialTheme = normalizeUiTheme(localStorage.getItem("ta-ui-theme"));
localStorage.setItem("ta-ui-theme-v4", "neon-stage");
applyUiTheme(initialTheme);
bind();
switchPane("main");
refreshStatus().catch(handleError);
