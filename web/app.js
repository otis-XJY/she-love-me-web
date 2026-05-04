const state = {
  status: null,
  contacts: [],
  filtered: [],
  selected: null,
  busy: false,
  logs: [],
  discoverProgressLines: [],
  latestReportUrl: "",
  pendingApiKey: "",
  quizIndex: 0,
  quizAnswers: [],
  quizDone: false,
  heroSlideIndex: 0,
  heroScrollLocked: false,
  lastScrollY: 0,
  touchStartY: 0,
  dateFrom: "",
  dateTo: "",
  dailySeries: [],
  dailyTotal: 0,
  messagesReadyContact: "",
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
const ROMAN = ["I.", "II.", "III.", "IV.", "V.", "VI.", "VII.", "VIII.", "IX.", "X."];
const QUIZ_QUESTIONS = [
  {
    question: "对方三个小时后回“刚忙完”，你的第一反应是？",
    options: [
      "松一口气。TA只是忙，逻辑合理。",
      "怀疑。谁会刚好忙到这个点？",
      "无所谓。我还没看手机。",
      "慌。先在备忘录写三版回复。",
    ],
  },
  {
    question: "连续两天都是你主动开启话题，你会怎么处理？",
    options: [
      "照常聊。关系需要稳定投入。",
      "停一下。我要看TA会不会主动找我。",
      "换个节奏。没必要把聊天当考核。",
      "反复检查上一句是不是说错了。",
    ],
  },
  {
    question: "TA发来一句很短的“嗯嗯”，你更容易读成什么？",
    options: [
      "只是简短确认，不代表态度变差。",
      "温度下降了，可能在敷衍。",
      "信息量太少，先不解读。",
      "我需要补一句，把场面救回来。",
    ],
  },
  {
    question: "你最舒服的恋爱沟通频率是？",
    options: [
      "每天有稳定交流，哪怕很短。",
      "最好频繁一点，不然会没有安全感。",
      "双方自然来，不需要固定打卡。",
      "取决于对方热不热，我会跟着调整。",
    ],
  },
  {
    question: "对方临时取消见面，你第一步会做什么？",
    options: [
      "问清原因，再一起改时间。",
      "判断是不是借口，先观察态度。",
      "接受变化，安排自己的事。",
      "忍住情绪，但心里已经排练很多句。",
    ],
  },
  {
    question: "看到TA在线但没回你，你通常会？",
    options: [
      "先做自己的事，晚点再看。",
      "开始推测TA在回谁。",
      "不太在意，在线不等于要回复。",
      "反复点开聊天框，又假装没事。",
    ],
  },
  {
    question: "你更希望关系里的主动权是什么状态？",
    options: [
      "互相主动，节奏清楚。",
      "TA多给一点确定性，我才放心。",
      "不用谈主动权，舒服就继续。",
      "我会主动，但希望看起来不太主动。",
    ],
  },
  {
    question: "发生误会时，你最自然的处理方式是？",
    options: [
      "直接说清楚，避免越想越乱。",
      "先看对方有没有解释意愿。",
      "冷静一会儿，等情绪降下来再谈。",
      "写很多话，但真正发出去会删掉一半。",
    ],
  },
  {
    question: "如果TA突然变得很热情，你会怎么感受？",
    options: [
      "开心，也会顺着回应。",
      "警觉。是不是有什么原因？",
      "看整体，不被一两天带着走。",
      "兴奋，但又怕自己表现得太明显。",
    ],
  },
  {
    question: "你最想从这段关系里确认什么？",
    options: [
      "我们是不是在认真靠近彼此。",
      "TA到底有没有把我放在重要位置。",
      "这段相处是否让我更自在。",
      "我该怎么回复，才不会失去优势。",
    ],
  },
];
const QUIZ_TYPES = [
  { name: "稳定靠近型", text: "你更看重持续投入和清楚表达，适合用稳定节奏推进关系。" },
  { name: "高敏侦测型", text: "你会快速捕捉温度变化，优势是敏锐，风险是过度解读。" },
  { name: "低卷观察型", text: "你更重视自洽和边界，不轻易被单次互动牵着走。" },
  { name: "预演回复型", text: "你擅长斟酌表达，但也容易在发送前消耗太多情绪。" },
];

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function clampInt(value, fallback, min, max) {
  const n = Number.parseInt(String(value ?? ""), 10);
  if (Number.isNaN(n)) return fallback;
  return Math.max(min, Math.min(max, n));
}

function refreshLogView() {
  const discover =
    state.discoverProgressLines?.length > 0
      ? `—— 读取联系人 · 实时进度 ——\n${state.discoverProgressLines.join("\n")}\n——\n\n`
      : "";
  if ($("log")) $("log").textContent = discover + state.logs.join("\n\n");
}

/** @param {{ running?: boolean, contact_current?: number|null, contact_total?: number|null }} payload */
function updateReadContactProgress(payload) {
  const el = $("readContactProgress");
  if (!el) return;
  if (!payload || payload.running === false) {
    el.hidden = true;
    el.textContent = "";
    return;
  }
  el.hidden = false;
  const ct = payload.contact_total != null ? Number(payload.contact_total) : null;
  const cu = payload.contact_current != null ? Number(payload.contact_current) : null;
  if (ct != null && ct > 0 && cu != null && !Number.isNaN(cu) && !Number.isNaN(ct)) {
    el.textContent = `进度：联系人 ${cu}/${ct}`;
    return;
  }
  if (ct != null && ct > 0) {
    el.textContent = `进度：联系人 0/${ct}`;
    return;
  }
  el.textContent = "进度：解密与准备中…";
}

function log(message, data) {
  const line = `[${new Date().toLocaleTimeString()}] ${message}`;
  const extra = data ? `\n${typeof data === "string" ? data : JSON.stringify(data, null, 2)}` : "";
  state.logs.unshift(`${line}${extra}`);
  state.logs = state.logs.slice(0, 80);
  if ($("logLatest")) $("logLatest").textContent = message;
  refreshLogView();
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
  document.body.classList.remove("pane-changing");
  void document.body.offsetWidth;
  document.body.classList.add("pane-changing");
  document.querySelectorAll(".nav-item").forEach((el) => el.classList.toggle("active", el.dataset.step === name));
  document.querySelectorAll(".pane").forEach((el) => el.classList.toggle("visible", el.id === `pane-${name}`));
  $("panelTitle").textContent = PANE_META[name] || PANE_META.main;
}

function scrollToPane(id) {
  requestAnimationFrame(() => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
}

function scrollToElementCenter(element) {
  if (!element) return;
  const rect = element.getBoundingClientRect();
  const target = window.scrollY + rect.top - Math.max(24, (window.innerHeight - rect.height) / 2);
  window.scrollTo({ top: Math.max(0, target), behavior: "smooth" });
}

function scrollToWorkflow() {
  scrollToElementCenter(document.querySelector(".workflow-board"));
}

function scrollToReportPanel() {
  const panel = document.querySelector(".report-panel");
  if (!panel) return;
  window.scrollTo({ top: Math.max(0, window.scrollY + panel.getBoundingClientRect().top - 88), behavior: "smooth" });
}

function jumpFromHero() {
  if (document.body.dataset.pane !== "main") return;
  if (state.heroScrollLocked) return;
  if (window.scrollY > 90) return;
  state.heroScrollLocked = true;
  document.body.classList.add("hero-leaving");
  document.body.classList.add("nav-hidden");
  scrollToWorkflow();
  window.setTimeout(() => {
    state.heroScrollLocked = false;
    document.body.classList.remove("hero-leaving");
  }, 900);
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
  document.body.classList.toggle("environment-ready", Boolean(status.environment_ready));
  if ($("heroStatusText")) {
    $("heroStatusText").textContent = status.environment_ready ? "" : "环境异常";
  }
  if ($("heroStatusBar")) {
    $("heroStatusBar").style.width = status.environment_ready ? "100%" : "42%";
  }

  if ($("llmProvider")) $("llmProvider").value = status.llm_provider || "openai";
  if ($("llmBaseUrl")) $("llmBaseUrl").value = status.llm_base_url || "";
  if ($("llmModel")) $("llmModel").value = status.llm_model || "";
  const limits = status.analysis_limits || {};
  if ($("maxChatChars")) $("maxChatChars").value = String(limits.max_chat_chars || 60000);
  if ($("retryChatChars")) $("retryChatChars").value = String(limits.retry_chat_chars || 24000);
  if ($("maxOutputTokens")) $("maxOutputTokens").value = String(limits.max_output_tokens || 12288);
  if ($("configHint")) {
    $("configHint").textContent = `当前：${status.llm_provider || "openai"} · ${status.llm_base_url || "未设置 BaseURL"} · ${status.llm_model || "未设置模型"} · ${status.llm_key_hint || "未设置"} · 聊天${limits.max_chat_chars || 60000}字 · 输出${limits.max_output_tokens || 12288}token`;
  }
  updateEndpointPreview();

  const strip = $("runtimeStatus");
  strip.querySelector("i").className = status.environment_ready ? "ok" : "bad";
  strip.querySelector("span").textContent = status.environment_label || (status.environment_ready ? "环境就绪" : "环境异常");
  renderArchives(status.archives || []);
  if (loadLatestReport && status.latest_report) setReport(status.latest_report, { silent: true });
}

function clearMainAnalysis() {
  state.latestReportUrl = "";
  document.body.classList.remove("report-ready", "analysis-running");
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
  if ($("selectedHint")) $("selectedHint").textContent = "先选择一个联系人。";
  resetRangeState();
  setAnalysisProgress(0, "", { hidden: true });
  if ($("scrollReportCue")) $("scrollReportCue").hidden = true;
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
  if (!options.silent) {
    document.body.classList.add("report-ready");
    document.body.classList.remove("analysis-running", "nav-hidden");
  }
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
  if (!options.silent) {
    setAnalysisProgress(100, "分析完成", { done: true });
    if ($("scrollReportCue")) $("scrollReportCue").hidden = false;
  }
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

function reportEnhancementCss() {
  return `
    .glass-title {
      position: relative;
      display: inline-block;
      isolation: isolate;
    }
    .glass-title::after {
      content: "";
      position: absolute;
      inset: -10% -4%;
      border-radius: 18px;
      background:
        radial-gradient(circle at var(--glass-x, 50%) var(--glass-y, 50%), rgba(255,255,255,.34), rgba(255,255,255,.1) 16%, transparent 34%),
        linear-gradient(110deg, transparent 0 38%, rgba(255,255,255,.26) 45%, transparent 54% 100%);
      mix-blend-mode: screen;
      opacity: .66;
      filter: blur(.2px);
      transform: translate3d(0, 0, 0);
      pointer-events: none;
      z-index: -1;
    }
    .glass-title::before {
      content: "";
      position: absolute;
      inset: -18% -8%;
      border-radius: 22px;
      border: 1px solid rgba(255,255,255,.14);
      backdrop-filter: blur(7px) saturate(1.35);
      -webkit-backdrop-filter: blur(7px) saturate(1.35);
      opacity: .38;
      pointer-events: none;
      z-index: -2;
    }
  `;
}

function applyGlassTitle(root) {
  const candidates = [
    ".result-hero h1",
    ".report-document h1",
    ".report-document h2",
    ".report-document .main-result",
  ];
  const title = candidates.map((selector) => root.querySelector(selector)).find(Boolean);
  if (!title) return;
  title.classList.add("glass-title");
  title.addEventListener("pointermove", (event) => {
    const rect = title.getBoundingClientRect();
    title.style.setProperty("--glass-x", `${((event.clientX - rect.left) / rect.width) * 100}%`);
    title.style.setProperty("--glass-y", `${((event.clientY - rect.top) / rect.height) * 100}%`);
  });
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
    <style>${adaptReportCss(styles, bodyClass)}${reportEnhancementCss()}</style>
    <div class="report-document ${esc(bodyClass)}">${doc.body.innerHTML}</div>
  `;
  applyGlassTitle(root);
  for (const src of externalScripts) await loadScriptOnce(src);
  for (const code of inlineScripts) {
    new Function("document", "window", "Chart", code)(root, window, window.Chart);
  }
}

function renderContacts() {
  const search = $("contactSearch");
  const list = $("contactList");
  if (!search || !list) return;
  const q = search.value.trim().toLowerCase();
  state.filtered = state.contacts.filter((item) => {
    const text = `${item.display_name || ""} ${item.nick_name || ""} ${item.remark || ""} ${item.username || ""}`.toLowerCase();
    return !q || text.includes(q);
  }).slice(0, 120);

  if (!state.filtered.length) {
    list.innerHTML = `<div class="contact-empty">没有联系人。点击“开始读取联系人”，或换个关键词。</div>`;
    return;
  }

  list.innerHTML = state.filtered.map((item, index) => {
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

function resetRangeState() {
  state.dateFrom = "";
  state.dateTo = "";
  state.dailySeries = [];
  state.dailyTotal = 0;
  state.messagesReadyContact = "";
  if ($("rangeStart")) {
    $("rangeStart").value = "";
    $("rangeStart").disabled = true;
  }
  if ($("rangeEnd")) {
    $("rangeEnd").value = "";
    $("rangeEnd").disabled = true;
  }
  if ($("rangeTotal")) $("rangeTotal").textContent = "所选范围消息总数：-";
  if ($("dailyList")) $("dailyList").innerHTML = `<div class="contact-empty">选择联系人后显示每日聊天条数。</div>`;
  if ($("rangeHint")) $("rangeHint").textContent = "选择联系人后可按日期筛选，并查看每天聊天条数。";
}

function renderDailyList() {
  const list = $("dailyList");
  if (!list) return;
  if (!state.dailySeries.length) {
    list.innerHTML = `<div class="contact-empty">当前联系人没有可用消息。</div>`;
    return;
  }
  list.innerHTML = state.dailySeries
    .map((d) => `<div class="daily-row"><span>${esc(d.date)}</span><strong>${Number(d.count || 0).toLocaleString()} 条</strong></div>`)
    .join("");
}

function updateRangeSummary() {
  const totalEl = $("rangeTotal");
  if (!totalEl || !state.dailySeries.length) {
    if (totalEl) totalEl.textContent = "所选范围消息总数：-";
    return;
  }
  const from = state.dateFrom || state.dailySeries[0].date;
  const to = state.dateTo || state.dailySeries[state.dailySeries.length - 1].date;
  let total = 0;
  for (const d of state.dailySeries) {
    if (d.date >= from && d.date <= to) total += Number(d.count || 0);
  }
  totalEl.textContent = `所选范围消息总数：${total.toLocaleString()} 条（${from} 至 ${to}）`;
}

function applyDailyData(data) {
  state.dailySeries = Array.isArray(data.daily) ? data.daily : [];
  state.dailyTotal = Number(data.total || 0);
  const minDate = data.min_date || (state.dailySeries[0] && state.dailySeries[0].date) || "";
  const maxDate = data.max_date || (state.dailySeries[state.dailySeries.length - 1] && state.dailySeries[state.dailySeries.length - 1].date) || "";
  state.dateFrom = minDate;
  state.dateTo = maxDate;
  if ($("rangeStart")) {
    $("rangeStart").value = minDate;
    $("rangeStart").min = minDate;
    $("rangeStart").max = maxDate;
    $("rangeStart").disabled = !minDate;
  }
  if ($("rangeEnd")) {
    $("rangeEnd").value = maxDate;
    $("rangeEnd").min = minDate;
    $("rangeEnd").max = maxDate;
    $("rangeEnd").disabled = !maxDate;
  }
  if ($("rangeHint")) $("rangeHint").textContent = `已加载 ${state.dailySeries.length} 天聊天分布。`;
  renderDailyList();
  updateRangeSummary();
}

async function ensureSelectedMessagesAndDaily(forceExtract = false) {
  if (!state.selected) return;
  const username = state.selected.username || "";
  const contact = state.selected.display_name || username;
  if (!username) return;
  if (forceExtract || state.messagesReadyContact !== username) {
    if ($("rangeHint")) $("rangeHint").textContent = "正在读取该联系人聊天记录…";
    const extracted = await api("/api/extract", { method: "POST", body: { contact } });
    log("消息提取完成", extracted.result.json || extracted.result.stderr);
    state.messagesReadyContact = username;
  }
  const daily = await api("/api/messages/daily");
  if ((daily.contact_username || "") && daily.contact_username !== username) {
    throw new Error("读取到的聊天记录与当前联系人不一致，请重试。");
  }
  applyDailyData(daily);
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
  const body = readConfigForm();
  log("保存模型接口配置");
  const data = await api("/api/config", { method: "POST", body });
  renderStatus(data.status);
  state.pendingApiKey = "";
  $("llmApiKey").value = "";
  log("模型配置已保存", data.config);
}

function buildEndpoint(provider, baseUrl, model) {
  const base = (baseUrl || PROVIDER_DEFAULTS[provider]?.baseUrl || PROVIDER_DEFAULTS.openai.baseUrl).trim().replace(/\/+$/, "");
  const selectedModel = (model || PROVIDER_DEFAULTS[provider]?.model || PROVIDER_DEFAULTS.openai.model).trim();
  if (provider === "anthropic") return `${base}/messages`;
  if (provider === "gemini") return `${base}/models/${encodeURIComponent(selectedModel)}:generateContent?key=***`;
  return `${base}/chat/completions`;
}

function readConfigForm() {
  const inputValue = $("llmApiKey")?.value.trim() || "";
  return {
    provider: $("llmProvider")?.value || "openai",
    base_url: $("llmBaseUrl")?.value.trim() || "",
    model: $("llmModel")?.value.trim() || "",
    api_key: state.pendingApiKey || (inputValue === MASKED_KEY ? "" : inputValue),
    max_chat_chars: clampInt($("maxChatChars")?.value, 60000, 4000, 200000),
    retry_chat_chars: clampInt($("retryChatChars")?.value, 24000, 2000, 120000),
    max_output_tokens: clampInt($("maxOutputTokens")?.value, 12288, 256, 32768),
  };
}

function updateEndpointPreview() {
  const body = readConfigForm();
  const provider = body.provider || "openai";
  const endpoint = buildEndpoint(provider, body.base_url, body.model);
  if ($("llmEndpoint")) $("llmEndpoint").textContent = endpoint;
}

async function testConfig() {
  const body = readConfigForm();
  updateEndpointPreview();
  if ($("configTestResult")) {
    $("configTestResult").className = "config-test";
    $("configTestResult").textContent = "正在测试连通性...";
  }
  log("测试模型接口连通性");
  const data = await api("/api/config/test", { method: "POST", body });
  const result = data.result;
  if ($("configTestResult")) {
    $("configTestResult").className = "config-test ok";
    $("configTestResult").textContent = `连通成功 · HTTP ${result.status} · ${result.latency_ms}ms`;
  }
  log("模型接口连通成功", { endpoint: result.endpoint, latency_ms: result.latency_ms });
}

function applyProviderDefaults(provider) {
  const defaults = PROVIDER_DEFAULTS[provider] || PROVIDER_DEFAULTS.openai;
  $("llmBaseUrl").value = defaults.baseUrl;
  $("llmModel").value = defaults.model;
  updateEndpointPreview();
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
  updateEndpointPreview();
  log("API Key 已粘贴并隐藏。");
}

async function loadContacts() {
  log("开始读取联系人：检查环境、解密并扫描微信");
  state.discoverProgressLines = [];
  refreshLogView();
  updateReadContactProgress({ running: true, step: 0, step_total: 3 });
  const wrap = $("consoleWrap");
  if (wrap) wrap.classList.add("expanded");
  if ($("contactSummary")) $("contactSummary").textContent = "正在读取联系人（下方显示步骤进度）…";
  const poll = window.setInterval(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/discover/progress`);
      if (!res.ok) return;
      const j = await res.json();
      state.discoverProgressLines = j.lines || [];
      refreshLogView();
      updateReadContactProgress(j);
      if ($("logLatest") && (j.phase || j.running)) {
        $("logLatest").textContent = j.phase || "进行中…";
      }
    } catch (_) {}
  }, 350);
  try {
    const data = await api("/api/discover", { method: "POST" });
    renderStatus(data.status);
    state.contacts = data.contacts || [];
    state.selected = null;
    resetRangeState();
    if ($("reportBtn")) $("reportBtn").disabled = true;
    renderContacts();
    switchPane("main");
    if ($("contactSummary")) $("contactSummary").textContent = `已读取 ${state.contacts.length} 个联系人。`;
    log(`读取到 ${state.contacts.length} 个联系人`);
  } finally {
    window.clearInterval(poll);
    updateReadContactProgress({ running: false });
    try {
      const res = await fetch(`${API_BASE}/api/discover/progress`);
      if (res.ok) {
        const j = await res.json();
        state.discoverProgressLines = j.lines || [];
        refreshLogView();
      }
    } catch (_) {}
  }
}

async function discoverWechat() {
  log("开始识别微信：检查环境、解密数据库、扫描联系人");
  state.discoverProgressLines = [];
  refreshLogView();
  updateReadContactProgress({ running: true, step: 0, step_total: 3 });
  const poll = window.setInterval(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/discover/progress`);
      if (!res.ok) return;
      const j = await res.json();
      state.discoverProgressLines = j.lines || [];
      refreshLogView();
      updateReadContactProgress(j);
      if ($("logLatest") && (j.phase || j.running)) $("logLatest").textContent = j.phase || "进行中…";
    } catch (_) {}
  }, 350);
  try {
    const data = await api("/api/discover", { method: "POST" });
    renderStatus(data.status);
    state.contacts = data.contacts || [];
    state.selected = null;
    resetRangeState();
    if ($("reportBtn")) $("reportBtn").disabled = true;
    renderContacts();
    switchPane("main");
    log(`微信识别完成，读取到 ${state.contacts.length} 个联系人`);
  } finally {
    window.clearInterval(poll);
    updateReadContactProgress({ running: false });
    try {
      const res = await fetch(`${API_BASE}/api/discover/progress`);
      if (res.ok) {
        const j = await res.json();
        state.discoverProgressLines = j.lines || [];
        refreshLogView();
      }
    } catch (_) {}
  }
}

async function extractAndStats(onProgress) {
  if (!state.selected) return;
  const username = state.selected.username || "";
  const contact = state.selected.display_name || username;
  if (!username) return;
  if (state.messagesReadyContact !== username) {
    log(`提取联系人：${contact}`);
    onProgress?.(18, "正在提取聊天记录");
    const extracted = await api("/api/extract", { method: "POST", body: { contact } });
    log("消息提取完成", extracted.result.json || extracted.result.stderr);
    state.messagesReadyContact = username;
    const daily = await api("/api/messages/daily");
    applyDailyData(daily);
  } else {
    log("复用已提取聊天记录");
    onProgress?.(22, "复用已提取聊天记录");
  }
  onProgress?.(38, "正在计算互动统计");
  const statsBody = {};
  if (state.dateFrom) statsBody.date_from = state.dateFrom;
  if (state.dateTo) statsBody.date_to = state.dateTo;
  const stats = await api("/api/stats", { method: "POST", body: statsBody });
  onProgress?.(52, "互动统计完成");
  log("统计完成", stats.stats.scores || stats.result.stdout);
}

async function runSubtextScan() {
  log("调用模型生成潜台词扫描");
  const data = await api("/api/analyze", { method: "POST", body: { use_llm: true } });
  renderStatus(data.status);
  log("analysis.json 已生成", { mode: data.analysis._analysis_mode });
  return data;
}

async function analyze() {
  await runSubtextScan();
}

function setAnalysisProgress(percent, text, options = {}) {
  const box = $("analysisProgress");
  const bar = $("analysisProgressBar");
  const label = $("analysisProgressText");
  if (!box || !bar || !label) return;
  const value = Math.max(0, Math.min(100, Number(percent) || 0));
  box.hidden = Boolean(options.hidden);
  box.classList.toggle("done", Boolean(options.done));
  bar.style.width = `${value}%`;
  label.textContent = text || "";
}

async function report() {
  if (!state.selected) return;
  log("提取聊天并生成报告");
  document.body.classList.add("analysis-running");
  document.body.classList.remove("report-ready");
  setAnalysisProgress(8, "准备读取聊天记录");
  if ($("scrollReportCue")) $("scrollReportCue").hidden = true;
  scrollToWorkflow();
  await extractAndStats(setAnalysisProgress);
  setAnalysisProgress(64, "正在生成潜台词扫描");
  await runSubtextScan();
  setAnalysisProgress(78, "潜台词扫描完成");
  const data = await api("/api/report", { method: "POST" });
  setAnalysisProgress(92, "正在渲染结果分析报告");
  renderStatus(data.status);
  setReport(data.report);
  scrollToWorkflow();
  log("报告已生成", data.report);
}

function renderQuiz() {
  const step = $("quizStep");
  const count = $("quizCount");
  const bar = $("quizBar");
  const question = $("quizQuestion");
  const options = $("quizOptions");
  const prev = $("quizPrevBtn");
  const next = $("quizNextBtn");
  if (!step || !count || !bar || !question || !options || !prev || !next) return;

  if (state.quizDone) {
    const scores = [0, 0, 0, 0];
    state.quizAnswers.forEach((answer) => {
      if (Number.isInteger(answer)) scores[answer] += 1;
    });
    const top = scores.reduce((best, value, index) => (value > scores[best] ? index : best), 0);
    const profile = QUIZ_TYPES[top];
    step.textContent = "完成";
    count.textContent = `${QUIZ_QUESTIONS.length} / ${QUIZ_QUESTIONS.length}`;
    bar.style.width = "100%";
    question.textContent = profile.name;
    question.classList.add("glass-title");
    options.classList.add("result-mode");
    options.innerHTML = `
      <article class="quiz-result">
        <p>${esc(profile.text)}</p>
        <dl>
          ${QUIZ_TYPES.map((type, index) => `
            <div>
              <dt>${esc(type.name)}</dt>
              <dd>${scores[index]} 题</dd>
            </div>
          `).join("")}
        </dl>
      </article>
    `;
    prev.hidden = true;
    next.disabled = false;
    next.textContent = "重新测试";
    return;
  }

  const item = QUIZ_QUESTIONS[state.quizIndex];
  const selected = state.quizAnswers[state.quizIndex];
  question.classList.remove("glass-title");
  step.textContent = `第 ${ROMAN[state.quizIndex].replace(".", "")} 题`;
  count.textContent = `${state.quizIndex + 1} / ${QUIZ_QUESTIONS.length}`;
  bar.style.width = `${((state.quizIndex + 1) / QUIZ_QUESTIONS.length) * 100}%`;
  question.textContent = item.question;
  options.classList.remove("result-mode");
  options.innerHTML = item.options.map((option, index) => `
    <button class="secondary quiz-option ${selected === index ? "selected" : ""}" data-index="${index}" type="button">
      <span>${ROMAN[index]}</span>
      ${esc(option)}
    </button>
  `).join("");
  prev.hidden = false;
  prev.disabled = state.quizIndex === 0;
  prev.textContent = "上一题";
  next.disabled = selected === undefined;
  next.textContent = state.quizIndex === QUIZ_QUESTIONS.length - 1 ? "查看结果" : "下一题";
}

function selectQuizOption(index) {
  state.quizAnswers[state.quizIndex] = index;
  renderQuiz();
}

function nextQuiz() {
  if (state.quizDone) {
    state.quizIndex = 0;
    state.quizAnswers = [];
    state.quizDone = false;
    renderQuiz();
    return;
  }
  if (state.quizAnswers[state.quizIndex] === undefined) return;
  if (state.quizIndex >= QUIZ_QUESTIONS.length - 1) {
    state.quizDone = true;
  } else {
    state.quizIndex += 1;
  }
  renderQuiz();
}

function prevQuiz() {
  if (state.quizIndex <= 0) return;
  state.quizIndex -= 1;
  renderQuiz();
}

function initReveals() {
  const nodes = document.querySelectorAll(".workflow-card, .report-panel, .archive-card, .archive-empty, .personality-panel, .config-panel, .theme-panel, .console-wrap");
  if (!("IntersectionObserver" in window)) {
    nodes.forEach((node) => node.classList.add("is-visible"));
    return;
  }
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add("is-visible");
      observer.unobserve(entry.target);
    });
  }, { rootMargin: "0px 0px -8% 0px", threshold: 0.12 });
  nodes.forEach((node) => {
    node.classList.add("reveal-item");
    observer.observe(node);
  });
}

function initHeroSlides() {
  const slides = [...document.querySelectorAll(".hero-slide")];
  if (slides.length < 2) return;
  window.setInterval(() => {
    if (document.body.dataset.pane !== "main") return;
    state.heroSlideIndex = (state.heroSlideIndex + 1) % slides.length;
    slides.forEach((slide, index) => slide.classList.toggle("active", index === state.heroSlideIndex));
  }, 5200);
}

function initCursorParticles() {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  if (window.matchMedia("(pointer: coarse)").matches) return;
  const canvas = document.createElement("canvas");
  canvas.className = "cursor-particles";
  canvas.setAttribute("aria-hidden", "true");
  document.body.appendChild(canvas);
  const context = canvas.getContext("2d");
  if (!context) return;
  const particles = [];
  const ribbons = [];
  const pointer = { x: 0, y: 0, mx: 0, my: 0 };
  const palette = [
    { hue: 43, sat: 96, light: 66 },
    { hue: 35, sat: 88, light: 58 },
    { hue: 282, sat: 72, light: 58 },
    { hue: 199, sat: 86, light: 58 },
  ];
  let frame = 0;

  function resize() {
    const ratio = window.devicePixelRatio || 1;
    canvas.width = window.innerWidth * ratio;
    canvas.height = window.innerHeight * ratio;
    canvas.style.width = `${window.innerWidth}px`;
    canvas.style.height = `${window.innerHeight}px`;
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
  }

  function addParticles(event, count, burst = 1) {
    pointer.x = event.clientX;
    pointer.y = event.clientY;
    pointer.mx = event.movementX || 0;
    pointer.my = event.movementY || 0;
    const velocity = Math.max(1, Math.hypot(pointer.mx, pointer.my));
    ribbons.push({
      x: pointer.x,
      y: pointer.y,
      width: 7 + Math.min(velocity * .18, 9) * burst,
      alpha: .42,
    });
    if (ribbons.length > 28) ribbons.shift();
    for (let index = 0; index < count; index += 1) {
      const angle = Math.random() * Math.PI * 2;
      const speed = (0.62 + Math.random() * 2.6) * burst + Math.min(velocity * .018, 1.45);
      const color = palette[index % (burst > 1.2 ? palette.length : 2)];
      particles.push({
        x: pointer.x - pointer.mx * .7,
        y: pointer.y - pointer.my * .7,
        vx: Math.cos(angle) * speed - pointer.mx * .022,
        vy: Math.sin(angle) * speed - pointer.my * .022,
        size: .95 + Math.random() * 2.3 * burst,
        decay: .032 + Math.random() * .024,
        hue: color.hue + (Math.random() - .5) * 10,
        sat: color.sat,
        light: color.light,
        alpha: .22 + Math.random() * .2,
      });
    }
    if (particles.length > 300) particles.splice(0, particles.length - 300);
  }

  function draw() {
    frame = window.requestAnimationFrame(draw);
    context.clearRect(0, 0, window.innerWidth, window.innerHeight);
    context.globalCompositeOperation = "lighter";
    if (ribbons.length > 1) {
      for (let index = 1; index < ribbons.length; index += 1) {
        const prev = ribbons[index - 1];
        const point = ribbons[index];
        const alpha = Math.min(prev.alpha, point.alpha);
        const gradient = context.createLinearGradient(prev.x, prev.y, point.x, point.y);
        gradient.addColorStop(0, `rgba(95, 62, 17, ${alpha * .22})`);
        gradient.addColorStop(.45, `rgba(247, 194, 94, ${alpha * .42})`);
        gradient.addColorStop(1, `rgba(255, 237, 175, ${alpha * .16})`);
        context.strokeStyle = gradient;
        context.lineWidth = Math.max(1, point.width * alpha);
        context.lineCap = "round";
        context.beginPath();
        context.moveTo(prev.x, prev.y);
        context.quadraticCurveTo((prev.x + point.x) / 2, (prev.y + point.y) / 2, point.x, point.y);
        context.stroke();
      }
      for (let index = ribbons.length - 1; index >= 0; index -= 1) {
        ribbons[index].alpha *= .9;
        ribbons[index].width *= .965;
        if (ribbons[index].alpha <= .025) ribbons.splice(index, 1);
      }
    }
    for (let index = particles.length - 1; index >= 0; index -= 1) {
      const particle = particles[index];
      const radius = particle.size * 2.7;
      const gradient = context.createRadialGradient(particle.x, particle.y, 0, particle.x, particle.y, radius);
      gradient.addColorStop(0, `hsla(${particle.hue}, ${particle.sat}%, 88%, ${particle.alpha})`);
      gradient.addColorStop(.45, `hsla(${particle.hue}, ${particle.sat}%, ${particle.light}%, ${particle.alpha * .56})`);
      gradient.addColorStop(1, "rgba(0,0,0,0)");
      context.fillStyle = gradient;
      context.beginPath();
      context.arc(particle.x, particle.y, radius, 0, Math.PI * 2);
      context.fill();
      particle.x += particle.vx;
      particle.y += particle.vy;
      particle.vx *= .955;
      particle.vy *= .955;
      particle.size -= particle.decay;
      particle.alpha *= .968;
      if (particle.size <= .18 || particle.alpha <= .02) particles.splice(index, 1);
    }
  }

  resize();
  window.addEventListener("resize", resize);
  window.addEventListener("pointermove", (event) => addParticles(event, 4), { passive: true });
  window.addEventListener("click", (event) => addParticles(event, 42, 1.55), { passive: true });
  frame = window.requestAnimationFrame(draw);
}

function initHeroScrollTrigger() {
  function handleDownScroll(event) {
    if (document.body.dataset.pane !== "main") return false;
    if (state.heroScrollLocked) return true;
    const workflow = document.querySelector(".workflow-board");
    const reportPanel = document.querySelector(".report-panel");
    const workflowRect = workflow?.getBoundingClientRect();
    const reportRect = reportPanel?.getBoundingClientRect();
    if (window.scrollY <= 90) {
      event.preventDefault();
      jumpFromHero();
      return true;
    }
    if (workflowRect && reportRect && workflowRect.top < window.innerHeight * .58 && reportRect.top > window.innerHeight * .78) {
      event.preventDefault();
      state.heroScrollLocked = true;
      document.body.classList.add("nav-hidden");
      scrollToReportPanel();
      window.setTimeout(() => { state.heroScrollLocked = false; }, 820);
      return true;
    }
    return false;
  }

  window.addEventListener("wheel", (event) => {
    if (event.deltaY > 8) handleDownScroll(event);
    if (event.deltaY < -8) document.body.classList.remove("nav-hidden");
  }, { passive: false });

  window.addEventListener("touchstart", (event) => {
    state.touchStartY = event.touches[0]?.clientY || 0;
  }, { passive: true });

  window.addEventListener("touchmove", (event) => {
    const currentY = event.touches[0]?.clientY || 0;
    if (state.touchStartY - currentY > 14) handleDownScroll(event);
    if (currentY - state.touchStartY > 14) document.body.classList.remove("nav-hidden");
  }, { passive: false });

  window.addEventListener("scroll", () => {
    const current = window.scrollY;
    if (document.body.classList.contains("report-ready")) {
      document.body.classList.remove("nav-hidden");
      state.lastScrollY = current;
      return;
    }
    if (current > state.lastScrollY + 8 && current > 88) document.body.classList.add("nav-hidden");
    if (current < state.lastScrollY - 8) document.body.classList.remove("nav-hidden");
    state.lastScrollY = current;
  }, { passive: true });
}

function bind() {
  const on = (id, event, handler) => {
    const el = $(id);
    if (el) el.addEventListener(event, handler);
  };

  document.querySelectorAll(".nav-item").forEach((button) => {
    button.addEventListener("click", () => switchPane(button.dataset.step));
  });
  on("heroScrollCue", "click", jumpFromHero);
  on("scrollReportCue", "click", scrollToReportPanel);
  on("saveConfigBtn", "click", () => saveConfig().catch(handleError));
  on("testConfigBtn", "click", () => testConfig().catch(handleError));
  on("llmProvider", "change", (event) => applyProviderDefaults(event.target.value));
  on("llmBaseUrl", "input", updateEndpointPreview);
  on("llmModel", "input", updateEndpointPreview);
  on("maxChatChars", "input", updateEndpointPreview);
  on("retryChatChars", "input", updateEndpointPreview);
  on("maxOutputTokens", "input", updateEndpointPreview);
  on("llmApiKey", "paste", maskApiKeyFromPaste);
  on("llmApiKey", "input", () => {
    if ($("llmApiKey")?.value !== MASKED_KEY) state.pendingApiKey = "";
  });
  on("setupBtn", "click", () => runSetup().catch(handleError));
  on("loadContactsBtn", "click", () => loadContacts().catch(handleError));
  on("reportBtn", "click", () => report().catch(handleError));
  on("quizOptions", "click", (event) => {
    const button = event.target.closest(".quiz-option");
    if (!button) return;
    selectQuizOption(Number(button.dataset.index));
  });
  on("quizPrevBtn", "click", prevQuiz);
  on("quizNextBtn", "click", nextQuiz);
  on("consoleHead", "click", (event) => {
    if (event.target.closest("#clearLog")) return;
    $("consoleWrap").classList.toggle("expanded");
  });
  on("clearLog", "click", () => {
    state.logs = [];
    state.discoverProgressLines = [];
    $("log").textContent = "";
    $("logLatest").textContent = "日志已清空。";
  });
  on("contactSearch", "input", renderContacts);
  on("rangeStart", "change", () => {
    const start = $("rangeStart")?.value || "";
    const end = $("rangeEnd")?.value || "";
    state.dateFrom = start;
    if (start && end && start > end) {
      state.dateTo = start;
      if ($("rangeEnd")) $("rangeEnd").value = start;
    }
    updateRangeSummary();
  });
  on("rangeEnd", "change", () => {
    const start = $("rangeStart")?.value || "";
    const end = $("rangeEnd")?.value || "";
    state.dateTo = end;
    if (start && end && start > end) {
      state.dateFrom = end;
      if ($("rangeStart")) $("rangeStart").value = end;
    }
    updateRangeSummary();
  });
  on("contactList", "click", async (event) => {
    const button = event.target.closest(".contact");
    if (!button) return;
    state.selected = state.filtered[Number(button.dataset.index)];
    state.messagesReadyContact = "";
    if ($("reportBtn")) $("reportBtn").disabled = false;
    if ($("selectedHint")) {
      const label = state.selected.display_name || state.selected.username;
      $("selectedHint").textContent = `将分析：${label}`;
    }
    renderContacts();
    try {
      await ensureSelectedMessagesAndDaily(true);
      updateRangeSummary();
    } catch (error) {
      handleError(error);
    }
  });
  document.querySelectorAll(".theme-choice").forEach((button) => {
    button.addEventListener("click", () => applyUiTheme(button.dataset.theme));
  });
  renderQuiz();
  resetRangeState();
  initReveals();
  initHeroSlides();
  initCursorParticles();
  initHeroScrollTrigger();
}

function handleError(error) {
  const detail = error.data?.details || error.message;
  document.body.classList.remove("analysis-running");
  setAnalysisProgress(0, "分析失败，请查看后台记录");
  if ($("configTestResult") && String(error.message || "").includes("连通性测试失败")) {
    const endpoint = error.data?.details?.endpoint;
    $("configTestResult").className = "config-test bad";
    $("configTestResult").textContent = endpoint ? `${error.message} · ${endpoint}` : error.message;
  }
  log(`失败：${error.message}`, detail);
}

const themeVersion = "neon-stage-v5";
const savedTheme = localStorage.getItem("ta-ui-theme-version") === themeVersion ? localStorage.getItem("ta-ui-theme") : "";
const initialTheme = normalizeUiTheme(savedTheme || "neon");
localStorage.setItem("ta-ui-theme-version", themeVersion);
applyUiTheme(initialTheme);
bind();
switchPane("main");
refreshStatus().catch(handleError);
